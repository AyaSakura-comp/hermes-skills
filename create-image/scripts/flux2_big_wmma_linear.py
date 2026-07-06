import functools
import os
import torch
from torch.utils.cpp_extension import load_inline

_ORIG_LINEAR = torch.nn.functional.linear

_REPO = "/home/chihmin/models-work/rocm_wmma_gemm"
_BUILD = _REPO + "/build"

_CPP_DECL = """
void run_rocm_wmma_f32_accum(
    torch::Tensor a,
    torch::Tensor b,
    torch::Tensor c,
    int layout_a,
    int layout_b,
    int layout_c);
"""

_HIP_SRC = r"""
#include <torch/extension.h>
#include <c10/hip/HIPStream.h>
#include <hip/hip_bf16.h>
#include <rocm_wmma_gemm/kernel_loader.hpp>

using rocm_wmma_gemm::m_layout;

static rocm_wmma_gemm::loader& get_loader() {
    static rocm_wmma_gemm::loader l;
    return l;
}

void run_rocm_wmma_f32_accum(
    torch::Tensor a,
    torch::Tensor b,
    torch::Tensor c,
    int layout_a,
    int layout_b,
    int layout_c)
{
    auto stream_obj = c10::hip::getCurrentHIPStream();
    hipStream_t stream = stream_obj.stream();

    float* c_ptr = c.data_ptr<float>();
    __hip_bfloat16* a_ptr = reinterpret_cast<__hip_bfloat16*>(a.data_ptr<at::BFloat16>());
    __hip_bfloat16* b_ptr = reinterpret_cast<__hip_bfloat16*>(b.data_ptr<at::BFloat16>());

    m_layout la = (layout_a == 0) ? m_layout::row_major : m_layout::col_major;
    m_layout lb = (layout_b == 0) ? m_layout::row_major : m_layout::col_major;
    m_layout lc = (layout_c == 0) ? m_layout::row_major : m_layout::col_major;

    size_t M = a.size(0);
    size_t K = a.size(1);
    size_t N = (lb == m_layout::row_major) ? b.size(1) : b.size(0);

    if (la == m_layout::row_major && lb == m_layout::row_major && lc == m_layout::row_major) {
        get_loader().gemm<m_layout::row_major, m_layout::row_major, m_layout::row_major>(c_ptr, a_ptr, b_ptr, M, N, K, stream);
    } else if (la == m_layout::row_major && lb == m_layout::row_major && lc == m_layout::col_major) {
        get_loader().gemm<m_layout::col_major, m_layout::row_major, m_layout::row_major>(c_ptr, a_ptr, b_ptr, M, N, K, stream);
    } else if (la == m_layout::row_major && lb == m_layout::col_major && lc == m_layout::row_major) {
        get_loader().gemm<m_layout::row_major, m_layout::row_major, m_layout::col_major>(c_ptr, a_ptr, b_ptr, M, N, K, stream);
    } else if (la == m_layout::row_major && lb == m_layout::col_major && lc == m_layout::col_major) {
        get_loader().gemm<m_layout::col_major, m_layout::row_major, m_layout::col_major>(c_ptr, a_ptr, b_ptr, M, N, K, stream);
    } else if (la == m_layout::col_major && lb == m_layout::row_major && lc == m_layout::row_major) {
        get_loader().gemm<m_layout::row_major, m_layout::col_major, m_layout::row_major>(c_ptr, a_ptr, b_ptr, M, N, K, stream);
    } else if (la == m_layout::col_major && lb == m_layout::row_major && lc == m_layout::col_major) {
        get_loader().gemm<m_layout::col_major, m_layout::col_major, m_layout::row_major>(c_ptr, a_ptr, b_ptr, M, N, K, stream);
    } else if (la == m_layout::col_major && lb == m_layout::col_major && lc == m_layout::row_major) {
        get_loader().gemm<m_layout::row_major, m_layout::col_major, m_layout::col_major>(c_ptr, a_ptr, b_ptr, M, N, K, stream);
    } else if (la == m_layout::col_major && lb == m_layout::col_major && lc == m_layout::col_major) {
        get_loader().gemm<m_layout::col_major, m_layout::col_major, m_layout::col_major>(c_ptr, a_ptr, b_ptr, M, N, K, stream);
    }
}
"""

