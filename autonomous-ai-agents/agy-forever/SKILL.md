---
name: agy-forever
description: Start and operate agy inside a tmux session so once activated, every subsequent user input is redirected to agy and agy output is relayed back in the chat. Use when the user wants a persistent terminal-based agy bridge, a forever session, or asks to route prompts through tmux.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [agy, antigravity, tmux, relay, bridge, cli, interactive]
    related_skills: [agy, restart-claude, restart-gpt]
---

# agy forever

This skill turns `agy` into a **tmux-backed conversational bridge**.

## Behavior

When this skill is active:

- Every subsequent user message is redirected to `agy`.
- Do not answer directly in chat unless `agy` fails or produces no output.
- Forward each message into the running `agy` tmux session.
- Capture the pane output.
- Return agy's response to the user.
- Keep the same session alive for follow-ups unless the user asks for a new session.

## Prerequisites

- `tmux` installed
- agy installed at `/home/chihmin/.local/bin/agy`
- a terminal/PTY-capable environment

## Default session

Use a stable session name:

```bash
AGY_TMUX_SESSION=agy-bridge
```

## Start / restart / status

If the user sends `/agy-forever status`, immediately check whether the tmux session exists and whether agy is running, then report the result in chat.

If the user sends `/agy-forever restart`, kill the existing tmux session first and relaunch agy.

If no session exists, start one in tmux with interactive mode:

```bash
tmux new-session -d -s agy-bridge -x 120 -y 40 "/home/chihmin/.local/bin/agy -i --continue"
```

If the user explicitly asks for a fresh start, or uses `/agy-forever restart`, kill the old session first:

```bash
tmux kill-session -t agy-bridge 2>/dev/null
```

Then relaunch with the command above.

## Forwarding input

Send the user's text directly into the tmux pane:

```bash
tmux send-keys -t agy-bridge "<user message>" Enter
```

If the message contains quotes or shell-sensitive text, escape it safely before sending.

## Reading output / status check

Capture the latest pane content after agy finishes responding:

For an immediate status check, use:

```bash
tmux has-session -t agy-bridge
```

and then:

```bash
tmux capture-pane -t agy-bridge -p -S -40
```

Use this to distinguish:
- session missing
- session alive but waiting for input
- session alive and currently generating output


```bash
tmux capture-pane -t agy-bridge -p -S -200
```

Return the newest relevant answer, not the entire scrollback.

## Operating rule

After activation, all incoming user input must be redirected to `agy`.
Do not invent a separate answer unless agy failed or produced no output. The bridge should be:

1. input -> tmux -> agy
2. agy output -> capture-pane
3. output -> user

## Pitfalls

- `agy --prompt-interactive` needs a real TTY; tmux provides that.
- Avoid using plain backgrounding (`&`) because agy is interactive.
- If the pane is waiting on a prompt, capture the pane before sending more text.
- If agy exits unexpectedly, recreate the tmux session and resend the user's message.

## Verification steps

1. `tmux has-session -t agy-bridge` succeeds.
2. `tmux capture-pane -t agy-bridge -p` shows agy running.
3. `/agy-forever status` reports the current session state immediately.
4. A test message sent with `tmux send-keys` appears in agy's response.
5. The response is relayed back to the user.
