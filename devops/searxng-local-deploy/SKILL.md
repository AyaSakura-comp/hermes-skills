---
name: searxng-local-deploy
description: Deploy SearXNG from official repo with localhost access on port 8081 (8080 occupied by Open WebUI). Also covers Tailscale serve path routing.
---

# SearXNG Local Docker Deploy

Deploy SearXNG from official repo with localhost access (port 8081) and optional Tailscale serve exposure.

## Trigger Conditions
- User wants to deploy SearXNG via Docker on localhost
- Port 8080 is occupied (typically by Open WebUI)
- User wants SearXNG accessible via Tailscale

## Steps

### 1. Check port conflicts
```bash
ss -tlnp | grep 8080
```
If Open WebUI (or anything else) uses 8080, use **8081** for SearXNG.

### 2. Remove old deployment (if any)
```bash
docker ps --filter "name=searxng" --format "{{.Names}}" | xargs -r docker stop
docker ps -a --filter "name=searxng" --format "{{.Names}}" | xargs -r docker rm
docker rmi searxng/searxng:latest 2>/dev/null
```
**Important:** Also stop Tailscale serve to free port 443:
```bash
sudo tailscale serve reset
```

### 3. Clean up old directories
```bash
sudo rm -rf /home/chihmin/searxng 2>/dev/null
rm -rf /home/chihmin/searxng-config 2>/dev/null
rm -f /home/chihmin/docker-compose-v2.yml 2>/dev/null
```
**Note:** `sudo rm` needed — searxng dir often owned by UID 977 (Docker user).
**Note:** `rm -rf` on skill directories times out in terminal tool — use Python `shutil.rmtree()` via execute_code instead.

### 4. Clone official repo
```bash
cd /home/chihmin && git clone https://github.com/searxng/searxng.git
```

### 5. Create deploy directory
```bash
mkdir -p /home/chihmin/searxng-deploy/core-config
```

### 6. Create docker-compose.yml
```yaml
name: searxng
services:
  core:
    container_name: searxng-core
    image: docker.io/searxng/searxng:${SEARXNG_VERSION:-latest}
    restart: always
    ports:
      - ${SEARXNG_HOST:+${SEARXNG_HOST}:}${SEARXNG_PORT:-8081}:${SEARXNG_PORT:-8081}
    env_file: ./.env
    volumes:
      - ./core-config/:/etc/searxng/:Z
      - core-data:/var/cache/searxng/
  valkey:
    container_name: searxng-valkey
    image: docker.io/valkey/valkey:9-alpine
    command: valkey-server --save 30 1 --loglevel warning
    restart: always
    volumes:
      - valkey-data:/data/
volumes:
  core-data:
  valkey-data:
```

### 7. Create .env file
```bash
SEARXNG_HOST=
SEARXNG_PORT=8081
SEARXNG_BASE_URL=http://localhost:8081/
SEARXNG_SECRET=$(openssl rand -hex 32)
SEARXNG_INTERNAL_PORT=8081
```

### 8. Create settings.yml (in `core-config/`)
```yaml
use_default_settings: true
search:
  default_locale: ""
server:
  limiter: false
```

### 9. Deploy
```bash
cd /home/chihmin/searxng-deploy
docker compose pull
docker compose up -d   # background mode (long-lived process)
```

### 10. Verify — CRITICAL: Always check both paths
```bash
# SearXNG serves at ROOT path (/), NOT /searxng subpath
curl -sI http://localhost:8081/
```
Expected: `HTTP/1.1 200 OK` + `<title>SearXNG</title>` in body.

**⚠️ CRITICAL:** SearXNG serves at `/` (root path). Accessing `/searxng` returns **404**. Tailscale serve must proxy to `http://localhost:8081/` (NOT `/searxng`).

### 11. (Optional) Tailscale Serve — Path Routing

**Tailscale MagicDNS limitation:** MagicDNS format is `<hostname>.<tailnet-domain>.ts.net`. It does **NOT** support nested subdomains like `search.aya.crayfish-monitor.ts.net`. Use **path routing** instead:
- `https://aya.crayfish-monitor.ts.net/` → SearXNG
- `https://aya.crayfish-monitor.ts.net/stock` → stock service

Reset old routes:
```bash
sudo tailscale serve reset
```

**Incremental approach (recommended, avoids overwriting):**
```bash
# Set root path first
sudo tailscale serve --bg http://localhost:8081/
# Then add subpaths with --set-path (does NOT overwrite existing)
sudo tailscale serve --bg --set-path /stock http://localhost:8501/
```

**⚠️ DO NOT use `--json` for current Tailscale CLI** — the config format is fragile (requires specific version string, unsupported top-level keys). Use incremental `--set-path` instead.

Verify:
```bash
sudo tailscale serve status --json
```

## ⚠️ Known Pitfalls

- **Port 8080 conflict:** Open WebUI uses 8080. Use 8081 for SearXNG.
- **`default_locale` MUST be `""`:** Any locale value (e.g. `"zh-TW"`) causes **500 error**.
- **SearXNG serves at `/` (root path), NOT `/searxng`:** This is a common misconception. Tailscale serve and any reverse proxy MUST proxy to `http://localhost:8081/` (bare root). Accessing `/searxng` returns **404**.
- **`sudo rm` needed for old dirs:** searxng dir often owned by UID 977 (Docker user).
- **docker compose up:** Long-lived process — use `background=true`.
- **radio_browser engine SQL error:** `OperationalError: no such table: radios` on first start is **normal** — the table auto-creates on first search. Safe to ignore.
- **startpage CAPTCHA exception:** `SearxEngineCaptchaException` on first run is **normal** — startpage suspends the engine for 3600s. Subsequent searches will succeed.
- **First-start SQLite errors:** Normal — tables auto-create on first search.
- **limiter.toml missing:** Benign if `limiter: false` in settings.yml.
- **Tailscale serve incremental overwrites:** Each `tailscale serve --bg <root>` call overwrites ALL existing routes. Use `--set-path <subpath>` to ADD routes without overwriting.
- **Tailscale serve `--json` is fragile:** Current CLI version rejects standard JSON format. Use incremental `--set-path` instead.
- **curl from localhost needs SNI:** When testing Tailscale serve via curl from the same machine, use `--resolve "hostname:443:100.x.x.x"` to provide SNI. Without it, TLS handshake fails with `no SNI ServerName`.

## Management
```bash
cd /home/chihmin/searxng-deploy
docker compose ps
docker compose logs -f core
docker compose down
docker compose pull && docker compose up -d   # update
```

## Update from upstream
```bash
cd /home/chihmin/searxng && git pull
docker compose -f /home/chihmin/searxng-deploy/docker-compose.yml pull
docker compose -f /home/chihmin/searxng-deploy/docker-compose.yml up -d
```

## Related: Streamlit apps behind Tailscale subpath
When deploying any Streamlit app via Tailscale serve on a subpath (e.g. `/stock`), the app returns a **blank page** because it can't load static resources from the wrong base path. **Fix:** Add `--server.baseUrlPath=<subpath>` to the Streamlit command.

```bash
# Wrong (blank page on /stock)
streamlit run app.py --server.address 0.0.0.0

# Correct (static resources load properly on /stock)
streamlit run app.py --server.address 0.0.0.0 --server.baseUrlPath=/stock
```