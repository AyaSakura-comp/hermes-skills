#!/usr/bin/env bash
# Central restart hub: operates ONLY the separately authorized fixed-sample GPU unit.
set -euo pipefail
unit=embeddinggemma2-gpu.service
action=${1:-status}
case "$action" in
  start) systemctl --user daemon-reload; systemctl --user start "$unit" ;;
  restart) systemctl --user daemon-reload; systemctl --user restart "$unit" ;;
  stop) systemctl --user stop "$unit"; exit 0 ;;
  status) ;;
  *) echo 'Usage: restart-embeddinggemma2-gpu.sh [start|restart|stop|status]' >&2; exit 2 ;;
esac
for attempt in $(seq 1 60); do
  if response=$(curl -fsS --connect-timeout 1 --max-time 2 http://127.0.0.1:8795/health 2>/dev/null); then
    pid=$(systemctl --user show "$unit" -p MainPID --value)
    if HEALTH_JSON="$response" EXPECTED_PID="$pid" /home/chihmin/workloads/embeddinggemma2/.venv/bin/python - <<'PY'
import json, os
r=json.loads(os.environ['HEALTH_JSON'])
assert r['ready'] and r['resident'] and r['device']=='cuda'
assert r['pid']==int(os.environ['EXPECTED_PID']) and r['pid']>0
print(json.dumps(r,ensure_ascii=False))
PY
    then exit 0; fi
  fi
  if [[ $action == status ]]; then break; fi
  sleep 1
done
systemctl --user status "$unit" --no-pager >&2 || true
journalctl --user -u "$unit" -n 25 --no-pager >&2 || true
echo 'Resident GPU sample service not verified; do not repair or stop shared model services.' >&2
exit 1
