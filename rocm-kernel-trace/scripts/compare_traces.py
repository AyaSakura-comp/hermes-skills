#!/usr/bin/env python3
"""Per-category decode cost across trace variants, traced and scaled.

    compare_traces.py --variant f16=/tmp/t/f16:15.444 \
                      --variant q4tiled=/tmp/t/q4tiled:16.945 \
                      [--out compare.json]

Each --variant is  label=trace_dir:real_ms_per_token, where trace_dir holds the
decode-kernel-summary.json / decode-category-summary.json written by
analyze_trace_db.py and categorize_kernels.py. real_ms_per_token comes from an
UNPROFILED benchmark of the same request shape (1000 / decode_tps).

The first --variant is the baseline; deltas are computed against it.

Two tables are printed and they are not equally trustworthy:

  (a) TRACED  — all variants carried the same profiler overhead, so differences
      between them are measurements. Attribute regressions with this one.

  (b) SCALED  — multiplies each category by real/traced so the categories sum to
      the variant's true per-token budget. This assumes the profiler inflates
      every category by the same factor, which is false: rocprof mainly inflates
      launch overhead, so launch-heavy categories are over-credited. Presentation
      only. If a category that your change cannot touch moves here, that is the
      artifact, not a finding.
"""
import argparse, json
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument('--variant', action='append', required=True,
                help='label=trace_dir:real_ms_per_token (first one is the baseline)')
ap.add_argument('--out', default=None)
args = ap.parse_args()

variants = []
for spec in args.variant:
    label, rest = spec.split('=', 1)
    d, real = rest.rsplit(':', 1)
    variants.append((label, Path(d), float(real)))
base = variants[0][0]

data, scale, traced_tot = {}, {}, {}
print(f"{'variant':10s} {'traced':>8s} {'real':>8s} {'scale':>8s} {'launches/tok':>13s}")
for label, d, real in variants:
    cat = json.loads((d / 'decode-category-summary.json').read_text())
    meta = json.loads((d / 'decode-kernel-summary.json').read_text())
    data[label] = {c['category']: c['ms_per_token'] for c in cat['categories']}
    traced_tot[label] = cat['kernel_total_ms'] / cat['equivalent_output_tokens']
    scale[label] = real / traced_tot[label]
    print(f"{label:10s} {traced_tot[label]:8.3f} {real:8.3f} {scale[label]:8.4f} "
          f"{meta['dispatches_per_token_est']:13.0f}")

cats = sorted(set().union(*[set(v) for v in data.values()]),
              key=lambda c: -data[base].get(c, 0.0))
labels = [v[0] for v in variants]

def emit(scaled):
    tag = 'SCALED to unprofiled wall time (presentation only — see docstring)' if scaled \
          else 'TRACED ms/token (measured under identical overhead — use this)'
    print(f"\n=== {tag} ===")
    def val(lb, c):
        v = data[lb].get(c, 0.0)
        return v * scale[lb] if scaled else v
    head = f"{'category':28s}" + ''.join(f"{lb:>10s}" for lb in labels) + \
           ''.join(f"{'Δ' + lb:>10s}" for lb in labels[1:])
    print(head); print('-' * len(head))
    order = sorted(cats, key=lambda c: -abs(val(labels[-1], c) - val(base, c)))
    for c in order:
        line = f"{c:28s}" + ''.join(f"{val(lb, c):10.3f}" for lb in labels)
        line += ''.join(f"{val(lb, c) - val(base, c):+10.3f}" for lb in labels[1:])
        print(line)
    print('-' * len(head))
    tots = {lb: sum(val(lb, c) for c in cats) for lb in labels}
    line = f"{'TOTAL':28s}" + ''.join(f"{tots[lb]:10.3f}" for lb in labels)
    line += ''.join(f"{tots[lb] - tots[base]:+10.3f}" for lb in labels[1:])
    print(line)

    if not scaled and len(labels) > 1:
        last = labels[-1]
        total_delta = tots[last] - tots[base]
        if abs(total_delta) > 1e-9:
            print(f"\nshare of the {last} vs {base} delta ({total_delta:+.3f} ms/tok):")
            for c in order[:5]:
                dv = val(last, c) - val(base, c)
                print(f"  {c:28s} {dv:+7.3f}  {100 * dv / total_delta:5.1f}%")

emit(False)
emit(True)

if args.out:
    rows = [{'category': c,
             'traced': {lb: data[lb].get(c, 0.0) for lb in labels},
             'scaled': {lb: data[lb].get(c, 0.0) * scale[lb] for lb in labels}}
            for c in cats]
    Path(args.out).write_text(json.dumps(
        {'baseline': base, 'scale': scale, 'traced_total_ms_per_tok': traced_tot,
         'rows': rows}, indent=2) + '\n')
    print(f"\nwrote {args.out}")
