#!/usr/bin/env bash
set -euo pipefail

skill_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
runner="$skill_dir/scripts/run-pi-subagent.sh"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

fake_pi="$tmp_dir/fake-pi"
capture="$tmp_dir/capture"
workdir="$tmp_dir/worktree"
task_file="$tmp_dir/task.txt"
mkdir -p "$workdir"
printf '%s\n' 'Inspect the repository and fix the failing test.' > "$task_file"

cat > "$fake_pi" <<'FAKE'
#!/usr/bin/env bash
set -euo pipefail
{
  printf 'PWD=%s\n' "$PWD"
  printf 'ARG=%s\n' "$@"
} > "$CAPTURE"
FAKE
chmod +x "$fake_pi"

CAPTURE="$capture" \
PI_BIN="$fake_pi" \
PI_PROVIDER="test-provider" \
PI_MODEL="test-model" \
PI_REASONING_LEVEL="xhigh" \
  "$runner" --cwd "$workdir" --task-file "$task_file"

cat > "$tmp_dir/expected" <<EOF
PWD=$workdir
ARG=--model
ARG=test-provider/test-model
ARG=--thinking
ARG=xhigh
ARG=--no-session
ARG=--no-skills
ARG=-p
ARG=Inspect the repository and fix the failing test.
EOF

diff -u "$tmp_dir/expected" "$capture"

if env -u PI_REASONING_LEVEL \
  PI_BIN="$fake_pi" PI_PROVIDER="test-provider" PI_MODEL="test-model" \
  "$runner" --cwd "$workdir" --task-file "$task_file" >"$tmp_dir/stdout" 2>"$tmp_dir/stderr"; then
  echo "expected missing PI_REASONING_LEVEL to fail" >&2
  exit 1
fi
grep -q 'PI_REASONING_LEVEL' "$tmp_dir/stderr"

echo "pi-subagent runner tests passed"
