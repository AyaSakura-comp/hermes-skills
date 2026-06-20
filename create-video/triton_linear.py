"""Triton bf16 linear for the LTX DiT's heavy FFN GEMMs on gfx1151.

Background (HANDOFF §10-11): after the attention `.contiguous()` fix, the 22B DiT's
bottleneck shifted to the FFN GEMMs. rocBLAS/Tensile picks a 128x128x32 kernel that
runs at only ~12.5% occupancy (VGPR=256, LDS=51200) on gfx1151. A plain Triton
register-tiled kernel with a *small* 64x64x64 tile and **num_stages=1** (lowest VGPR
=168 -> highest occupancy ~30%) is markedly faster on the large-K ffn_down shape:

    stage2 ffn_down (M=14280, K=16384, N=4096):  rocBLAS 110.8ms -> Triton 83.0ms  (+33%)
    stage2 ffn_up   (M=14280, K=4096,  N=16384): rocBLAS  69.2ms -> Triton 66.9ms  (+3%)

Both are bit-exact vs torch.nn.functional.linear (verified, 0/58.5M mismatches).
We only route the shapes we have validated as wins (keyed by (K, N)); every other
linear (qkv = tie, audio FF, odd dtypes, non-cuda, M too small) falls back to
torch.nn.functional.linear so we never regress.

Gate off with env LTX_NO_TRITON_GEMM=1 for A/B.
"""
from __future__ import annotations

import torch
import torch.nn.functional as F

try:
    import triton
    import triton.language as tl
    _TRITON_OK = True
except Exception:  # pragma: no cover - triton missing
    _TRITON_OK = False


# (K, N) -> (BLOCK_M, BLOCK_N, BLOCK_K, num_warps, num_stages), GROUP_M=8.
# Tuned + validated on gfx1151 (HANDOFF §11e items 1/3). Only large GEMMs where
# Triton clearly wins; qkv (4096x4096) is a tie so deliberately omitted.
_TUNED: dict[tuple[int, int], tuple[int, int, int, int, int]] = {
    (16384, 4096): (64, 64, 64, 4, 1),    # video ffn_down  (+33%)
    (4096, 16384): (128, 64, 64, 4, 1),   # video ffn_up    (+3%)
}
_GROUP_M = 8
# Below this many output rows the launch overhead isn't worth it; use rocBLAS.
_MIN_M = 512


if _TRITON_OK:

    @triton.jit
    def _linear_bf16_kernel(
        a_ptr, b_ptr, c_ptr, bias_ptr,
        M, N, K,
        stride_am, stride_ak,
        stride_bn, stride_bk,
        stride_cm, stride_cn,
        HAS_BIAS: tl.constexpr,
        BLOCK_M: tl.constexpr, BLOCK_N: tl.constexpr, BLOCK_K: tl.constexpr,
        GROUP_M: tl.constexpr,
    ):
        pid = tl.program_id(0)
        num_pid_m = tl.cdiv(M, BLOCK_M)
        num_pid_n = tl.cdiv(N, BLOCK_N)
        num_pid_in_group = GROUP_M * num_pid_n
        group_id = pid // num_pid_in_group
        first_pid_m = group_id * GROUP_M
        group_size_m = tl.minimum(num_pid_m - first_pid_m, GROUP_M)
        pid_m = first_pid_m + ((pid % num_pid_in_group) % group_size_m)
        pid_n = (pid % num_pid_in_group) // group_size_m

        offs_m = pid_m * BLOCK_M + tl.arange(0, BLOCK_M)
        offs_n = pid_n * BLOCK_N + tl.arange(0, BLOCK_N)
        offs_k = tl.arange(0, BLOCK_K)

        acc = tl.zeros((BLOCK_M, BLOCK_N), tl.float32)
        for k0 in range(0, K, BLOCK_K):
            k = k0 + offs_k
            a = tl.load(
                a_ptr + offs_m[:, None] * stride_am + k[None, :] * stride_ak,
                mask=(offs_m[:, None] < M) & (k[None, :] < K), other=0.0,
            )
            b = tl.load(
                b_ptr + offs_n[:, None] * stride_bn + k[None, :] * stride_bk,
                mask=(offs_n[:, None] < N) & (k[None, :] < K), other=0.0,
            )
            acc += tl.dot(a, tl.trans(b), out_dtype=tl.float32)

        if HAS_BIAS:
            # Add bias in fp32 before the bf16 cast, matching F.linear exactly.
            bias = tl.load(bias_ptr + offs_n, mask=offs_n < N, other=0.0).to(tl.float32)
            acc += bias[None, :]

        tl.store(
            c_ptr + offs_m[:, None] * stride_cm + offs_n[None, :] * stride_cn,
            acc.to(tl.bfloat16),
            mask=(offs_m[:, None] < M) & (offs_n[None, :] < N),
        )


def _triton_mm(a2d: torch.Tensor, weight: torch.Tensor, bias, cfg) -> torch.Tensor:
    """a2d [M,K] @ weight[N,K]^T (+ bias) -> [M,N], bf16. Bias fused in fp32."""
    M, K = a2d.shape
    N = weight.shape[0]
    bm, bn, bk, warps, stages = cfg
    out = torch.empty((M, N), device=a2d.device, dtype=torch.bfloat16)
    grid = (triton.cdiv(M, bm) * triton.cdiv(N, bn),)
    _linear_bf16_kernel[grid](
        a2d, weight, out, bias if bias is not None else a2d, M, N, K,
        a2d.stride(0), a2d.stride(1),
        weight.stride(0), weight.stride(1),
        out.stride(0), out.stride(1),
        HAS_BIAS=bias is not None,
        BLOCK_M=bm, BLOCK_N=bn, BLOCK_K=bk, GROUP_M=_GROUP_M,
        num_warps=warps, num_stages=stages,
    )
    return out


def triton_linear(input: torch.Tensor, weight: torch.Tensor, bias=None) -> torch.Tensor:
    """Drop-in for F.linear that routes validated heavy bf16 shapes to Triton.

    Falls back to torch.nn.functional.linear for anything not in the tuned table,
    non-bf16, non-cuda, or with too few rows to amortise launch overhead.
    """
    K = input.shape[-1]
    N = weight.shape[0]
    cfg = _TUNED.get((K, N))
    if (
        not _TRITON_OK
        or cfg is None
        or input.dtype != torch.bfloat16
        or weight.dtype != torch.bfloat16
        or not input.is_cuda
    ):
        return F.linear(input, weight, bias)

    a2d = input.reshape(-1, K)
    if a2d.shape[0] < _MIN_M:
        return F.linear(input, weight, bias)
    if not a2d.is_contiguous():
        a2d = a2d.contiguous()
    w = weight if weight.is_contiguous() else weight.contiguous()
    b = bias
    if b is not None and (b.dtype != torch.bfloat16 or not b.is_contiguous()):
        b = b.to(torch.bfloat16).contiguous()

    out = _triton_mm(a2d, w, b, cfg)
    return out.reshape(*input.shape[:-1], N)
