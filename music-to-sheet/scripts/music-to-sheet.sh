#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 AUDIO OUTPUT_DIR [--title TITLE] [--bpm BPM] [--upload]" >&2
  exit 2
}

[[ $# -ge 2 ]] || usage
AUDIO=$(realpath "$1")
OUTPUT=$(realpath -m "$2")
shift 2
TITLE=$(basename "${AUDIO%.*}")
BPM=95
UPLOAD=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --title) [[ $# -ge 2 ]] || usage; TITLE=$2; shift 2 ;;
    --bpm) [[ $# -ge 2 ]] || usage; BPM=$2; shift 2 ;;
    --upload) UPLOAD=true; shift ;;
    *) usage ;;
  esac
done

[[ -f "$AUDIO" ]] || { echo "Audio not found: $AUDIO" >&2; exit 1; }
mkdir -p "$OUTPUT"
API=${MUSIC_TRANSCRIBER_API:-http://127.0.0.1:8789}
if ! curl -fsS "$API/health" | grep -q '"status":"ready"'; then
  systemctl --user start music-transcriber.service
  for _ in $(seq 1 60); do
    curl -fsS "$API/health" | grep -q '"status":"ready"' && break
    sleep 1
  done
fi

RESPONSE=$(mktemp)
trap 'rm -f "$RESPONSE"' EXIT
curl --max-time 900 -fsS -F "file=@$AUDIO" "$API/transcribe" > "$RESPONSE"
JOB_ID=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["job_id"])' "$RESPONSE")
for artifact in chords.json chords.csv chords.mid drums.json drums.mid; do
  curl -fsS "$API/jobs/$JOB_ID/$artifact" -o "$OUTPUT/$artifact"
done
EXT=${AUDIO##*.}
cp "$AUDIO" "$OUTPUT/song.$EXT"
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PYTHON=${MUSIC_TRANSCRIBER_PYTHON:-/home/chihmin/src/music-transcriber/.venv-adtof/bin/python}
DURATION=$(python3 -c 'import json,sys; print(max((x["end"] for x in json.load(open(sys.argv[1]))), default=0))' "$OUTPUT/chords.json")
python3 "$SCRIPT_DIR/generate_drum_score.py" \
  --drums "$OUTPUT/drums.json" --output "$OUTPUT/drum-score.musicxml" \
  --title "$TITLE" --bpm "$BPM" --duration "$DURATION"
"$PYTHON" "$SCRIPT_DIR/render_drum_score.py" \
  --musicxml "$OUTPUT/drum-score.musicxml" --output-dir "$OUTPUT/drum-score" \
  --pdf "$OUTPUT/drum-score.pdf"
python3 "$SCRIPT_DIR/render_sheet.py" \
  --chords "$OUTPUT/chords.json" \
  --drums "$OUTPUT/drums.json" \
  --output "$OUTPUT/index.html" \
  --title "$TITLE" \
  --bpm "$BPM" \
  --audio-relative "song.$EXT"

printf 'HTML: %s\n' "$OUTPUT/index.html"
if $UPLOAD; then
  "$HOME/.pi/agent/skills/upload-html/scripts/upload-html.sh" "$OUTPUT"
fi
