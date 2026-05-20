---
name: tailscale-docker-serve
description: Deploy services inside Docker containers with Tailscale providing HTTPS via MagicDNS + 'tailscale serve'. Covers container setup, auth key flow, MagicDNS propagation, and reverse proxy configuration.
---

# Tailscale Docker Serve — HTTPS Reverse Proxy

Deploy a service inside a Docker container with Tailscale providing HTTPS via MagicDNS + `tailscale serve`.

## Prerequisites

- Docker Compose installed
- Tailscale auth key (format: `tskey-auth-...`) from https://login.tailscale.com/admin/authkeys
- Service running on a port inside the same Docker Compose network

## Setup Steps

### 1. Directory structure

```
/opt/<service>-tailscale/
├── docker-compose.yml
├── .env
└── service-config/
    ├── ts-entrypoint.sh
    └── tailscaled.state (optional, for persistence)
```

### 2. `.env` file

```bash
TS_AUTH_KEY=tskey-auth-<your-key-here>
TS_DOMAIN=<your-tailscale-domain>  # e.g., aya.crayfish-monitor.ts.net
```

### 3. Docker Compose

```yaml
services:
  # Your main service (e.g., SearXNG)
  service:
    image: <your-image>
    container_name: <service-name>
    restart: always
    ports:
      - "<host-port>:<container-port>"
    volumes:
      - ./service-config:/etc/<service>

  # Tailscale + serve container
  ts:
    image: tailscale/tailscale:latest
    container_name: <service-name>-ts
    restart: always
    cap_add:
      - NET_ADMIN
      - SYS_ADMIN
    ports:
      - "443:443"
      - "80:80"
    environment:
      - TS_AUTH_KEY=${TS_AUTH_KEY}
      - TS_STATE_DIR=/var/lib/tailscale
      - TS_DOMAIN=${TS_DOMAIN}
    volumes:
      - ./service-config/ts-entrypoint.sh:/etc/tailscale/entrypoint.sh
      - tailscale-state:/var/lib/tailscale
      - ./service-config/certs:/certs
    depends_on:
      - service

volumes:
  tailscale-state:
```

### 4. Entrypoint script (`ts-entrypoint.sh`)

```bash
#!/bin/sh
set -e

# ─── CRITICAL: Add external DNS BEFORE Tailscale starts ───
# Tailscale overwrites /etc/resolv.conf with MagicDNS (100.100.100.100)
# which blocks external HTTP calls (ACME, etc.). Fix: add Google DNS.
echo "nameserver 8.8.8.8" >> /etc/resolv.conf
echo "nameserver 8.8.4.4" >> /etc/resolv.conf

# Start tailscaled with persistent state
tailscaled --state=${TS_STATE_DIR}/tailscaled.state &

# Authenticate with auth key
tailscale up --auth-key="$TS_AUTH_KEY" --hostname=<hostname> --accept-routes=false 2>&1

# Wait for node to be approved and get IP/FQDN
echo "Waiting for node approval and MagicDNS..."
for i in $(seq 1 60); do
  STATUS=$(tailscale status --json 2>/dev/null | grep -o '"BackendState": *"[^"]*"' | grep -o 'Running' || echo "unknown")
  if [ "$STATUS" = "Running" ]; then
    break
  fi
  sleep 1
done

TS_IP=$(tailscale ip -4 2>/dev/null)
FQDN=$(tailscale status --json 2>/dev/null | grep -o '"Fqdn": *"[^"]*"' | cut -d'"' -f4)

echo "Tailscale IP: $TS_IP"
echo "FQDN: $FQDN"

# Wait for MagicDNS propagation
echo "Waiting for MagicDNS propagation..."
sleep 10

# ─── IMPORTANT: Use tailscale serve (not tailscale cert) ───
# tailscale serve --bg handles HTTPS/ACME automatically.
# tailscale cert FAILS inside Docker because MagicDNS blocks ACME DNS resolution.
echo "Setting up HTTPS serve on ${FQDN} -> http://service:8080..."
tailscale serve --bg "http://${FQDN} http://service:8080" 2>&1

echo ""
echo "=== Service is now accessible at ==="
echo "  https://${FQDN}"
echo ""

# ─── DO NOT use `wait` — it blocks docker compose up -d ───
# Let the container stay alive via Tailscale's background process.
# If the container exits, restart: always will handle it.
sleep infinity
```

## Gotchas

1. **Capabilities required:** Container needs `NET_ADMIN` and `SYS_ADMIN` for Tailscale to work.
2. **State persistence:** Mount `/var/lib/tailscale` as a named volume so the auth state survives container restarts.
3. **Auth key scope:** Use an expiring or non-expiring auth key with appropriate key restrictions in the Tailscale admin console.
4. **MagicDNS timing:** After the node is `Running`, wait ~10 seconds for MagicDNS to propagate before `tailscale serve` will resolve the FQDN.
5. **Backend state detection:** The JSON parsing trick `grep -o '"BackendState": *"[^"]*"' | grep -o 'Running'` works reliably in Alpine/busybox sh environments (no python3 needed).
6. **Docker Compose internal DNS:** The `http://service:8080` in `tailscale serve` uses Docker's internal DNS — the hostname must match the service name in docker-compose.yml exactly.
7. **Port conflicts:** If port 443 is already in use on the host (e.g., by another Tailscale node or nginx), change the host port mapping (e.g., `8443:443`).
8. **External DNS BEFORE Tailscale:** Tailscale overwrites `/etc/resolv.conf` with MagicDNS (`100.100.100.100`), blocking all external DNS resolution (including ACME/Let's Encrypt). Add `8.8.8.8` and `8.8.4.4` to `resolv.conf` BEFORE running `tailscaled`.
9. **Never use `tailscale cert` inside Docker:** It tries to contact ACME servers via DNS, which fails because MagicDNS blocks external resolution. Use `tailscale serve --bg` instead — it handles HTTPS/ACME automatically.
10. **Never use `wait $PID` in entrypoint:** It makes `docker compose up -d` appear to hang forever. Use `sleep infinity` or let Tailscale's background daemon keep the container alive.
11. **`tailscale serve --https=` is deprecated:** Use `tailscale serve --bg "http://${FQDN} http://backend:port"` (the new key-value syntax).

## Troubleshooting

- **Container won't start:** Check `docker logs <container>` for Tailscale auth errors.
- **Serve config not applied:** Verify MagicDNS propagation with `dig <service>.<domain> @100.100.100.100`.
- **Node not approved:** Check Tailscale admin console for pending node approvals.
- **Port already in use:** Change the host port in the `ports:` mapping.
- **Tailscale not authenticating:** Verify the auth key is correct and hasn't expired. Regenerate if needed from the Tailscale admin console.