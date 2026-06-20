"""LTX distilled launcher with two gfx1151-specific optimizations.

1. Audio vocoder -> CPU. The BigVGAN-style vocoder's fp32 1D convs fall onto
   MIOpen's naive (fp64-accumulate) path on this GPU and dominate runtime
   (~700s of a 10s clip). The same fp32 vocoder on CPU (oneDNN) is ~14x faster
   per call with identical math, so quality is preserved.
2. Transformer load dedup. The distilled pipeline builds the 22B denoise
   transformer once per stage (stage1 + stage2) and frees it between — i.e. it
   loads + fp8-casts the same weights twice (~13-17s wasted). We build it once
   and keep it resident across both stages. Skipped when --offload is used
   (that path intentionally streams weights to save memory).

Behaviour:
  * Always: vocoder on CPU; transformer kept resident (non-offload).
  * If env LTX_NO_AUDIO=1: skip audio decoding entirely (silent video).

Passes CLI args through to `ltx_pipelines.distilled`.
"""
import contextlib
import os
import torch
import ltx_pipelines.distilled as D
from ltx_core.model.audio_vae import vocoder as Vmod
from ltx_core.model.transformer import attention as _attn
from ltx_pipelines.utils import blocks as _blocks
from ltx_pipelines.utils.types import OffloadMode

# The CPU vocoder is multi-threaded (oneDNN/OpenMP). torch defaults to the physical
# core count (16 here); 24 threads benchmarked ~17% faster for these conv1d shapes
# (16 cores + partial SMT; full 32 is slightly worse). Cap to available CPUs.
try:
    torch.set_num_threads(min(24, os.cpu_count() or 16))
except Exception:
    pass

# --- vocoder -> CPU (fp32, full quality) ---
_orig_voc_fwd = Vmod.VocoderWithBWE.forward


def _cpu_vocoder_forward(self, mel_spec):
    dev = mel_spec.device
    # Explicit .float() (CPU autocast won't upcast conv bias like CUDA autocast does).
    self.to("cpu").float()
    out = _orig_voc_fwd(self, mel_spec.to("cpu").float())
    return out.to(dev)


Vmod.VocoderWithBWE.forward = _cpu_vocoder_forward

# --- transformer load dedup: build once, keep resident across stage1+stage2 ---
_orig_tx_ctx = _blocks.DiffusionStage._transformer_ctx
_tx_cache: dict[int, object] = {}


def _resident_transformer_ctx(self, **kwargs):
    # When offloading, keep the original streaming/freeing behaviour (memory-bound).
    if getattr(self, "_offload_mode", OffloadMode.NONE) != OffloadMode.NONE:
        return _orig_tx_ctx(self, **kwargs)
    key = id(self)
    if key not in _tx_cache:
        _tx_cache[key] = self._build_transformer(**kwargs)

    @contextlib.contextmanager
    def _ctx():
        yield _tx_cache[key]

    return _ctx()


_blocks.DiffusionStage._transformer_ctx = _resident_transformer_ctx

# --- SDPA contiguous q/k/v: fix AOTriton head-interleaved stride bottleneck ---
# LTX builds q/k/v as [B,S,H*D] then `.view(...).transpose(1,2)` -> [B,H,S,D] with a
# head-interleaved non-contiguous stride [.., 128, 4096, 1]. AOTriton's gfx1151
# attn_fwd handles that layout terribly: ~2.2s/call at the LTX long-attention shape
# (B=1,H=32,S=15640,D=128,bf16). Forcing q/k/v contiguous before SDPA drops it to
# ~0.22s/call (~10x), and is bit-exact (verified RMSE=0 over multiple seeds). Costs
# ~39ms of copy kernels per call — a clear win for 3s+/1080p (attention-bound) clips.
def _contig_pytorch_attention(self, q, k, v, heads, mask=None):
    if q.ndim == 4:
        # Optional head-major q/k path: preattention already produced contiguous-ish
        # [B,H,S,D] tensors after RoPE, avoiding the extra q/k transpose+contiguous
        # copies here. v still comes from the value projection as [B,S,H*D].
        b, h, _, dim_head = q.shape
        v = v.view(b, -1, heads, dim_head).transpose(1, 2).contiguous()
    else:
        b, _, dim_head = q.shape
        dim_head //= heads
        q, k, v = (t.view(b, -1, heads, dim_head).transpose(1, 2).contiguous() for t in (q, k, v))

    if mask is not None:
        if mask.ndim == 2:
            mask = mask.unsqueeze(0)
        if mask.ndim == 3:
            mask = mask.unsqueeze(1)

    with _attn.sdpa_kernel(self._priority, set_priority=True):
        out = torch.nn.functional.scaled_dot_product_attention(
            q, k, v, attn_mask=mask, dropout_p=0.0, is_causal=False
        )
    out = out.transpose(1, 2).reshape(b, -1, heads * dim_head)
    return out


