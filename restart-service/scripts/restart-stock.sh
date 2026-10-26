#!/usr/bin/env bash
set -euo pipefail

# Explicit owner-authorized, service-scoped in-place update. No Docker image
# rebuild/recreation; the helper enforces private backups and identity checks.
if [[ -n "${STOCK_INPLACE_PHASE:-}" ]]; then
  : "${STOCK_INPLACE_BUNDLE:?Set the owner-controlled deployment bundle}"
  exec python3 "$(dirname "${BASH_SOURCE[0]}")/stock-inplace.py" \
    "$STOCK_INPLACE_PHASE" "$STOCK_INPLACE_BUNDLE"
fi

# Preserve the active read-only artifact release on an ordinary stock restart.
CURRENT_RELEASE="${HOME}/.local/state/hayaegis-inplace/current"
if [[ "${REBUILD:-0}" == "0" && "${STOCK_FULL_STACK:-0}" != "1" && -f "$CURRENT_RELEASE" ]]; then
  IFS= read -r STOCK_INPLACE_BUNDLE < "$CURRENT_RELEASE"
  exec python3 "$(dirname "${BASH_SOURCE[0]}")/stock-inplace.py" restart "$STOCK_INPLACE_BUNDLE"
fi

# Restarting a service does NOT require rebuilding its image. Every `--build`
# orphans the previous image AND each intermediate stage of a multi-stage
# Dockerfile (~5 images, ~12GB per HayAegis build), and Docker never reclaims
# them — that is how /var/lib/containerd reached 528GB by 2026-09-03.
# REBUILD=1 requires explicit owner authorization for Docker image rebuilding.
# Application compilation alone does not require this flag.
REBUILD="${REBUILD:-0}"
BUILD_FLAG=(--no-build)
[[ "$REBUILD" == "1" ]] && BUILD_FLAG=(--build)


# ==============================================================================
# restart.sh — Rebuild, restart, and health-check the HayAegis stock stack
# ==============================================================================

PROJECT_DIR="${HAYAEGIS_PROJECT_DIR:-/home/chihmin/HayAegis/HayAegis}"
FQDN="${STOCK_FQDN:-stock.crayfish-monitor.ts.net}"
MAX_WAIT_SECONDS="${MAX_WAIT_SECONDS:-45}"
PORT="${WEB_PORT:-80}"

echo "=== [HayAegis Stock] Initiating stack restart ==="
echo "Project directory: $PROJECT_DIR"
echo "Target FQDN:       $FQDN"

if [[ ! -d "$PROJECT_DIR" ]]; then
  echo "[-] ERROR: Project directory $PROJECT_DIR does not exist!" >&2
  exit 1
fi

COMPOSE_ARGS=(-f "$PROJECT_DIR/docker-compose.yml")
if [[ -f "$PROJECT_DIR/docker-compose.override.yml" ]]; then
  COMPOSE_ARGS+=(-f "$PROJECT_DIR/docker-compose.override.yml")
fi
COMPOSE_ARGS+=(--profile tailscale)

echo "[*] Step 1: Building and starting core application services..."
docker compose "${COMPOSE_ARGS[@]}" up -d "${BUILD_FLAG[@]}" fourget agent api scheduler web

echo "[*] Step 2: Ensuring Tailscale sidecar is recreated attached to network..."
docker compose "${COMPOSE_ARGS[@]}" up -d --force-recreate tailscale-stock

echo "[*] Step 3: Verifying local service health..."
start_time=$(date +%s)
api_ready=0
web_ready=0

while true; do
  current_time=$(date +%s)
  elapsed=$((current_time - start_time))

  if [[ $api_ready -eq 0 ]]; then
    if curl -fsS "http://127.0.0.1:${PORT}/health/ready" >/dev/null 2>&1; then
      echo "  [+] API service is healthy (http://127.0.0.1:${PORT}/health/ready)"
      api_ready=1
    fi
  fi

  if [[ $web_ready -eq 0 ]]; then
    if curl -fsS "http://127.0.0.1:${PORT}/" >/dev/null 2>&1; then
      echo "  [+] Web frontend is healthy (Nginx/React)"
      web_ready=1
    fi
  fi

  if [[ $api_ready -eq 1 && $web_ready -eq 1 ]]; then
    echo "[+] Core services responded successfully within ${elapsed}s."
    break
  fi

  if [[ $elapsed -ge $MAX_WAIT_SECONDS ]]; then
    echo "[-] WARNING: Health check timed out after ${MAX_WAIT_SECONDS}s." >&2
    echo "    Dumping container statuses:"
    docker compose "${COMPOSE_ARGS[@]}" ps
    exit 1
  fi

  sleep 2
done

echo "[*] Step 4: Checking Tailscale Serve & Sidecar status..."
TS_CONTAINER=$(docker compose "${COMPOSE_ARGS[@]}" ps -q tailscale-stock)
if [[ -n "$TS_CONTAINER" ]]; then
  echo "  [+] Tailscale container ID: $TS_CONTAINER"
  sleep 3
  if docker exec "$TS_CONTAINER" tailscale status >/dev/null 2>&1; then
    echo "  [+] Tailscale node is authenticated and connected."
  else
    echo "  [!] Tailscale container is starting up; check serve status."
  fi
fi

echo "[*] Step 5: Testing HTTPS endpoint (https://$FQDN)..."
http_code=$(curl -k -s -o /dev/null -w "%{http_code}" "https://$FQDN" || echo "000")
echo "  [+] HTTPS response code: $http_code"

# The local checks above prove nothing about public reachability: a sidecar can
# report `Funnel on` while the control plane has dropped the public DNS record.
# Delegate that verification (and repair) to restart-funnel.sh so a dead funnel
# fails LOUDLY here instead of being skipped into a false "success".
FUNNEL_SH="$(dirname "${BASH_SOURCE[0]}")/restart-funnel.sh"
if [[ -x "$FUNNEL_SH" ]]; then
  echo "[*] Step 6: Verifying the public Funnel is actually registered..."
  if ! bash "$FUNNEL_SH" stock; then
    echo "[-] ERROR: stock is up locally but NOT reachable from the public internet." >&2
    exit 1
  fi
else
  echo "  [!] restart-funnel.sh not found — public reachability NOT verified."
fi

echo "=== [HayAegis Stock] Restart and redeploy completed successfully! ==="
