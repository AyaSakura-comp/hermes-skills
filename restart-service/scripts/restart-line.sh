#!/usr/bin/env bash
# LINE desktop (Wine via Bottles flatpak) on headless Xvfb :121 -- user systemd units
#   line-xvfb.service (Xvfb :121)  +  line-wine.service (LINE.exe, Restart=always)
# Usage: restart-line.sh [start|restart|stop|status]
# Exit codes (status/start/restart): 0 running+logged in, 2 running but at the LOGIN SCREEN (needs QR scan), 1 down.
set -uo pipefail

DIR=$HOME/line-wine-test
action=${1:-restart}

case "$action" in
  start)   systemctl --user daemon-reload; systemctl --user start line-xvfb.service line-wine.service ;;
  restart) systemctl --user daemon-reload; systemctl --user restart line-xvfb.service; systemctl --user restart line-wine.service ;;
  stop)    systemctl --user stop line-wine.service line-xvfb.service; echo "LINE stopped"; exit 0 ;;
  status)  ;;
  *) echo "usage: $0 [start|restart|stop|status]" >&2; exit 64 ;;
esac

# LINE needs up to ~60 s to start (longer right after a self-update)
if [ "$action" != status ]; then
  for _ in $(seq 1 60); do pgrep -f '[L]INE\.exe run' >/dev/null && break; sleep 2; done
  sleep 8
fi
"$DIR/line-status.sh"
rc=$?
if [ "$rc" -eq 2 ]; then
  echo "-> LINE is at the login screen. Make a fresh QR with: python3 -W ignore $DIR/line_qr.py"
fi
if [ "$rc" -eq 1 ]; then
  journalctl --user -u line-wine.service -n 40 --no-pager >&2 || true
fi
exit "$rc"