def _head_major_preattention(self, q, k, attn_module, mask, pe, k_pe):
    # Dead-end experiment kept only for reproducibility (LTX_QK_HEAD_MAJOR=1): it
    # removes q/k copy kernels but feeds AOTriton a bad non-contiguous stride and
    # makes full 1080p attention ~3.3x slower. Do not enable for production runs.
    q = attn_module.q_norm(q)
    k = attn_module.k_norm(k)
    if pe is not None:
        from ltx_core.model.transformer.rope import apply_rotary_emb
        b, _, inner = q.shape
        dim_head = inner // attn_module.heads
        q = q.unflatten(-1, (attn_module.heads, dim_head)).transpose(1, 2)
        k = k.unflatten(-1, (attn_module.heads, dim_head)).transpose(1, 2)
        q = apply_rotary_emb(q, pe, attn_module.rope_type)
        k = apply_rotary_emb(k, pe if k_pe is None else k_pe, attn_module.rope_type)
    return q, k


def _triton_rope_preattention(self, q, k, attn_module, mask, pe, k_pe):
    q = attn_module.q_norm(q)
    k = attn_module.k_norm(k)
    if pe is None:
        return q, k

    from ltx_core.model.transformer.rope import LTXRopeType, apply_rotary_emb
    if attn_module.rope_type != LTXRopeType.SPLIT or q.dtype is not torch.bfloat16 or not q.is_cuda:
        q = apply_rotary_emb(q, pe, attn_module.rope_type)
        k = apply_rotary_emb(k, pe if k_pe is None else k_pe, attn_module.rope_type)
        return q, k

    try:
        q = _fused_split_rope_to_contiguous(q, pe[0], pe[1], attn_module.heads)
        k_freqs = pe if k_pe is None else k_pe
        k = _fused_split_rope_to_contiguous(k, k_freqs[0], k_freqs[1], attn_module.heads)
        return q, k
    except Exception:
        # Shape/dtype guardrail: if an odd attention block appears, preserve correctness.
        q = apply_rotary_emb(q, pe, attn_module.rope_type)
        k = apply_rotary_emb(k, pe if k_pe is None else k_pe, attn_module.rope_type)
        return q, k


# Gate with LTX_NO_CONTIG=1 to A/B against the original head-interleaved layout.
if os.environ.get("LTX_NO_CONTIG") != "1":
    _attn.PytorchAttention.__call__ = _contig_pytorch_attention
    if os.environ.get("LTX_QK_HEAD_MAJOR") == "1":
        from ltx_core.model.transformer import ops as _ops
        _ops.PytorchPreAttention.__call__ = _head_major_preattention
    elif os.environ.get("LTX_TRITON_ROPE") == "1":
        import sys as _sys
        _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from triton_rope import fused_split_rope_to_contiguous as _fused_split_rope_to_contiguous  # noqa: E402
        from ltx_core.model.transformer import ops as _ops
        _ops.PytorchPreAttention.__call__ = _triton_rope_preattention

# --- Triton bf16 linear for the heavy FFN GEMMs (gfx1151, HANDOFF §11e) ---
# After the attention fix the DiT bottleneck is the FFN GEMMs; rocBLAS's
# 128x128x32 Tensile kernel runs at ~12.5% occupancy. A 64x64x64 num_stages=1
# Triton kernel (VGPR 168 -> ~30% occupancy) is +33% on ffn_down, +3% on ffn_up,
# bit-exact. The fp8-cast Linears upcast fp8->bf16 then call F.linear, so we patch
# that bf16 matmul. Only validated (K,N) shapes are routed; all else falls back to
# F.linear. Gate off with LTX_NO_TRITON_GEMM=1.
if os.environ.get("LTX_NO_TRITON_GEMM") != "1":
    import sys as _sys
    _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from triton_linear import triton_linear as _triton_linear  # noqa: E402
    from ltx_core.quantization import fp8_cast as _fp8

    def _fp8_forward_triton(self, input):  # noqa: A002
        w_up = _fp8._upcast_and_round(self.weight, input.dtype, self._with_stochastic_rounding, self._seed)
        b_up = (
            _fp8._upcast_and_round(self.bias, input.dtype, self._with_stochastic_rounding, self._seed)
            if self.bias is not None
            else None
        )
        return _triton_linear(input, w_up, b_up)

    _fp8.Fp8CastLinear.forward = _fp8_forward_triton

# --- optional: skip audio entirely ---
if os.environ.get("LTX_NO_AUDIO") == "1":
    _orig_call = D.DistilledPipeline.__call__

    def _no_audio_call(self, *args, **kwargs):
        self.audio_decoder = lambda *a, **k: None
        return _orig_call(self, *args, **kwargs)

    D.DistilledPipeline.__call__ = _no_audio_call

from ltx_pipelines.distilled import main  # noqa: E402

if __name__ == "__main__":
    main()
