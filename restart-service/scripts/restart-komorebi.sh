#!/usr/bin/env bash
# Manage the full stack, or the explicit runtime-only NPU profile.
set -euo pipefail

ACTION=${1:-restart}
PROJECT=/home/chihmin/src/komorebi-voice
TARGET_UNIT=${KOMOREBI_UNIT:-komorebi.service}
case "$TARGET_UNIT" in
  komorebi.service|komorebi-npu.service) ;;
  *) echo "Unsupported KOMOREBI_UNIT: $TARGET_UNIT" >&2; exit 2 ;;
esac
if [[ -z ${KOMOREBI_UNIT:-} && "$ACTION" =~ ^(stop|disable|status|reload-app)$ ]] && systemctl is-active --quiet komorebi-npu.service; then
  TARGET_UNIT=komorebi-npu.service
fi

status() {
  echo "== Komorebi Master Service ($TARGET_UNIT)"
  printf 'enabled: '; systemctl is-enabled "$TARGET_UNIT" 2>/dev/null || true
  printf 'active : '; systemctl is-active "$TARGET_UNIT" 2>/dev/null || true
  if curl -sf --max-time 5 http://127.0.0.1:8792/api/config >/dev/null; then
    echo "health : healthy (port 8792)"
  else
    echo "health : unavailable"
  fi
  echo
  echo "== Backends (Bound to Komorebi Service)"
  for s in gemma-mtp:8002:GPU gemma-cpu:8031:CPU flm-serve:52625:NPU breeze-asr:8025:ASR; do
    IFS=: read -r unit port label <<< "$s"
    st=$(systemctl is-active "$unit.service" 2>/dev/null || true)
    if [ -z "$st" ] || [ "$st" = "inactive" ] || [ "$st" = "failed" ]; then
      if systemctl is-active --quiet "$unit.socket" 2>/dev/null; then
        st="socket"
      else
        st="down"
      fi
    fi
    printf '%-5s (%-18s): %-8s' "$label" "$unit" "$st"
    if [ "$port" = "52625" ]; then
      curl -sf --max-time 2 http://127.0.0.1:$port/v1/models >/dev/null 2>&1 && echo " [healthy :$port]" || echo " [unavailable]"
    else
      curl -sf --max-time 2 http://127.0.0.1:$port/health >/dev/null 2>&1 && echo " [healthy :$port]" || echo " [unavailable]"
    fi
  done
  echo
  echo "== Docker Stack"
  (cd "$PROJECT" && /usr/local/bin/docker-compose ps)
}

case "$ACTION" in
  reload-app)
    # Deploy a separately verified image without restarting shared model services.
    systemctl is-active --quiet "$TARGET_UNIT" || { echo "!! $TARGET_UNIT must already be active" >&2; exit 1; }
    files=(-f "$PROJECT/compose.yaml")
    if [[ "$TARGET_UNIT" == komorebi-npu.service ]]; then
      files+=(-f /home/chihmin/.hermes/skills/restart-service/scripts/komorebi-npu-only.compose.yaml)
    fi
    docker compose "${files[@]}" up -d --no-build --no-deps app
    for _ in $(seq 1 30); do
      if curl -sf --max-time 5 http://127.0.0.1:8792/api/config >/dev/null; then
        echo "== Komorebi app ready; model services unchanged"
        exit 0
      fi
      sleep 2
    done
    echo "!! Komorebi app did not become healthy" >&2
    exit 1
    ;;
  restart|start)
    echo "== starting $TARGET_UNIT..."
    sudo -n systemctl restart "$TARGET_UNIT"
    echo "== waiting for Komorebi health"
    for _ in $(seq 1 30); do
      if curl -sf --max-time 5 http://127.0.0.1:8792/api/config >/dev/null && {
        [[ "$TARGET_UNIT" != komorebi-npu.service ]] ||
        curl -sf --max-time 5 http://127.0.0.1:52625/v1/models >/dev/null;
      }; then
        status
        exit 0
      fi
      sleep 2
    done
    echo "!! Komorebi did not become healthy" >&2
    status
    exit 1
    ;;
  disable|stop)
    echo "== stopping $TARGET_UNIT..."
    sudo -n systemctl stop "$TARGET_UNIT"
    status
    ;;
  status)
    status
    ;;
  *)
    echo "Usage: $0 [start|restart|reload-app|stop|disable|status]" >&2
    exit 2
    ;;
esac
