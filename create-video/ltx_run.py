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


# Gate with LTX_NO_CONTIG=1 to A/B against the original head-interleaved layout.
if os.environ.get("LTX_NO_CONTIG") != "1":
    _attn.PytorchAttention.__call__ = _contig_pytorch_attention

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
