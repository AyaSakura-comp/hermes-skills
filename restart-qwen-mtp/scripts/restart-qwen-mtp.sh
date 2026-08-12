#!/usr/bin/env bash
set -euo pipefail

SERVICE=qwen-mtp.service
HEALTH_URL=http://127.0.0.1:8001/health
MODELS_URL=http://127.0.0.1:8001/v1/models
TIMEOUT_SECONDS=${QWEN_MTP_RESTART_TIMEOUT:-300}
DROPIN=/etc/systemd/system/qwen-mtp.service.d/zz-flashhead.conf
FLASH_DEPLOY=/home/chihmin/llama-mtp-deploy/gfx1151-dynamic-mtp-pp-15bd9b0028-120407c7b2
DENSE_DEPLOY=$FLASH_DEPLOY
MODEL_DIR=/home/chihmin/models/Qwen3.6-35B-A3B-selective-Q4_0-proof
FLASH_MODEL=$MODEL_DIR/Qwen3.6-35B-A3B-UD-Q4_K_M-selective-Q4_0-flashhead.gguf
DENSE_MODEL=$MODEL_DIR/Qwen3.6-35B-A3B-UD-Q4_K_M-selective-Q4_0.gguf
MM_PROJ=/home/chihmin/models/mmproj.gguf

usage() {
    cat <<'EOF'
Usage: restart-qwen-mtp.sh [flashhead|draft-flashhead|f16-baseline]
       restart-qwen-mtp.sh --print-config [flashhead|draft-flashhead|f16-baseline]

Variants:
  flashhead        Draft + target FlashHead with F16 KV (default, approximate target)
  draft-flashhead  Draft-only FlashHead with dense target verification
  f16-baseline     Dense draft and target LM heads with F16 KV
EOF
}

normalize_variant() {
    case "${1:-flashhead}" in
        flashhead|all-flashhead|all) printf '%s\n' flashhead ;;
        draft-flashhead|partial|draft) printf '%s\n' draft-flashhead ;;
        f16-baseline|f16|baseline|dense) printf '%s\n' f16-baseline ;;
        *) echo "Unknown Qwen variant: $1" >&2; usage >&2; return 64 ;;
    esac
}

render_config() {
    local variant=$1
    case "$variant" in
        flashhead)
            cat <<EOF
# Managed by restart-qwen-mtp.sh: dynamic MTP PP reserve, draft + target FlashHead, patch 120407c7b2.
# Target retrieval is approximate. This filename must sort after selective-q4-proof.conf.
[Service]
Environment=LLAMA_FLASHHEAD_PROBES=256
Environment=LLAMA_FLASHHEAD_TARGET=1
Environment=LD_LIBRARY_PATH=$FLASH_DEPLOY/bin:/opt/rocm-7.2.2/lib
ExecStart=
ExecStart=$FLASH_DEPLOY/bin/llama-server -m $FLASH_MODEL --port 8001 --host 0.0.0.0 -ngl 99 -fit off -fa 1 -c 260000 -np 1 -b 4096 -ub 2048 --mmproj $MM_PROJ --alias qwen3.6-35b-q4 --spec-type mtp --spec-draft-n-max 3 --log-file /tmp/qwen35-server.log
EOF
            ;;
        draft-flashhead)
            cat <<EOF
# Managed by restart-qwen-mtp.sh: dynamic MTP PP reserve, draft-only FlashHead with dense target, patch 120407c7b2.
# This filename must sort after selective-q4-proof.conf.
[Service]
Environment=LLAMA_FLASHHEAD_PROBES=256
Environment=LD_LIBRARY_PATH=$FLASH_DEPLOY/bin:/opt/rocm-7.2.2/lib
ExecStart=
ExecStart=$FLASH_DEPLOY/bin/llama-server -m $FLASH_MODEL --port 8001 --host 0.0.0.0 -ngl 99 -fit off -fa 1 -c 260000 -np 1 -b 4096 -ub 2048 --mmproj $MM_PROJ --alias qwen3.6-35b-q4 --spec-type mtp --spec-draft-n-max 3 --log-file /tmp/qwen35-server.log
EOF
            ;;
        f16-baseline)
            cat <<EOF
