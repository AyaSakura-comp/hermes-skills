#!/usr/bin/env bash
set -uo pipefail
BACKEND_DIR="/home/chihmin/models-work/breeze-asr-26"
FRONTEND_DIR="/home/chihmin/src/breeze-asr-streaming"
PUBLIC_URL="https://taigi.crayfish-monitor.ts.net"
LOCAL_BACKEND="http://127.0.0.1:8025"
LOCAL_TTS="http://127.0.0.1:8026"
PY="/home/chihmin/models-work/flux2/.venv-rocm72/bin/python"
FORCE_TTS=0; REBUILD=0; NO_UI=0
for arg in "$@"; do
  case "$arg" in
    --tts|--restart-tts) FORCE_TTS=1 ;;
    --rebuild) REBUILD=1 ;;
    --no-ui|--backend-only) NO_UI=1 ;;
    -h|--help) echo "Usage: restart.sh [--tts] [--rebuild] [--no-ui]"; exit 0 ;;
    *) echo "unknown option: $arg"; exit 2 ;;
  esac
done
log(){ printf '  %s\n' "$*"; }
section(){ printf '\n== %s ==\n' "$*"; }
wait_http(){ local url="$1" seconds="${2:-60}" label="${3:-$url}"; for i in $(seq 1 "$seconds"); do curl -sf --max-time 3 "$url" >/dev/null 2>&1 && { log "$label: healthy"; return 0; }; sleep 1; done; log "$label: DOWN"; return 1; }
json_or_raw(){ local url="$1"; curl -sf --max-time 5 "$url" 2>/dev/null | "$PY" -m json.tool 2>/dev/null || curl -sS --max-time 5 "$url" 2>/dev/null || true; }
ok=1
echo "== restart-taigi =="
section "[1/5] Breeze ASR backend supervisor (:8025)"
cd "$BACKEND_DIR" || { echo "missing backend dir: $BACKEND_DIR"; exit 1; }
./stop.sh >/tmp/restart-taigi-stop.log 2>&1 || true
sed 's/^/  /' /tmp/restart-taigi-stop.log 2>/dev/null || true
./start-bg.sh
if wait_http "$LOCAL_BACKEND/health" 90 "backend health"; then json_or_raw "$LOCAL_BACKEND/health" | sed 's/^/      /' | head -20; else ok=0; log "recent backend log:"; tail -80 "$BACKEND_DIR/logs/server.log" 2>/dev/null | sed 's/^/      /' || true; fi
section "[2/5] MERaLiON / OmniVoice TTS (:8026)"
if [[ "$FORCE_TTS" -eq 1 ]] || ! curl -sf --max-time 3 "$LOCAL_TTS/health" >/dev/null 2>&1; then
  log "restarting meralion-tts.service..."; systemctl --user reset-failed meralion-tts.service 2>/dev/null || true; systemctl --user restart meralion-tts.service || true
  wait_http "$LOCAL_TTS/health" 120 "tts health" || log "TTS is still down; ASR/text translation can still work with TTS toggled off."
else log "tts health: already healthy"; fi
json_or_raw "$LOCAL_TTS/health" | sed 's/^/      /' | head -20
section "[3/5] Frontend + Tailscale sidecar"
if [[ "$NO_UI" -eq 1 ]]; then log "--no-ui set; skipping frontend/tailscale restart"; else
  cd "$FRONTEND_DIR" || { echo "missing frontend dir: $FRONTEND_DIR"; exit 1; }
  if [[ "$REBUILD" -eq 1 ]]; then
    log "docker compose up -d --build frontend"
    docker compose up -d --build frontend
    log "docker compose up -d --force-recreate tailscale"
    docker compose up -d --force-recreate tailscale
  else
    log "docker compose up -d frontend"
    docker compose up -d frontend
    log "docker compose up -d --force-recreate tailscale"
    docker compose up -d --force-recreate tailscale
  fi
fi
section "[4/5] Verification"
wait_http "http://127.0.0.1:8080/" 30 "local frontend" || ok=0
for i in $(seq 1 20); do code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$PUBLIC_URL/" 2>/dev/null); [[ "$code" = "200" ]] && break; sleep 2; done
log "$PUBLIC_URL/ -> HTTP ${code:-?}"; [[ "${code:-}" = "200" ]] || ok=0
WS_URL="$PUBLIC_URL/ws/stream?translate=off&tts=off" "$PY" - <<'PY'
import asyncio, json, os, sys
import websockets
async def main():
    uri = os.environ["WS_URL"].replace("https://", "wss://").replace("http://", "ws://")
    async with websockets.connect(uri, open_timeout=10, close_timeout=3) as ws:
        await ws.send(json.dumps({"type":"config","translate":"off","tts":"off","language":"zh","vad_threshold":0.015,"silence_duration":1.2}))
        msg=json.loads(await asyncio.wait_for(ws.recv(), timeout=8)); assert msg.get("type")=="config_applied", msg
        print("      websocket: OK", msg)
try: asyncio.run(main())
except Exception as exc: print(f"      websocket: DOWN {type(exc).__name__}: {exc}"); sys.exit(1)
PY
[[ "$?" -eq 0 ]] || ok=0
section "[5/5] Runtime status"
printf '      %-28s %s\n' "breeze supervisor" "$(cat "$BACKEND_DIR/breeze-asr.pid" 2>/dev/null || echo missing)"
printf '      %-28s %s\n' "breeze backend pid" "$(pgrep -f 'uvicorn app.server:app.*8025' | tr '\n' ' ' || echo missing)"
printf '      %-28s %s\n' "meralion-tts.service" "$(systemctl --user is-active meralion-tts.service 2>/dev/null || echo unknown)"
printf '      %-28s %s\n' "breeze-asr-frontend" "$(docker inspect -f '{{.State.Status}}' breeze-asr-frontend 2>/dev/null || echo missing)"
printf '      %-28s %s\n' "breeze-asr-tailscale-taigi" "$(docker inspect -f '{{.State.Status}}' breeze-asr-tailscale-taigi 2>/dev/null || echo missing)"
node=$(docker exec breeze-asr-tailscale-taigi tailscale status --json 2>/dev/null | python3 -c "import sys,json;d=json.load(sys.stdin)['Self'];print(d.get('DNSName','?').rstrip('.'),'online='+str(d.get('Online')))" 2>/dev/null)
log "tailscale node: ${node:-unknown}"
echo
if [[ "$ok" -eq 1 ]]; then echo "Done. Open/reload $PUBLIC_URL/ and try again."; exit 0; else echo "Not fully healthy. Check: $BACKEND_DIR/logs/server.log and docker compose logs --tail=80 in $FRONTEND_DIR"; exit 1; fi
