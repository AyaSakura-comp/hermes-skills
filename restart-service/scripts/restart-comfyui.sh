#!/usr/bin/env bash
set -euo pipefail

unit=comfyui.service
url=http://127.0.0.1:8188/system_stats

systemctl --user daemon-reload
systemctl --user restart "$unit"
for _ in $(seq 1 90); do
    if curl -fsS "$url" >/dev/null 2>&1; then
        printf 'ComfyUI restart complete: %s is healthy at %s\n' "$unit" "$url"
        exit 0
    fi
    sleep 1
done

systemctl --user status "$unit" --no-pager >&2 || true
journalctl --user -u "$unit" -n 80 --no-pager >&2 || true
printf 'ComfyUI health check failed: %s\n' "$url" >&2
exit 1
