#!/usr/bin/env bash
set -euo pipefail

skill_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
converter="$skill_dir/scripts/webm-to-mp4.sh"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

source_webm="$tmp_dir/workflow.webm"
output_mp4="$tmp_dir/workflow.mp4"

ffmpeg -hide_banner -loglevel error -y \
  -f lavfi -i 'color=c=#123456:s=390x844:r=24' \
  -t 1 -an -c:v libvpx-vp9 "$source_webm"

"$converter" "$source_webm" "$output_mp4"

[[ -s "$output_mp4" ]]
metadata="$(ffprobe -v error -select_streams v:0 \
  -show_entries stream=codec_name,pix_fmt,width,height \
  -of csv=p=0 "$output_mp4")"
[[ "$metadata" == "h264,390,844,yuv420p" ]]

for valid_crf in 0 08 51; do
  MP4_CRF="$valid_crf" "$converter" "$source_webm" "$tmp_dir/crf-$valid_crf.mp4" >/dev/null
  [[ -s "$tmp_dir/crf-$valid_crf.mp4" ]]
done
for invalid_crf in 052 999; do
  if MP4_CRF="$invalid_crf" "$converter" "$source_webm" "$tmp_dir/crf-$invalid_crf.mp4" \
    >"$tmp_dir/stdout" 2>"$tmp_dir/stderr"; then
    echo "expected MP4_CRF=$invalid_crf to fail" >&2
    exit 1
  fi
  grep -q 'MP4_CRF must be an integer from 0 to 51' "$tmp_dir/stderr"
done

if "$converter" "$tmp_dir/missing.webm" "$tmp_dir/missing.mp4" \
  >"$tmp_dir/stdout" 2>"$tmp_dir/stderr"; then
  echo "expected a missing input to fail" >&2
  exit 1
fi
grep -q 'Input video not found' "$tmp_dir/stderr"

directory_output="$tmp_dir/directory.mp4"
mkdir "$directory_output"
if "$converter" "$source_webm" "$directory_output" \
  >"$tmp_dir/stdout" 2>"$tmp_dir/stderr"; then
  echo "expected a directory output path to fail" >&2
  exit 1
fi
grep -q 'Output path is a directory' "$tmp_dir/stderr"
[[ -z "$(find "$directory_output" -mindepth 1 -print -quit)" ]]

(
  cd "$tmp_dir"
  "$converter" workflow.webm -leading-dash.mp4 >/dev/null
  [[ -s ./-leading-dash.mp4 ]]
)

printf '%s\n' 'keep-existing-output' > "$tmp_dir/existing.mp4"
printf '%s\n' 'not a video' > "$tmp_dir/corrupt.webm"
if "$converter" "$tmp_dir/corrupt.webm" "$tmp_dir/existing.mp4" \
  >"$tmp_dir/stdout" 2>"$tmp_dir/stderr"; then
  echo "expected a corrupt input to fail" >&2
  exit 1
fi
[[ "$(<"$tmp_dir/existing.mp4")" == 'keep-existing-output' ]]

[[ -z "$(find "$tmp_dir" -maxdepth 1 -type d -name '.webm-to-mp4.*' -print -quit)" ]]

echo "webm-to-mp4 tests passed"
