#!/usr/bin/env bash
set -euo pipefail

UNIT=${PISCORD_UNIT:-pi-discord-gateway.service}
EXPECTED_ENTRYPOINT=${PISCORD_ENTRYPOINT:-/home/chihmin/src/pi-discord-gateway/dist/cli/index.js}

log() { printf '\n==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

command -v systemctl >/dev/null || die 'missing required command: systemctl'
[[ -f "$EXPECTED_ENTRYPOINT" ]] || die "Piscord build not found: $EXPECTED_ENTRYPOINT"

log "Restart Piscord"
systemctl --user daemon-reload
systemctl --user restart "$UNIT"

log "Verify systemd process"
for _ in $(seq 1 20); do
  if [[ $(systemctl --user is-active "$UNIT" 2>/dev/null || true) == active ]]; then
    pid=$(systemctl --user show "$UNIT" -p MainPID --value)
    if [[ $pid =~ ^[1-9][0-9]*$ ]] && [[ -r /proc/$pid/cmdline ]]; then
      cmdline=$(tr '\0' ' ' </proc/$pid/cmdline)
      [[ $cmdline == *"$EXPECTED_ENTRYPOINT"* ]] || die "unexpected Piscord entrypoint: $cmdline"
      break
    fi
  fi
  sleep 1
done
[[ ${pid:-0} =~ ^[1-9][0-9]*$ ]] || die 'Piscord did not become active'

log "Verify Discord connection"
connected=false
for _ in $(seq 1 20); do
  if journalctl --user -u "$UNIT" --since '-30 seconds' --no-pager 2>/dev/null | grep -q '"msg":"Gateway running"'; then
    connected=true
    break
  fi
  sleep 1
done
$connected || {
  journalctl --user -u "$UNIT" -n 80 --no-pager >&2 || true
  die 'Piscord restarted but did not report Gateway running'
}

printf '\nPiscord restart complete\n  Unit: %s\n  PID:  %s\n  Entrypoint: %s\n' "$UNIT" "$pid" "$EXPECTED_ENTRYPOINT"
