#!/usr/bin/env bash
# Interleaved cold-start A/B across llama-server variants on an isolated port.
#
# Usage:
#   ab-run.sh --root /tmp/my-ab --tokens 1024 --samples 3 \
#     --variant 'f16=BIN'                                  \
#     --variant 'q4tiled=BIN|kv=q4_0|env=GGML_CUDA_EXPERIMENTAL_GFX1151_Q4_KV_TILED=1'
#
# Variant spec: label=binary[|kv=TYPE][|env=VAR=VAL][|extra=ARGS][|model=PATH]
# The first variant is the baseline. Run order is interleaved automatically
# (v1 v2 v3 / v3 v2 v1 / v1 v2 v3 ...) so thermal drift cannot masquerade as a
# variant effect. Every sample restarts the server cold.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="" TOKENS=256 SAMPLES=3 PORT=8101
MODEL=/home/chihmin/models/Qwen3.6-35B-A3B-selective-Q4_0-proof/Qwen3.6-35B-A3B-UD-Q4_K_M-selective-Q4_0.gguf
PROMPT="$HERE/../assets/qwen-prompt-20000.txt"
BENCH="$HERE/bench_20k_prompt.py"
SPECS=()

while [ $# -gt 0 ]; do
  case "$1" in
    --root)    ROOT=$2; shift 2 ;;
    --tokens)  TOKENS=$2; shift 2 ;;
    --samples) SAMPLES=$2; shift 2 ;;
    --port)    PORT=$2; shift 2 ;;
    --model)   MODEL=$2; shift 2 ;;
    --prompt)  PROMPT=$2; shift 2 ;;
    --variant) SPECS+=("$2"); shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done
[ -n "$ROOT" ] && [ ${#SPECS[@]} -ge 1 ] || { echo "need --root and at least one --variant" >&2; exit 2; }
mkdir -p "$ROOT"

SERVER_PID=""
restore() {
  echo "[restore] $(date +%T)" | tee -a "$ROOT/driver.log"
  [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null
  sleep 5; pkill -f "llama-server.*--port $PORT" 2>/dev/null; sleep 3
  sudo -n powerprofilesctl set performance
  sudo -n systemctl start qwen-mtp.service
  sudo -n systemctl start gemma-mtp.service
}
trap restore EXIT

{
  echo "root=$ROOT tokens=$TOKENS samples=$SAMPLES port=$PORT"
  echo "model=$MODEL"
  echo "prompt=$(md5sum "$PROMPT")"
  for s in "${SPECS[@]}"; do echo "variant: $s"; done
} | tee "$ROOT/driver.log"

sudo -n powerprofilesctl set performance
sudo -n systemctl stop qwen-mtp.service gemma-mtp.service
sleep 10

field() {  # field <spec> <key> -> value or empty
  local spec=$1 key=$2 part
  IFS='|' read -ra parts <<< "$spec"
  for part in "${parts[@]:1}"; do
    [[ $part == $key=* ]] && { echo "${part#*=}"; return; }
  done
}

wait_idle() {
  local n=0 tries=0 b
  while [ $n -lt 10 ] && [ $tries -lt 300 ]; do
    b=$(cat /sys/class/drm/card1/device/gpu_busy_percent 2>/dev/null || echo 100)
    if [ "$b" -eq 0 ]; then n=$((n+1)); else n=0; fi
    tries=$((tries+1)); sleep 1
  done
}

run_sample() {  # run_sample <spec> <sample-number>
  local spec=$1 n=$2
  local label="${spec%%=*}" rest="${spec#*=}"
  local bin="${rest%%|*}"
  local kv;    kv=$(field "$spec" kv)
  local envs;  envs=$(field "$spec" env)
  local extra; extra=$(field "$spec" extra)
  local vmodel; vmodel=$(field "$spec" model)
  local effective_model="${vmodel:-$MODEL}"  # per-variant model override, fallback to global MODEL
  local tag="$label-$n"
  local log="$ROOT/$tag.server.log"

  local args=( -m "$effective_model" --port "$PORT" --host 127.0.0.1
               -ngl 99 -fit off -fa 1 -c 260000 -np 1 -b 4096 -ub 2048
               --mmproj /home/chihmin/models/mmproj.gguf
               --alias qwen3.6-35b-q4 --spec-type mtp --spec-draft-n-max 3 )
  [ -n "$kv" ] && args+=( -ctk "$kv" -ctv "$kv" -ctkd "$kv" -ctvd "$kv" )
  [ -n "$extra" ] && args+=( $extra )
  if [ "$kv" = "q4_0" ] && [[ "$envs" != *"GGML_CUDA_EXPERIMENTAL_GFX1151_Q4_KV_TILED"* ]]; then
    envs="${envs:+$envs }GGML_CUDA_EXPERIMENTAL_GFX1151_Q4_KV_TILED=1"
  fi

  echo "=== [$tag] $(date +%T) kv=${kv:-f16} env='${envs:-none}'" | tee -a "$ROOT/driver.log"
  rm -f "$log"
  if [ -n "$envs" ]; then
    env $envs LD_LIBRARY_PATH="$(dirname "$bin"):/opt/rocm-7.2.2/lib" \
      "$bin" "${args[@]}" --log-file "$log" >"$ROOT/$tag.stdout" 2>&1 &
  else
    env LD_LIBRARY_PATH="$(dirname "$bin"):/opt/rocm-7.2.2/lib" \
      "$bin" "${args[@]}" --log-file "$log" >"$ROOT/$tag.stdout" 2>&1 &
  fi
  SERVER_PID=$!

  local t0=$(date +%s)
  until curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; do
    if ! kill -0 $SERVER_PID 2>/dev/null; then
      echo "[$tag] SERVER DIED — see $tag.stdout" | tee -a "$ROOT/driver.log"
      grep -m1 -E "GGML_ASSERT|error" "$ROOT/$tag.stdout" | tee -a "$ROOT/driver.log"
      SERVER_PID=""; return 1
    fi
    [ $(( $(date +%s) - t0 )) -gt 2400 ] && { echo "[$tag] health timeout"; kill $SERVER_PID; SERVER_PID=""; return 1; }
    sleep 5
  done
  echo "[$tag] healthy after $(( $(date +%s) - t0 ))s" | tee -a "$ROOT/driver.log"
  grep -E "llama_kv_cache: size" "$log" | tee -a "$ROOT/driver.log"
  wait_idle
  python3 "$BENCH" run "$tag" "$PORT" qwen3.6-35b-q4 "$PROMPT" "$log" "$ROOT/$tag.json" "$SERVER_PID" "$TOKENS" \
    2>&1 | tee -a "$ROOT/driver.log"
  kill $SERVER_PID 2>/dev/null; wait $SERVER_PID 2>/dev/null; SERVER_PID=""
  sleep 10
}

# interleave: forward, reverse, forward, ...
for ((s=1; s<=SAMPLES; s++)); do
  if (( s % 2 == 1 )); then
    for spec in "${SPECS[@]}"; do run_sample "$spec" "$s"; done
  else
    for ((i=${#SPECS[@]}-1; i>=0; i--)); do run_sample "${SPECS[$i]}" "$s"; done
  fi
done

echo "=== DONE $(date +%T)" | tee -a "$ROOT/driver.log"
python3 "$HERE/summarize_ab.py" "$ROOT" | tee -a "$ROOT/driver.log"
