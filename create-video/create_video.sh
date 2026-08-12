#!/usr/bin/env bash
# create-video — MiniMax H3 synchronized audio-video on local ROCm through ComfyUI.
set -euo pipefail

COMFY_DIR="${COMFY_DIR:-$HOME/src/ComfyUI}"
MODEL="minimax-h3"
PROMPT=""
IMAGE_PATH=""
DURATION=5
FPS=24
ASPECT="16:9"
RESOLUTION=""
SPATIAL_EXPLICIT=0
HQ=0
SEED="$RANDOM"
STEPS=""
TURBO=1
AUDIO=1
OUTPUT=""

usage() {
  cat <<'EOF'
create-video — generate synchronized audio-video with MiniMax H3 on local ROCm.

Usage:
  create_video.sh -p "PROMPT" [options]
  create_video.sh -p "PROMPT" --image first-frame.png [options]

Options:
      --model MODEL     minimax-h3|minimax|h3 (optional compatibility selector).
  -p, --prompt TEXT     Observable video, environment, and sound description (required).
  -i, --image PATH      Optional first-frame image for H3 FL2VA image-to-video.
  -d, --duration SEC    Single-shot duration, 3–5 seconds recommended (default: 5).
      --fps N           Native frame rate; MiniMax H3 requires 24 (default: 24).
  -a, --aspect W:H      Aspect ratio when no resolution is given (default: 16:9).
  -r, --resolution WxH  Explicit dimensions, snapped to multiples of 32.
      --hq              Use a 576-pixel short side instead of the tuned 480-pixel default.
  -o, --output PATH     Output MP4 (default: ./video_<timestamp>.mp4).
      --seed N          Random seed (default: random).
      --steps N         Override denoise steps.
      --turbo           Turbo v4 sampler, normally 6–8 steps (default).
      --no-turbo        Reference sampler, normally 20 steps.
      --audio           Preserve native synchronized 32 kHz stereo audio (default).
      --no-audio        Strip audio from the generated MP4.
  -h, --help            Show this help.

The tuned default is 864x480, about 5.17 seconds (124 valid 17k+5 frames),
24 fps, Turbo 6 steps, with native synchronized stereo audio. For a requested
video longer than one reliable shot, plan ordered 3–5 second H3 segments as
described in SKILL.md, then chain them using motion context or endpoint frames.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --model) MODEL="$2"; shift 2 ;;
    -p|--prompt) PROMPT="$2"; shift 2 ;;
    -i|--image) IMAGE_PATH="$2"; shift 2 ;;
    -d|--duration) DURATION="$2"; shift 2 ;;
    --fps) FPS="$2"; shift 2 ;;
    -a|--aspect) ASPECT="$2"; SPATIAL_EXPLICIT=1; shift 2 ;;
    -r|--resolution) RESOLUTION="$2"; SPATIAL_EXPLICIT=1; shift 2 ;;
    --hq) HQ=1; SPATIAL_EXPLICIT=1; shift ;;
    -o|--output) OUTPUT="$2"; shift 2 ;;
    --seed) SEED="$2"; shift 2 ;;
    --steps) STEPS="$2"; shift 2 ;;
    --turbo) TURBO=1; shift ;;
    --no-turbo) TURBO=0; shift ;;
    --audio) AUDIO=1; shift ;;
    --no-audio) AUDIO=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 1 ;;
  esac
done

[[ -n "$PROMPT" ]] || { echo "ERROR: --prompt is required." >&2; usage; exit 1; }
case "$MODEL" in
  minimax-h3|minimax|h3) MODEL="minimax-h3" ;;
  *) echo "ERROR: create-video only supports minimax-h3." >&2; exit 1 ;;
esac
[[ "$FPS" == "24" ]] || { echo "ERROR: MiniMax H3 requires native 24 fps." >&2; exit 1; }
awk -v d="$DURATION" 'BEGIN{exit !(d>5.2)}' && {
  echo "ERROR: One MiniMax H3 shot is limited to about five seconds; use ordered 3–5 second H3 segments." >&2
  exit 1
}
awk -v d="$DURATION" 'BEGIN{exit !(d<=0)}' && { echo "ERROR: --duration must be positive." >&2; exit 1; }
[[ -z "$IMAGE_PATH" || -f "$IMAGE_PATH" ]] || { echo "ERROR: image not found: $IMAGE_PATH" >&2; exit 1; }
[[ -x "$COMFY_DIR/.venv/bin/python" ]] || { echo "ERROR: ComfyUI Python not found: $COMFY_DIR/.venv/bin/python" >&2; exit 1; }
[[ -f "$COMFY_DIR/scripts/minimax_h3_generate.py" ]] || { echo "ERROR: MiniMax H3 CLI not found under $COMFY_DIR" >&2; exit 1; }

round_dim() {
  awk -v x="$1" 'BEGIN{v=int((x+16)/32)*32; if(v<32)v=32; print v}'
}

