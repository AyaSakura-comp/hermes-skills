#!/usr/bin/env python3
"""Group decode kernels into comparable categories.

    categorize_kernels.py DB DECODE_SUMMARY.json OUT_CATEGORIES.json

DECODE_SUMMARY.json is the output of analyze_trace_db.py; its window boundaries
are reused so the categories cover exactly the decode phase.

The ggml_type numbers in the mangled kernel names are what separate an LM head
from MoE experts: 2=Q4_0, 8=Q8_0, 12=Q4_K, 13=Q5_K, 14=Q6_K.
"""
import json, sqlite3, sys
from collections import defaultdict
from pathlib import Path

db_path, summary_path, out_path = map(Path, sys.argv[1:4])
meta = json.loads(summary_path.read_text())
c = sqlite3.connect(db_path)

def table(p):
    return c.execute("select name from sqlite_master where type='table' and name like ?", (p,)).fetchone()[0]

D, K = table('rocpd_kernel_dispatch_%'), table('rocpd_info_kernel_symbol_%')
rows = c.execute(f'''select coalesce(k.display_name,k.kernel_name,'<unknown>'), d.end-d.start,
                            d.grid_size_x/d.workgroup_size_x
                     from {D} d join {K} k on k.id=d.kernel_id
                     where d.start>=? and d.start<?''',
                 (meta['prefill_end_ns'], meta['trace_decode_end_ns'])).fetchall()

# The LM head is not identifiable by kernel name: it uses the same mul_mat_vec_q
# template as every other dense projection, and its ggml_type follows whatever the
# gguf quantised lm_head to (Q6_K in the default model, Q4_0 in ...-lmhead_q40.gguf).
# What separates it is the output row count — one block per vocab row, vs at most a
# few thousand for any attention/MLP projection. Anything above this many blocks is
# the vocabulary projection; below it is an ordinary dense matvec.
VOCAB_BLOCKS_MIN = 32768

QUANT = {'2': 'Q4_0', '8': 'Q8_0', '12': 'Q4_K', '13': 'Q5_K', '14': 'Q6_K'}

def quant_of(n):
    for t in ('14', '13', '12', '8', '2'):
        if f'(ggml_type){t}' in n:
            return QUANT[t]
    return None

def cat(n, blocks):
    if 'flash_attn_tile' in n or 'flash_attn_ext_vec' in n or 'fattn' in n:
        return 'Flash Attention compute'
    if 'dequantize_block_q4_0' in n:
        return 'KV Q4 global dequant'
    if 'mul_mat_vec_q_moe' in n:
        for t, l in [('13', 'MoE Q5_K Down'), ('12', 'MoE Q4_K Gate/Up')]:
            if f'(ggml_type){t}' in n:
                return l
        return 'MoE other matvec'
    if 'mul_mat_vec_q' in n:
        q = quant_of(n)
        # VocabTailor projects against a prefill-selected subset, so its row count is
        # no longer vocab-scale — identify it by kernel name instead of by grid.
        if 'vocab_tailor' in n:
            return f'Dense {q} LM head (VocabTailor)' if q else 'LM head (VocabTailor)'
        if blocks >= VOCAB_BLOCKS_MIN:
            return f'Dense {q} LM head' if q else 'Dense LM head'
        return f'Dense {q}' if q else 'Dense other quant matvec'
    if 'mul_mat_vec_f' in n or n.startswith('Cijk_'):
        return 'Dense F32/GEMM'
    if 'quantize_q8_1' in n:            return 'Q8_1 activation quantize'
    if 'rms_norm' in n or 'l2_norm' in n: return 'Norms'
    if 'k_bin_bcast' in n or 'unary_' in n or 'reduce_rows' in n or 'op_clamp' in n:
        return 'Elementwise/reductions'
    if '__amd_rocclr_copyBuffer' in n or 'cpy_' in n or 'concat_' in n or 'get_rows' in n or 'set_rows' in n:
        return 'Copies/rows/concat'
    if 'gated_delta_net' in n or 'ssm_' in n: return 'GDN/SSM'
    if 'soft_max' in n or 'argsort' in n or 'topk' in n: return 'MoE routing'
    if 'rope_' in n: return 'RoPE'
    return 'Other'

agg = defaultdict(lambda: [0, 0.0])
for n, ns, blocks in rows:
    k = cat(n, blocks)
    agg[k][0] += 1
    agg[k][1] += ns / 1e6

tot = sum(v[1] for v in agg.values())
tokens = meta['equivalent_output_tokens_est']
out = [{'category': k, 'count': cnt, 'launches_per_token': cnt / tokens, 'total_ms': ms,
        'ms_per_token': ms / tokens, 'gpu_time_pct': 100 * ms / tot}
       for k, (cnt, ms) in sorted(agg.items(), key=lambda x: x[1][1], reverse=True)]

Path(out_path).write_text(json.dumps(
    {'db': str(db_path), 'kernel_total_ms': tot,
     'equivalent_output_tokens': tokens, 'categories': out}, indent=2) + '\n')

for x in out:
    print(f"{x['gpu_time_pct']:6.2f}% {x['ms_per_token']:7.3f} ms/tok "
          f"{x['launches_per_token']:7.2f}/tok {x['category']}")
