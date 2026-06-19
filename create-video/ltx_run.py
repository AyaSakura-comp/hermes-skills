"""LTX distilled launcher with the audio vocoder routed to CPU.

On gfx1151 the BigVGAN-style vocoder's fp32 1D convolutions fall onto MIOpen's
naive (fp64-accumulate) path and dominate runtime (~700s of a 10s clip). Running
that vocoder on the CPU (fp32 oneDNN) is ~90x faster (10s clip: 7.7s vs ~704s)
with identical fp32 math, so audio quality is preserved.

Behaviour:
  * Always: the vocoder runs on CPU.
  * If env LTX_NO_AUDIO=1: skip audio decoding entirely (silent video, marginally
    faster), e.g. when the user wants to add music separately (create-music).

Passes CLI args through to `ltx_pipelines.distilled`.
"""
import os
import torch
import ltx_pipelines.distilled as D
from ltx_core.model.audio_vae import vocoder as Vmod

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
