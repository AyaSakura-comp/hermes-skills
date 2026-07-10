#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 /path/to/audio.[ogg|wav|mp3|m4a|webm|flac|aac|opus]" >&2
  exit 2
fi

AUDIO_PATH="$1"
ASR_URL="${VOICE_ASR_URL:-http://127.0.0.1:8025}"

if [[ ! -f "$AUDIO_PATH" ]]; then
  echo "Audio file not found: $AUDIO_PATH" >&2
  exit 1
fi

curl -fsS -F "file=@${AUDIO_PATH}" "${ASR_URL%/}/transcribe" | python3 -m json.tool
