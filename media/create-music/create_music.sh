#!/usr/bin/env bash
# create_music.sh — generate a song with HeartMuLa (heartlib) on ROCm GPU.
# Flexible genre (tags) + lyrics, one command.
#
# Usage:
#   ./create_music.sh -t "piano,happy,lofi" -l ./my_lyrics.txt -o song.mp3
#   ./create_music.sh -t "rock,energetic" -L "[Verse]\nbla bla\n[Chorus]\nyeah" -d 60
#
# Options:
#   -t TAGS     Genre/style tags, comma-separated (e.g. "piano,happy"). Default: keep assets/tags.txt
#   -l FILE     Lyrics file path (structured with [Intro]/[Verse]/[Chorus]/[Bridge] sections)
#   -L TEXT     Inline lyrics string (use \n for line breaks). Overrides -l.
#   -o OUT      Output audio path (.mp3/.wav/.flac). Default: ./assets/output.mp3
#   -d SEC      Max song length in seconds. Default: 240 (full ~4min song)
#   -T TEMP     Sampling temperature (default 1.0)
#   -c CFG      Classifier-free guidance scale (default 1.5)
#   -k TOPK     Top-k sampling (default 50)
#   -Q LEVEL    Quality preset: high (default) = 320k mp3 + codec_steps 16;
#               low = 128k mp3 + codec_steps 8 (faster, smaller — drafts).
#   -q STEPS    Override HeartCodec decode steps (higher = better fidelity, slower).
#               For max quality also use a lossless output ext (.flac/.wav) instead of .mp3.
#   -S          Clarity-repair post-processing: run the generated song through audio-separator
#               (UVR-MDX-NET-Inst_HQ_4 on GPU), splitting into vocals+instrumental and summing
#               the cleaned stems back -> a subtle de-noise / de-mud pass. Keeps vocals.
#   -C          Compile MuLa model using TorchDynamo for accelerated generation
#               (recommended for long runs, e.g., > 3 minutes).
#
# Requires: heartlib deployed at this dir with .venv (torch 2.11+rocm7.2), ./ckpt models.
# Notes: runs on GPU with --lazy_load (peaks ~6.2GB). Generation is ~RTF 1 (a 4min song ≈ a few min).
set -euo pipefail

# Script lives in the skill folder; the heartlib install (venv, ./ckpt, ./examples) is elsewhere.
HERE="${HEARTLIB_DIR:-$HOME/src/heartlib}"
PY="$HERE/.venv/bin/python"
[ -x "$PY" ] || { echo "ERROR: heartlib venv not found at $HERE/.venv (set HEARTLIB_DIR)"; exit 1; }
TAGS=""; LYRICS_FILE=""; LYRICS_TEXT=""; OUT="./assets/output.mp3"
DUR=240; TEMP=1.0; CFG=1.5; TOPK=50; CSTEPS=""; QUALITY="high"; MP3_BR=""; CLARITY=0; COMPILE=0

while getopts "t:l:L:o:d:T:c:k:q:Q:SC" opt; do
  case "$opt" in
    t) TAGS="$OPTARG" ;; l) LYRICS_FILE="$OPTARG" ;; L) LYRICS_TEXT="$OPTARG" ;;
    o) OUT="$OPTARG" ;; d) DUR="$OPTARG" ;; T) TEMP="$OPTARG" ;;
    c) CFG="$OPTARG" ;; k) TOPK="$OPTARG" ;; q) CSTEPS="$OPTARG" ;;
    Q) QUALITY="$OPTARG" ;; S) CLARITY=1 ;; C) COMPILE=1 ;;
    *) exit 2 ;;
  esac
done

# Quality preset (default high). -q (codec steps) overrides the preset's step count.
case "${QUALITY,,}" in
  high) MP3_BR=320k; CSTEPS="${CSTEPS:-16}" ;;
  low)  MP3_BR=128k; CSTEPS="${CSTEPS:-8}"  ;;
  *) echo "ERROR: -Q must be 'high' or 'low'"; exit 2 ;;
esac

cd "$HERE"
export PYTHONUTF8=1
export TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL=1

# Resolve tags file
TAGS_PATH="./assets/tags.txt"
if [ -n "$TAGS" ]; then
  TAGS_PATH="$(mktemp /tmp/cm_tags.XXXX.txt)"
  printf '%s' "$TAGS" > "$TAGS_PATH"
  echo "[tags] $TAGS"
fi

# Resolve lyrics file
LYRICS_PATH="./assets/lyrics.txt"
if [ -n "$LYRICS_TEXT" ]; then
  LYRICS_PATH="$(mktemp /tmp/cm_lyrics.XXXX.txt)"
  printf '%b\n' "$LYRICS_TEXT" > "$LYRICS_PATH"
  echo "[lyrics] inline ($(wc -l < "$LYRICS_PATH") lines)"
elif [ -n "$LYRICS_FILE" ]; then
  LYRICS_PATH="$LYRICS_FILE"
  echo "[lyrics] $LYRICS_FILE"
fi

DUR_MS=$(( DUR * 1000 ))

# For .mp3 output: generate lossless wav from the model, then encode at the preset bitrate
# (avoids soundfile's low default mp3 bitrate / double-lossy). .wav/.flac pass through.
case "${OUT,,}" in
  *.mp3) GEN_OUT="$(mktemp /tmp/cm_gen.XXXX.wav)" ;;
  *)     GEN_OUT="$OUT" ;;
esac
COMPILE_FLAG="false"
if [ "$COMPILE" = 1 ]; then
  COMPILE_FLAG="true"
fi

echo "[gen] quality=$QUALITY (mp3 $MP3_BR, codec_steps=$CSTEPS, compile=$COMPILE_FLAG) len=${DUR}s -> $OUT"

"$PY" ./examples/run_music_generation.py \
  --model_path=./ckpt --version="3B" --lazy_load false --codec_dtype bfloat16 \
  --tags "$TAGS_PATH" --lyrics "$LYRICS_PATH" \
  --max_audio_length_ms "$DUR_MS" \
  --temperature "$TEMP" --cfg_scale "$CFG" --topk "$TOPK" \
  --codec_steps "$CSTEPS" --compile "$COMPILE_FLAG" \
  --save_path "$GEN_OUT" 2>&1 | grep -aviE "MIOpen|IsEnoughWorkspace" | tail -5

if [ "$GEN_OUT" != "$OUT" ]; then
  ffmpeg -y -i "$GEN_OUT" -b:a "$MP3_BR" "$OUT" >/dev/null 2>&1 && rm -f "$GEN_OUT"
  echo "[encode] ${MP3_BR} mp3"
fi

# Optional clarity-repair post-processing via audio-separator (UVR-MDX-NET) on GPU.
if [ "$CLARITY" = 1 ]; then
  CLARITY_SH="${AUDIO_SEPARATOR_DIR:-$HOME/src/audio-separator}/enhance_clarity.sh"
  if [ -x "$CLARITY_SH" ]; then
    echo "[clarity] post-processing $OUT via audio-separator..."
    CTMP="$(mktemp "/tmp/cm_clarity.XXXX.${OUT##*.}")"
    if "$CLARITY_SH" -i "$OUT" -o "$CTMP"; then
      mv -f "$CTMP" "$OUT"
    else
      echo "[clarity] WARN: clarity repair failed, keeping un-processed song"; rm -f "$CTMP"
    fi
  else
    echo "[clarity] WARN: $CLARITY_SH not found/executable, skipping clarity repair"
  fi
fi

echo "DONE -> $OUT"
