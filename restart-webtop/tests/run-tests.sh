#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
SCRIPT="$ROOT/scripts/restart.sh"
SKILL="$ROOT/SKILL.md"

fail() { echo "FAIL: $*" >&2; exit 1; }
assert_contains() { grep -Fq -- "$2" "$1" || fail "$1 does not contain: $2"; }
assert_not_contains() { grep -Fq -- "$2" "$1" && fail "$1 unexpectedly contains: $2" || true; }

[[ -f "$SCRIPT" ]] || fail "restart script is missing"
[[ -x "$SCRIPT" ]] || fail "restart script is not executable"
bash -n "$SCRIPT"

assert_not_contains "$SCRIPT" 'WEBTOP_TOKEN='
assert_contains "$SCRIPT" 'WEBTOP_PASSWORD=2169'
assert_contains "$SCRIPT" 'WEBTOP_SESSION_SECRET='
assert_contains "$SCRIPT" 'npm run build'
assert_contains "$SCRIPT" 'tailscale/tailscale:latest 0755 /state'
assert_contains "$SCRIPT" 'systemctl --user daemon-reload'
assert_contains "$SCRIPT" 'systemctl --user enable --now webtop-amd.service'
assert_contains "$SCRIPT" 'systemctl --user restart webtop-amd.service'
assert_contains "$SCRIPT" 'up -d --build --force-recreate frontend'
assert_contains "$SCRIPT" 'up -d --force-recreate tailscale'
assert_contains "$SCRIPT" 'http://127.0.0.1:8787/api/health'
assert_contains "$SCRIPT" 'tailscale status --json'
assert_contains "$SCRIPT" 'tailscale serve status --json'
assert_contains "$SCRIPT" 'expected_funnel'
assert_contains "$SCRIPT" '@1.1.1.1'
assert_contains "$SCRIPT" '--resolve'
assert_contains "$SCRIPT" 'public_ok=false'
assert_contains "$SCRIPT" '"https://$FQDN/api/health"'

front_line=$(grep -nF 'up -d --build --force-recreate frontend' "$SCRIPT" | head -1 | cut -d: -f1)
ts_line=$(grep -nF 'up -d --force-recreate tailscale' "$SCRIPT" | head -1 | cut -d: -f1)
(( front_line < ts_line )) || fail "frontend must be recreated before its network-sharing sidecar"

assert_contains "$SKILL" '/restart-webtop'
assert_contains "$SKILL" '~/.config/webtop-amd/env'
assert_not_contains "$SKILL" 'WEBTOP_TOKEN'
assert_contains "$SKILL" 'WEBTOP_PASSWORD'
assert_contains "$SKILL" 'WEBTOP_SESSION_SECRET'
assert_contains "$SKILL" 'amdgpu_top'
assert_contains "$SKILL" 'network_mode: service:frontend'
assert_contains "$SKILL" 'stale network namespace'
assert_contains "$SKILL" 'TS_AUTHKEY'
assert_contains "$SKILL" '60 秒'
assert_contains "$SKILL" '公開 Funnel'
assert_contains "$SKILL" 'restart.sh'

echo "PASS: restart-webtop skill contract"
