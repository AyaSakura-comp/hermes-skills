---
name: restart-claude
description: Start or restart Claude Code in a background tmux session with Discord channel integration, remote-control, Chrome browser, and dangerous permissions enabled.
version: 2.0.2
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [claude-code, tmux, discord, automation, ai-agents]
---

# restart-claude

This skill provides a reliable way to launch or restart **Claude Code** in a background `tmux` session. It ensures the session is started with Discord channel integration, remote-control mode, Chrome browser support, and the "dangerous" YOLO mode (bypassing permission prompts).

## Prerequisites

- **Claude Code** installed (`npm install -g @anthropic-ai/claude-code`).
- **Bun** installed (required for the Discord plugin).
- **tmux** installed for session management.
- Discord plugin configured (`claude plugins add discord@claude-plugins-official`).

## Usage

When the user asks to "restart Claude" or "start Claude with Discord," follow these steps:

### 1. Cleanup Existing Session

Always kill the previous session to avoid conflicts:

```bash
tmux kill-session -t claude-discord 2>/dev/null
```

### 2. Launch New Session

Start a detached tmux session and send the launch command (includes Discord, remote-control, and Chrome):

```bash
tmux new-session -d -s claude-discord
tmux send-keys -t claude-discord "claude --channels plugin:discord@claude-plugins-official --dangerously-skip-permissions --remote-control --chrome" Enter
```

### 3. Handle Workspace Trust Prompt

Claude Code usually asks to trust the directory on startup. Wait for the prompt and send "1" (Yes):

```bash
sleep 8
tmux send-keys -t claude-discord "1" Enter
```

### 4. Handle Permissions Bypass Dialog (when using --dangerously-skip-permissions)

When launched with `--dangerously-skip-permissions`, Claude Code shows a second confirmation dialog:

```
❯ 1. No, exit                    ← DEFAULT (WRONG!)
  2. Yes, I accept
```

**You MUST navigate DOWN first, then Enter** — the default selection is "No, exit" which will terminate the session:

```bash
sleep 3
tmux send-keys -t claude-discord Down
sleep 0.5
tmux send-keys -t claude-discord Enter
```

### 5. Verification

Capture the pane output to ensure it started correctly:

```bash
tmux capture-pane -t claude-discord -p
```

## Pitfalls

- **Timing**: The `sleep` duration might need to be adjusted based on system performance (increase if the trust prompt hasn't appeared yet).
- **Full Plugin Path**: Do not use `--channels discord`; you MUST use the full identifier: `--channels plugin:discord@claude-plugins-official`.
- **Environment**: Ensure the command is run in the intended workspace directory.
- **PTY requirement**: Claude Code requires a TTY/PTY, which is why `tmux` is preferred over standard backgrounding (`&`).

## Verification Steps

1. Run `tmux ls` to see if `claude-discord` is active.
2. Run `tmux capture-pane -t claude-discord -p` and look for the "Listening for channel messages" line.
3. Check Discord to see if the bot status changes to online.
