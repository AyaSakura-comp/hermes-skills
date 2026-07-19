#!/usr/bin/env bash
set -euo pipefail

script="$(cd "$(dirname "$0")/.." && pwd)/scripts/restart.sh"

assert_contains() {
  local needle="$1"
  grep -Fq -- "$needle" "$script" || {
    echo "Expected restart script to contain: $needle" >&2
    exit 1
  }
}

assert_contains 'EXPECTED_MIOPEN_FIND_MODE="FAST"'
assert_contains 'MIOPEN_FIND_MODE='
assert_contains 'MIOpen mode: FAST'
assert_contains 'MIOpen mode mismatch'

echo "restart-taigi MIOpen policy checks: OK"
