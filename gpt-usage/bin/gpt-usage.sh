#!/usr/bin/env bash
set -euo pipefail
# gpt-usage: show ChatGPT/Codex (openai-codex) subscription rate-limit usage.
# Reads pi's OAuth token from ~/.pi/agent/auth.json and reads the X-Codex-* headers
# off the Codex responses endpoint (request aborted right after headers → ~no quota).
# Legacy flags (--no-probe) are accepted and ignored; pass --json for machine output.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec node "$HERE/gpt-usage.mjs" "$@"
