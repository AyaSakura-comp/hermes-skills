#!/usr/bin/env bash
# create-video — LTX-2.3 (22B audio-video DiT) text/image-to-video on the local ROCm GPU.
# Distilled two-stage pipeline, fp8-cast, flash-attention (AOTriton) on by default.
set -euo pipefail

LTX_DIR="${LTX_DIR:-$HOME/src/LTX-2}"
PY="$LTX_DIR/.venv/bin/python"
CKPT="$LTX_DIR/models/ltx/ltx-2.3-22b-distilled-1.1.safetensors"
UPSAMPLER="$LTX_DIR/models/ltx/ltx-2.3-spatial-upscaler-x2-1.1.safetensors"
GEMMA="$LTX_DIR/models/gemma-3-12b-it"

# --- defaults ---
PROMPT=""
IMAGE_PATH=""        # optional source image for image-to-video conditioning
IMAGE_FRAME=0         # condition the first generated frame by default
IMAGE_STRENGTH="0.9" # strong adherence to the source photo by default
IMAGE_CRF=""         # optional H.264 CRF for image conditioning (LTX default when empty)
DURATION=3            # seconds
FPS=24
ASPECT="16:9"         # used when no explicit --resolution
RESOLUTION=""         # WxH overrides aspect
HQ=0                  # --hq bumps the short side to 576 (e.g. 1024x576 for 16:9)
SHORT_LOW=320         # default 320p
SHORT_HQ=576
SEED="$RANDOM"
STEPS=""              # optional override of stage-1 steps
QUANTIZATION="fp8-cast" # default lower-memory transformer weight quantization; empty = bf16/no quant
FLASH=1               # AOTriton flash attention on by default
OFFLOAD=""            # none|cpu|disk
AUDIO=1              # 1 = synced audio (vocoder on CPU, nearly free); 0 = silent (--no-audio)
LORA_PATH=""         # path to a .safetensors LoRA file
LORA_STRENGTH="1.0"  # LoRA strength (default 1.0)
OUTPUT=""

usage() {
  cat <<'EOF'
create-video — generate a short video (with synced audio) from text, or animate a source image.

Usage:
  create_video.sh -p "PROMPT" [options]
  create_video.sh -p "PROMPT" --image photo.jpg [options]

Options:
  -p, --prompt TEXT     What to generate (required). Be cinematic & specific.
  -i, --image PATH      Optional source photo/image to animate from frame 0.
      --image-frame N   Target frame index for --image conditioning (default: 0).
      --image-strength X  Image adherence strength for --image (default: 0.9).
      --image-crf N     Optional conditioning image CRF (0=lossless; LTX default when omitted).
  -d, --duration SEC    Clip length in seconds (default: 3).
      --fps N           Frames per second (default: 24).
  -a, --aspect W:H      Aspect ratio when no -r given (default: 16:9). e.g. 9:16, 1:1, 4:3.
  -r, --resolution WxH  Explicit resolution (must be multiples of 64). Overrides -a.
      --hq              High quality: bumps short side to 576 (e.g. 1024x576 for 16:9).
  -o, --output PATH     Output .mp4 (default: ./video_<timestamp>.mp4).
      --seed N          Random seed (default: random).
      --steps N         Override stage-1 denoise steps.
      --quantization MODE  fp8-cast|fp8-scaled-mm|bf16|none (default: fp8-cast).
      --bf16            Disable quantization; run weights in bf16/no-quant mode.
      --offload MODE    none|cpu|disk — lower GPU memory (default: none).
      --audio           Synced audio on (default; vocoder runs on CPU, nearly free).
      --no-audio        Silent video (skip the vocoder entirely).
      --no-flash        Disable flash attention (use plain SDPA).
      --lora PATH STRENGTH  Path to a .safetensors LoRA + optional strength (default 1.0).
  -h, --help            Show this help.

Audio note: synced audio is ON by default. The vocoder runs on CPU (its fp32 1D
convs are crippled on this GPU's MIOpen path); on CPU it's ~90x faster and full
fp32 quality, so audio costs only a few seconds (10s clip: ~148s with audio vs
~144s silent). Use --no-audio for silent output (e.g. to score with create-music).

Resolution rules: dims are snapped to multiples of 64 (two-stage requirement);
frame count is snapped to 8k+1. Default is 320p 16:9 (576x320).

Precision note: default is --quantization fp8-cast to reduce memory. Use --bf16
(or --quantization none) to disable quantization; this can improve fidelity slightly
but uses much more memory and may require --offload cpu.

Image note: --image forwards to LTX image conditioning as PATH FRAME STRENGTH [CRF].
The wrapper defaults to frame 0 and strength 0.9 so a single source photo can be
animated with a prompt while preserving the original subject/composition.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -p|--prompt)     PROMPT="$2"; shift 2;;
    -i|--image)      IMAGE_PATH="$2"; shift 2;;
    --image-frame)   IMAGE_FRAME="$2"; shift 2;;
    --image-strength) IMAGE_STRENGTH="$2"; shift 2;;
    --image-crf)     IMAGE_CRF="$2"; shift 2;;
    -d|--duration)   DURATION="$2"; shift 2;;
    --fps)           FPS="$2"; shift 2;;
    -a|--aspect)     ASPECT="$2"; shift 2;;
    -r|--resolution) RESOLUTION="$2"; shift 2;;
    --hq)            HQ=1; shift;;
    -o|--output)     OUTPUT="$2"; shift 2;;
    --seed)          SEED="$2"; shift 2;;
    --steps)         STEPS="$2"; shift 2;;
    --quantization)  QUANTIZATION="$2"; shift 2;;
    --bf16)          QUANTIZATION=""; shift;;
    --offload)       OFFLOAD="$2"; shift 2;;
    --audio)         AUDIO=1; shift;;
    --no-audio)      AUDIO=0; shift;;
    --no-flash)      FLASH=0; shift;;
    --lora)          LORA_PATH="$2"; shift 2;;
    -h|--help)       usage; exit 0;;
    *) echo "Unknown arg: $1" >&2; usage; exit 1;;
  esac
