#!/usr/bin/env bash
set -euo pipefail

SCRIPT=$(cd "$(dirname "$0")/.." && pwd)/scripts/restart-qwen-mtp.sh
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin"
cat >"$TMP/bin/sudo" <<'EOF'
#!/usr/bin/env bash
exit 99
EOF
chmod +x "$TMP/bin/sudo"

fail() { echo "FAIL: $*" >&2; exit 1; }

out=$(PATH="$TMP/bin:$PATH" "$SCRIPT" --help) || fail '--help should succeed without touching systemd'
grep -q 'flashhead' <<<"$out" || fail '--help must list flashhead'
grep -q 'draft-flashhead' <<<"$out" || fail '--help must list draft-flashhead'
grep -q 'f16-baseline' <<<"$out" || fail '--help must list f16-baseline'

out=$(PATH="$TMP/bin:$PATH" "$SCRIPT" --print-config) || fail 'default --print-config should succeed'
grep -q 'gfx1151-all-flashhead-15bd9b0028/bin/llama-server' <<<"$out" || fail 'default must select multimodal-safe all-FlashHead deployment'
grep -q 'LLAMA_FLASHHEAD_PROBES=256' <<<"$out" || fail 'default must enable 256 FlashHead probes'
grep -q 'LLAMA_FLASHHEAD_TARGET=1' <<<"$out" || fail 'default must enable target FlashHead'
grep -q -- '-flashhead.gguf' <<<"$out" || fail 'default must select FlashHead GGUF'

out=$(PATH="$TMP/bin:$PATH" "$SCRIPT" --print-config draft-flashhead) || fail 'draft-only --print-config should succeed'
grep -q 'gfx1151-all-flashhead-15bd9b0028/bin/llama-server' <<<"$out" || fail 'draft-only must use the same multimodal-safe binary'
grep -q 'LLAMA_FLASHHEAD_PROBES=256' <<<"$out" || fail 'draft-only must enable 256 probes'
if grep -q 'LLAMA_FLASHHEAD_TARGET' <<<"$out"; then fail 'draft-only must not enable target FlashHead'; fi

out=$(PATH="$TMP/bin:$PATH" "$SCRIPT" --print-config f16-baseline) || fail 'baseline --print-config should succeed'
grep -q 'gfx1151-all-flashhead-15bd9b0028/bin/llama-server' <<<"$out" || fail 'baseline must use the same multimodal-safe binary as FlashHead'
grep -q 'selective-Q4_0.gguf' <<<"$out" || fail 'baseline must select dense selective-Q4 GGUF'
if grep -q 'LLAMA_FLASHHEAD_PROBES\|LLAMA_FLASHHEAD_TARGET' <<<"$out"; then fail 'baseline must not set FlashHead variables'; fi
if grep -q -- '-flashhead.gguf' <<<"$out"; then fail 'baseline must not select FlashHead GGUF'; fi

if PATH="$TMP/bin:$PATH" "$SCRIPT" --print-config invalid >/dev/null 2>&1; then
  fail 'invalid variant must fail'
fi

printf 'PASS: qwen variant selection\n'
