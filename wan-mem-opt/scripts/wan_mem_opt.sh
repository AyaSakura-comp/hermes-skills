#!/usr/bin/env bash
set -euo pipefail

# Low-memory Wan2.1 1.3B launcher for AMD UMA/ROCm.
# Defaults: CPU UMT5 text encoder + tiled VAE decode.

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNNER="$SKILL_DIR/scripts/run_wan21_direct_optimized.py"
PROFILER="$SKILL_DIR/scripts/profile_uma_memory.py"
COMFY_PY="${COMFY_PY:-/home/chihmin/src/ComfyUI/.venv/bin/python}"
export COMFY_DIR="${COMFY_DIR:-/home/chihmin/src/ComfyUI}"

export TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL="${TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL:-1}"
export MIOPEN_FIND_MODE="${MIOPEN_FIND_MODE:-FAST}"
export MIOPEN_USER_DB_PATH="${MIOPEN_USER_DB_PATH:-/home/chihmin/.cache/miopen-wan21}"
export PYTHONUTF8=1

PROFILE=0
WARMUP=0
WARMUP_STEPS=1
OUTDIR="/home/chihmin/generated/wan21_mem_opt_$(date +%Y%m%d_%H%M%S)"
ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile)
      PROFILE=1; shift ;;
    --warmup)
      WARMUP=1; shift ;;
    --warmup-steps)
      WARMUP=1; WARMUP_STEPS="$2"; shift 2 ;;
    --no-warmup)
      WARMUP=0; shift ;;
    --outdir)
      OUTDIR="$2"; shift 2 ;;
    --help|-h)
      cat <<EOF
Usage: wan_mem_opt.sh [--profile] [--warmup] [--warmup-steps N] [--outdir DIR] --output OUT.mp4 [runner options]

Low-memory Wan2.1 1.3B runner. Defaults inside the runner:
  --clip-device cpu      keep UMT5 text encoder on CPU (~6 GiB UMA saved)
  --vae-mode tiled       tiled VAE decode for lowest peak memory

Recommended lowest-memory run:
  wan_mem_opt.sh --profile --output /home/chihmin/generated/cat.mp4 --steps 12 --vae-mode tiled --tile-size 256

Warmup/precompile run, same process and same shape:
  wan_mem_opt.sh --profile --warmup --output /home/chihmin/generated/cat.mp4 --steps 12 --vae-mode tiled --tile-size 256

Common runner options:
  --prompt TEXT --negative TEXT --width 832 --height 480 --frames 17 --fps 16
  --steps 12 --cfg 6 --seed 2026070118
  --clip-device cpu|default --free-clip-after-encode/--no-free-clip-after-encode
  --warmup-decode/--no-warmup-decode
  --vae-mode regular|tiled --tile-size 256 --overlap 64 --temporal-size 16 --temporal-overlap 4

Environment variables:
  COMFY_PY=$COMFY_PY
  COMFY_DIR=$COMFY_DIR
  TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL=$TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL
  MIOPEN_FIND_MODE=$MIOPEN_FIND_MODE
  MIOPEN_USER_DB_PATH=$MIOPEN_USER_DB_PATH
EOF
      exit 0 ;;
    *) ARGS+=("$1"); shift ;;
  esac
done

mkdir -p "$OUTDIR" "$(dirname "${MIOPEN_USER_DB_PATH}")" "$MIOPEN_USER_DB_PATH"

[[ -x "$COMFY_PY" ]] || { echo "Missing ComfyUI python: $COMFY_PY" >&2; exit 1; }
[[ -d "$COMFY_DIR" ]] || { echo "Missing ComfyUI dir: $COMFY_DIR" >&2; exit 1; }
[[ -f "$COMFY_DIR/models/diffusion_models/wan2.1_t2v_1.3B_fp16.safetensors" ]] || { echo "Missing Wan2.1 1.3B safetensors in ComfyUI diffusion_models" >&2; exit 1; }
[[ -f "$COMFY_DIR/models/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors" ]] || { echo "Missing UMT5 text encoder in ComfyUI text_encoders" >&2; exit 1; }
[[ -f "$COMFY_DIR/models/vae/wan_2.1_vae.safetensors" ]] || { echo "Missing Wan VAE in ComfyUI vae" >&2; exit 1; }

if [[ ${#ARGS[@]} -eq 0 ]]; then
  ARGS=(--output "$OUTDIR/wan21_1p3b_memopt_cat_12step.mp4" --steps 12 --vae-mode tiled --tile-size 256)
fi

if [[ "$WARMUP" == 1 ]]; then
  ARGS+=(--warmup-steps "$WARMUP_STEPS")
fi

if [[ "$PROFILE" == 1 ]]; then
  "$PROFILER" "$OUTDIR/uma_profile.csv" 'run_wan21_direct_optimized.py|ComfyUI/.venv/bin/python' \
    "$COMFY_PY" "$RUNNER" "${ARGS[@]}"
  echo "Profile summary: $OUTDIR/uma_profile.csv.summary"
else
  "$COMFY_PY" "$RUNNER" "${ARGS[@]}"
fi
