#!/bin/bash
# restart-claude.sh — Reliable restart for Claude Code Discord tmux session

set -e

echo "[+] Killing previous claude-discord tmux session..."
tmux kill-session -t claude-discord 2>/dev/null || true
sleep 1

echo "[+] Starting fresh claude-discord session in background..."
tmux new-session -d -s claude-discord
tmux send-keys -t claude-discord "claude --channels plugin:discord@claude-plugins-official --dangerously-skip-permissions --remote-control --chrome" Enter
sleep 2

# Check if session is alive
if tmux has-session -t claude-discord 2>/dev/null; then
    echo "[✓] Claude Code Discord tmux session successfully started!"
else
    echo "[!] Failed to launch Claude Code tmux session."
    exit 1
fi
