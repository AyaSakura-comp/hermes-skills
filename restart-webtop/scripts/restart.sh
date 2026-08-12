#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR=${WEBTOP_PROJECT_DIR:-/home/chihmin/src/webtop-amd}
ENV_FILE=${WEBTOP_ENV_FILE:-/home/chihmin/.config/webtop-amd/env}
UNIT_SOURCE="$PROJECT_DIR/deploy/webtop-amd.service"
UNIT_TARGET=${WEBTOP_UNIT_TARGET:-/home/chihmin/.config/systemd/user/webtop-amd.service}
FQDN=${WEBTOP_FQDN:-webtop-amd.crayfish-monitor.ts.net}
COMPOSE=(docker compose --project-directory "$PROJECT_DIR" -f "$PROJECT_DIR/compose.yaml")

log() { printf '\n==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
require() { command -v "$1" >/dev/null || die "missing required command: $1"; }

for command in docker npm node systemctl curl jq openssl amdgpu_top dig; do
  require "$command"
done
[[ -d "$PROJECT_DIR" ]] || die "project not found: $PROJECT_DIR"
[[ -f "$UNIT_SOURCE" ]] || die "systemd unit not found: $UNIT_SOURCE"
docker compose version >/dev/null

log "Ensure backend environment"
mkdir -p "$(dirname "$ENV_FILE")"
if [[ ! -f "$ENV_FILE" ]]; then
  printf 'WEBTOP_PASSWORD=2169\nWEBTOP_SESSION_SECRET=%s\nWEBTOP_HOST=0.0.0.0\nWEBTOP_PORT=8787\n' "$(openssl rand -hex 32)" >"$ENV_FILE"
fi
grep -Eq '^WEBTOP_PASSWORD=.+$' "$ENV_FILE" || printf 'WEBTOP_PASSWORD=2169\n' >>"$ENV_FILE"
grep -Eq '^WEBTOP_SESSION_SECRET=.+$' "$ENV_FILE" || printf 'WEBTOP_SESSION_SECRET=%s\n' "$(openssl rand -hex 32)" >>"$ENV_FILE"
grep -Eq '^WEBTOP_HOST=.+$' "$ENV_FILE" || printf 'WEBTOP_HOST=0.0.0.0\n' >>"$ENV_FILE"
grep -Eq '^WEBTOP_PORT=.+$' "$ENV_FILE" || printf 'WEBTOP_PORT=8787\n' >>"$ENV_FILE"
chmod 600 "$ENV_FILE"

log "Build tested application sources"
cd "$PROJECT_DIR"
# The official sidecar creates this bind-mounted directory as root:0700. The
# classic Docker builder stats the build context before honoring .dockerignore,
# so make only the directory traversable while keeping state files ignored.
if [[ -d "$PROJECT_DIR/tailscale/state" && ! -x "$PROJECT_DIR/tailscale/state" ]]; then
  docker run --rm --entrypoint chmod \
    -v "$PROJECT_DIR/tailscale/state:/state" \
    tailscale/tailscale:latest 0755 /state
fi
if [[ ! -d node_modules ]]; then
  npm ci
fi
npm test
npm run typecheck
npm run build

log "Install and restart host backend"
mkdir -p "$(dirname "$UNIT_TARGET")"
install -m 0644 "$UNIT_SOURCE" "$UNIT_TARGET"
systemctl --user daemon-reload
systemctl --user enable --now webtop-amd.service
systemctl --user restart webtop-amd.service

log "Rebuild frontend, then recreate its network-sharing Tailscale sidecar"
"${COMPOSE[@]}" up -d --build --force-recreate frontend
"${COMPOSE[@]}" up -d --force-recreate tailscale

log "Verify backend health"
backend_ok=false
for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8787/api/health >/dev/null; then backend_ok=true; break; fi
  sleep 1
done
$backend_ok || die "host backend health check failed"
[[ $(systemctl --user is-active webtop-amd.service) == active ]] || die "webtop-amd.service is not active"

log "Verify frontend container"
frontend_ok=false
for _ in $(seq 1 30); do
  health=$(docker inspect -f '{{.State.Health.Status}}' webtop-amd-frontend 2>/dev/null || true)
  if [[ $health == healthy ]]; then frontend_ok=true; break; fi
  sleep 1
done
$frontend_ok || die "frontend container is not healthy"

log "Verify Tailscale identity and Serve configuration"
tailscale_ok=false
for _ in $(seq 1 45); do
  state=$(docker exec webtop-amd-ts tailscale status --json 2>/dev/null | jq -r '.BackendState // empty' || true)
  proxy=$(docker exec webtop-amd-ts tailscale serve status --json 2>/dev/null | jq -r --arg host "$FQDN:443" '.Web[$host].Handlers["/"].Proxy // empty' || true)
  if [[ $state == Running && $proxy == http://127.0.0.1:80 ]]; then tailscale_ok=true; break; fi
  sleep 1
done
$tailscale_ok || {
  "${COMPOSE[@]}" logs --tail=80 tailscale >&2 || true
  die "Tailscale is not Running or Serve proxy is missing; first registration may be required"
}

serve_json=$(docker exec webtop-amd-ts tailscale serve status --json)
expected_funnel=$(jq -r --arg host "$FQDN:443" '.AllowFunnel[$host] // false' "$PROJECT_DIR/tailscale/config/serve.json")
actual_funnel=$(jq -r --arg host "$FQDN:443" '.AllowFunnel[$host] // false' <<<"$serve_json")
[[ $actual_funnel == "$expected_funnel" ]] || die "Funnel state does not match declarative Serve config"

log "Verify HTTPS endpoint"
https_ok=false
for _ in $(seq 1 20); do
  if curl -fsS "https://$FQDN/api/health" | jq -e '.ok == true' >/dev/null; then https_ok=true; break; fi
  sleep 1
done
$https_ok || die "HTTPS health check failed: https://$FQDN/api/health"

if [[ $expected_funnel == true ]]; then
  log "Verify the real public Funnel path (bypass MagicDNS)"
  public_ok=false
  for _ in $(seq 1 6); do
    public_ips=$(dig +short @1.1.1.1 "$FQDN" A)
    [[ -n $public_ips ]] || { sleep 2; continue; }
    for ip in $public_ips; do
      if curl --resolve "$FQDN:443:$ip" --connect-timeout 5 -fsS \
        "https://$FQDN/api/health" 2>/dev/null | jq -e '.ok == true' >/dev/null; then
        public_ok=true
        break 2
      fi
    done
    sleep 2
  done
  $public_ok || die "public Funnel probes failed through all public ingress addresses"
fi

printf '\nWebtop restart complete\n'
printf '  Backend:   active at http://127.0.0.1:8787\n'
printf '  Frontend:  healthy at http://127.0.0.1:8788\n'
printf '  Tailscale: Running at https://%s (Funnel %s)\n' "$FQDN" "$([[ $expected_funnel == true ]] && echo enabled || echo disabled)"
