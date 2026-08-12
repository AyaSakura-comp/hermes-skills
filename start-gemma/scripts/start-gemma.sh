#!/usr/bin/env bash
# Start / restart one of the local Gemma 4 llama.cpp services, handling the
# memory and load-order constraints of this UMA box.
set -uo pipefail

usage() {
  cat <<'EOF'
Usage: start-gemma.sh <e2b|12b|26b|31b|status|stop-all> [--keep-others] [--no-wait]

  e2b   Gemma 4 E2B        port 8002   ~5 GB    pi: local-gemma-e2b
  12b   Gemma 4 12B QAT    port 8004   ~11 GB   pi: local-gemma-12b
  26b   Gemma 4 26B-A4B    port 8005   ~17 GB   pi: local-gemma-26b
  31b   Gemma 4 31B QAT    port 8003   ~30 GB   pi: local-gemma-31b

  status        show every Gemma service, its port, health and served alias
  stop-all      stop all four Gemma services (leaves Qwen on 8001 alone)

  --keep-others do not stop other Gemma services even if memory looks tight
  --no-wait     return as soon as the unit is started, without health polling
EOF
}

# name unit port alias pi_provider need_gb
svc_unit()     { case $1 in e2b) echo gemma-mtp.service;; 12b) echo gemma4-12b-mtp.service;; 26b) echo gemma4-26b-mtp.service;; 31b) echo gemma4-31b-mtp.service;; esac; }
svc_port()     { case $1 in e2b) echo 8002;; 12b) echo 8004;; 26b) echo 8005;; 31b) echo 8003;; esac; }
svc_provider() { case $1 in e2b) echo local-gemma-e2b;; 12b) echo local-gemma-12b;; 26b) echo local-gemma-26b;; 31b) echo local-gemma-31b;; esac; }
svc_need()     { case $1 in e2b) echo 5;;  12b) echo 11;; 26b) echo 17;; 31b) echo 30;; esac; }

ALL="e2b 12b 26b 31b"

avail_gb() { free -g | awk '/^Mem:/ {print $7}'; }

status() {
  printf '%-5s %-28s %-6s %-9s %s\n' MODEL UNIT PORT STATE SERVING
  for m in $ALL; do
    local u p st served
    u=$(svc_unit "$m"); p=$(svc_port "$m")
    st=$(systemctl is-active "$u" 2>/dev/null)
    served=$(curl -sf --max-time 5 "http://127.0.0.1:$p/v1/models" 2>/dev/null \
             | python3 -c 'import json,sys; print(json.load(sys.stdin)["data"][0]["id"])' 2>/dev/null)
    printf '%-5s %-28s %-6s %-9s %s\n' "$m" "$u" "$p" "$st" "${served:--}"
  done
  echo
  echo "RAM available: $(avail_gb) GB   |   $(amdgpu_top -d 2>/dev/null | grep GTT | sed 's/  */ /g')"
  local qwen
  qwen=$(systemctl is-active qwen-mtp.service 2>/dev/null)
  echo "qwen-mtp (port 8001, not a Gemma): $qwen"
}

[ $# -ge 1 ] || { usage; exit 1; }
TARGET=$1; shift
KEEP_OTHERS=0; NO_WAIT=0
for a in "$@"; do
  case $a in
    --keep-others) KEEP_OTHERS=1;;
    --no-wait)     NO_WAIT=1;;
    *) echo "unknown option: $a"; usage; exit 1;;
  esac
done

case $TARGET in
  status) status; exit 0;;
  stop-all)
    for m in $ALL; do sudo -n systemctl stop "$(svc_unit "$m")" 2>/dev/null; done
    sleep 5; status; exit 0;;
  e2b|12b|26b|31b) ;;
  *) usage; exit 1;;
esac

UNIT=$(svc_unit "$TARGET"); PORT=$(svc_port "$TARGET"); NEED=$(svc_need "$TARGET")

echo "== target: $TARGET  ($UNIT, port $PORT, needs ~${NEED} GB)"
sudo -n powerprofilesctl set performance 2>/dev/null