@functools.lru_cache(maxsize=1)
def _extension():
    return load_inline(
        name="flux2_rocm_wmma_tuned_ext_v2",
        cpp_sources=_CPP_DECL,
        cuda_sources=_HIP_SRC,
        functions=["run_rocm_wmma_f32_accum"],
        extra_cuda_cflags=[
            f"-I{_REPO}/rocm_wmma_gemm/include",
            "--offload-arch=gfx1151",
            "-D__AMDGCN_WAVEFRONT_SIZE=32",
            "-DHIP_ENABLE_WARP_SYNC_BUILTINS=1",
        ],
        extra_ldflags=[
            f"-L{_BUILD}/rocm_wmma_gemm",
            "-lrocm_wmma_gemm_gfx1151",
            f"-Wl,-rpath,{_BUILD}/rocm_wmma_gemm",
            "-ldl",
        ],
        verbose=bool(os.environ.get("FLUX2_BIG_WMMA_VERBOSE")),
    )

# Cache transposed contiguous weights to avoid costly transposing on each call
_TRANSPOSED_WEIGHT_CACHE = {}

def get_transposed_weight(weight: torch.Tensor) -> torch.Tensor:
    ptr = weight.data_ptr()
    if ptr not in _TRANSPOSED_WEIGHT_CACHE:
        # Prevent memory leaks by resetting the cache if it gets too large
        if len(_TRANSPOSED_WEIGHT_CACHE) > 120:
            _TRANSPOSED_WEIGHT_CACHE.clear()
        _TRANSPOSED_WEIGHT_CACHE[ptr] = weight.t().contiguous()
    return _TRANSPOSED_WEIGHT_CACHE[ptr]

def _can_use_big_wmma(input: torch.Tensor, weight: torch.Tensor, bias) -> bool:
    if not (input.is_cuda and weight.is_cuda):
        return False
    if input.dtype is not torch.bfloat16 or weight.dtype is not torch.bfloat16:
        return False
    if bias is not None and (not bias.is_cuda or bias.dtype is not torch.bfloat16):
        return False
    if input.shape[-1] != weight.shape[-1]:
        return False
        
    m = input.reshape(-1, input.shape[-1]).shape[0]
    k = input.shape[-1]
    n = weight.shape[0]
    
    # Target only the specific large shapes to ensure the GOMEA-tuned configuration matches.
    # Shape 1: M=12168, K=4096, N=4096
    # Shape 2: M=12680, K=16384, N=4096
    return (m == 12168 and k == 4096 and n == 4096) or (m == 12680 and k == 16384 and n == 4096)

def big_wmma_linear(input: torch.Tensor, weight: torch.Tensor, bias=None) -> torch.Tensor:
    original_shape = input.shape[:-1]
    m = input.reshape(-1, input.shape[-1]).shape[0]
    k = input.shape[-1]
    n = weight.shape[0]

    if not _can_use_big_wmma(input, weight, bias):
        return _ORIG_LINEAR(input, weight, bias)

    if os.environ.get("FLUX2_BIG_WMMA_VERBOSE") == "1":
        print(f"[BIG WMMA Dispatch] m={m}, k={k}, n={n}", flush=True)

    a = input.reshape(-1, k).contiguous()
    
    # Use pre-transposed weight cache for maximum speed (Layout 0_0_0)
    w_t = get_transposed_weight(weight)
    
    # Allocate float32 output tensor for precision accumulation
    out_f32 = torch.empty((a.shape[0], n), device=input.device, dtype=torch.float32)
    
    # Dispatch to tuned library
    _extension().run_rocm_wmma_f32_accum(a, w_t, out_f32, 0, 0, 0)
    
    # Convert float32 back to bfloat16 output
    out = out_f32.to(torch.bfloat16)
    
    # Apply bias if present
    if bias is not None:
        out.add_(bias)
        
    return out.reshape(*original_shape, n)

def install_patch():
    torch.nn.functional.linear = big_wmma_linear

def uninstall_patch():
    torch.nn.functional.linear = _ORIG_LINEAR
