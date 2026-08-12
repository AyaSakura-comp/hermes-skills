#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
PARSER="$SKILL_DIR/scripts/parse_server_log.py"
PI_BIN=${PI_BIN:-/home/chihmin/.local/bin/pi}
MODEL=${QWEN_BENCH_MODEL:-qwen3.6-35b-q4}
PROVIDER=${QWEN_BENCH_PROVIDER:-local-llama}
SERVER_LOG=/tmp/qwen35-server.log

MODE=${1:-decode}
RUNS=${2:-3}
if [[ "$MODE" != "decode" ]]; then
  if [[ "$MODE" =~ ^[1-9][0-9]*$ ]]; then
    RUNS=$MODE
    MODE="decode"
  else
    echo "usage: $(basename "$0") [decode] [runs]" >&2
    exit 2
  fi
fi

PROMPT='Do not use any tools. Write a correct stable merge sort implementation in Python. Include type hints, a docstring, a short explanation of the algorithm and its time and space complexity, and five assert-based tests. Return one self-contained answer.'

OUT=${QWEN_BENCH_OUT:-/tmp/benchmark-qwen-${MODE}-$(date +%Y%m%d-%H%M%S)}
[[ "$RUNS" =~ ^[1-9][0-9]*$ ]] || { echo "runs must be a positive integer" >&2; exit 2; }
command -v "$PI_BIN" >/dev/null || { echo "Pi not found: $PI_BIN" >&2; exit 1; }
mkdir -p "$OUT"

initial_qwen=$(systemctl is-active qwen-mtp.service 2>/dev/null || true)
[[ "$initial_qwen" == active ]] || { echo "qwen-mtp.service must be active before benchmarking" >&2; exit 1; }
initial_pid=$(systemctl show -p MainPID --value qwen-mtp.service)
initial_exe=$(readlink -f "/proc/$initial_pid/exe")
initial_gemma=$(systemctl is-active gemma-mtp.service 2>/dev/null || true)

restore() {
  local failed=0
  sudo -n powerprofilesctl set performance >/dev/null 2>&1 || failed=1
  sudo -n systemctl restart qwen-mtp.service >/dev/null 2>&1 || failed=1
  if [[ "$initial_gemma" == active ]]; then
    sudo -n systemctl start gemma-mtp.service >/dev/null 2>&1 || failed=1
  else
    sudo -n systemctl stop gemma-mtp.service >/dev/null 2>&1 || failed=1
  fi
  for _ in $(seq 1 300); do
    curl -fsS --max-time 2 http://127.0.0.1:8001/health >/dev/null 2>&1 && break
    sleep 1
  done
  [[ $(systemctl is-active qwen-mtp.service 2>/dev/null || true) == active ]] || failed=1
  curl -fsS --max-time 2 http://127.0.0.1:8001/health >/dev/null 2>&1 || failed=1
  if [[ "$initial_gemma" == active ]]; then
    [[ $(systemctl is-active gemma-mtp.service 2>/dev/null || true) == active ]] || failed=1
    curl -fsS --max-time 2 http://127.0.0.1:8002/health >/dev/null 2>&1 || failed=1
  fi
  [[ $(powerprofilesctl get) == performance ]] || failed=1
  return "$failed"
}
cleanup() {
  local rc=$?
  trap - EXIT INT TERM
  if ! restore; then
    echo "ERROR: benchmark cleanup could not restore/verify production services" >&2
    rc=1
  fi
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

sudo -n powerprofilesctl set performance
sudo -n systemctl stop gemma-mtp.service

wait_idle() {
  python3 - <<'PY'
import time
from pathlib import Path
busy = Path('/sys/class/drm/card1/device/gpu_busy_percent')
power_files = list(Path('/sys/class/drm/card1/device/hwmon').glob('hwmon*/power1_input'))
ok = 0
for _ in range(180):
    gpu = int(busy.read_text()) if busy.exists() else 0
    watts = int(power_files[0].read_text()) / 1e6 if power_files else 0
    ok = ok + 1 if gpu == 0 and (not power_files or watts < 15) else 0
    if ok >= 10:
        raise SystemExit(0)
    time.sleep(1)
raise SystemExit('GPU did not reach ten consecutive idle samples')
PY
}

for i in $(seq 1 "$RUNS"); do
  echo "===> [Run $i/$RUNS] Restarting qwen-mtp.service for cold-KV state..."
  rm -f "$SERVER_LOG"
  sudo -n systemctl restart qwen-mtp.service
  ready=0
  echo "===> [Run $i/$RUNS] Waiting for server /health endpoint..."
  for _ in $(seq 1 300); do
    if curl -fsS --max-time 2 http://127.0.0.1:8001/health >/dev/null 2>&1; then ready=1; break; fi
    sleep 1
  done
  [[ $ready == 1 ]] || { echo "Qwen health timeout" >&2; exit 1; }
  echo "===> [Run $i/$RUNS] Server healthy. Waiting for GPU idle stability..."
  wait_idle

  echo "===> [Run $i/$RUNS] Running Pi Agent workload under timer..."
  /usr/bin/time -f '%e' -o "$OUT/run-$i.wall" \
    "$PI_BIN" --offline --provider "$PROVIDER" --model "$MODEL" --no-session --mode json -p "$PROMPT" \
    < /dev/null >"$OUT/run-$i.jsonl" 2>"$OUT/run-$i.stderr"
  echo "===> [Run $i/$RUNS] Execution finished. Parsing server timing log..."
  cp "$SERVER_LOG" "$OUT/run-$i.server.log"
  python3 "$PARSER" "$OUT/run-$i.server.log" >"$OUT/run-$i.metrics.json"
  python3 - "$OUT/run-$i.metrics.json" "$OUT/run-$i.wall" "$i" <<'PY'
import json,sys
p,wall,run=sys.argv[1:]
d=json.load(open(p));d['run']=int(run);d['wall_s']=float(open(wall).read());open(p,'w').write(json.dumps(d,indent=2)+'\n');print(json.dumps(d))
PY
done

python3 - "$OUT" "$MODE" "$initial_exe" <<'PY'
import json,statistics,sys
from pathlib import Path
out,mode,exe=Path(sys.argv[1]),sys.argv[2],sys.argv[3]
runs=[json.loads(p.read_text()) for p in sorted(out.glob('run-*.metrics.json'))]
summary={'mode':mode,'executable':exe,'runs':runs}
for key in ('wall_s','prompt_tokens','prompt_ms','prompt_tps','output_tokens','decode_ms','server_decode_tps','standard_decode_tps_estimate','mtp_acceptance'):
    values=[r[key] for r in runs]
    summary[key]={'values':values,'mean':statistics.mean(values),'median':statistics.median(values)}
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
PY

if ! restore; then
  echo "ERROR: benchmark completed but production restoration verification failed" >&2
  exit 1
fi
trap - EXIT INT TERM
printf 'Evidence: %s\n' "$OUT"
