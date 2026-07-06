#!/usr/bin/env bash
# restart-gemini: restart the whole LazyGravity -> Antigravity (Gemini IDE) stack
# via systemd and verify it end-to-end.
#
# Stack (all `systemctl --user`, tied together by lazygravity.target):
#   openclaw-xvfb.service          -> headless X display :99
#   lazygravity-antigravity.service-> Antigravity IDE on :99, CDP 9223 (forces X11 ozone)
#   lazygravity-bot.service        -> Discord bot (DISPLAY=:99), ordered After antigravity
#   lazygravity-autoapprove.service-> clicks "Always Allow" browser prompts
#
# Usage: restart.sh [--no-bot]   (--no-bot: only restart Xvfb + Antigravity)
set -uo pipefail
CDP_PORT="9223"
log(){ printf '  %s\n' "$*"; }
cdp_up(){ curl -sf "http://localhost:${CDP_PORT}/json/version" >/dev/null 2>&1; }

echo "== restart-gemini =="

if [ "${1:-}" = "--no-bot" ]; then
  log "[1/2] restarting Xvfb + Antigravity only..."
  systemctl --user reset-failed lazygravity-antigravity.service 2>/dev/null || true
  systemctl --user restart openclaw-xvfb.service lazygravity-antigravity.service
else
  log "[1/2] restarting full stack (lazygravity.target)..."
  systemctl --user reset-failed lazygravity-antigravity.service 2>/dev/null || true
  systemctl --user restart lazygravity.target
fi

# antigravity unit holds in 'activating' until CDP answers; poll ourselves too
for i in $(seq 1 40); do cdp_up && break; sleep 1; done

log "[2/2] verifying..."
for u in openclaw-xvfb lazygravity-antigravity lazygravity-bot lazygravity-autoapprove; do
  printf '      %-26s %s\n' "$u" "$(systemctl --user is-active ${u}.service)"
done
if cdp_up; then log "CDP ${CDP_PORT}: responding"; else log "CDP ${CDP_PORT}: DOWN"; fi
curl -sf "http://localhost:${CDP_PORT}/json/list" 2>/dev/null \
  | python3 -c "import sys,json;d=json.load(sys.stdin);ps=[p.get('title') for p in d if p.get('type')=='page' and 'workbench' in (p.get('url') or '')];print('\n'.join('      workbench: '+t for t in ps) or '      (no workbench page yet)')" 2>/dev/null

echo
echo "Done. Retry the workspace command in Discord."
echo "Full check: cd ~/src/LazyGravity && node dist/bin/cli.js doctor"
