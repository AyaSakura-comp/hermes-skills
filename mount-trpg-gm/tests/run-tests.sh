#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$SKILL_DIR/scripts/mount.sh"
SKILL="$SKILL_DIR/SKILL.md"
REPO="${TRPG_GM_REPO:-/home/chihmin/src/trpg-gm-skill}"
REAL_PI="${PI_BIN:-/home/chihmin/.local/bin/pi}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

[[ -f "$SKILL" ]] || { echo "FAIL: missing $SKILL" >&2; exit 1; }
grep -Fq 'name: mount-trpg-gm' "$SKILL"
grep -Fq 'scripts/mount.sh' "$SKILL"
[[ -x "$SCRIPT" ]] || { echo "FAIL: missing executable $SCRIPT" >&2; exit 1; }

cat >"$TMP/systemctl" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"$SYSTEMCTL_LOG"
if [[ "$*" == "--user is-active pi-discord-gateway.service" ]] ||
   [[ "$*" == "--user is-active piweb-worker.service" ]]; then
  echo active
  exit 0
fi
exit 1
EOF
chmod +x "$TMP/systemctl"

export SYSTEMCTL_LOG="$TMP/systemctl.log"
for run in 1 2; do
  HOME="$TMP/home" \
  PI_BIN="$REAL_PI" \
  SYSTEMCTL_BIN="$TMP/systemctl" \
  TRPG_GM_REPO="$REPO" \
    "$SCRIPT" >"$TMP/run-$run.out"
done

python3 - "$TMP/home/.pi/agent/settings.json" "$REPO" <<'PY'
import json
import pathlib
import sys
settings = json.loads(pathlib.Path(sys.argv[1]).read_text())
repo = str(pathlib.Path(sys.argv[2]).resolve())
packages = settings.get("packages", [])
resolved = []
for package in packages:
    source = package if isinstance(package, str) else package.get("source", "")
    if source.startswith(("npm:", "git:", "http://", "https://", "ssh://")):
        continue
    resolved.append(str((pathlib.Path(sys.argv[1]).parent / source).resolve()) if not pathlib.Path(source).is_absolute() else str(pathlib.Path(source).resolve()))
assert resolved.count(repo) == 1, (packages, resolved, repo)
PY

grep -Fq 'TRPG GM package mounted globally' "$TMP/run-2.out"
grep -Fq 'Piscord gateway: active' "$TMP/run-2.out"
grep -Fq 'Piweb worker: active' "$TMP/run-2.out"
if grep -Eq '(^| )restart( |$)' "$SYSTEMCTL_LOG"; then
  echo "FAIL: mount script must not interrupt Piscord or Piweb" >&2
  exit 1
fi

echo "PASS: mount-trpg-gm installs idempotently for shared Pi HOME without restarting gateways"
