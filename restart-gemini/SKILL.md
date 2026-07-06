---
name: restart-gemini
description: 重啟 LazyGravity → Antigravity（Google 的 Gemini IDE）整條遙控鏈並驗證有在動。當使用者說「重啟 gemini / antigravity / lazygravity」、Discord 回報 "Workbench page for workspace ... not found within 30 seconds"、workspace 連不上、或 /restart-gemini 時使用。會依序：起 Xvfb :99、在 CDP 9223 上啟動 Antigravity、重啟 lazygravity-bot 與 autoapprove service，最後透過 CDP 實際驗證 workbench 頁面可連。
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [lazygravity, antigravity, gemini, discord, cdp, restart, xvfb]
---

# Restart Gemini (LazyGravity → Antigravity control chain)

Use when Antigravity / LazyGravity needs restarting — typically the Discord error
**`Failed to connect to workspace: Workbench page for workspace "X" not found within 30 seconds`**,
or the user says「重啟 gemini / antigravity / lazygravity」.

## Just run it

```bash
bash ~/.hermes/skills/restart-gemini/scripts/restart.sh
```

Idempotent: safe to run anytime. Add `--no-bot` to leave the Discord bot untouched
(only fix Xvfb + Antigravity). Then tell the user to retry the workspace command in Discord.

## Why this is needed (the architecture)

LazyGravity (Discord bot `Ado#4549`, `~/src/LazyGravity`) drives the Antigravity IDE
remotely over Chrome DevTools Protocol. As of 2026-07-05 the **whole stack is systemd
`--user`**, tied together by `lazygravity.target`:

| Unit | What |
|------|------|
| `openclaw-xvfb.service` | headless X display **:99** |
| `lazygravity-antigravity.service` | Antigravity IDE on :99, CDP **9223** (Requires xvfb; forces X11 ozone) |
| `lazygravity-bot.service` | the Discord bot (`DISPLAY=:99`); ordered `After=` antigravity |
| `lazygravity-autoapprove.service` | clicks "Always Allow" browser prompts |
| `lazygravity.target` | pulls in all four; `WantedBy=default.target` (starts at boot) |

All enabled → **survive reboot**. The antigravity unit holds in `activating` (via
`ExecStartPost` polling) until CDP 9223 actually answers, so the bot won't start talking
to a not-yet-ready IDE.

**Historical gotcha (now solved by the target):** in the task path the bot does NOT
auto-launch Antigravity — it only launches it via the `open` command. Before it was a
service, if Antigravity wasn't up on CDP 9223 every workspace command timed out with
"workbench page not found". Two causes were: Xvfb :99 down, or Antigravity not running.
Now the target keeps both up (and `Restart=always` respawns Antigravity if it crashes).

Key facts:
- Port **9223** is fixed by `ANTIGRAVITY_ACCOUNTS=default:9223` in `~/src/LazyGravity/.env`
  (9222 is Hermes's own Chrome — don't touch it).
- The antigravity unit runs the **Electron binary directly**
  (`/usr/share/antigravity/antigravity`), not the `bin/antigravity` CLI wrapper (which
  detaches). It **must force X11** (`--ozone-platform=x11` + `XDG_SESSION_TYPE=x11`);
  the login session is Wayland and the binary otherwise picks Wayland and **segfaults**.

## What the script does

Restarts `lazygravity.target` (or, with `--no-bot`, just Xvfb + Antigravity), waits for
CDP 9223, then prints each unit's active state, CDP status, and the open **workbench**
pages (workspaces the bot can reach, e.g. `ComfyUI - Antigravity - …`).

## Manual verification (if needed)

```bash
curl -s http://localhost:9223/json/version                  # CDP alive?
curl -s http://localhost:9223/json/list | python3 -c "import sys,json;[print(p['type'],p.get('title')) for p in json.load(sys.stdin)]"
cd ~/src/LazyGravity && node dist/bin/cli.js doctor          # full check (CDP ports)
```

To prove the chain end-to-end you can connect to a workbench page's
`webSocketDebuggerUrl` and `Runtime.evaluate` (e.g. check `document.querySelector('.monaco-workbench')`).

## Notes / caveats

- Antigravity is a plain detached process, **not** a systemd unit. If it dies, the same
  failure recurs — re-run this skill. (If the user wants it auto-restarting, wrap it in a
  `systemd --user` unit with `Environment=DISPLAY=:99` and `Restart=always`.)
- Workspaces live under `WORKSPACE_BASE_DIR=~/src` (e.g. `~/src/ComfyUI`).
- Don't kill CDP **9222** — that's Hermes's Chrome, not Antigravity.