if [[ -n "$RESOLUTION" ]]; then
  [[ "$RESOLUTION" == *x* ]] || { echo "ERROR: --resolution must be WxH." >&2; exit 1; }
  WIDTH=$(round_dim "${RESOLUTION%x*}")
  HEIGHT=$(round_dim "${RESOLUTION#*x}")
elif [[ "$SPATIAL_EXPLICIT" -eq 0 ]]; then
  WIDTH=864
  HEIGHT=480
else
  SHORT=$([[ "$HQ" -eq 1 ]] && echo 576 || echo 480)
  AW="${ASPECT%:*}"; AH="${ASPECT#*:}"
  [[ "$ASPECT" == *:* ]] || { echo "ERROR: --aspect must be W:H." >&2; exit 1; }
  if awk -v a="$AW" -v b="$AH" 'BEGIN{exit !(a>=b)}'; then
    HEIGHT=$(round_dim "$SHORT")
    WIDTH=$(round_dim "$(awk -v s="$SHORT" -v a="$AW" -v b="$AH" 'BEGIN{print s*a/b}')")
  else
    WIDTH=$(round_dim "$SHORT")
    HEIGHT=$(round_dim "$(awk -v s="$SHORT" -v a="$AW" -v b="$AH" 'BEGIN{print s*b/a}')")
  fi
fi

[[ -n "$STEPS" ]] || { if [[ "$TURBO" -eq 1 ]]; then STEPS=6; else STEPS=20; fi; }
NUM_FRAMES=$(awk -v d="$DURATION" 'BEGIN{n=int(d*24+0.5); if(n<5)n=5; print n+((5-(n%17))%17)}')
[[ -n "$OUTPUT" ]] || OUTPUT="./video_$(date +%Y%m%d_%H%M%S).mp4"
mkdir -p "$(dirname "$OUTPUT")"
OUTPUT="$(realpath -m "$OUTPUT")"

echo ">> create-video model=minimax-h3"
echo "   prompt    : $PROMPT"
echo "   image     : ${IMAGE_PATH:-none}${IMAGE_PATH:+ (first-frame FL2VA)}"
echo "   resolution: ${WIDTH}x${HEIGHT}"
echo "   length    : ${DURATION}s @ 24fps -> ${NUM_FRAMES} valid 17k+5 frames"
echo "   seed=$SEED turbo=$TURBO steps=$STEPS native_audio=$AUDIO -> $OUTPUT"

if [[ "${MINIMAX_H3_SKIP_HEALTHCHECK:-0}" != "1" ]]; then
  SERVER="${MINIMAX_H3_SERVER:-http://127.0.0.1:8188}"
  if ! curl -fsS "$SERVER/system_stats" >/dev/null; then
    echo ">> starting comfyui.service"
    systemctl --user start comfyui.service
    ready=0
    for _ in $(seq 1 90); do
      if curl -fsS "$SERVER/system_stats" >/dev/null; then ready=1; break; fi
      sleep 2
    done
    [[ "$ready" -eq 1 ]] || { echo "ERROR: ComfyUI did not become healthy on port 8188." >&2; exit 1; }
  fi
fi

H3_LOG="$(mktemp)"
H3_PREFIX="video/minimax_h3_skill_$(date +%Y%m%d_%H%M%S)_${SEED}"
H3_CMD=(
  "$COMFY_DIR/.venv/bin/python" "$COMFY_DIR/scripts/minimax_h3_generate.py"
  --prompt "$PROMPT" --width "$WIDTH" --height "$HEIGHT" --seconds "$DURATION"
  --steps "$STEPS" --seed "$SEED" --prefix "$H3_PREFIX"
  --server "${MINIMAX_H3_SERVER:-http://127.0.0.1:8188}"
)
[[ -n "$IMAGE_PATH" ]] && H3_CMD+=(--image "$IMAGE_PATH")
if [[ "$TURBO" -eq 1 ]]; then H3_CMD+=(--turbo); else H3_CMD+=(--no-turbo); fi

if ! (cd "$COMFY_DIR" && "${H3_CMD[@]}") | tee "$H3_LOG"; then
  rm -f "$H3_LOG"
  echo "ERROR: MiniMax H3 generation failed." >&2
  exit 1
fi
GENERATED="$(grep -E '\.mp4$' "$H3_LOG" | tail -n 1)"
rm -f "$H3_LOG"
[[ -n "$GENERATED" && -s "$GENERATED" ]] || {
  echo "ERROR: MiniMax H3 completed without a readable MP4 path." >&2
  exit 1
}

if [[ "$AUDIO" -eq 1 ]]; then
  cp -- "$GENERATED" "$OUTPUT"
else
  ffmpeg -nostdin -loglevel error -y -i "$GENERATED" -map 0:v:0 -c copy -an "$OUTPUT"
fi
echo ">> done: $OUTPUT"
