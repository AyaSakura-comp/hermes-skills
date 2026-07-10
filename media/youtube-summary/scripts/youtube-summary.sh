#!/bin/bash
# youtube-summary.sh - Wrapper script for YouTube Summary pipeline
# Usage: ./youtube-summary.sh <youtube_url> [title]

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."

python3 "$SCRIPT_DIR/youtube-summary.py" "$@"
