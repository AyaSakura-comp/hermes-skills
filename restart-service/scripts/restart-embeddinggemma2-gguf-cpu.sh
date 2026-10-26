#!/usr/bin/env bash
set -euo pipefail
action=${1:-status}
unit=embeddinggemma2-gguf-cpu.service
case "$action" in start|restart|stop|status) ;; *) exit 2;; esac
if [[ $action == start || $action == restart ]]; then systemctl --user daemon-reload; fi
if [[ $action != status ]]; then systemctl --user "$action" "$unit"; fi
if [[ $action == stop ]]; then exit 0; fi
for attempt in $(seq 1 60); do
 if systemctl --user is-active --quiet "$unit" && curl -fsS --max-time 2 http://127.0.0.1:8798/health | python3 -c 'import json,sys; assert json.load(sys.stdin)["status"] == "ok"' 2>/dev/null; then
  pid=$(systemctl --user show "$unit" -p MainPID --value)
  if grep -E 'libggml-(hip|cuda|vulkan)' "/proc/$pid/maps" >/dev/null; then echo 'Unexpected GPU backend!' >&2; exit 1; fi
  printf 'Q8_0 CPU ready :8798 PID=%s (no GPU backend mapped)\n' "$pid";exit 0
 fi
 if [[ $action == status ]]; then break; fi
 sleep 1
done
journalctl --user -u "$unit" -n 35 --no-pager >&2
exit 1
