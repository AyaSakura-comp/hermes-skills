import functools
import os

import torch
from torch.utils.cpp_extension import load_inline


_ORIG_LINEAR = torch.nn.functional.linear


_CPP_DECL = """
void run_m1_bf16_linear(torch::Tensor a, torch::Tensor w, torch::Tensor c);
"""


_HIP_SRC = r"""
#include <torch/extension.h>
#include <hip/hip_runtime.h>
#include <stdint.h>

__device__ __forceinline__ float bf16_to_float(uint16_t x) {
    union { uint32_t u; float f; } v;
    v.u = ((uint32_t)x) << 16;
    return v.f;
}

__device__ __forceinline__ uint16_t float_to_bf16_rn(float x) {
    union { float f; uint32_t u; } v;
    v.f = x;
    uint32_t lsb = (v.u >> 16) & 1u;
    v.u += 0x7fffu + lsb;
    return (uint16_t)(v.u >> 16);
}

__global__ void m1_bf16_linear_kernel(
    const uint16_t* __restrict__ a,
    const uint16_t* __restrict__ w,
    uint16_t* __restrict__ c,
    int n,
    int k)
{
    const int col = blockIdx.x;
    const int tid = threadIdx.x;
    constexpr int BLOCK = 256;
    __shared__ float partial[BLOCK];

    float acc = 0.0f;
    for (int kk = tid; kk < k; kk += BLOCK) {
        acc += bf16_to_float(a[kk]) * bf16_to_float(w[col * k + kk]);
    }
    partial[tid] = acc;
    __syncthreads();

    for (int stride = BLOCK / 2; stride > 0; stride >>= 1) {
        if (tid < stride) {
            partial[tid] += partial[tid + stride];
        }
        __syncthreads();
    }

    if (tid == 0) {
        c[col] = float_to_bf16_rn(partial[0]);
    }
}

void run_m1_bf16_linear(torch::Tensor a, torch::Tensor w, torch::Tensor c) {
    const int k = static_cast<int>(a.size(1));
    const int n = static_cast<int>(w.size(0));
    dim3 block(256);
    dim3 grid(n);
    m1_bf16_linear_kernel<<<grid, block>>>(
        reinterpret_cast<const uint16_t*>(a.data_ptr<at::BFloat16>()),
        reinterpret_cast<const uint16_t*>(w.data_ptr<at::BFloat16>()),
        reinterpret_cast<uint16_t*>(c.data_ptr<at::BFloat16>()),
        n,
        k);
}
"""


@functools.lru_cache(maxsize=1)
def _extension():
    return load_inline(
        name="flux2_m1_bf16_linear_ext_v2",
        cpp_sources=_CPP_DECL,
        cuda_sources=_HIP_SRC,
        functions=["run_m1_bf16_linear"],
        extra_cuda_cflags=["--offload-arch=gfx1151", "-D__AMDGCN_WAVEFRONT_SIZE=32", "-O3"],
        verbose=bool(os.environ.get("FLUX2_M1_LINEAR_VERBOSE")),
    )


def _can_use_custom(input: torch.Tensor, weight: torch.Tensor, bias) -> bool:
    if bias is not None:
        return False
    if not (input.is_cuda and weight.is_cuda):
        return False
    if input.dtype is not torch.bfloat16 or weight.dtype is not torch.bfloat16:
        return False
    if input.shape[-1] != weight.shape[-1]:
        return False
    if input.numel() == 0 or weight.numel() == 0:
        return False
    # The first real FLUX.2 kernel we can safely replace is the M=1 BF16 no-bias linear
    # (timestep / pooled embedding and output-layer style calls in the handoff table).
    return input.reshape(-1, input.shape[-1]).shape[0] == 1


def rocwmma_linear(input: torch.Tensor, weight: torch.Tensor, bias=None) -> torch.Tensor:
    """Custom BF16 F.linear replacement for the FLUX.2 M=1 GEMM shape.

    This intentionally targets one real FLUX.2 GEMM family first. Other shapes
    fall back to PyTorch/hipBLAS unchanged.
    """
    if not _can_use_custom(input, weight, bias):
        return _ORIG_LINEAR(input, weight, bias)

    original_shape = input.shape[:-1]
    k = input.shape[-1]
    n = weight.shape[0]
    a2d = input.reshape(1, k).contiguous()
    w = weight.contiguous()
    out = torch.empty((1, n), device=input.device, dtype=torch.bfloat16)
    _extension().run_m1_bf16_linear(a2d, w, out)
    return out.reshape(*original_shape, n)


def install_patch():
    torch.nn.functional.linear = rocwmma_linear


def uninstall_patch():
    torch.nn.functional.linear = _ORIG_LINEAR
