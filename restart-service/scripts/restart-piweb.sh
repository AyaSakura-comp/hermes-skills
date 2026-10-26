#!/usr/bin/env bash
# Restart piweb's host worker, Docker web tier, and Tailscale sidecar in the only safe order.
set -Eeuo pipefail

# Restarting a service does NOT require rebuilding its image. Every `--build`
# orphans the previous image AND each intermediate stage of a multi-stage
# Dockerfile (~5 images, ~12GB per HayAegis build), and Docker never reclaims
# them — that is how /var/lib/containerd reached 528GB by 2026-09-03.
# Rebuild explicitly only when the code actually changed:  REBUILD=1 <script>
REBUILD="${REBUILD:-0}"
BUILD_FLAG=()
[[ "$REBUILD" == "1" ]] && BUILD_FLAG=(--build)


DIR="${PIWEB_DIR:-$HOME/src/piweb}"
URL="${PIWEB_URL:-https://piweb.crayfish-monitor.ts.net}"
APP_CONTAINER="${PIWEB_APP_CONTAINER:-piweb-app}"
TS_CONTAINER="${PIWEB_TS_CONTAINER:-piweb-ts}"

log() { printf '  %s\n' "$*"; }
diagnostics() {
  local rc=$?
  (( rc == 0 )) && return
  echo
  echo "Restart failed (exit $rc). Recent diagnostics:" >&2
  systemctl --user --no-pager --full status piweb-worker.service pi-discord-gateway.service 2>&1 | tail -30 >&2 || true
  docker compose -f "$DIR/docker-compose.yml" logs --tail=30 app tailscale >&2 || true
}
trap diagnostics EXIT

[[ -f "$DIR/docker-compose.yml" ]] || { echo "Missing $DIR/docker-compose.yml" >&2; exit 1; }
cd "$DIR"

# If invoked from inside piweb-worker.service (e.g. by an agent tool call),
# restarting piweb-worker synchronously in step 1 terminates the cgroup immediately,
# killing this script and the agent mid-turn before the web container can be rebuilt.
INSIDE_WORKER=0
if grep -qs 'piweb-worker\.service' /proc/self/cgroup 2>/dev/null || [[ -n "${PIWEB_CHANNEL_JID:-}" ]]; then
  INSIDE_WORKER=1
fi

# Targeted worker restart: invoke from an external systemd unit, never from
# the worker's own cgroup. Leave gateway, Docker web, Tailscale and tmux alone.
if [[ "${PIWEB_WORKER_ONLY:-0}" == "1" ]]; then
  trap - EXIT
  if (( INSIDE_WORKER )); then
    echo "Worker-only restart requires an external unit; refusing self-restart." >&2
    exit 1
  fi
  echo "== restart-piweb: worker only =="
  systemctl --user restart piweb-worker.service
  worker_state=$(systemctl --user is-active piweb-worker.service)
  [[ "$worker_state" == active ]] || { echo "Worker is not active: $worker_state" >&2; exit 1; }
  log "piweb worker: $worker_state; gateway, web, Tailscale and tmux unchanged."
  exit 0
fi

echo "== restart-piweb =="
log "[1/8] Starting the Pi agent gateway and host pi worker..."
systemctl --user reset-failed pi-discord-gateway.service piweb-worker.service 2>/dev/null || true
systemctl --user enable --now pi-discord-gateway.service
systemctl --user enable --now piweb-worker.service
if (( INSIDE_WORKER )); then
  log "      Running inside piweb-worker; skipping host worker restart to avoid terminating current agent turn..."
else
  systemctl --user restart piweb-worker.service
fi

log "[2/8] Rebuilding and force-recreating the web app..."
docker compose up -d "${BUILD_FLAG[@]}" --force-recreate app

# CRITICAL: network_mode: service:app resolves to a container network namespace.
# Recreating app leaves an already-running sidecar attached to the old namespace.
log "[3/8] Force-recreating Tailscale after app (prevents stale netns / HTTP 502)..."
docker compose up -d --force-recreate tailscale

log "[4/8] Waiting for app reachability inside the shared namespace..."
app_ok=false
for _ in $(seq 1 20); do
  if docker exec "$TS_CONTAINER" sh -c \
    "wget -q -O /dev/null http://127.0.0.1:8099/" 2>/dev/null; then
    app_ok=true
    break
  fi
  sleep 1
done
[[ "$app_ok" == true ]] || { echo "Sidecar cannot reach http://127.0.0.1:8099/" >&2; exit 1; }

