#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage: run-pi-subagent.sh [--cwd DIR] (--task-file FILE | -- TASK...)

Runs an isolated Pi agent with the parent session's active provider, model, and
reasoning level. Skills are disabled in the child to prevent recursive dispatch.
EOF
}

cwd="$PWD"
task_file=""
task=""

while (($#)); do
  case "$1" in
    --cwd)
      (($# >= 2)) || { usage; exit 2; }
      cwd="$2"
      shift 2
      ;;
    --task-file)
      (($# >= 2)) || { usage; exit 2; }
      task_file="$2"
      shift 2
      ;;
    --)
      shift
      task="$*"
      break
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage
      exit 2
      ;;
  esac
done

if [[ -n "$task_file" ]]; then
  [[ -f "$task_file" ]] || { echo "Task file not found: $task_file" >&2; exit 2; }
  task="$(<"$task_file")"
fi

[[ -n "$task" ]] || { echo "Task must not be empty" >&2; exit 2; }
[[ -d "$cwd" ]] || { echo "Working directory not found: $cwd" >&2; exit 2; }
: "${PI_PROVIDER:?PI_PROVIDER is required to inherit the parent provider}"
: "${PI_MODEL:?PI_MODEL is required to inherit the parent model}"
: "${PI_REASONING_LEVEL:?PI_REASONING_LEVEL is required to inherit the parent thinking level}"

if [[ -n "${PI_BIN:-}" && -x "$PI_BIN" ]]; then
  pi_command="$PI_BIN"
elif command -v pi >/dev/null 2>&1; then
  pi_command="$(command -v pi)"
else
  echo "Pi executable not found; set PI_BIN or add pi to PATH" >&2
  exit 127
fi

cd "$cwd"
exec "$pi_command" \
  --model "$PI_PROVIDER/$PI_MODEL" \
  --thinking "$PI_REASONING_LEVEL" \
  --no-session \
  --no-skills \
  -p \
  "$task"
