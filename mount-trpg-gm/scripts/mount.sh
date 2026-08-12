#!/usr/bin/env bash
set -euo pipefail

REPO="${TRPG_GM_REPO:-/home/chihmin/src/trpg-gm-skill}"
SYSTEMCTL="${SYSTEMCTL_BIN:-systemctl}"

if [[ -n "${PI_BIN:-}" ]]; then
  PI="$PI_BIN"
elif [[ -x "$HOME/.local/bin/pi" ]]; then
  PI="$HOME/.local/bin/pi"
elif command -v pi >/dev/null 2>&1; then
  PI="$(command -v pi)"
else
  echo "ERROR: Pi executable not found; set PI_BIN." >&2
  exit 1
fi

REPO="$(python3 -c 'import pathlib,sys; print(pathlib.Path(sys.argv[1]).resolve())' "$REPO")"
[[ -f "$REPO/package.json" ]] || { echo "ERROR: missing $REPO/package.json" >&2; exit 1; }
[[ -f "$REPO/.agents/skills/trpg-gm/SKILL.md" ]] || { echo "ERROR: missing trpg-gm skill in $REPO" >&2; exit 1; }
[[ -f "$REPO/extensions/trpg-gm-guard.js" ]] || { echo "ERROR: missing TRPG GM extension in $REPO" >&2; exit 1; }

"$PI" install "$REPO"
if ! "$PI" list | grep -Fq "$REPO"; then
  echo "ERROR: Pi installed-package list does not resolve to $REPO" >&2
  exit 1
fi

service_state() {
  local unit="$1"
  local label="$2"
  local state
  state="$($SYSTEMCTL --user is-active "$unit" 2>/dev/null || true)"
  [[ -n "$state" ]] || state="unavailable"
  printf '%s: %s\n' "$label" "$state"
}

echo "TRPG GM package mounted globally: $REPO"
echo "Shared Pi settings: $HOME/.pi/agent/settings.json"
service_state pi-discord-gateway.service "Piscord gateway"
service_state piweb-worker.service "Piweb worker"
echo "No service restart was performed: both gateways spawn a fresh Pi process for the next message."
echo "Piscord/Piweb usage: 請使用 trpg-gm skill，開一個新團。"
echo "Pi TUI usage: /skill:trpg-gm"