# Managed by restart-qwen-mtp.sh: dense-head F16-KV baseline.
# This filename must sort after selective-q4-proof.conf.
[Service]
ExecStart=
ExecStart=$DENSE_DEPLOY/bin/llama-server -m $DENSE_MODEL --port 8001 --host 0.0.0.0 -ngl 99 -fit off -fa 1 -c 260000 -np 1 -b 4096 -ub 2048 --mmproj $MM_PROJ --alias qwen3.6-35b-q4 --spec-type mtp --spec-draft-n-max 3 --log-file /tmp/qwen35-server.log
EOF
            ;;
    esac
}

fail() {
    echo "ERROR: $*" >&2
    sudo -n systemctl status "$SERVICE" --no-pager -l >&2 || true
    sudo -n journalctl -u "$SERVICE" -n 80 --no-pager >&2 || true
    exit 1
}

if [[ "${1:-}" == --help || "${1:-}" == -h ]]; then
    usage
    exit 0
fi

if [[ "${1:-}" == --print-config ]]; then
    [[ $# -le 2 ]] || { usage >&2; exit 64; }
    variant=$(normalize_variant "${2:-flashhead}") || exit $?
    render_config "$variant"
    exit 0
fi

[[ $# -le 1 ]] || { usage >&2; exit 64; }
variant=$(normalize_variant "${1:-flashhead}") || exit $?

case "$variant" in
    flashhead|draft-flashhead)
        expected_exe=$FLASH_DEPLOY/bin/llama-server
        expected_model=$FLASH_MODEL
        ;;
    f16-baseline)
        expected_exe=$DENSE_DEPLOY/bin/llama-server
        expected_model=$DENSE_MODEL
        ;;
esac

command -v systemctl >/dev/null || fail "systemctl is unavailable"
command -v curl >/dev/null || fail "curl is unavailable"
[[ -x "$expected_exe" ]] || fail "missing executable for $variant: $expected_exe"
[[ -r "$expected_model" ]] || fail "missing model for $variant: $expected_model"

config_tmp=$(mktemp)
trap 'rm -f "$config_tmp"' EXIT
render_config "$variant" >"$config_tmp"
if ! cmp -s "$config_tmp" "$DROPIN"; then
    if [[ -e "$DROPIN" ]]; then
        backup="$DROPIN.bak-$(date +%Y%m%d-%H%M%S)"
        sudo -n cp "$DROPIN" "$backup" || fail "could not back up variant drop-in"
        echo "Backed up previous variant drop-in: $backup"
    fi
    sudo -n install -o root -g root -m 0644 "$config_tmp" "$DROPIN" || fail "could not install $variant drop-in"
fi

if ! sudo -n powerprofilesctl set performance; then
    echo "WARNING: performance power profile is unavailable; continuing with the current platform profile" >&2
fi
sudo -n systemctl daemon-reload || fail "systemd daemon-reload failed"
sudo -n systemctl restart "$SERVICE" || fail "systemd restart failed"

health=''
for ((elapsed = 0; elapsed < TIMEOUT_SECONDS; elapsed++)); do
    if health=$(curl -fsS --max-time 2 "$HEALTH_URL" 2>/dev/null); then
        break
    fi
    if ! systemctl is-active --quiet "$SERVICE"; then
        fail "service stopped while loading $variant"
    fi
    sleep 1
done
[[ -n "$health" ]] || fail "health endpoint did not become ready within ${TIMEOUT_SECONDS}s"

state=$(systemctl is-active "$SERVICE" 2>/dev/null || true)
[[ "$state" == active ]] || fail "service state is $state"

pid=$(systemctl show -p MainPID --value "$SERVICE")
[[ "$pid" =~ ^[1-9][0-9]*$ && -r "/proc/$pid/exe" ]] || fail "invalid live MainPID: $pid"

exe=$(readlink -f "/proc/$pid/exe")
[[ "$exe" == "$expected_exe" ]] || fail "wrong executable for $variant: $exe"
exe_dir=$(dirname "$exe")
hip_lib=$(grep -m1 -o '/[^ ]*/libggml-hip\.so[^ ]*' "/proc/$pid/maps" || true)
[[ -n "$hip_lib" ]] || fail "live process has no mapped libggml-hip.so"
hip_lib=$(readlink -f "$hip_lib")
[[ $(dirname "$hip_lib") == "$exe_dir" ]] || fail "libggml-hip is not self-contained: exe=$exe hip=$hip_lib"

cmdline=$(tr '\0' ' ' <"/proc/$pid/cmdline")
[[ "$cmdline" == *"-m $expected_model "* ]] || fail "wrong GGUF for $variant: $cmdline"
environ=$(tr '\0' '\n' <"/proc/$pid/environ")
for denied in GPU_MAX_HW_QUEUES ROCP_TOOL_ATTACH; do
    if grep -q "^${denied}=" <<<"$environ"; then
        fail "declined production environment variable is set: $denied"
    fi
done

pid_journal=$(journalctl _PID="$pid" --no-pager 2>/dev/null || true)
if [[ "$variant" == flashhead || "$variant" == draft-flashhead ]]; then
    grep -q 'FlashHead tables found - 7760 clusters of 32, 4096 static tokens' <<<"$pid_journal" \
        || fail "current FlashHead process did not log table activation"
    grep -q '^LLAMA_FLASHHEAD_PROBES=256$' <<<"$environ" \
        || fail "current FlashHead process does not have 256 probes"
    if [[ "$variant" == flashhead ]]; then
        grep -q '^LLAMA_FLASHHEAD_TARGET=1$' <<<"$environ" \
            || fail "all-FlashHead process does not have target retrieval enabled"
        grep -q 'approximate target-side FlashHead is enabled' <<<"$pid_journal" \
            || fail "all-FlashHead process did not log the approximate-target warning"
    elif grep -q '^LLAMA_FLASHHEAD_TARGET=' <<<"$environ"; then
        fail "draft-only FlashHead unexpectedly inherited target retrieval"
    fi
else
    if grep -q 'FlashHead tables found' <<<"$pid_journal"; then
        fail "dense baseline unexpectedly activated FlashHead tables"
    fi
    if grep -q '^LLAMA_FLASHHEAD_PROBES=\|^LLAMA_FLASHHEAD_TARGET=' <<<"$environ"; then
        fail "dense baseline unexpectedly inherited FlashHead variables"
    fi
fi

grep -q 'K (f16).*V (f16)' <<<"$pid_journal" || fail "$variant did not report F16 KV"

models=$(curl -fsS --max-time 10 "$MODELS_URL") || fail "models endpoint failed"
model_summary=$(python3 -c 'import json,sys; m=json.load(sys.stdin)["data"][0]; print("{} context={}".format(m.get("id"), m.get("meta", {}).get("n_ctx", "unknown")))' <<<"$models") || fail "could not parse models response"

profile=$(powerprofilesctl get 2>/dev/null || true)
if [[ -n "$profile" && "$profile" != performance ]]; then
    fail "power profile changed unexpectedly to $profile"
fi
profile=${profile:-unavailable}

gemma_state=$(systemctl is-active gemma-mtp.service 2>/dev/null || true)
gemma_health=not-checked
if [[ "$gemma_state" == active ]]; then
    if curl -fsS --max-time 2 http://127.0.0.1:8002/health >/dev/null 2>&1; then
        gemma_health=ok
    else
        gemma_health=unhealthy
    fi
fi

printf 'Qwen MTP variant verified\n'
printf '  variant: %s\n' "$variant"
printf '  service: %s\n' "$state"
printf '  health: %s\n' "$health"
printf '  pid: %s\n' "$pid"
printf '  executable: %s\n' "$exe"
printf '  model GGUF: %s\n' "$expected_model"
printf '  HIP library: %s\n' "$hip_lib"
printf '  model API: %s\n' "$model_summary"
printf '  KV cache: F16 target/draft\n'
printf '  power profile: %s\n' "$profile"
printf '  Gemma: %s (health=%s, port=8002)\n' "$gemma_state" "$gemma_health"
