#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
SCRIPT="$ROOT/scripts/restart.sh"
SKILL="$ROOT/SKILL.md"

fail() { echo "FAIL: $*" >&2; exit 1; }
assert_contains() { grep -Fq -- "$2" "$1" || fail "$1 does not document: $2"; }

[[ -f "$SCRIPT" ]] || fail "restart script is missing"
[[ -x "$SCRIPT" ]] || fail "restart script is not executable"
bash -n "$SCRIPT"

assert_contains "$SCRIPT" 'systemctl --user enable --now pi-discord-gateway.service'
assert_contains "$SCRIPT" 'systemctl --user restart piweb-worker.service'
assert_contains "$SCRIPT" 'agent_state=$(systemctl --user is-active pi-discord-gateway.service)'
assert_contains "$SCRIPT" 'up -d --build --force-recreate app'
assert_contains "$SCRIPT" 'up -d --force-recreate tailscale'
assert_contains "$SCRIPT" 'http://127.0.0.1:8099/'
assert_contains "$SCRIPT" 'tailscale status --json'
assert_contains "$SCRIPT" 'tailscale serve status'
assert_contains "$SCRIPT" 'serve_ok=false'
if grep -Fq 'd.get(\"' "$SCRIPT"; then
  fail "embedded Python contains invalid backslash-escaped f-string expressions"
fi
assert_contains "$SCRIPT" '@1.1.1.1'
assert_contains "$SCRIPT" '--resolve'

app_line=$(grep -nF 'up -d --build --force-recreate app' "$SCRIPT" | head -1 | cut -d: -f1)
ts_line=$(grep -nF 'up -d --force-recreate tailscale' "$SCRIPT" | head -1 | cut -d: -f1)
(( app_line < ts_line )) || fail "app must be recreated before its network-sharing sidecar"

assert_contains "$SKILL" 'network_mode: service:app'
assert_contains "$SKILL" 'stale network namespace'
assert_contains "$SKILL" '502'
assert_contains "$SKILL" 'MagicDNS'
assert_contains "$SKILL" 'containerboot'
assert_contains "$SKILL" '60-second timeout'
assert_contains "$SKILL" '/restart-piweb'
assert_contains "$SKILL" 'pi-discord-gateway.service'
assert_contains "$SKILL" 'The Docker app alone is not a complete'

echo "PASS: restart-piweb skill contract"
