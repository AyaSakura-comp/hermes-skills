#!/usr/bin/env bash
set -euo pipefail

SESSION="codex-session"

# Start codex session if not running
if ! tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "[reset-gpt-budget] Starting codex session..."
  tmux new-session -d -s "$SESSION" 'codex'
  sleep 5
  echo "[reset-gpt-budget] Codex session started, waiting for TUI to load..."
  sleep 3
fi

echo "[reset-gpt-budget] Sending /usage to codex session..."
tmux send-keys -t "$SESSION" '/usage Enter'

echo "[reset-gpt-budget] Waiting for confirmation prompt..."
sleep 2

echo "[reset-gpt-budget] Confirming with 'y'..."
tmux send-keys -t "$SESSION" 'y Enter'

sleep 2

# Verify result
output=$(tmux capture-pane -t "$SESSION" -p 2>/dev/null)

if echo "$output" | grep -qi "reset"; then
  echo "[reset-gpt-budget] ✓ GPT usage limit has been reset successfully."
else
  echo "[reset-gpt-budget] ✓ /usage command sent. Check the codex session for confirmation."
fi

echo ""
echo "You can attach to the session with:"
echo "  tmux attach -t $SESSION"
