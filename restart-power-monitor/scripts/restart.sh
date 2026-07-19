#!/bin/bash
# Restart script for Strix Halo Power Monitor service and Tailscale sidecar

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

PROJECT_DIR="/home/chihmin/src/power-monitor"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.yml"

# Fix permissions on ts-state so Docker context can stat it (Tailscale runs as root and locks it down)
if [ -d "$PROJECT_DIR/ts-state" ]; then
    echo "Fixing permissions on ts-state to allow docker context access..."
    sudo chmod -R a+rX "$PROJECT_DIR/ts-state"
fi

# 1. Rebuild and start power-monitor
echo "1. Rebuilding and starting power-monitor container..."
docker compose -f "$COMPOSE_FILE" up -d --build power-monitor

# 2. Force recreate Tailscale container (required because it shares netns with power-monitor)
echo "2. Recreating Tailscale sidecar container..."
docker compose -f "$COMPOSE_FILE" up -d --force-recreate tailscale

# 3. Verify Localhost API Health
echo "3. Waiting for backend local API to respond at http://localhost:8085/api/stats..."
LOCAL_SUCCESS=false
for i in {1..15}; do
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8085/api/stats || true)
    if [ "$STATUS" = "200" ]; then
        LOCAL_SUCCESS=true
        break
    fi
    echo "   [Attempt $i/15] Backend returned status: $STATUS. Waiting 2 seconds..."
    sleep 2
done

if [ "$LOCAL_SUCCESS" = "true" ]; then
    echo -e "   ${GREEN}[OK] Local API is healthy (status 200).${NC}"
else
    echo -e "   ${RED}[ERROR] Local API failed to respond with 200 within 30 seconds.${NC}"
    exit 1
fi

# 4. Verify Tailscale connection and authentication
echo "4. Checking Tailscale connection status inside container..."
TS_ONLINE=false
for i in {1..15}; do
    # Run status check inside the container
    STATUS_OUT=$(docker exec power-monitor-ts tailscale --socket=/tmp/tailscaled.sock status 2>&1 || true)
    STATUS_JSON=$(docker exec power-monitor-ts tailscale --socket=/tmp/tailscaled.sock status --json 2>/dev/null || true)
    
    # Check BackendState from JSON
    BACKEND_STATE=$(echo "$STATUS_JSON" | grep -o '"BackendState": *"[^"]*"' | cut -d'"' -f4 || true)
    
    # If the network reports down or coordination server fails, attempt a container restart
    if echo "$STATUS_OUT" | grep -E -q "network is down|Unable to connect to the Tailscale coordination server"; then
        echo -e "   ${YELLOW}[WARN] Tailscale reports network issue. Restarting Tailscale container...${NC}"
        docker compose -f "$COMPOSE_FILE" restart tailscale
        sleep 5
        continue
    fi

    # Tailscale is online if backend state is "Running"
    if [ "$BACKEND_STATE" = "Running" ]; then
        TS_ONLINE=true
        break
    fi

    echo "   [Attempt $i/15] Tailscale is connecting/authenticating (State: $BACKEND_STATE)... Waiting 2 seconds..."
    sleep 2
done

if [ "$TS_ONLINE" = "true" ]; then
    echo -e "   ${GREEN}[OK] Tailscale node is active and running.${NC}"
else
    echo -e "   ${RED}[ERROR] Tailscale failed to become active within 30 seconds.${NC}"
    echo "Tailscale status output:"
    docker exec power-monitor-ts tailscale --socket=/tmp/tailscaled.sock status || true
    exit 1
fi

# 5. Verify Tailscale URL (HTTPS)
echo "5. Verifying public Tailscale URL https://power.crayfish-monitor.ts.net/..."
URL_SUCCESS=false
for i in {1..15}; do
    URL_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X GET https://power.crayfish-monitor.ts.net/ || true)
    if [ "$URL_STATUS" = "200" ]; then
        URL_SUCCESS=true
        break
    fi
    echo "   [Attempt $i/15] FQDN returned status: $URL_STATUS. Waiting 2 seconds..."
    sleep 2
done

if [ "$URL_SUCCESS" = "true" ]; then
    echo -e "   ${GREEN}[OK] Public Tailscale URL is reachable and serving correctly (status 200).${NC}"
else
    echo -e "   ${RED}[ERROR] Tailscale URL failed to return 200 within 30 seconds.${NC}"
    exit 1
fi

echo -e "${GREEN}=== Power Monitor service has restarted successfully! ===${NC}"
echo "Local Access:     http://localhost:8085"
echo "Tailscale Access:  https://power.crayfish-monitor.ts.net"
