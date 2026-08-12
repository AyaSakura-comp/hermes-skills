#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

fail() { echo "FAIL: $*" >&2; exit 1; }
assert_contains() { grep -Fq -- "$2" "$1" || fail "expected $1 to contain: $2"; }
assert_not_contains() { ! grep -Fiq -- "$2" "$1" || fail "expected $1 not to contain: $2"; }

setup_fake_h3() {
  local tmp="$1" fake="$tmp/ComfyUI"
  mkdir -p "$fake/.venv/bin" "$fake/scripts" "$fake/output/video"
  : > "$fake/scripts/minimax_h3_generate.py"
  cat >"$fake/.venv/bin/python" <<'PY'
#!/usr/bin/env bash
printf '%s\n' "$@" > "$FAKE_MINIMAX_ARGS"
out="$FAKE_MINIMAX_OUTPUT"
ffmpeg -nostdin -loglevel error -y \
  -f lavfi -i "testsrc2=size=64x64:rate=24:duration=1" \
  -f lavfi -i "anullsrc=channel_layout=stereo:sample_rate=32000" -shortest \
  -c:v libx264 -pix_fmt yuv420p -c:a aac "$out"
printf '%s\n' "$out"
PY
  chmod +x "$fake/.venv/bin/python"
}

run_fake_h3() {
  local tmp="$1"; shift
  COMFY_DIR="$tmp/ComfyUI" MINIMAX_H3_SKIP_HEALTHCHECK=1 \
    FAKE_MINIMAX_ARGS="$tmp/args.txt" \
    FAKE_MINIMAX_OUTPUT="$tmp/ComfyUI/output/video/fake.mp4" \
    "$SCRIPT_DIR/create_video.sh" "$@"
}

test_default_is_minimax_h3() {
  local tmp output args
  tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' RETURN
  setup_fake_h3 "$tmp"; output="$tmp/out.mp4"; args="$tmp/args.txt"
  run_fake_h3 "$tmp" -p "paper boat in rain" -o "$output" >"$tmp/log.txt"
  assert_contains "$args" "minimax_h3_generate.py"
  assert_contains "$args" "--width"
  assert_contains "$args" "864"
  assert_contains "$args" "--height"
  assert_contains "$args" "480"
  assert_contains "$args" "--seconds"
  assert_contains "$args" "5"
  assert_contains "$args" "--steps"
  assert_contains "$args" "6"
  assert_contains "$args" "--turbo"
  [[ -s "$output" ]] || fail "default MiniMax output was not created"
}

test_image_is_forwarded() {
  local tmp image output args
  tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' RETURN
  setup_fake_h3 "$tmp"; image="$tmp/first frame.png"; output="$tmp/out.mp4"; args="$tmp/args.txt"; : >"$image"
  run_fake_h3 "$tmp" --model minimax-h3 -p "wave" --image "$image" -o "$output" >"$tmp/log.txt"
  assert_contains "$args" "--image"
  assert_contains "$args" "$image"
}

test_missing_image_fails_before_generation() {
  local tmp log
  tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' RETURN
  setup_fake_h3 "$tmp"; log="$tmp/log.txt"
  if run_fake_h3 "$tmp" -p "wave" --image "$tmp/missing.png" -o "$tmp/out.mp4" >"$log" 2>&1; then
    fail "missing image should fail"
  fi
  assert_contains "$log" "image not found"
  [[ ! -e "$tmp/args.txt" ]] || fail "generator ran despite missing image"
}

test_reference_sampler_defaults_to_20_steps() {
  local tmp args
  tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' RETURN
  setup_fake_h3 "$tmp"; args="$tmp/args.txt"
  run_fake_h3 "$tmp" -p "wave" --no-turbo -o "$tmp/out.mp4" >"$tmp/log.txt"
  assert_contains "$args" "--no-turbo"
  assert_contains "$args" "20"
}

test_no_audio_strips_audio_stream() {
  local tmp output
  tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' RETURN
  setup_fake_h3 "$tmp"; output="$tmp/out.mp4"
  run_fake_h3 "$tmp" -p "silent wave" --no-audio -o "$output" >"$tmp/log.txt"
  [[ "$(ffprobe -v error -select_streams a -show_entries stream=index -of csv=p=0 "$output")" == "" ]] || fail "--no-audio retained audio"
}

test_other_backends_are_rejected() {
  local tmp log
  tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' RETURN
  setup_fake_h3 "$tmp"; log="$tmp/log.txt"
  if run_fake_h3 "$tmp" --model other -p "must fail" -o "$tmp/out.mp4" >"$log" 2>&1; then
    fail "an unsupported backend was accepted"
  fi
  assert_contains "$log" "only supports minimax-h3"
}

test_long_single_shot_is_rejected() {
  local tmp log
  tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' RETURN
  setup_fake_h3 "$tmp"; log="$tmp/log.txt"
  if run_fake_h3 "$tmp" -p "too long" -d 6 -o "$tmp/out.mp4" >"$log" 2>&1; then
    fail "unsupported long single shot was accepted"
  fi
  assert_contains "$log" "3–5 second H3 segments"
}

test_help_mentions_minimax_backend() {
  local tmp help
  tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' RETURN
  help="$tmp/help.txt"
  "$SCRIPT_DIR/create_video.sh" --help >"$help"
  assert_contains "$help" "MiniMax H3"
  assert_contains "$help" "minimax-h3|minimax|h3"
}

test_default_is_minimax_h3
test_image_is_forwarded
test_missing_image_fails_before_generation
test_reference_sampler_defaults_to_20_steps
test_no_audio_strips_audio_stream
test_other_backends_are_rejected
test_long_single_shot_is_rejected
test_help_mentions_minimax_backend
echo "OK: MiniMax-only create_video.sh CLI tests passed"
