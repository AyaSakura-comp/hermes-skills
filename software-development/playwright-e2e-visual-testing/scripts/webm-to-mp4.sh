#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: webm-to-mp4.sh INPUT.webm OUTPUT.mp4" >&2
}

(($# == 2)) || { usage; exit 2; }
input="$1"
output="$2"

[[ -f "$input" ]] || { echo "Input video not found: $input" >&2; exit 2; }
[[ "${output,,}" == *.mp4 ]] || { echo "Output path must end in .mp4: $output" >&2; exit 2; }
[[ ! -d "$output" ]] || { echo "Output path is a directory: $output" >&2; exit 2; }
command -v ffmpeg >/dev/null 2>&1 || { echo "ffmpeg is required" >&2; exit 127; }
command -v ffprobe >/dev/null 2>&1 || { echo "ffprobe is required" >&2; exit 127; }

crf="${MP4_CRF:-20}"
[[ "$crf" =~ ^[0-9]+$ ]] || {
  echo "MP4_CRF must be an integer from 0 to 51" >&2
  exit 2
}
crf_decimal=$((10#$crf))
((crf_decimal <= 51)) || {
  echo "MP4_CRF must be an integer from 0 to 51" >&2
  exit 2
}
crf="$crf_decimal"

output_dir="$(dirname -- "$output")"
mkdir -p -- "$output_dir"
tmp_dir="$(mktemp -d -- "$output_dir/.webm-to-mp4.XXXXXX")"
tmp_output="$tmp_dir/output.mp4"
trap 'rm -rf -- "$tmp_dir"' EXIT

ffmpeg -hide_banner -loglevel error -y \
  -i "$input" \
  -map 0:v:0 \
  -c:v libx264 \
  -preset medium \
  -crf "$crf" \
  -pix_fmt yuv420p \
  -movflags +faststart \
  -an \
  "$tmp_output"

codec=""
pix_fmt=""
width=""
height=""
duration=""
size=""
while IFS='=' read -r key value; do
  case "$key" in
    codec_name) codec="$value" ;;
    pix_fmt) pix_fmt="$value" ;;
    width) width="$value" ;;
    height) height="$value" ;;
    duration) duration="$value" ;;
    size) size="$value" ;;
  esac
done < <(
  ffprobe -v error -select_streams v:0 \
    -show_entries stream=codec_name,pix_fmt,width,height \
    -show_entries format=duration,size \
    -of default=noprint_wrappers=1 "$tmp_output"
)

[[ "$codec" == "h264" ]] || { echo "Unexpected MP4 codec: $codec" >&2; exit 1; }
[[ "$pix_fmt" == "yuv420p" ]] || { echo "Unexpected MP4 pixel format: $pix_fmt" >&2; exit 1; }
[[ "$width" =~ ^[1-9][0-9]*$ && "$height" =~ ^[1-9][0-9]*$ ]] || {
  echo "Invalid MP4 dimensions: ${width}x${height}" >&2
  exit 1
}
[[ "$size" =~ ^[1-9][0-9]*$ ]] || { echo "Invalid MP4 size: $size" >&2; exit 1; }
awk -v duration="$duration" 'BEGIN { exit !(duration + 0 > 0) }' || {
  echo "Invalid MP4 duration: $duration" >&2
  exit 1
}

mv -fT -- "$tmp_output" "$output"
rmdir -- "$tmp_dir"
trap - EXIT
printf '%s\n' "$output"
