#!/usr/bin/env bash
# Isolated quantized embedding hosts; NEVER touches Qwen/Strata or the PyTorch GPU service.
set -euo pipefail
action=${1:-status}; quant=${2:-all}
case "$action" in start|restart|stop|status) ;; *) echo 'Invalid action' >&2; exit 2;; esac
case "$quant" in Q4_0|Q8_0|Q8_FLASH) quants=("$quant");; all) quants=(Q4_0 Q8_0);; *) echo 'Only Q4_0/Q8_0/Q8_FLASH allowed' >&2; exit 2;; esac
if [[ $action == start || $action == restart ]]; then systemctl --user daemon-reload; fi
for q in "${quants[@]}"; do
 case "$q" in
  Q4_0) unit="embeddinggemma2-gguf@Q4_0.service"; port=8796;;
  Q8_0) unit="embeddinggemma2-gguf@Q8_0.service"; port=8797;;
  Q8_FLASH) unit="embeddinggemma2-gguf-flash.service"; port=8799;;
 esac
 if [[ $action != status ]]; then systemctl --user "$action" "$unit"; fi
 if [[ $action == stop ]]; then continue; fi
 ok=false
 for attempt in $(seq 1 60); do
  if curl -fsS --max-time 2 "http://127.0.0.1:$port/health" | /home/chihmin/workloads/embeddinggemma2/.venv/bin/python -c 'import json,sys; assert json.load(sys.stdin)["status"]=="ok"' 2>/dev/null && [[ $(systemctl --user is-active "$unit") == active ]]; then
   printf '%s ready on loopback :%s PID=%s\n' "$q" "$port" "$(systemctl --user show "$unit" -p MainPID --value)"
   ok=true;break
  fi
  if [[ $action == status ]]; then break; fi
  sleep 1
 done
 if ! $ok; then
  journalctl --user -u "$unit" -n 35 --no-pager >&2 || true
  echo "$unit not ready; do not repair shared model services" >&2;exit 1
 fi
done
