#!/usr/bin/env bash
set -uo pipefail

# ==============================================================================
# restart-funnel.sh — Detect and repair silently de-registered Tailscale Funnels
# ==============================================================================
#
# A Tailscale sidecar can report `Funnel on` locally while the control plane has
# NOT published the node's public ts.net A record. The site is then unreachable
# without VPN even though every node-side check looks healthy: IngressEnabled is
# true, the cert is valid, `tailscale funnel status` says on. The node has no way
# to detect this — the failure lives on the control-plane side.
#
# So the ONLY trustworthy probe is public DNS from OUTSIDE, and the fix is to
# restart the sidecar, which forces re-registration.
#
# Usage:
#   restart-funnel.sh              # check every node, repair the broken ones
#   restart-funnel.sh status       # check only, never restart
#   restart-funnel.sh stock piweb  # check/repair just these nodes
#
# Restarting a sidecar is safe for the app in BOTH network layouts: the app
# container is never touched. (The reverse is NOT true — recreating an app whose
# sidecar uses `network_mode: container:<app>` destroys the sidecar's netns.)

TAILNET="${TAILNET:-crayfish-monitor.ts.net}"
DNS_WAIT="${DNS_WAIT:-360}"   # seconds to wait for the record to reappear.
                             # Observed 2026-09-01: stock came back in ~20s but
                             # webtop-amd and fuji-camera took well over 90s, so a
                             # short wait reports a false failure. Be generous.
RESOLVERS=(8.8.8.8 1.1.1.1 9.9.9.9)

# node            container
NODES=(
  "piweb          piweb-ts"
  "evo            evo-ts"
  "stock          hayaegis-tailscale-stock-1"
  "taigi          breeze-asr-tailscale-taigi"
  "webtop-amd     webtop-amd-ts"
  "fuji-camera    fuji-camera-ts"
  "komorebi       komorebi-ts"
)

MODE="repair"
SELECT=()
for a in "$@"; do
  case "$a" in
    status|--status|-s) MODE="status" ;;
    all|--all)          ;;
    *)                  SELECT+=("$a") ;;
  esac
done

# Query several resolvers. A SINGLE empty answer proves nothing: ts.net serves a
# 300s negative-cache SOA, so a resolver that saw the name while it was down
# keeps returning NXDOMAIN for minutes after it comes back. Majority wins.
dns_live() {
  local fqdn="$1" hits=0 answers=0 r out
  for r in "${RESOLVERS[@]}"; do
    out=$(dig +short +time=3 +tries=1 A "$fqdn" "@$r" 2>/dev/null | grep -E '^[0-9]+\.' || true)
    [[ -n "$out" ]] && hits=$((hits + 1))
    answers=$((answers + 1))
    LAST_IP="${LAST_IP:-}"
    [[ -n "$out" && -z "$LAST_IP" ]] && LAST_IP=$(echo "$out" | head -1)
  done
  (( hits * 2 > answers ))
}

# Prove the site answers from the PUBLIC path, not over the tailnet: pin the
# connection to a Tailscale ingress IP so the request really leaves the tailnet.
public_probe() {
  local fqdn="$1" ip="$2"
  curl -s -o /dev/null -w '%{http_code}' --max-time 20 \
       --resolve "$fqdn:443:$ip" "https://$fqdn/" 2>/dev/null || echo 000
}

echo "=== [Tailscale Funnel] health check over ${#RESOLVERS[@]} public resolvers ==="
broken=() ok=() skipped=()

for row in "${NODES[@]}"; do
  read -r node container <<<"$row"
  [[ ${#SELECT[@]} -gt 0 ]] && ! printf '%s\n' "${SELECT[@]}" | grep -qx "$node" && continue

  fqdn="$node.$TAILNET"
  if ! docker inspect "$container" >/dev/null 2>&1; then
    printf '  [?] %-13s container %s not found — skipping\n' "$node" "$container"
    skipped+=("$node"); continue
  fi
  if [[ "$(docker inspect -f '{{.State.Running}}' "$container")" != "true" ]]; then
    printf '  [!] %-13s sidecar %s is NOT running\n' "$node" "$container"
    broken+=("$node $container"); continue
  fi

  LAST_IP=""
  if dns_live "$fqdn"; then
    code=$(public_probe "$fqdn" "$LAST_IP")
    printf '  [+] %-13s public DNS ok, HTTP %s via %s\n' "$node" "$code" "$LAST_IP"
    ok+=("$node")
  else
    printf '  [-] %-13s NO public DNS record — funnel is de-registered\n' "$node"
    broken+=("$node $container")
  fi
done

if [[ ${#broken[@]} -eq 0 ]]; then
  echo "=== All checked funnels are live. Nothing to do. ==="
  exit 0
fi

if [[ "$MODE" == "status" ]]; then
  echo "=== ${#broken[@]} funnel(s) down (status mode, not repairing) ==="
  printf '    %s\n' "${broken[@]}"
  exit 1
fi

echo
echo "=== Repairing ${#broken[@]} funnel(s) by restarting their sidecars ==="
failed=()
for row in "${broken[@]}"; do
  read -r node container <<<"$row"
  fqdn="$node.$TAILNET"
  echo "[*] $node: docker restart $container"
  docker restart "$container" >/dev/null || { echo "  [-] restart failed"; failed+=("$node"); continue; }

  echo "    waiting up to ${DNS_WAIT}s for the public record to reappear..."
  deadline=$(( $(date +%s) + DNS_WAIT )) up=0
  while (( $(date +%s) < deadline )); do
    sleep 10
    LAST_IP=""
    if dns_live "$fqdn"; then up=1; break; fi
  done

  if (( up )); then
    # Both ingress IPs register independently; one may TLS-error for ~20s.
    code=$(public_probe "$fqdn" "$LAST_IP")
    if [[ "$code" != "200" ]]; then sleep 15; code=$(public_probe "$fqdn" "$LAST_IP"); fi
    echo "  [+] $node RECOVERED — https://$fqdn HTTP $code"
    [[ "$code" == "200" ]] || echo "      (non-200: DNS is back, check the app behind the proxy)"
  else
    echo "  [-] $node still has no public DNS after ${DNS_WAIT}s"
    echo "      check the tailnet ACL grants this node the 'funnel' node attribute"
    failed+=("$node")
  fi
done

echo
if [[ ${#failed[@]} -eq 0 ]]; then
  echo "=== All funnels repaired successfully. ==="
else
  echo "=== Repair FAILED for: ${failed[*]} ==="
  exit 1
fi
