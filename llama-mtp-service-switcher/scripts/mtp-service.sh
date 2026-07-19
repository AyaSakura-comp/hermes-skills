#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 {start|stop|restart} {qwen|gemma} | status" >&2
  exit 64
}

wait_for_api() {
  local expected="$1" payload
  for _ in $(seq 1 240); do
    if payload=$(curl -fsS --max-time 3 http://127.0.0.1:8001/v1/models 2>/dev/null) \
      && jq -e --arg expected "$expected" '.data[0].id == $expected' >/dev/null <<<"$payload"; then
      jq '.data[0] | {id, context: .meta.n_ctx}' <<<"$payload"
      return 0
    fi
    sleep 2
  done
  echo "Timed out waiting for $expected on port 8001" >&2
  return 1
}

if [[ "${1:-}" == "status" && $# -eq 1 ]]; then
  systemctl is-active qwen-mtp.service || true
  systemctl is-active gemma-mtp.service || true
  curl -fsS http://127.0.0.1:8001/v1/models | jq '.data[0] | {id, context: .meta.n_ctx}'
  exit 0
fi

[[ $# -eq 2 ]] || usage
action="$1"
model="$2"
case "$action" in start|stop|restart) ;; *) usage ;; esac
case "$model" in
  qwen) service=qwen-mtp.service; alias=qwen3.6-35b-q4 ;;
  gemma) service=gemma-mtp.service; alias=gemma-4-26b-a4b-qat-q4 ;;
  *) usage ;;
esac

sudo systemctl "$action" "$service"
if [[ "$action" != stop ]]; then
  wait_for_api "$alias"
fi
