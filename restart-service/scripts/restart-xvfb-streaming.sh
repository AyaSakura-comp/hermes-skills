#!/usr/bin/env bash
set -euo pipefail

PROJECT="$HOME/src/xvfb-streaming"
ENV_FILE="$PROJECT/.env"
FQDN="xvfb-streaming.crayfish-monitor.ts.net"
ALT_FQDN="gemma-stream.crayfish-monitor.ts.net"
MODE="${1:-restart}"

usage() {
  echo "Usage: $0 [restart|disable|status]"
}

if [[ ! -f "$PROJECT/compose.yaml" ]]; then
  echo "Xvfb Streaming Docker project not found: $PROJECT" >&2
  exit 1
fi

case "$MODE" in
  status)
    docker ps -a --filter name=xvfb-stream --format '{{.Names}} | {{.Status}}'
    if docker inspect xvfb-streaming >/dev/null 2>&1; then
      docker exec xvfb-streaming curl -fsS \
        -H "Host: $FQDN" \
        http://127.0.0.1:8771/api/status || true
      echo
    fi
    exit 0
    ;;
  disable)
    if docker inspect xvfb-streaming >/dev/null 2>&1 || docker inspect xvfb-stream-ts >/dev/null 2>&1; then
      (cd "$PROJECT" && docker compose down) || true
    fi
    systemctl --user stop xvfb-streaming.service 2>/dev/null || true
    systemctl --user stop gemma-stream-monitor.service 2>/dev/null || true
    echo 'Xvfb streaming disabled: container stack stopped'
    exit 0
    ;;
  restart) ;;
  *) usage; exit 1 ;;
esac

ENV_INFO="$HOME/.pi/agent/nodriver-browser.env"
if [[ -f "$ENV_INFO" ]]; then
  display=$(grep -E '^DISPLAY=' "$ENV_INFO" | cut -d= -f2- || true)
  xauthority=$(grep -E '^XAUTHORITY=' "$ENV_INFO" | cut -d= -f2- || true)
  worker_pid=$(grep -E '^PID=' "$ENV_INFO" | cut -d= -f2- || true)
fi

if [[ -z "${display:-}" ]] || [[ -z "${xauthority:-}" ]]; then
  worker_pid=$(pgrep -u "$USER" -f '^/home/chihmin/.pi/agent/extensions/nodriver-browser/.venv/bin/python .*worker.py --server' | head -1 || true)
  if [[ -z "$worker_pid" ]]; then
    echo 'nodriver-browser worker is not running' >&2
    exit 1
  fi
  display=$(tr '\0' '\n' < "/proc/$worker_pid/environ" | sed -n 's/^DISPLAY=//p' | head -1)
  xauthority=$(tr '\0' '\n' < "/proc/$worker_pid/environ" | sed -n 's/^XAUTHORITY=//p' | head -1)
fi

if [[ -z "$display" || -z "$xauthority" || ! -r "$xauthority" ]]; then
  echo 'could not resolve the worker DISPLAY/XAUTHORITY' >&2
  exit 1
fi

# Hard protection: prevent grabbing Antigravity/OpenClaw (:99) or non-Chrome displays
if [[ "$display" == ":99" ]]; then
  echo "FATAL: Detected display :99 which belongs to Antigravity (LazyGravity)! Refusing to stream wrong display." >&2
  exit 1
fi

# Verify the display belongs to Chrome via xlsclients
client_check=$(DISPLAY="$display" XAUTHORITY="$xauthority" xlsclients 2>/dev/null || true)
if echo "$client_check" | grep -iq "antigravity"; then
  echo "FATAL: Display $display runs Antigravity, not Chrome! Refusing to stream wrong display." >&2
  exit 1
fi

if ! echo "$client_check" | grep -iqE "chrome|chromium"; then
  if [[ -n "$worker_pid" ]] && ! pgrep -P "$worker_pid" -f "chrome" >/dev/null 2>&1; then
    echo "FATAL: No Chrome window or process detected on $display! Refusing to stream non-browser display." >&2
    exit 1
  fi
fi

