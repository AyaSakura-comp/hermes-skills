#!/usr/bin/env bash
# restyle-music — change the style/genre of an existing song while keeping its melody.
# Uses ACE-Step 1.5 "cover" mode on the local AMD GPU (ROCm, gfx1151).
#
# Usage:
#   restyle_music.sh -i input.mp3 -s "lofi jazz, mellow piano" -o out.mp3
#   restyle_music.sh -i song.wav -s "traditional Japanese wagaku: shamisen, koto, taiko" \
#                    -S 0.5 -l ./lyrics.txt -o wagaku.mp3
#   # -i also accepts a YouTube/URL (yt-dlp grabs the audio first):
#   restyle_music.sh -i "https://youtu.be/XXXX" -k -s "lofi jazz, instrumental" -o out.mp3
#
# Keep the ORIGINAL singing voice (-k): cover mode re-synthesizes vocals too, so to truly
# keep the original voice we split the song into vocals + instrumental (audio-separator,
# UVR-MDX-NET on GPU), restyle ONLY the instrumental, then mix the original vocals back on top:
#   restyle_music.sh -i song.mp3 -s "lofi jazz, mellow Rhodes piano, brushed drums" -k -o lofi.mp3
#   (-V VOCAL_GAIN to balance the original voice against the new backing, default 1.0)
set -euo pipefail

ACE_ROOT="${ACE_ROOT:-$HOME/src/ACE-Step-1.5}"
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$ACE_ROOT/.venv/bin/python"
SEP_DIR="${AUDIO_SEPARATOR_DIR:-$HOME/src/audio-separator}"

# --- ROCm / gfx1151 env, filled in so this runs painlessly on this box ---------------------
# Critical: HSA_OVERRIDE_GFX_VERSION must be UNSET (repo defaults it to 11.0.0 -> GPU vanishes).
# MIOpen kernel cache is pinned under the skill's .cache so the ~JIT only happens once.
mkdir -p "$SKILL_DIR/.cache/miopen"
ACE_ENV=(env -u HSA_OVERRIDE_GFX_VERSION
  HIP_VISIBLE_DEVICES="${HIP_VISIBLE_DEVICES:-0}"
  MIOPEN_FIND_MODE=FAST
  MIOPEN_USER_DB_PATH="$SKILL_DIR/.cache/miopen"
  MIOPEN_CUSTOM_CACHE_DIR="$SKILL_DIR/.cache/miopen"
  PYTORCH_HIP_ALLOC_CONF="${PYTORCH_HIP_ALLOC_CONF:-expandable_segments:True}"
  TOKENIZERS_PARALLELISM=false
  ACESTEP_LM_BACKEND=pt
  ACESTEP_ROCM_DTYPE="${ACESTEP_ROCM_DTYPE:-float32}"
  ACE_ROOT="$ACE_ROOT")

IN=""; STYLE=""; OUT="./restyled.mp3"; STRENGTH="0.6"; STEPS="8"
LYRICS=""; LYRICS_INLINE=""; LANG="auto"; LM="acestep-5Hz-lm-0.6B"; BITRATE="256k"
KEEP_VOCALS=0; VOCAL_GAIN="1.0"

usage() { grep '^#' "$0" | sed 's/^# \{0,1\}//' | head -24; exit 1; }

while getopts "i:s:o:S:q:l:L:g:m:b:kV:h" opt; do
  case "$opt" in
    i) IN="$OPTARG" ;;
    s) STYLE="$OPTARG" ;;
    o) OUT="$OPTARG" ;;
    S) STRENGTH="$OPTARG" ;;
    q) STEPS="$OPTARG" ;;
    l) LYRICS="$OPTARG" ;;
    L) LYRICS_INLINE="$OPTARG" ;;
    g) LANG="$OPTARG" ;;
    m) LM="$OPTARG" ;;
    b) BITRATE="$OPTARG" ;;
    k) KEEP_VOCALS=1 ;;
    V) VOCAL_GAIN="$OPTARG" ;;
    h|*) usage ;;
  esac
done

[[ -z "$IN"    ]] && { echo "ERROR: -i input (audio file or URL) required"; usage; }
[[ -z "$STYLE" ]] && { echo "ERROR: -s style description required"; usage; }
[[ -x "$PY"    ]] || { echo "ERROR: ACE-Step venv not found at $PY (ACE_ROOT=$ACE_ROOT)"; exit 1; }
command -v ffmpeg >/dev/null || { echo "ERROR: ffmpeg required"; exit 1; }