# ---- memory policy -------------------------------------------------------
# GTT free is NOT the constraint on this UMA box: GTT allocations come out of
# system RAM. Judge by `free -g` available. Starting a model without headroom
# does not fail cleanly, it stalls for tens of minutes in ROCm kernel JIT while
# competing for pages (see the 26B's 40-minute first load).
AVAIL=$(avail_gb)
echo "== RAM available: ${AVAIL} GB"
if [ "$AVAIL" -lt "$NEED" ] && [ "$KEEP_OTHERS" -eq 0 ]; then
  echo "== insufficient headroom; stopping the other Gemma services"
  for m in $ALL; do
    [ "$m" = "$TARGET" ] && continue
    u=$(svc_unit "$m")
    if [ "$(systemctl is-active "$u")" = active ]; then
      echo "   stopping $m ($u)"
      sudo -n systemctl stop "$u"
    fi
  done
  sleep 8
  AVAIL=$(avail_gb)
  echo "== RAM available after freeing: ${AVAIL} GB"
  if [ "$AVAIL" -lt "$NEED" ]; then
    echo "!! still below ~${NEED} GB. The remaining consumer is probably qwen-mtp (port 8001)."
    echo "!! stop it with: sudo systemctl stop qwen-mtp.service   — then re-run."
  fi
fi

sudo -n systemctl restart "$UNIT" || { echo "!! systemctl restart failed"; exit 1; }
[ "$NO_WAIT" -eq 1 ] && { echo "== started, not waiting"; exit 0; }

# ---- wait, distinguishing "loading" from "stalled in JIT" ----------------
echo "== waiting for http://127.0.0.1:$PORT/health"
DEADLINE=$((SECONDS + 1800))
LAST_NOTE=0
while [ $SECONDS -lt $DEADLINE ]; do
  if curl -sf --max-time 5 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
    echo "== healthy after ${SECONDS}s"
    break
  fi
  if ! systemctl is-active --quiet "$UNIT"; then
    echo "!! unit died. Recent log:"; journalctl -u "$UNIT" --no-pager -n 20; exit 1
  fi
  if [ $((SECONDS - LAST_NOTE)) -ge 120 ]; then
    LAST_NOTE=$SECONDS
    pid=$(journalctl -u "$UNIT" --no-pager -n 60 | grep -oP '\.sh\[\K[0-9]+' | tail -1)
    if [ -n "$pid" ] && [ -d "/proc/$pid" ]; then
      read -r rss st < <(ps -o rss=,stat= -p "$pid" | awk '{print $1, $2}')
      echo "   ${SECONDS}s: still loading (RSS $((rss/1024)) MB, state $st)"
      case $st in
        R*) echo "        CPU-bound with weights already resident => ROCm kernel JIT."
            echo "        This is normal on a cold ~/.cache/comgr and is one-time."
            echo "        Do NOT kill it unless RSS is shrinking (that means memory pressure);"
            echo "        in that case stop another model and re-run this script.";;
      esac
    fi
  fi
  sleep 5
done

if ! curl -sf --max-time 5 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
  echo "!! not healthy after 30 minutes — see the JIT note above"; exit 1
fi

# ---- verify --------------------------------------------------------------
echo
echo "== verification"
served=$(curl -sf --max-time 10 "http://127.0.0.1:$PORT/v1/models" \
         | python3 -c 'import json,sys; print(json.load(sys.stdin)["data"][0]["id"])' 2>/dev/null)
echo "   serving alias : ${served:-UNKNOWN}"
pid=$(ss -tlnp 2>/dev/null | grep ":$PORT " | grep -oP 'pid=\K[0-9]+' | head -1)
if [ -n "$pid" ]; then
  cl=$(tr '\0' ' ' < "/proc/$pid/cmdline")
  echo "   flash attn    : $(grep -oE '(--flash-attn (on|off|auto)|-fa [01])' <<<"$cl" | head -1)"
  echo "   speculative   : $(grep -oE '\--spec-type [a-z-]+' <<<"$cl" | head -1)"
  echo "   ctx size      : $(grep -oE '\--ctx-size [0-9]+|-c [0-9]+' <<<"$cl" | head -1)"
fi
echo "   pi provider   : $(svc_provider "$TARGET")  (model id: ${served:-?})"
echo
status
