#!/usr/bin/env bash
# restyle_music_ac.sh — Restyle a song using AudioCraft MusicGen-Style + stem separation.
#
# Pipeline:
#   1. Separate vocals + instrumental (audio-separator, UVR-MDX-NET on GPU)
#   2. Feed instrumental to MusicGen-Style as style reference, target style as text
#   3. Generate new instrumental in target style
#   4. Mix original vocals back over the generated instrumental
#
# Usage:
#   ./restyle_music_ac.sh -i song.mp3 -s "lofi jazz, mellow Rhodes piano" -o lofi.mp3
#   ./restyle_music_ac.sh -i song.wav -s "和樂器 band: shamisen, koto, taiko" \
#                         -o wagaku.mp3 --duration 30 --music_gain 1.5
#   # Also accepts URLs:
#   ./restyle_music_ac.sh -i "https://youtu.be/XXXX" -s "city pop" -o citypop.mp3
#
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$SKILL_DIR/restyle_ac.py"

IN=""; STYLE=""; OUT="./restyled_ac.mp3"; DURATION=15; CFG=3.0; TOPK=250; TEMP=1.0
EXCERPT=3.0; VOC_GAIN=1.0; MUSIC_GAIN=1.5; LOUDNESS=-13; SEP_DIR="$HOME/src/audio-separator"
VERBOSE=0

usage() { grep '^#' "$0" | sed 's/^# \{0,1\}//' | head -30; exit 1; }

while getopts "i:s:o:d:c:t:T:x:V:M:N:se:vh" opt; do
  case "$opt" in
    i) IN="$OPTARG" ;;
    s) STYLE="$OPTARG" ;;
    o) OUT="$OPTARG" ;;
    d) DURATION="$OPTARG" ;;
    c) CFG="$OPTARG" ;;
    t) TOPK="$OPTARG" ;;
    T) TEMP="$OPTARG" ;;
    x) EXCERPT="$OPTARG" ;;
    V) VOC_GAIN="$OPTARG" ;;
    M) MUSIC_GAIN="$OPTARG" ;;
    N) LOUDNESS="$OPTARG" ;;
    s) SEP_DIR="$OPTARG" ;;
    v) VERBOSE=1 ;;
    h|*) usage ;;
  esac
done

[[ -z "$IN"    ]] && { echo "ERROR: -i input (audio file or URL) required"; usage; }
[[ -z "$STYLE" ]] && { echo "ERROR: -s style description required"; usage; }
[[ -f "$PY"    ]] || { echo "ERROR: restyle_ac.py not found at $PY"; exit 1; }
command -v ffmpeg >/dev/null || { echo "ERROR: ffmpeg required"; exit 1; }

# -i may be a URL — check yt-dlp availability
if [[ "$IN" =~ ^https?:// ]]; then
  command -v yt-dlp >/dev/null || { echo "ERROR: -i is a URL but yt-dlp is not installed"; exit 1; }
fi

echo "[restyle_ac] input:    $IN"
echo "[restyle_ac] style:     $STYLE"
echo "[restyle_ac] output:    $OUT"
echo "[restyle_ac] duration:  ${DURATION}s"
echo "[restyle_ac] cfg:       $CFG"
echo "[restyle_ac] excerpt:   ${EXCERPT}s"
echo "[restyle_ac] vocal_gain:$VOC_GAIN"
echo "[restyle_ac] music_gain:$MUSIC_GAIN"

PY_ARGS=(--input "$IN" --style "$STYLE" --output "$OUT"
         --duration "$DURATION" --cfg "$CFG" --topk "$TOPK" --temp "$TEMP"
         --excerpt "$EXCERPT"
         --voc_gain "$VOC_GAIN" --music_gain "$MUSIC_GAIN" --loudness "$LOUDNESS"
         --sep_dir "$SEP_DIR")

[[ "$VERBOSE" == 1 ]] && PY_ARGS+=(--verbose)

# Run Python script
python3 "$PY" "${PY_ARGS[@]}"