# -i may be a URL (YouTube etc.) — yt-dlp grabs the audio first. Otherwise it's a local file.
IS_URL=0
[[ "$IN" =~ ^https?:// ]] && IS_URL=1
if [[ "$IS_URL" == 0 ]]; then
  [[ -f "$IN" ]] || { echo "ERROR: input not found: $IN"; exit 1; }
else
  command -v yt-dlp >/dev/null || { echo "ERROR: -i is a URL but yt-dlp is not installed"; exit 1; }
fi

# resolve lyrics: -L inline wins over -l file
LYRICS_TEXT=""
if [[ -n "$LYRICS_INLINE" ]]; then
  LYRICS_TEXT="$(printf '%b' "$LYRICS_INLINE")"
elif [[ -n "$LYRICS" ]]; then
  [[ -f "$LYRICS" ]] || { echo "ERROR: lyrics file not found: $LYRICS"; exit 1; }
  LYRICS_TEXT="$(cat "$LYRICS")"
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
SRC_WAV="$WORK/src.wav"

# Download from YouTube/URL first if -i was a link.
if [[ "$IS_URL" == 1 ]]; then
  echo "[restyle] downloading audio from URL with yt-dlp ..."
  yt-dlp -f bestaudio -x --audio-format wav --no-playlist \
    -o "$WORK/yt.%(ext)s" "$IN"
  IN="$(ls "$WORK"/yt.wav 2>/dev/null | head -1)"
  [[ -f "$IN" ]] || { echo "ERROR: yt-dlp produced no audio for $IN"; exit 1; }
fi

echo "[restyle] normalizing input -> 48kHz stereo wav ..."
ffmpeg -y -loglevel error -i "$IN" -ac 2 -ar 48000 "$SRC_WAV"

# --- keep-vocals: split off the original singing voice; restyle only the instrumental -------
ORIG_VOCALS=""; COVER_SRC="$SRC_WAV"
if [[ "$KEEP_VOCALS" == 1 ]]; then
  SEP="$SEP_DIR/.venv/bin/audio-separator"
  [[ -x "$SEP" ]] || { echo "ERROR: -k needs audio-separator at $SEP_DIR/.venv (set AUDIO_SEPARATOR_DIR)"; exit 1; }
  echo "[restyle] -k: separating vocals/instrumental on GPU (UVR-MDX-NET) ..."
  "${ACE_ENV[@]}" "$SEP" "$SRC_WAV" \
    --model_filename "UVR-MDX-NET-Inst_HQ_4.onnx" --model_file_dir "$SEP_DIR/models" \
    --output_dir "$WORK/stems" --output_format WAV \
    --mdx_segment_size 512 --mdx_overlap 0.85 --log_level INFO 2>&1 \
    | grep -aviE "MIOpen|IsEnoughWorkspace|UserWarning|warnings.warn|iB/s|it/s" | tail -6
  ORIG_VOCALS="$(ls "$WORK"/stems/*"(Vocals)"*.wav 2>/dev/null | head -1)"
  COVER_SRC="$(ls "$WORK"/stems/*"(Instrumental)"*.wav 2>/dev/null | head -1)"
  [[ -f "$ORIG_VOCALS" && -f "$COVER_SRC" ]] || { echo "ERROR: stem separation failed"; exit 1; }
  # restyle the instrumental only -> don't feed lyrics (keeps the cover purely instrumental)
  LYRICS_TEXT=""
  echo "[restyle] -k: original vocals preserved; restyling instrumental backing only."
fi

echo "[restyle] running ACE-Step cover on GPU (strength=$STRENGTH, steps=$STEPS) ..."
RAW_OUT="$("${ACE_ENV[@]}" \
  "$PY" "$SKILL_DIR/cover_runner.py" \
    --src "$COVER_SRC" --caption "$STYLE" --out-dir "$WORK/out" \
    --lyrics "$LYRICS_TEXT" --strength "$STRENGTH" --steps "$STEPS" \
    --language "$LANG" --lm "$LM" \
  | tee /dev/stderr | sed -n 's/^RESULT_WAV=//p' | tail -1)"

[[ -n "$RAW_OUT" && -f "$RAW_OUT" ]] || { echo "ERROR: generation produced no audio"; exit 1; }

# --- keep-vocals: mix the original voice back over the restyled instrumental ----------------
FINAL="$RAW_OUT"
if [[ "$KEEP_VOCALS" == 1 ]]; then
  echo "[restyle] -k: mixing original vocals (gain=$VOCAL_GAIN) over restyled instrumental ..."
  FINAL="$WORK/mixed.wav"
  ffmpeg -y -loglevel error -i "$ORIG_VOCALS" -i "$RAW_OUT" \
    -filter_complex "[0]volume=${VOCAL_GAIN}[v];[v][1]amix=inputs=2:duration=longest:normalize=0[a]" \
    -map "[a]" -ac 2 -ar 48000 "$FINAL"
fi

mkdir -p "$(dirname "$OUT")"
case "$OUT" in
  *.wav|*.flac) cp "$FINAL" "$OUT" ;;
  *)            ffmpeg -y -loglevel error -i "$FINAL" -b:a "$BITRATE" "$OUT" ;;
esac

echo "[restyle] done -> $OUT"
