#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

assert_contains() {
  local file="$1"
  local needle="$2"
  grep -Fq -- "$needle" "$file" || fail "expected $file to contain: $needle"
}

assert_not_contains() {
  local file="$1"
  local needle="$2"
  ! grep -Fq -- "$needle" "$file" || fail "expected $file to not contain: $needle"
}

run_with_fake_ltx() {
  local tmp="$1"
  shift
  local fake_ltx="$tmp/ltx"
  mkdir -p "$fake_ltx/.venv/bin" "$fake_ltx/models/ltx" "$fake_ltx/models/gemma-3-12b-it"
  touch "$fake_ltx/models/ltx/ltx-2.3-22b-distilled-1.1.safetensors"
  touch "$fake_ltx/models/ltx/ltx-2.3-spatial-upscaler-x2-1.1.safetensors"
  cat >"$fake_ltx/.venv/bin/python" <<'PY'
#!/usr/bin/env bash
{
  printf '%s\n' '---CALL---'
  printf '%s\n' "$@"
} >> "$FAKE_PY_ARGS"
if [[ "${FAKE_CREATE_VIDEO:-0}" == "1" ]]; then
  out=""; width=64; height=64; frames=121; fps=24; no_audio="${LTX_NO_AUDIO:-0}"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --output-path) out="$2"; shift 2;;
      --width) width="$2"; shift 2;;
      --height) height="$2"; shift 2;;
      --num-frames) frames="$2"; shift 2;;
      --frame-rate) fps="$2"; shift 2;;
      *) shift;;
    esac
  done
  if [[ -n "$out" ]]; then
    dur=$(awk -v n="$frames" -v f="$fps" 'BEGIN{printf "%.6f", n/f}')
    if [[ "$no_audio" == "1" ]]; then
      ffmpeg -nostdin -loglevel error -y -f lavfi -i "testsrc2=size=${width}x${height}:rate=${fps}:duration=${dur}" \
        -frames:v "$frames" -c:v libx264 -pix_fmt yuv420p "$out"
    else
      ffmpeg -nostdin -loglevel error -y -f lavfi -i "testsrc2=size=${width}x${height}:rate=${fps}:duration=${dur}" \
        -f lavfi -i "anullsrc=channel_layout=stereo:sample_rate=48000" -frames:v "$frames" -shortest \
        -c:v libx264 -pix_fmt yuv420p -c:a aac "$out"
    fi
  fi
fi
PY
  chmod +x "$fake_ltx/.venv/bin/python"
  LTX_DIR="$fake_ltx" "$SCRIPT_DIR/create_video.sh" "$@"
}

test_image_input_is_forwarded_to_ltx_pipeline() {
  local tmp image output args
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' RETURN
  image="$tmp/source photo.png"
  output="$tmp/out.mp4"
  args="$tmp/args.txt"
  : > "$image"

  FAKE_PY_ARGS="$args" run_with_fake_ltx "$tmp" \
    -p "make the subject wave at camera" \
    --image "$image" \
    -d 1 \
    --no-audio \
    -o "$output" >/tmp/create-video-test.log

  assert_contains "$args" "--image"
  assert_contains "$args" "$image"
  assert_contains "$args" "0"
  assert_contains "$args" "0.9"
}

test_missing_image_path_fails_before_generation() {
  local tmp missing output args log
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' RETURN
  missing="$tmp/does-not-exist.png"
  output="$tmp/out.mp4"
  args="$tmp/args.txt"
  log="$tmp/log.txt"

  if FAKE_PY_ARGS="$args" run_with_fake_ltx "$tmp" \
    -p "animate this" \
    --image "$missing" \
    -o "$output" >"$log" 2>&1; then
    fail "expected missing image path to fail"
  fi

  assert_contains "$log" "image not found"
  [[ ! -e "$args" ]] || fail "python should not run when image path is missing"
}

test_default_quantization_is_fp8_cast() {
  local tmp output args
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' RETURN
  output="$tmp/out.mp4"
  args="$tmp/args.txt"

  FAKE_PY_ARGS="$args" run_with_fake_ltx "$tmp" \
    -p "make a cat video" \
    --no-audio \
    -o "$output" >/tmp/create-video-test.log

  assert_contains "$args" "--quantization"
  assert_contains "$args" "fp8-cast"
}

test_bf16_omits_quantization_argument() {
  local tmp output args log
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' RETURN
  output="$tmp/out.mp4"
  args="$tmp/args.txt"
  log="$tmp/log.txt"

  FAKE_PY_ARGS="$args" run_with_fake_ltx "$tmp" \
    -p "make a cat video" \
    --bf16 \
    --no-audio \
    -o "$output" >"$log"

  assert_not_contains "$args" "--quantization"
  assert_contains "$log" "quantization=bf16"
}

test_long_clips_default_to_smooth_multikeyframe_chunks() {
  local tmp output args log image_count
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' RETURN
  output="$tmp/out.mp4"
  args="$tmp/args.txt"
  log="$tmp/log.txt"

  FAKE_CREATE_VIDEO=1 FAKE_PY_ARGS="$args" run_with_fake_ltx "$tmp" \
    -p "make a long cat video" \
    -d 6 \
    -r 64x64 \
    --no-audio \
    -o "$output" >"$log"

  assert_contains "$log" "smooth segments"
  assert_contains "$log" "multi-keyframe"
  image_count=$(grep -Fc -- "--image" "$args")
  [[ "$image_count" -ge 4 ]] || fail "expected smooth continuation to pass at least 4 --image keyframes, got $image_count"
  assert_contains "$args" "0.95"
  [[ -s "$output" ]] || fail "expected smooth chunk output video to exist"
}

test_fast_chunks_keeps_legacy_single_frame_continuation() {
  local tmp output args log image_count
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' RETURN
  output="$tmp/out.mp4"
  args="$tmp/args.txt"
  log="$tmp/log.txt"

  FAKE_CREATE_VIDEO=1 FAKE_PY_ARGS="$args" run_with_fake_ltx "$tmp" \
    -p "make a long cat video" \
    -d 6 \
    -r 64x64 \
    --fast-chunks \
    --no-audio \
    -o "$output" >"$log"

  assert_contains "$log" "fast segments"
  image_count=$(grep -Fc -- "--image" "$args")
  [[ "$image_count" -eq 1 ]] || fail "expected fast continuation to pass exactly one --image, got $image_count"
  [[ -s "$output" ]] || fail "expected fast chunk output video to exist"
}

test_image_input_is_forwarded_to_ltx_pipeline
test_missing_image_path_fails_before_generation
test_default_quantization_is_fp8_cast
test_bf16_omits_quantization_argument
test_long_clips_default_to_smooth_multikeyframe_chunks
test_fast_chunks_keeps_legacy_single_frame_continuation
echo "OK: create_video.sh CLI tests passed"
