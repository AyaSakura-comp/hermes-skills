---
name: restart-claude
description: Start or restart Claude Code in a background tmux session with dangerous permissions and Discord channel integration enabled.
version: 2.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [claude-code, tmux, discord, automation, ai-agents]
---

# restart-claude

This skill provides a reliable way to launch or restart **Claude Code** in a background `tmux` session. It ensures that the session is started with the "dangerous" YOLO mode (bypassing permission prompts) and the official Discord channel plugin for remote interaction.

## Prerequisites

- **Claude Code** installed (`npm install -g @anthropic-ai/claude-code`).
- **Bun** installed (required for the Discord plugin).
- **tmux** installed for session management.
- Discord plugin configured (`claude plugins add discord@claude-plugins-official`).

## Launch Modes

### Standard Mode (default — tmux + Discord)

Use when you want an interactive Claude Code session with Discord channel integration.

### Remote-Control Mode (`--remote-control` flag)

Use `--remote-control` to run Claude Code headlessly without tmux or a TTY. This mode replaces the entire tmux workflow — Claude Code runs directly and listens on stdout.

## Usage

When the user asks to "restart Claude" or "start Claude with Discord and dangerous flags," follow these steps:

### Standard Mode

#### 1. Cleanup Existing Session
Always kill the previous session to avoid conflicts:
```bash
tmux kill-session -t claude-discord 2>/dev/null
```

#### 2. Launch New Session
Start a detached tmux session and send the launch command:
```bash
tmux new-session -d -s claude-discord
tmux send-keys -t claude-discord "claude --channels plugin:discord@claude-plugins-official --dangerously-skip-permissions" Enter
```

#### 3. Handle Workspace Trust Prompt
Claude Code usually asks to trust the directory on startup. Wait for the prompt and send "1" (Yes):
```bash
sleep 8
tmux send-keys -t claude-discord "1" Enter
```

#### 4. Verification
Capture the pane output to ensure it started correctly:
```bash
tmux capture-pane -t claude-discord -p
```

### Remote-Control Mode (`--remote-control`)

#### 1. Launch
Run Claude Code directly with the flag:
```bash
claude --dangerously-skip-permissions --remote-control
```

Wait for it to print `Listening for channel messages` in stdout.

#### 2. Verification
Check the running process:
```bash
ps aux | grep "[c]laude --remote-control"
```
Look for `Listening for channel messages` in the output.

## Pitfalls

- **Timing**: The `sleep` duration might need to be adjusted based on system performance (increase if the trust prompt hasn't appeared yet).
- **Full Plugin Path**: Do not use `--channels discord`; you MUST use the full identifier: `--channels plugin:discord@claude-plugins-official`.
- **Environment**: Ensure the command is run in the intended workspace directory.
- **PTY requirement**: Claude Code requires a TTY/PTY, which is why `tmux` is preferred over standard backgrounding (`&`).
- **Remote-control mode**: `--remote-control` bypasses the TTY requirement entirely. Do NOT use tmux or `--channels` with this flag — it replaces the standard workflow. Verify via `ps aux` instead of `tmux capture-pane`.

## Verification Steps

1. Run `tmux ls` to see if `claude-discord` is active.
2. Run `tmux capture-pane -t claude-discord -p` and look for the "Listening for channel messages" line.
3. Check Discord to see if the bot status changes to online.

For remote-control mode, skip tmux steps and verify via `ps aux`.
