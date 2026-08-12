#!/usr/bin/env python3
"""Slice the decode window out of a rocprofv3 kernel-trace database.

    analyze_trace_db.py DB PROMPT_EVAL_MS EVAL_MS OUT.json [N_OUTPUT_TOKENS]

PROMPT_EVAL_MS / EVAL_MS come from the server log of that same run:

    prompt eval time = 14144.95 ms / 20000 tokens
           eval time = 14139.37 ms /   512 tokens

Window method: the request's first GPU work is the first dispatch after the
largest multi-second gap in the trace (model load -> health -> idle). Prefill ends
prompt_eval_ms later; decode runs from there to prefill_end + eval_ms.
"""
import json, sqlite3, statistics, sys
from collections import defaultdict
from pathlib import Path

db_path, prompt_ms, decode_ms, out_path = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), Path(sys.argv[4])
output_tokens = int(sys.argv[5]) if len(sys.argv) > 5 else 512

c = sqlite3.connect(db_path)
def table(pattern):
    row = c.execute("select name from sqlite_master where type='table' and name like ?", (pattern,)).fetchone()
    if not row:
        raise SystemExit(f"{db_path}: no table matching {pattern} — is this an empty/partial trace?")
    return row[0]

D, K = table('rocpd_kernel_dispatch_%'), table('rocpd_info_kernel_symbol_%')
all_times = c.execute(f'select start,end from {D} order by start').fetchall()
if not all_times:
    raise SystemExit(f"{db_path}: zero dispatches — the trace was killed before rocprofv3 flushed")

gaps = [(all_times[i][0] - all_times[i-1][1], i) for i in range(1, len(all_times)) if 0 < all_times[i][0] - all_times[i-1][1] < 100e9]
gap_ns, request_i = max(gaps)
request_start = all_times[request_i][0]
prefill_end = request_start + int(prompt_ms * 1e6)
trace_end = min(all_times[-1][1], prefill_end + int(decode_ms * 1e6))

rows = c.execute(f'''select coalesce(k.display_name,k.kernel_name,'<unknown>'), d.start, d.end
                     from {D} d join {K} k on k.id=d.kernel_id
                     where d.start >= ? and d.start < ? order by d.start''',
                 (prefill_end, trace_end)).fetchall()

by = defaultdict(list)
for name, start, end in rows:
    by[name].append((end - start) / 1000.0)          # us

equiv_tokens = output_tokens * ((trace_end - prefill_end) / 1e6) / decode_ms
summary = [{'name': n, 'count': len(us), 'launches_per_token_est': len(us) / equiv_tokens,
            'total_ms': sum(us) / 1000, 'avg_us': statistics.mean(us),
            'median_us': statistics.median(us), 'lt5us': sum(x < 5 for x in us)}
           for n, us in by.items()]

by_count = sorted(summary, key=lambda x: x['count'], reverse=True)
by_time = sorted(summary, key=lambda x: x['total_ms'], reverse=True)
result = {
    'db': db_path,
    'method': 'request start = first dispatch after largest post-load gap; prefill boundary = start + prompt_eval_ms',
    'largest_gap_s': gap_ns / 1e9,
    'request_start_ns': request_start,
    'prefill_end_ns': prefill_end,
    'trace_decode_end_ns': trace_end,
    'decode_trace_s': (trace_end - prefill_end) / 1e9,
    'equivalent_output_tokens_est': equiv_tokens,
    'dispatches': len(rows),
    'dispatches_per_token_est': len(rows) / equiv_tokens,
    'lt5us_count': sum(x['lt5us'] for x in summary),
    'lt5us_pct': 100 * sum(x['lt5us'] for x in summary) / len(rows),
    'kernel_total_ms': sum(x['total_ms'] for x in summary),
    'top_by_count': by_count[:40],
    'top_by_gpu_time': by_time[:30],
}
out_path.write_text(json.dumps(result, indent=2) + '\n')

print(json.dumps({k: result[k] for k in
                  ('decode_trace_s', 'equivalent_output_tokens_est', 'dispatches',
                   'dispatches_per_token_est', 'lt5us_pct', 'kernel_total_ms')}, indent=2))
print('\nTOP BY COUNT')
for x in by_count[:20]:
    print(f"{x['count']:7d} {x['launches_per_token_est']:7.2f}/tok {x['avg_us']:8.3f} us "
          f"{x['total_ms']:9.3f} ms  {x['name'][:120]}")
