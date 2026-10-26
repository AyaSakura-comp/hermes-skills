#!/usr/bin/env bash
# Restart the Fuji Camera stack and verify it end-to-end.
#
# LIVE DEPLOYMENT = Docker + Tailscale-in-Docker (GPU stays on the host):
#   fuji-gen.service        -> HOST generation service (FLUX.2 底片風, GPU) on :7863
#   docker: fuji-camera-app -> FastAPI web/pool (no GPU); reaches gen via host.docker.internal
#   docker: fuji-camera-ts  -> tailscale sidecar; serves https://fuji-camera.<tailnet>.ts.net
#   (managed by `fuji-camera-docker.service` / docker-compose.yml in ~/src/fuji_camera)
#
# Usage: restart.sh
set -uo pipefail
DIR="$HOME/src/fuji_camera"
URL="https://fuji-camera.crayfish-monitor.ts.net"
log(){ printf '  %s\n' "$*"; }

echo "== restart-fuji-camera =="
cd "$DIR" || { echo "no $DIR"; exit 1; }

log "[1/4] host GPU gen service (fuji-gen.service)..."
systemctl --user reset-failed fuji-gen.service 2>/dev/null || true
systemctl --user restart fuji-gen.service
for i in $(seq 1 10); do curl -sf --max-time 3 http://127.0.0.1:7863/health >/dev/null 2>&1 && break; sleep 1; done
log "gen health: $(curl -sf --max-time 3 http://127.0.0.1:7863/health 2>/dev/null || echo DOWN)"

log "[2/4] docker stack (compose)..."
docker compose up -d >/dev/null 2>&1
# restart app first, then the ts sidecar (it shares app's netns, must come up after)
docker restart fuji-camera-app >/dev/null 2>&1
docker restart fuji-camera-ts  >/dev/null 2>&1

log "[3/4] waiting for the app + tailscale serve..."
for i in $(seq 1 20); do
  docker exec fuji-camera-app python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8090/api/photos',timeout=3)" >/dev/null 2>&1 && break
  sleep 1
done

log "[4/4] verifying..."
printf '      %-22s %s\n' "fuji-gen.service" "$(systemctl --user is-active fuji-gen.service)"
printf '      %-22s %s\n' "fuji-camera-app"  "$(docker inspect -f '{{.State.Status}}' fuji-camera-app 2>/dev/null || echo missing)"
printf '      %-22s %s\n' "fuji-camera-ts"   "$(docker inspect -f '{{.State.Status}}' fuji-camera-ts 2>/dev/null || echo missing)"
# Online is a control-plane heartbeat that lags a few seconds after a restart; poll it
for i in $(seq 1 10); do
  node=$(docker exec fuji-camera-ts tailscale status --json 2>/dev/null | python3 -c "import sys,json;d=json.load(sys.stdin)['Self'];print(d.get('DNSName','?').rstrip('.'),'online='+str(d.get('Online')))" 2>/dev/null)
  echo "$node" | grep -q 'online=True' && break; sleep 2
done
log "tailscale node: ${node:-unknown}"
for i in $(seq 1 5); do
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 20 "${URL}/" 2>/dev/null)
  [ "$code" = "200" ] && break; sleep 3
done
# The public root must return 200 even when passcode-gated: it serves the login page.
# A 401 makes some browsers/webviews show an error instead of rendering that page.
if [ "${code:-}" = "200" ]; then
  log "${URL}/ -> HTTP ${code} (site/login page is reachable)"
  counts=$(curl -sf --max-time 10 "${URL}/api/photos" 2>/dev/null | python3 -c "import sys,json;print(json.load(sys.stdin).get('counts'))" 2>/dev/null)
  log "queue: ${counts:-?} (requires passcode when gated)"
  echo
echo "Done. Open ${URL}/ on the iPhone."
else
  log "${URL}/ -> HTTP ${code}"
  echo
  echo "Not healthy. Check: docker compose logs --tail=40 ; journalctl --user -u fuji-gen -n 40 --no-pager"
fi
