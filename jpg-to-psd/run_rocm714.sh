#!/usr/bin/env bash
# Convert one JPG/PNG to a layered PSD using the isolated ROCm 7.14 stack.
set -euo pipefail

BODY_ONLY=0
if [[ ${1:-} == "--body-only" ]]; then
  BODY_ONLY=1
  shift
fi
if [[ $# -ne 2 ]]; then
  echo "Usage: $0 [--body-only] /absolute/path/to/input.jpg /absolute/path/to/output_dir" >&2
  exit 2
fi

INPUT=$(realpath "$1")
OUTPUT=$(realpath -m "$2")
ROOT=/home/chihmin/src/see-through
PYTHON="$ROOT/.venv-rocm7.14/bin/python"
SKILL_DIR=/home/chihmin/.pi/agent/skills/jpg-to-psd

[[ -f "$INPUT" ]] || { echo "Input does not exist: $INPUT" >&2; exit 2; }
[[ -x "$PYTHON" ]] || { echo "Missing isolated ROCm 7.14 venv: $PYTHON" >&2; exit 2; }
mkdir -p "$OUTPUT"

export MIOPEN_DEBUG_CONV_WINOGRAD=0
export MIOPEN_FIND_MODE=FAST
export MIOPEN_USER_DB_PATH=/home/chihmin/.miopen-7.14-wheel
export PYTHONPATH="$ROOT/inference${PYTHONPATH:+:$PYTHONPATH}"
cd "$ROOT/inference"

# Separate processes are intentional: LayerDiff retains ~45GB if reused for Marigold.
if [[ $BODY_ONLY -eq 1 ]]; then
  "$PYTHON" "$SKILL_DIR/layerdiff_only.py" "$INPUT" "$OUTPUT" --body-only
  STEM=$(basename "${INPUT%.*}")
  echo "Body layers: $OUTPUT/$STEM/"
  exit 0
fi

"$PYTHON" "$SKILL_DIR/layerdiff_only.py" "$INPUT" "$OUTPUT"
"$PYTHON" "$SKILL_DIR/depth_and_psd.py" "$INPUT" "$OUTPUT"

STEM=$(basename "${INPUT%.*}")
echo "PSD: $OUTPUT/$STEM.psd"
echo "Preview: $OUTPUT/$STEM/reconstruction.png"