log "[5/8] Waiting for Tailscale node and Serve..."
ts_summary=""
for _ in $(seq 1 15); do
  ts_summary=$(docker exec "$TS_CONTAINER" tailscale status --json 2>/dev/null | python3 -c '
import json, sys
d = json.load(sys.stdin)
s = d.get("Self", {})
print("state=%s online=%s dns=%s" % (d.get("BackendState"), s.get("Online"), s.get("DNSName", "?").rstrip(".")))
' 2>/dev/null || true)
  [[ "$ts_summary" == *"state=Running online=True"* ]] && break
  sleep 2
done
[[ "$ts_summary" == *"state=Running online=True"* ]] || { echo "Tailscale unhealthy: ${ts_summary:-no status}" >&2; exit 1; }
# containerboot applies TS_SERVE_CONFIG shortly after the node reaches Running; poll both states.
serve_ok=false
serve_status=""
for _ in $(seq 1 15); do
  serve_status=$(docker exec "$TS_CONTAINER" tailscale serve status 2>&1 || true)
  if grep -Fq 'proxy http://127.0.0.1:8099' <<<"$serve_status"; then
    serve_ok=true
    break
  fi
  sleep 1
done
[[ "$serve_ok" == true ]] || { echo "Serve proxy missing" >&2; echo "$serve_status" >&2; exit 1; }

log "[6/8] Verifying tailnet HTTPS and the real public Funnel path..."
tailnet_code=""
for _ in $(seq 1 5); do
  tailnet_code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 "$URL/" 2>/dev/null || true)
  [[ "$tailnet_code" == 200 ]] && break
  sleep 2
done
[[ "$tailnet_code" == 200 ]] || { echo "Tailnet HTTPS returned ${tailnet_code:-no response}" >&2; exit 1; }

# MagicDNS resolves the hostname to 100.x on this host, which only tests tailnet Serve.
# Resolve via public DNS and pin curl to a public Funnel ingress IP to test Funnel itself.
mapfile -t public_ips < <(dig +short @1.1.1.1 "${URL#https://}" A 2>/dev/null | grep -E '^[0-9]+(\.[0-9]+){3}$' | sort -u)
((${#public_ips[@]} > 0)) || { echo "No public Funnel A records found via 1.1.1.1" >&2; exit 1; }

probe_funnel() {
  public_code=""
  public_ip=""
  for ip in "${public_ips[@]}"; do
    for _ in 1 2 3; do
      code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 \
        --resolve "${URL#https://}:443:$ip" "$URL/" 2>/dev/null || true)
      if [[ "$code" == 200 ]]; then public_code=$code; public_ip=$ip; return 0; fi
      sleep 5
    done
  done
  return 1
}

# A freshly recreated sidecar can advertise "Funnel on" before its ingress connection is live;
# public TLS then dies with `unexpected eof` (seen 2026-07-28). Restarting piweb-ts re-establishes
# ingress. This is safe here because the app container was NOT recreated in between, so the shared
# netns still exists -- never "fix" a stale-netns 502 this way, that needs the step [3] recreate.
if ! probe_funnel; then
  log "      Public Funnel not answering; restarting the sidecar to re-establish ingress..."
  docker compose restart tailscale
  sleep 20
  probe_funnel || { echo "Public Funnel did not return 200 via: ${public_ips[*]}" >&2; exit 1; }
  log "      Funnel recovered after sidecar restart."
fi

log "[7/8] Confirming the recovered Funnel path is stable..."
for _ in 1 2; do
  code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 \
    --resolve "${URL#https://}:443:$public_ip" "$URL/" 2>/dev/null || true)
  [[ "$code" == 200 ]] || { echo "Public Funnel flapped: got ${code:-no response}" >&2; exit 1; }
  sleep 3
done

log "[8/8] Confirming the Pi agent gateway and worker are active..."
agent_state=$(systemctl --user is-active pi-discord-gateway.service)
worker_state=$(systemctl --user is-active piweb-worker.service)
[[ "$agent_state" == active ]] || { echo "Pi agent gateway is not active: $agent_state" >&2; exit 1; }
[[ "$worker_state" == active ]] || { echo "piweb worker is not active: $worker_state" >&2; exit 1; }
app_state=$(docker inspect -f '{{.State.Status}}' "$APP_CONTAINER")
ts_state=$(docker inspect -f '{{.State.Status}}' "$TS_CONTAINER")

echo
log "pi agent gateway: $agent_state; worker: $worker_state"
log "app: $app_state; tailscale: $ts_state"
log "tailscale: $ts_summary"
log "tailnet: HTTP $tailnet_code"
log "public Funnel: HTTP $public_code via $public_ip"

if (( INSIDE_WORKER )); then
  log "Inside piweb-worker: worker is already active; keeping current worker process running."
fi

echo "Done: $URL/"
