---
name: assetsentry-stock-deploy
description: Deploy AssetSentry stock dashboard with Streamlit baseUrlPath configuration for Tailscale subdomain/proxy access.
tags:
  - docker
  - streamlit
  - assetsentry
  - deployment
---

# AssetSentry Stock Deployment

Deploy AssetSentry stock dashboard (Streamlit app) with proper path configuration for Tailscale proxy access.

## Repository

Clone from GitHub (if not already cloned):
```bash
git clone <assetsentry-repo-url> /home/chihmin/Assetsentry/AssetSentry
cd /home/chihmin/Assetsentry/AssetSentry
```

## Dockerfile (from repo)

Uses `ghcr.io/astral-sh/uv:python3.12-bookworm-slim` base image with `uv sync --frozen` for dependencies. Exposes ports 8000 (FastAPI) and 8501 (Streamlit).

## Deployment

### Method 1: Docker Compose (recommended)

```bash
cd /home/chihmin/Assetsentry/AssetSentry

# Build and start API service
docker compose up -d api

# Build and start Dashboard service (with baseUrlPath=/stock for Tailscale proxy)
docker compose up -d dashboard
```

The `docker-compose.yml` already contains the Streamlit `--server.baseUrlPath=/stock` flag for Tailscale subdomain/proxy compatibility.

### Method 2: Manual Docker Run (when compose fails)

**API Service:**
```bash
docker run -d --name assetssentry-api \
  -v /home/chihmin/Assetsentry/AssetSentry/data:/app/data \
  -v /home/chihmin/Assetsentry/AssetSentry/.env:/app/.env:ro \
  -p 8000:8000 \
  --restart always \
  assetsentry:latest \
  uv run python main_api.py
```

**Dashboard Service (Streamlit with baseUrlPath):**
```bash
docker run -d --name assetssentry-dashboard \
  -v /home/chihmin/Assetsentry/AssetSentry/data:/app/data \
  -v /home/chihmin/Assetsentry/AssetSentry/.env:/app/.env:ro \
  -p 8501:8501 \
  --restart always \
  assetsentry:latest \
  uv run streamlit run dashboard.py --server.address 0.0.0.0 --server.baseUrlPath=/stock
```

**⚠️ Critical:** The `--server.baseUrlPath=/stock` flag is REQUIRED when the service is accessed via a subpath (Tailscale `/stock`, nginx reverse proxy with path, etc.). Without it, the page will appear blank.

## Tailscale Subdomain Setup

After the service is running on localhost:8501, expose it via Tailscale:

```bash
# Check current hostname
tailscale status --json 2>&1 | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['Self'].get('HostName'))"

# Get FQDN: <hostname>.<tailnet-domain>
# Example: stock.crayfish-monitor.ts.net

# Generate TLS certificate for subdomain
sudo tailscale cert stock.crayfish-monitor.ts.net

# Configure serve with subdomain
sudo tailscale serve --json '{
  "TCP": {"443": {"HTTPS": true}},
  "Web": {
    "stock.crayfish-monitor.ts.net:443": {
      "Handlers": {
        "/": { "Proxy": "http://localhost:8501/stock" }
      }
    }
  }
}'
```

**Note:** Use `--json` to write the entire config at once. Do NOT use `--bg` or `reset` — `--json` auto-activates.

## Verification

```bash
# Check container is running
docker ps --filter name=assetssentry-dashboard --format "{{.Names}} {{.Status}}"

# Check logs
docker logs assetssentry-dashboard --tail 20

# Should see: "Local URL: http://localhost:8501/stock"

# Test locally
curl -s http://localhost:8501/stock | head -20

# Test via Tailscale
curl -sk https://stock.crayfish-monitor.ts.net/ | head -20
```

## Troubleshooting

### Blank page on Tailscale subdomain
- **Cause:** Missing `--server.baseUrlPath=/stock` in Streamlit command
- **Fix:** Rebuild the container with the flag: `docker compose up -d dashboard`

### Port conflict (Bind for 0.0.0.0:8501 failed)
- **Cause:** Old container still holding the port
- **Fix:** `docker stop assetssentry-dashboard && docker rm assetssentry-dashboard`

### Tailscale cert fails with "500 Internal Server Error"
- **Cause:** DNS resolution issue (MagicDNS overwrites /etc/resolv.conf)
- **Fix:** Use `sudo tailscale serve --json` instead — it handles cert internally

### Service not starting after Docker restart
- **Cause:** Missing `--restart always` flag
- **Fix:** Recreate container with restart policy

## Key Files

| File | Purpose |
|---|---|
| `/home/chihmin/Assetsentry/AssetSentry/docker-compose.yml` | Service definitions with baseUrlPath |
| `/home/chihmin/Assetsentry/AssetSentry/Dockerfile` | Container build instructions |
| `/home/chihmin/Assetsentry/AssetSentry/.env` | Environment variables (DB, API keys) |
| `/home/chihmin/Assetsentry/AssetSentry/dashboard.py` | Streamlit dashboard entry point |

## Pitfalls

- **Streamlit baseUrlPath is mandatory** when behind a subpath proxy (Tailscale serve, nginx, etc.)
- **Never use `--bg` with Tailscale serve** — use `--json` to write the entire config atomically
- **Docker port conflicts** — always stop and remove old containers before recreating
- **Tailscale cert generation inside Docker fails** — always run `tailscale cert` on the host, not inside the container
