#!/usr/bin/env bash
# switch-qwen-model.sh — switch the local Qwen model service (3.6 <-> 3.8 Flash)
# and update pi agent's defaultProvider/defaultModel to match.
#
# The two engines are mutually exclusive on this box (both would OOM together):
#   3.6  -> qwen-mtp.service (system systemd, :8001) provider local-llama  model qwen3.6-35b-q4
#   3.8  -> strata.service   (user systemd,   :8090) provider local-strata model qwen3.8-flash
#
# Usage: switch-qwen-model.sh [3.6|3.8|status]
set -u

SETTINGS="$HOME/.pi/agent/settings.json"
MODELS="$HOME/.pi/agent/models.json"
PISCORD_ENV="$HOME/.config/pi-discord-gateway/config.env"

health_36() { curl -sf --max-time 3 http://localhost:8001/health >/dev/null 2>&1; }
# Strata's wrapper answers /health even when its engine is not running (it died,
# e.g. exit -9, or was unloaded): the service stays "active" and only the next
# request restarts the engine (a minute or more, plus a cold prompt read). So
# 3.8 counts as healthy only once /health says "loaded": true.
health_38() { curl -sf --max-time 3 http://localhost:8090/health 2>/dev/null | grep -q '"loaded": *true'; }
# Start Strata's engine now rather than on the first real request (blocks until
# loaded; Strata's own /load control endpoint, JSON only).
load_38() {
  curl -sf --max-time "${1:-240}" -X POST -H 'Content-Type: application/json' -d '{}' \
    http://localhost:8090/load >/dev/null 2>&1
}

# Whether Strata started its image encoder (the config's "vision" section):
# /health "images": true. Prints true|false, empty when Strata is down.
images_38() {
  curl -sf --max-time 3 http://localhost:8090/health 2>/dev/null |
    python3 -c 'import json,sys; print(str(json.load(sys.stdin).get("images", False)).lower())' 2>/dev/null
}
# Keep pi's local-strata model input in step with what Strata really serves:
# ["text","image"] with the encoder, ["text"] without (pi then won't send
# pictures that Strata would refuse).
sync_pi_images() {
  local images; images=$(images_38)
  [ -n "$images" ] || return 0
  python3 - "$MODELS" "$images" <<'EOF'
import json, sys
p, images = sys.argv[1], sys.argv[2] == "true"
d = json.load(open(p))
want = ["text", "image"] if images else ["text"]
for m in d.get("providers", {}).get("local-strata", {}).get("models", []):
    if m.get("id") == "qwen3.8-flash" and m.get("input") != want:
        m["input"] = want
        json.dump(d, open(p, "w"), indent=2, ensure_ascii=False)
        print(f"pi local-strata input -> {want}")
        break
print(f"strata images: {'on (vision encoder loaded)' if images else 'off (no vision section)'}")
EOF
}

wait_health() { # $1 = 3.6|3.8, $2 = timeout seconds
  local target="$1" deadline=$(( $(date +%s) + ${2:-120} ))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    if [ "$target" = "3.6" ] && health_36; then return 0; fi
    if [ "$target" = "3.8" ] && health_38; then return 0; fi
    sleep 5
  done
  return 1
}

set_pi_default() { # $1 = 3.6|3.8
  local provider model
  if [ "$1" = "3.6" ]; then provider="local-llama";  model="qwen3.6-35b-q4"
  else                       provider="local-strata"; model="qwen3.8-flash"; fi
  cp "$SETTINGS" "$SETTINGS.bak-pre-switch-$(date +%Y%m%d-%H%M%S)"
  python3 - "$SETTINGS" "$provider" "$model" <<'EOF'
import json, sys
p, provider, model = sys.argv[1], sys.argv[2], sys.argv[3]
d = json.load(open(p))
d['defaultProvider'] = provider
d['defaultModel'] = model
json.dump(d, open(p, 'w'), indent=2, ensure_ascii=False)
print(f"pi default -> {provider}/{model}")
EOF
}

set_piscord_model() { # $1 = 3.6|3.8
  local pi_model
  if [ "$1" = "3.6" ]; then pi_model="local-llama/qwen3.6-35b-q4"
  else                       pi_model="local-strata/qwen3.8-flash"; fi
  if [ ! -f "$PISCORD_ENV" ]; then
    echo "WARN: $PISCORD_ENV not found; skipping piscord PI_MODEL update" >&2
    return 0
  fi
  cp "$PISCORD_ENV" "$PISCORD_ENV.bak-pre-switch-$(date +%Y%m%d-%H%M%S)"
  if grep -q '^PI_MODEL=' "$PISCORD_ENV"; then
    sed -i "s|^PI_MODEL=.*|PI_MODEL=$pi_model|" "$PISCORD_ENV"
  else
    echo "PI_MODEL=$pi_model" >> "$PISCORD_ENV"
  fi
  echo "piscord PI_MODEL -> $pi_model"
  if systemctl --user is-active --quiet pi-discord-gateway.service; then
    systemctl --user restart pi-discord-gateway.service
    echo "piscord gateway restarted"
  else
    echo "piscord gateway not running; PI_MODEL applies on next start"
  fi
}

status() {
  echo "== services =="
  systemctl is-active qwen-mtp.service 2>/dev/null | sed 's/^/qwen-mtp (3.6, :8001): /'
  systemctl --user is-active strata.service 2>/dev/null | sed 's/^/strata   (3.8, :8090): /'
  echo "== health =="
  health_36 && echo "3.6 :8001 /health OK" || echo "3.6 :8001 not responding"
  if health_38; then echo "3.8 :8090 engine loaded, images: $(images_38)"
  elif curl -sf --max-time 3 http://localhost:8090/health >/dev/null 2>&1; then echo "3.8 :8090 wrapper up, engine NOT loaded"
  else echo "3.8 :8090 not responding"; fi
  echo "== pi default =="
  python3 -c "import json;d=json.load(open('$SETTINGS'));print(d.get('defaultProvider'),'/',d.get('defaultModel'))"
  echo "== piscord =="
  grep '^PI_MODEL=' "$PISCORD_ENV" 2>/dev/null || echo "PI_MODEL not set"
  systemctl --user is-active pi-discord-gateway.service 2>/dev/null | sed 's/^/pi-discord-gateway: /'
}

case "${1:-}" in
  3.6)
    echo ">> stopping strata (3.8)..."
    systemctl --user stop strata.service
    echo ">> starting qwen-mtp (3.6)..."
    sudo systemctl start qwen-mtp.service
    wait_health 3.6 180 || { echo "ERROR: 3.6 did not become healthy in time" >&2; exit 1; }
    set_pi_default 3.6
    set_piscord_model 3.6
    echo "OK: Qwen 3.6 active on :8001"
    ;;
  3.8)
    echo ">> stopping qwen-mtp (3.6)..."
    sudo systemctl stop qwen-mtp.service
    echo ">> starting strata (3.8)..."
    systemctl --user start strata.service
    # The wrapper comes up first; then make sure the engine itself is loaded
    # (an already-"active" service can be holding a dead engine).
    deadline=$(( $(date +%s) + 60 ))
    until curl -sf --max-time 3 http://localhost:8090/health >/dev/null 2>&1 || [ "$(date +%s)" -ge "$deadline" ]; do sleep 2; done
    health_38 || { echo ">> strata engine not loaded; loading it now (a minute or two)..."; load_38 240; }
    wait_health 3.8 180 || { echo "ERROR: 3.8 engine did not load in time (check journalctl --user -u strata -n 50)" >&2; exit 1; }
    sync_pi_images
    set_pi_default 3.8
    set_piscord_model 3.8
    echo "OK: Qwen 3.8 Flash (Strata) active on :8090"
    ;;
  status)
    status
    ;;
  *)
    echo "Usage: $0 [3.6|3.8|status]" >&2
    exit 2
    ;;
esac
