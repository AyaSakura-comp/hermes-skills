#!/usr/bin/env bash
# Trace one llama-server variant's decode with rocprofv3 --kernel-trace.
#
# The whole reason this script exists is the shutdown sequence at the bottom:
# rocprofv3 flushes its database while handling SIGTERM, and llama-server then
# hangs spinning a core. kill -9 too early loses the trace; waiting for a clean
# exit never returns. See SKILL.md.
#
# Usage:
#   trace-decode.sh --label f16 --bin /path/to/llama-server --root /tmp/my-trace
#                   [--kv q4_0] [--env VAR=1]... [--extra "-arg val"]
#                   [--model PATH] [--prompt PATH] [--tokens 512] [--port 8101]
set -uo pipefail

LABEL="" BIN="" ROOT="" KV="" TOKENS=512 PORT=8101 EXTRA=""
MODEL=/home/chihmin/models/Qwen3.6-35B-A3B-selective-Q4_0-proof/Qwen3.6-35B-A3B-UD-Q4_K_M-selective-Q4_0.gguf
PROMPT=/tmp/bench-20k-prompt-20260724-094754/qwen-prompt.txt
ENVS=()

while [ $# -gt 0 ]; do
  case "$1" in
    --label)  LABEL=$2; shift 2 ;;
    --bin)    BIN=$2; shift 2 ;;
    --root)   ROOT=$2; shift 2 ;;
    --kv)     KV=$2; shift 2 ;;
    --env)    ENVS+=("$2"); shift 2 ;;
    --extra)  EXTRA=$2; shift 2 ;;
    --model)  MODEL=$2; shift 2 ;;
    --prompt) PROMPT=$2; shift 2 ;;
    --tokens) TOKENS=$2; shift 2 ;;
    --port)   PORT=$2; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done
[ -n "$LABEL" ] && [ -n "$BIN" ] && [ -n "$ROOT" ] || { echo "need --label --bin --root" >&2; exit 2; }
[ -x "$BIN" ] || { echo "no such binary: $BIN" >&2; exit 2; }

D="$ROOT/$LABEL"; mkdir -p "$D"
ROCM=/opt/rocm-7.2.2

restore() {
  pkill -9 -f "llama-server.*--port $PORT" 2>/dev/null
  sleep 3
  sudo -n powerprofilesctl set performance
  sudo -n systemctl start qwen-mtp.service
  sudo -n systemctl start gemma-mtp.service
}
trap restore EXIT

echo "[$LABEL] bin=$(md5sum "$BIN" | cut -c1-8) kv=${KV:-f16} env='${ENVS[*]:-none}'" | tee "$D/meta.log"

sudo -n powerprofilesctl set performance
sudo -n systemctl stop qwen-mtp.service gemma-mtp.service
sleep 10

ARGS=( -m "$MODEL" --port "$PORT" --host 127.0.0.1
       -ngl 99 -fit off -fa 1 -c 260000 -np 1 -b 4096 -ub 2048
       --mmproj /home/chihmin/models/mmproj.gguf
       --alias qwen3.6-35b-q4 --spec-type mtp --spec-draft-n-max 3 )
[ -n "$KV" ] && ARGS+=( -ctk "$KV" -ctv "$KV" -ctkd "$KV" -ctvd "$KV" )
[ -n "$EXTRA" ] && ARGS+=( $EXTRA )
if [ "$KV" = "q4_0" ]; then
  ENVS+=( "GGML_CUDA_EXPERIMENTAL_GFX1151_Q4_KV_TILED=1" )
fi

# The optimization usually lives in libggml-hip.so next to the binary, so the
# variant's own bin/ must come first on the library path.
env "${ENVS[@]}" LD_LIBRARY_PATH="$(dirname "$BIN"):$ROCM/lib" \
  "$ROCM/bin/rocprofv3" --kernel-trace --stats -d "$D/rocprof" -- \
  "$BIN" "${ARGS[@]}" --log-file "$D/server.log" \
  >"$D/server.stdout" 2>"$D/server.stderr" &
RPID=$!

ok=0
for _ in $(seq 1 900); do
  curl -fsS --max-time 2 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && { ok=1; break; }
  kill -0 "$RPID" 2>/dev/null || break
  sleep 1
done
if [ "$ok" != 1 ]; then
  echo "[$LABEL] server never became healthy:" >&2
  tail -n 20 "$D/server.stderr" >&2
  exit 1
fi
grep -E "llama_kv_cache: size" "$D/server.log" | tee -a "$D/meta.log"
sleep 8   # settle

python3 - "$PORT" "$PROMPT" "$D/result.json" "$TOKENS" <<'PY' 2>&1 | tee -a "$D/meta.log"
import json, requests, sys, time
port, prompt_path, out, ntok = int(sys.argv[1]), sys.argv[2], sys.argv[3], int(sys.argv[4])
prompt = open(prompt_path).read()
payload = {'model': 'qwen3.6-35b-q4', 'messages': [{'role': 'user', 'content': prompt}],
           'max_tokens': ntok, 'temperature': 0, 'seed': 42, 'cache_prompt': False, 'stream': False}
t = time.monotonic()
r = requests.post(f'http://127.0.0.1:{port}/v1/chat/completions', json=payload, timeout=1800)
r.raise_for_status()
d = r.json(); d['_wall_s'] = time.monotonic() - t
open(out, 'w').write(json.dumps(d, indent=2))
print(d['usage'], f"{d['_wall_s']:.2f}s")
assert d['usage']['completion_tokens'] == ntok, d['usage']
PY

# ---- the shutdown dance; do not simplify ----
# SIGTERM makes rocprofv3 flush the database. The server then hangs spinning a
# core (27 min observed), so poll the file until it stops growing, then -9.
kill -TERM "$RPID" 2>/dev/null
prev=-1 cur=0 stable=0
for _ in $(seq 1 240); do
  cur=$(find "$D/rocprof" -name '*_results.db' -printf '%s\n' 2>/dev/null | head -1)
  cur=${cur:-0}
  if [ "$cur" -gt 0 ] && [ "$cur" = "$prev" ]; then
    stable=$((stable + 1)); [ $stable -ge 3 ] && break
  else
    stable=0
  fi
  prev=$cur; sleep 5
done
echo "[$LABEL] trace db settled at ${cur} bytes" | tee -a "$D/meta.log"
[ "$cur" -gt 0 ] || echo "[$LABEL] WARNING: empty trace db — did something kill -9 the server early?" >&2
kill -9 "$RPID" 2>/dev/null
pkill -9 -f "llama-server.*--port $PORT" 2>/dev/null
wait "$RPID" 2>/dev/null
sleep 5

grep -E "prompt eval time|^\s+eval time|draft acceptance" "$D/server.log" | tail -3 | tee -a "$D/meta.log"
echo "[$LABEL] done -> $D"
