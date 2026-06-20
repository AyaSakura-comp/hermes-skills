"""Triton split-RoPE + [B,S,H*D] -> contiguous [B,H,S,D] layout for LTX attention.

The existing fast SDPA path must feed AOTriton q/k/v as true contiguous [B,H,S,D].
PyTorch's split RoPE produces a head-interleaved layout and then attention pays a
separate `.contiguous()` copy. This kernel fuses the split-RoPE arithmetic and the
layout transform for q/k so SDPA still sees the fast contiguous layout without the
extra q/k copy kernels.

Gate from ltx_run.py with LTX_TRITON_ROPE=1; falls back to stock PyTorch otherwise.
"""
from __future__ import annotations

import os
import torch

try:
    import triton
    import triton.language as tl
    _TRITON_OK = True
except Exception:  # pragma: no cover
    _TRITON_OK = False


if _TRITON_OK:

    @triton.jit
    def _split_rope_to_contig_kernel(
        x, cos, sin, out,
        B: tl.constexpr, T: tl.constexpr, H: tl.constexpr, D: tl.constexpr, CB: tl.constexpr,
        xs_b: tl.constexpr, xs_t: tl.constexpr, xs_c: tl.constexpr,
        cs_b: tl.constexpr, cs_h: tl.constexpr, cs_t: tl.constexpr, cs_d: tl.constexpr,
        ss_b: tl.constexpr, ss_h: tl.constexpr, ss_t: tl.constexpr, ss_d: tl.constexpr,
        os_b: tl.constexpr, os_h: tl.constexpr, os_t: tl.constexpr, os_d: tl.constexpr,
        N: tl.constexpr, BLOCK: tl.constexpr,
    ):
        offs = tl.program_id(0) * BLOCK + tl.arange(0, BLOCK)
        mask = offs < N
        d = offs % D
        tmp = offs // D
        t = tmp % T
        tmp = tmp // T
        h = tmp % H
        b = tmp // H

        half_d = D // 2
        dh = d % half_d
        second = d >= half_d

        # x is [B,T,H*D]. Split RoPE pairs first/second halves within each head.
        x0 = tl.load(x + b * xs_b + t * xs_t + (h * D + dh) * xs_c, mask=mask, other=0.0).to(tl.float32)
        x1 = tl.load(x + b * xs_b + t * xs_t + (h * D + dh + half_d) * xs_c, mask=mask, other=0.0).to(tl.float32)
        cb = tl.where(CB == 1, 0, b)
        c = tl.load(cos + cb * cs_b + h * cs_h + t * cs_t + dh * cs_d, mask=mask, other=0.0).to(tl.float32)
        s = tl.load(sin + cb * ss_b + h * ss_h + t * ss_t + dh * ss_d, mask=mask, other=0.0).to(tl.float32)

        # Match PyTorch's in-place split RoPE numerics exactly:
        #   output = split_input * cos      # rounded to bf16 tensor
        #   output.addcmul_(sin, other)     # reads rounded output, accumulates in fp32, stores bf16
        p0 = (x0 * c).to(tl.bfloat16).to(tl.float32)
        p1 = (x1 * c).to(tl.bfloat16).to(tl.float32)
        y0 = p0 - x1 * s
        y1 = p1 + x0 * s
        y = tl.where(second, y1, y0)
        tl.store(out + b * os_b + h * os_h + t * os_t + d * os_d, y, mask=mask)


def fused_split_rope_to_contiguous(x: torch.Tensor, cos: torch.Tensor, sin: torch.Tensor, heads: int) -> torch.Tensor:
    """Apply LTX split RoPE to x [B,T,H*D] and return contiguous [B,H,T,D]."""
    if not _TRITON_OK:
        raise RuntimeError("Triton is not available")
    if x.ndim != 3 or cos.ndim != 4 or sin.ndim != 4:
        raise ValueError("expected x [B,T,H*D], cos/sin [B,H,T,D/2]")
    if not x.is_cuda or not cos.is_cuda or not sin.is_cuda:
        raise ValueError("fused_split_rope_to_contiguous requires CUDA/ROCm tensors")
    if x.dtype != torch.bfloat16 or cos.dtype != torch.bfloat16 or sin.dtype != torch.bfloat16:
        raise ValueError("only bf16 tensors are routed to the fused RoPE kernel")

    B, T, C = x.shape
    H = heads
    if C % H != 0:
        raise ValueError(f"channels {C} not divisible by heads {H}")
    D = C // H
    if D % 2 != 0:
        raise ValueError(f"head dim {D} must be even")
    if cos.shape[1] != H or sin.shape != cos.shape or cos.shape[2] != T or cos.shape[3] != D // 2:
        raise ValueError(f"incompatible cos/sin shape {tuple(cos.shape)} for x={tuple(x.shape)}, heads={H}")
    if cos.shape[0] not in (1, B):
        raise ValueError(f"cos batch {cos.shape[0]} must be 1 or {B}")

    out = torch.empty((B, H, T, D), device=x.device, dtype=torch.bfloat16)
    N = B * H * T * D
    if "LTX_TRITON_ROPE_BLOCK" in os.environ:
        block = int(os.environ["LTX_TRITON_ROPE_BLOCK"])
        warps = int(os.environ.get("LTX_TRITON_ROPE_WARPS", "4"))
    elif T <= 2550:
        # Small/medium grids are launch/memory-latency sensitive; larger vector blocks win.
        block, warps = 1024, 4
    else:
        # Large 1080p grids prefer smaller blocks with more waves in the microbench sweep.
        block, warps = 128, 8
    grid = (triton.cdiv(N, block),)
    _split_rope_to_contig_kernel[grid](
        x, cos, sin, out,
        B, T, H, D, cos.shape[0],
        x.stride(0), x.stride(1), x.stride(2),
        cos.stride(0), cos.stride(1), cos.stride(2), cos.stride(3),
        sin.stride(0), sin.stride(1), sin.stride(2), sin.stride(3),
        out.stride(0), out.stride(1), out.stride(2), out.stride(3),
        N, BLOCK=block,
        num_warps=warps,
    )
    return out
