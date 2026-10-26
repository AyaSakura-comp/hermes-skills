#!/usr/bin/env bash
set -euo pipefail
systemctl --user daemon-reload
systemctl --user enable --now omniparser.service >/dev/null
systemctl --user restart omniparser.service
for _ in {1..60}; do
  if curl -fsS http://127.0.0.1:8012/health >/tmp/omniparser-health.json 2>/dev/null; then
    cat /tmp/omniparser-health.json
    exit 0
  fi
  sleep 1
done
systemctl --user status omniparser.service --no-pager >&2
exit 1
