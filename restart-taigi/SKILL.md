---
name: restart-taigi
description: 重啟 Taigi / Breeze ASR 26 即時語音辨識與翻譯服務。當使用者說「重啟 taigi / 台語服務 / Breeze ASR / 翻譯服務」、Discord 回報網頁能開但 Start Listening 連不上、WebSocket connection refused、ASR 沒反應、TTS/翻譯卡住、或 /restart-taigi 時使用。會重啟 host 上的 Breeze ASR 後端 supervisor、確認/必要時重啟 MERaLiON OmniVoice TTS、重啟 frontend + Tailscale sidecar，最後驗證 health、公開 URL、WebSocket。
version: 1.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [taigi, breeze-asr, asr, translation, tts, tailscale, docker, restart, discord]
---

# Restart Taigi / Breeze ASR Streaming

Use when the Taigi realtime ASR/translation web app needs restarting — page opens but
microphone/WebSocket does not connect, ASR stops responding, translation/TTS appears stuck, or the
user says `/restart-taigi`,「重啟 taigi / 台語服務 / Breeze ASR」.

## Just run it

```bash
bash ~/.hermes/skills/restart-taigi/scripts/restart.sh
```

Options:

```bash
bash ~/.hermes/skills/restart-taigi/scripts/restart.sh --tts      # force-restart MERaLiON/OmniVoice too
bash ~/.hermes/skills/restart-taigi/scripts/restart.sh --rebuild  # rebuild frontend, then force-recreate Tailscale sidecar
bash ~/.hermes/skills/restart-taigi/scripts/restart.sh --no-ui    # backend/TTS only; skip frontend/Tailscale
```

Report the final health lines to the user. If the script says `Done`, tell the user to reload
`https://taigi.crayfish-monitor.ts.net/` and try again.

## Live architecture

| Piece | What | Managed by |
| --- | --- | --- |
| Breeze ASR backend | FastAPI + WebSocket on host `:8025`; Breeze ASR for Taigi, Whisper Turbo for non-Taigi, Gemma translation routing | `~/models-work/breeze-asr-26/start-bg.sh` supervisor + `stop.sh` |
| MERaLiON/OmniVoice TTS | Local non-Taigi TTS on host `:8026`, default speaker/ref audio | `systemctl --user meralion-tts.service` |
| Frontend | Nginx static web client on Docker `:8080` | `~/src/breeze-asr-streaming/docker-compose.yml` service `frontend` |
| Tailscale sidecar | Serves `https://taigi.crayfish-monitor.ts.net/` and `/ws/stream` → host backend | Docker service `tailscale` sharing frontend netns |

The backend can crash from fatal ROCm/HIP C++ exceptions (`HSA_STATUS_ERROR_EXCEPTION`,
`unspecified launch failure`). `start-bg.sh` supervises uvicorn and restarts automatically, but this
skill forcibly cycles the stack and verifies it end-to-end.

## What the script does

1. Stops and starts the Breeze ASR backend supervisor (`./stop.sh && ./start-bg.sh`).
2. Waits for `http://127.0.0.1:8025/health`.
3. Checks MERaLiON/OmniVoice `http://127.0.0.1:8026/health`; restarts it only if unhealthy, unless
   `--tts` is passed.
4. Restarts Docker frontend + Tailscale sidecar. With `--rebuild`, it runs the safe deploy flow:
   `docker compose up -d --build frontend` then `docker compose up -d --force-recreate tailscale`.
   This matters because the Tailscale sidecar uses `network_mode: service:frontend`; any frontend
   recreate invalidates the old sidecar network namespace.
5. Verifies local frontend, public URL, public WebSocket, container states, and Tailscale node status.

## Correct deploy flows

### Backend-only code change or ASR/translation crash

```bash
bash ~/.hermes/skills/restart-taigi/scripts/restart.sh --no-ui
```

This calls `~/models-work/breeze-asr-26/stop.sh` then `start-bg.sh`. `stop.sh` is intentionally
aggressive: it kills the supervisor PID from `breeze-asr.pid`, sends TERM to any surviving
`uvicorn app.server:app.*8025`, waits briefly, then sends KILL to stale uvicorn children. This avoids
old ROCm processes staying alive and sharing the GPU/port with the new backend.

Manual equivalent:

```bash
cd ~/models-work/breeze-asr-26
./stop.sh
pgrep -af 'uvicorn app.server:app.*8025' || true   # should be empty
./start-bg.sh
curl http://127.0.0.1:8025/health
```

### Frontend/UI code change

```bash
bash ~/.hermes/skills/restart-taigi/scripts/restart.sh --rebuild
```

Manual equivalent if the skill is unavailable:

```bash
cd ~/src/breeze-asr-streaming
docker compose up -d --build frontend
docker compose up -d --force-recreate tailscale
curl -s -o /dev/null -w '%{http_code}\n' https://taigi.crayfish-monitor.ts.net/
```

Do **not** rely on plain `docker restart breeze-asr-tailscale-taigi` after a frontend rebuild; the
sidecar may still point at the deleted frontend network namespace.

## Troubleshooting notes

- If frontend works but WebSocket fails with `connection refused`, the backend on `:8025` is down or
  still loading. Check `~/models-work/breeze-asr-26/logs/server.log` and run `pgrep -af 'uvicorn app.server:app.*8025'`.
- If TTS fails but ASR/translation text works, check `systemctl --user status meralion-tts.service`
  and `curl http://127.0.0.1:8026/health`.
- Do **not** use system/default Python for Breeze/Whisper; use the ROCm 7.2 venv wired by
  `~/models-work/breeze-asr-26/start.sh`.
- Frontend code changes need `--rebuild`; normal outage recovery usually does not.
- If there are multiple backend PIDs, run `cd ~/models-work/breeze-asr-26 && ./stop.sh` and verify only the new `start-bg.sh` child returns after restart.
