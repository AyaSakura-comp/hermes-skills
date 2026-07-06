---
name: restart-gpt
description: Start, stop, or restart OpenAI Codex's remote-control app-server daemon. Use when the user asks to restart codex, start codex remote-control, stop codex server, check codex status, or bring up a background Codex daemon for remote sessions.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [codex, gpt, remote-control, daemon, openai, tmux]
    related_skills: [codex, claude-code, restart-claude]
---

# restart-gpt

This skill manages the **Codex remote-control app-server daemon**, which allows other processes or clients to control Codex sessions remotely. It provides start, stop, restart, and status commands.

## Prerequisites

- **Codex CLI** installed (`npm install -g @openai/codex`)
- **Codex authenticated** (run `codex login` if not already logged in)

## Commands

> **No sandbox:** every `start` below passes `-c sandbox_mode="danger-full-access"` so
> Codex runs WITHOUT the sandbox (it does not confine model-generated commands).
> `approval_policy` is already `never` in `~/.codex/config.toml`. Omit the `-c` flag
> only if you explicitly want the sandboxed (`workspace-write`) default back.

### 1. Start the daemon

```bash
codex remote-control start -c sandbox_mode="danger-full-access"
```

### 2. Stop the daemon

```bash
codex remote-control stop
```

### 3. Restart the daemon (stop + start)

```bash
codex remote-control stop && codex remote-control start -c sandbox_mode="danger-full-access"
```

### 4. Check status

```bash
codex remote-control start -c sandbox_mode="danger-full-access" --json 2>&1
```

If the daemon is already running, the command will report its status. If it's not running, it will start it.

## Configuration

You can override config values at runtime with `-c`:

```bash
# Use a specific model
codex remote-control start -c model="o3"

# Adjust sandbox permissions
codex remote-control start -c 'sandbox_permissions=["disk-full-read-access"]'

# Enable/disable features
codex remote-control start --enable feature-name
codex remote-control start --disable feature-name
```

## Connecting to the remote server

Once the daemon is running, clients connect using the `--remote` flag:

```bash
codex --remote ws://host:port --remote-auth-token-env CODEX_TOKEN "Do something"
```

The server address and auth token depend on the daemon's configuration. Check the start output for connection details.

## Pitfalls

- **Already running**: If the daemon is already started, calling `start` again may fail or create a second instance. Use `stop` first to be safe.
- **Authentication**: If `codex login` hasn't been run, the daemon will fail. Ensure the user is logged in.
- **Experimental**: The `remote-control` feature is marked as experimental — behavior may change in future Codex versions.
- **Port conflicts**: If another process is using the daemon's listening port, start will fail. Kill the conflicting process or choose a different port via config.

## Verification Steps

1. Run `codex remote-control start --json 2>&1` to confirm the daemon is running.
2. Check the JSON output for a status field indicating the daemon is active.
3. Optionally connect a test client: `codex --remote <ws://host:port>` to verify connectivity.