done

[[ -z "$PROMPT" ]] && { echo "ERROR: --prompt is required." >&2; usage; exit 1; }
case "$QUANTIZATION" in
  fp8-cast|fp8-scaled-mm) ;;
  bf16|none) QUANTIZATION="" ;;
  "") ;;
  *) echo "ERROR: --quantization must be one of: fp8-cast, fp8-scaled-mm, bf16, none" >&2; exit 1;;
esac
[[ -n "$IMAGE_PATH" && ! -f "$IMAGE_PATH" ]] && { echo "ERROR: image not found: $IMAGE_PATH" >&2; exit 1; }
[[ -f "$CKPT" ]] || { echo "ERROR: checkpoint not found: $CKPT" >&2; exit 1; }

round64() { awk -v x="$1" 'BEGIN{ v=int((x+32)/64)*64; if(v<64)v=64; print v }'; }

# --- compute WIDTH x HEIGHT ---
if [[ -n "$RESOLUTION" ]]; then
  WIDTH="${RESOLUTION%x*}"; HEIGHT="${RESOLUTION#*x}"
  WIDTH=$(round64 "$WIDTH"); HEIGHT=$(round64 "$HEIGHT")
else
  SHORT=$([[ "$HQ" -eq 1 ]] && echo "$SHORT_HQ" || echo "$SHORT_LOW")
  AW="${ASPECT%:*}"; AH="${ASPECT#*:}"
  if awk -v a="$AW" -v b="$AH" 'BEGIN{exit !(a>=b)}'; then
    # landscape / square: short side is height
    HEIGHT=$(round64 "$SHORT")
    WIDTH=$(round64 "$(awk -v s="$SHORT" -v a="$AW" -v b="$AH" 'BEGIN{print s*a/b}')")
  else
    # portrait: short side is width
    WIDTH=$(round64 "$SHORT")
    HEIGHT=$(round64 "$(awk -v s="$SHORT" -v a="$AW" -v b="$AH" 'BEGIN{print s*b/a}')")
  fi
fi

# --- frame count: nearest 8k+1 ---
NUM_FRAMES=$(awk -v d="$DURATION" -v f="$FPS" 'BEGIN{ n=d*f; k=int((n-1)/8+0.5); if(k<1)k=1; print k*8+1 }')