# Detect display dimensions
dims=$(DISPLAY="$display" XAUTHORITY="$xauthority" xdpyinfo 2>/dev/null | grep 'dimensions:' | awk '{print $2}' || true)
source_w=""
source_h=""
output_w=""
output_h=""
if [[ "$dims" =~ ^([0-9]+)x([0-9]+)$ ]]; then
  source_w="${BASH_REMATCH[1]}"
  source_h="${BASH_REMATCH[2]}"
  output_w=$(( (source_w / 2 / 2) * 2 ))
  output_h=$(( (source_h / 2 / 2) * 2 ))
  [[ $output_w -lt 32 ]] && output_w=32
  [[ $output_h -lt 32 ]] && output_h=32
fi

# Preserve first-registration secrets and other local values while refreshing the
# active display. The container discovers and continuously syncs the matching
# Xauthority cookie from the read-only /host-tmp mount.
tmp_env=$(mktemp)
trap 'rm -f "$tmp_env"' EXIT
if [[ -f "$ENV_FILE" ]]; then
  grep -vE '^(DISPLAY_NUMBER|XAUTHORITY_PATH|TAILSCALE_HOST|SOURCE_WIDTH|SOURCE_HEIGHT|OUTPUT_WIDTH|OUTPUT_HEIGHT)=' "$ENV_FILE" > "$tmp_env" || true
fi
printf 'DISPLAY_NUMBER=%s\n' "$display" >> "$tmp_env"
# Geometry is NOT pinned here any more: the container auto-sizes source/crop/output to the live
# display and browser window every few seconds (app/autosize.py). Pin it only on purpose by setting
# XVFB_STREAM_PIN_GEOMETRY=1 when running this script.
if [[ "${XVFB_STREAM_PIN_GEOMETRY:-0}" == "1" && -n "$source_w" && -n "$source_h" ]]; then
  printf 'SOURCE_WIDTH=%s\nSOURCE_HEIGHT=%s\nOUTPUT_WIDTH=%s\nOUTPUT_HEIGHT=%s\n' \
    "$source_w" "$source_h" "$output_w" "$output_h" >> "$tmp_env"
fi
install -m 600 "$tmp_env" "$ENV_FILE"

cd "$PROJECT"

# Root-owned Tailscale state stays excluded by .dockerignore, but the classic
# Docker builder still needs directory traversal permission while creating the
# build context. State files themselves retain their existing permissions.
if [[ -d tailscale-state ]]; then
  sudo find tailscale-state -type d -exec chmod 755 {} +
fi

if [[ "${BUILD:-0}" == "1" ]] || ! docker image inspect xvfb-streaming:latest >/dev/null 2>&1; then
  docker compose build xvfb-streaming
fi
docker compose up -d --force-recreate

for _ in $(seq 1 45); do
  app_health=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' xvfb-streaming 2>/dev/null || true)
  ts_state=$(docker exec xvfb-stream-ts tailscale --socket=/tmp/tailscaled.sock status --json 2>/dev/null \
    | python3 -c 'import json,sys; print(json.load(sys.stdin).get("BackendState", ""))' 2>/dev/null || true)
  if [[ "$app_health" == "healthy" && "$ts_state" == "Running" ]]; then
    status=$(curl -fsS --max-time 15 "https://$FQDN/api/status" 2>/dev/null || curl -fsS --max-time 15 "https://$ALT_FQDN/api/status" 2>/dev/null || docker exec xvfb-streaming curl -fsS -H "Host: $FQDN" http://127.0.0.1:8771/api/status)
    python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["error"] is None; print("state={} frames={}".format(d["state"], d["frame_id"]))' <<<"$status"
    echo "xvfb-streaming healthy at https://$FQDN/ (DISPLAY=$display)"
    exit 0
  fi
  sleep 1
done

echo 'Xvfb Streaming restart verification failed' >&2
docker ps -a --filter name=xvfb-stream >&2 || true
docker logs --tail 50 xvfb-streaming >&2 || true
docker logs --tail 50 xvfb-stream-ts >&2 || true
exit 1
