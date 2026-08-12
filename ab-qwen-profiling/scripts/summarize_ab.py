#!/usr/bin/env python3
"""Median-based summary of an ab-run.sh evidence directory.

    summarize_ab.py /tmp/my-ab [baseline_label]

Prints every run, then median per variant, and the percent change against the
baseline (the first variant alphabetically unless one is named). Also prints the
real ms/token that `rocm-kernel-trace`'s compare_traces.py wants as its scale
reference, and rejects runs whose token counts do not match the others.
"""
import json, statistics as st, sys
from collections import defaultdict
from pathlib import Path

root = Path(sys.argv[1])
want_base = sys.argv[2] if len(sys.argv) > 2 else None

runs = defaultdict(list)
for f in sorted(root.glob('*.json')):
    try:
        d = json.loads(f.read_text())
    except Exception:
        continue
    if 'server_decode_tps' not in d:
        continue
    runs[d['label'].rsplit('-', 1)[0]].append(d)

if not runs:
    raise SystemExit(f'no benchmark json found in {root}')

# validation: identical prompt and completion token counts across every run
ptoks = {r['prompt_tokens'] for v in runs.values() for r in v}
ctoks = {r['completion_tokens'] for v in runs.values() for r in v}
if len(ptoks) > 1 or len(ctoks) > 1:
    print(f'!! REJECT: token counts differ across runs — prompt={ptoks} completion={ctoks}')
    print('   Unequal work makes the TPS comparison meaningless. Rerun.')

base = want_base or next(iter(runs))
print(f"{'variant':10s} {'n':>2s} {'decode tps runs':>28s} {'median':>8s} {'ms/tok':>8s} "
      f"{'prefill':>9s} {'MTP%':>7s} {'vs ' + base:>10s}")
print('-' * 96)

med = {}
for k, v in runs.items():
    dec = [r['server_decode_tps'] for r in v]
    med[k] = st.median(dec)

for k, v in runs.items():
    dec = [r['server_decode_tps'] for r in v]
    pre = [r['server_prefill_tps'] for r in v]
    mtp = [r['mtp_acceptance'] for r in v if r.get('mtp_acceptance') is not None]
    rel = 100 * (med[k] / med[base] - 1) if base in med else float('nan')
    runs_s = ' '.join(f'{x:.2f}' for x in dec)
    print(f"{k:10s} {len(v):2d} {runs_s:>28s} {med[k]:8.2f} {1000/med[k]:8.3f} "
          f"{st.median(pre):9.1f} {100*st.mean(mtp) if mtp else 0:7.3f} {rel:+9.2f}%")

print('\nscale reference for rocm-kernel-trace/scripts/compare_traces.py:')
for k in runs:
    print(f'  --variant {k}=<trace_dir>:{1000/med[k]:.3f}')