[[ -z "$OUTPUT" ]] && OUTPUT="./video_$(date +%Y%m%d_%H%M%S).mp4"
mkdir -p "$(dirname "$OUTPUT")"

echo ">> create-video"
echo "   prompt    : $PROMPT"
echo "   image     : ${IMAGE_PATH:-none}${IMAGE_PATH:+ (frame=$IMAGE_FRAME strength=$IMAGE_STRENGTH${IMAGE_CRF:+ crf=$IMAGE_CRF})}"
echo "   resolution: ${WIDTH}x${HEIGHT}  (aspect ${ASPECT}, hq=$HQ)"
echo "   length    : ${DURATION}s @ ${FPS}fps -> ${NUM_FRAMES} frames"
echo "   seed=$SEED flash=$FLASH audio=$AUDIO offload=${OFFLOAD:-none} quantization=${QUANTIZATION:-bf16} lora=${LORA_PATH:-none} -> $OUTPUT"

# Always route through the skill launcher: it runs the vocoder on CPU (fast, full
# quality). --no-audio additionally skips the vocoder via LTX_NO_AUDIO.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[[ "$AUDIO" -eq 0 ]] && export LTX_NO_AUDIO=1

CMD=( "$PY" "$HERE/ltx_run.py"
  --distilled-checkpoint-path "$CKPT"
  --spatial-upsampler-path "$UPSAMPLER"
  --gemma-root "$GEMMA"
  --prompt "$PROMPT"
  --height "$HEIGHT" --width "$WIDTH"
  --num-frames "$NUM_FRAMES" --frame-rate "$FPS"
  --seed "$SEED"
  --output-path "$OUTPUT" )
[[ -n "$QUANTIZATION" ]] && CMD+=( --quantization "$QUANTIZATION" )
[[ -n "$IMAGE_PATH" ]] && CMD+=( --image "$IMAGE_PATH" "$IMAGE_FRAME" "$IMAGE_STRENGTH" )
[[ -n "$IMAGE_PATH" && -n "$IMAGE_CRF" ]] && CMD+=( "$IMAGE_CRF" )
[[ -n "$LORA_PATH" ]] && CMD+=( --lora "$LORA_PATH" "$LORA_STRENGTH" )
[[ -n "$STEPS" ]]   && CMD+=( --num-inference-steps "$STEPS" )
[[ -n "$OFFLOAD" ]] && CMD+=( --offload "$OFFLOAD" )

export PYTHONUTF8=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
[[ "$FLASH" -eq 1 ]] && export TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL=1

# MIOpen kernel selection. The VAE/upscaler use 3D convs; at high resolution MIOpen's
# default FIND would benchmark candidate kernels at runtime on each new shape, costing
# ~90s of pure search (e.g. a single 1080p frame's "decode" was 92s of FIND, 2s of actual
# conv). FIND_MODE=FAST uses the heuristic/immediate path instead — no search, ~2s decode
# even cold. (Do NOT use FIND_ENFORCE=3 / cudnn.benchmark: those force the slow search.)
# The persistent DB caches whatever it picks across runs.
export MIOPEN_FIND_MODE="${MIOPEN_FIND_MODE:-FAST}"
export MIOPEN_USER_DB_PATH="${MIOPEN_USER_DB_PATH:-$HOME/.cache/miopen-ltx}"
export MIOPEN_CUSTOM_CACHE_DIR="$MIOPEN_USER_DB_PATH"
mkdir -p "$MIOPEN_USER_DB_PATH"

cd "$LTX_DIR"
# Opt-in profiling: set LTX_ROCPROF_DIR to wrap the run in rocprofv3 (kernel trace +
# per-kernel stats). Adds overhead, so use a separate run, not for clean timings.
if [[ -n "${LTX_ROCPROF_DIR:-}" ]]; then
  mkdir -p "$LTX_ROCPROF_DIR"
  rocprofv3 --kernel-trace --stats --truncate-kernels -d "$LTX_ROCPROF_DIR" -- "${CMD[@]}"
else
  "${CMD[@]}"
fi
echo ">> done: $OUTPUT"
