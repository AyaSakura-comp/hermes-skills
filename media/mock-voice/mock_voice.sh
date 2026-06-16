#!/usr/bin/env bash
# mock_voice.sh — one-shot YouTube voice clone with OmniVoice (ROCm GPU).
# Pipeline: yt-dlp download -> gemma scan for transcribable window -> ffmpeg trim -> OmniVoice TTS.
#
# Usage:
#   ./mock_voice.sh -u <youtube_url> -t "<text to speak>" -l <lang> [options]
#
# Options:
#   -u URL        YouTube URL (required)
#   -t TEXT       Text to synthesize (required)
#   -l LANG       Language name/code (REQUIRED — agent must detect and pass, e.g. ja/zh/en/ko)
#   -o OUT        Output wav (default: results_omni/mock.wav)
#   -s SEC        Force trim start second (skip scan; default: auto-scan)
#   -d SEC        Trim duration of the reference clip (default: 8)
#   -n STEP       Diffusion steps, 16 fast / 32 quality (default: 32)
#   -r TEXT       Override ref_text (skip gemma transcription entirely)
#
# Requires: yt-dlp, ffmpeg, Ollama running with gemma4:e2b, OmniVoice .venv.
# Note: -l is REQUIRED. The agent (caller) must detect the language from -t and pass it.
#       Script no longer auto-detects language (bash regex has no reliable Unicode support).
#
# Scan mode (default): After downloading, tries samples every 15s. Picks the first window
# where gemma4:e2b produces non-empty text. Falls back to start=0 if no window works.
set -euo pipefail

# SCRIPT_DIR = skill folder (holds ref_transcribe.py). HERE = OmniVoice install (venv, omnivoice
# module, asset_mock/results_omni). They differ now that scripts live in the skill folder.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERE="${OMNIVOICE_DIR:-$HOME/src/OmniVoice}"
PY="$HERE/.venv/bin/python"
[ -x "$PY" ] || { echo "ERROR: OmniVoice venv not found at $HERE/.venv (set OMNIVOICE_DIR)"; exit 1; }
LANG_NAME=""; OUT="results_omni/mock.wav"; SS=""; DUR=8; NSTEP=32; REFTXT=""
URL=""; TEXT=""

while getopts "u:t:l:o:s:d:n:r:" opt; do
  case "$opt" in
    u) URL="$OPTARG" ;; t) TEXT="$OPTARG" ;; l) LANG_NAME="$OPTARG" ;;
    o) OUT="$OPTARG" ;; s) SS="$OPTARG" ;; d) DUR="$OPTARG" ;;
    n) NSTEP="$OPTARG" ;; r) REFTXT="$OPTARG" ;;
    *) exit 2 ;;
  esac
done
[ -z "$URL" ] && { echo "ERROR: -u URL required"; exit 2; }
[ -z "$TEXT" ] && { echo "ERROR: -t TEXT required"; exit 2; }

cd "$HERE"
export PYTHONUTF8=1
mkdir -p asset_mock results_omni
rm -f asset_mock/ref.wav asset_mock/ref_16k.wav

[ -z "$LANG_NAME" ] && { echo "ERROR: -l LANG required (agent must detect and pass)"; exit 2; }

echo "[1/4] Downloading audio ..."
yt-dlp -f bestaudio --extract-audio --audio-format wav \
  --output "asset_mock/ref.%(ext)s" --no-playlist "$URL" >/dev/null 2>&1

echo "[2/4] Finding transcribable window ..."
DUR_SEC=$(ffprobe -v quiet -show_entries format=duration \
  -of default=noprint_wrappers=1:nokey=1 asset_mock/ref.wav)
MAX_SEC=${DUR_SEC%.*}

# Use user-specified -s to skip scan, otherwise auto-scan
if [ -n "$SS" ]; then
  echo "      Using forced start=${SS}s (scan skipped)"
  REF_START=$SS
else
  REF_START=""
  INTERVAL=15
  for start in $(seq 0 "$INTERVAL" "$MAX_SEC"); do
    ffmpeg -y -i asset_mock/ref.wav -ss "$start" -t 6 \
      -ar 16000 -ac 1 -c:a pcm_s16le /tmp/ref_probe.wav 2>/dev/null
    PROBE_RT=$("$PY" "$SCRIPT_DIR/ref_transcribe.py" /tmp/ref_probe.wav 2>/dev/null)
    if [ -n "$PROBE_RT" ]; then
      echo "      Found at start=${start}s: $PROBE_RT"
      REF_START=$start
      break
    fi
    echo "      start=${start}s: empty — trying next"
  done
  # Fallback
  if [ -z "$REF_START" ]; then
    echo "      WARNING: no transcribable window — using start=0 as fallback"
    REF_START=0
  fi
fi

echo "[3/4] Trimming ref (start=${REF_START}s dur=${DUR}s, 16kHz mono) ..."
ffmpeg -y -i asset_mock/ref.wav -ss "$REF_START" -t "$DUR" -ar 16000 -ac 1 \
  -c:a pcm_s16le asset_mock/ref_16k.wav >/dev/null 2>&1

if [ -n "$REFTXT" ]; then
  echo "[4/4] Using provided ref_text: $REFTXT"
  RT="$REFTXT"
elif [ -n "${REF_FORCE_RT:-}" ]; then
  RT="$REF_FORCE_RT"
else
  echo "[4/4] Transcribing ref via gemma4:e2b (Ollama) ..."
  RT=$("$PY" "$SCRIPT_DIR/ref_transcribe.py" asset_mock/ref_16k.wav)
  echo "      ref_text: $RT"
fi

echo "[5/4] Synthesizing with OmniVoice (GPU, num_step=$NSTEP) ..."
"$PY" -m omnivoice.cli.infer \
  --text "$TEXT" --language "$LANG_NAME" \
  --ref_audio asset_mock/ref_16k.wav --ref_text "$RT" \
  --num_step "$NSTEP" --output "$OUT" --device cuda 2>&1 \
  | grep -E "Saved to|Generating audio" || true

echo "DONE -> $OUT"
