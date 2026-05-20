---
name: docker-compose-communication-debug
description: Systematic workflow for diagnosing and fixing inter-service communication failures in Docker Compose setups (e.g., Dashboard "Connection refused" when API works directly).
---

# Docker Compose Service Communication Debugging

Systematic workflow for diagnosing and fixing inter-service communication failures in Docker Compose setups.

## When to use
- Dashboard/UI service shows "Connection refused" or "Data unavailable"
- API service returns HTTP 200 when tested directly but UI cannot reach it
- Two containers in the same compose network cannot talk to each other

## Debugging Workflow (Numbered Steps)

### Step 1: Verify Database/Data Integrity
Before assuming network issues, confirm data exists:
```bash
docker exec <container-name> find /app -name "*.db" 2>/dev/null
```
Check tables and row counts:
```bash
docker cp /tmp/check_db.py <container>:/tmp/check_db.py && docker exec <container> /app/.venv/bin/python3 /tmp/check_db.py
```

### Step 2: Test API Directly (Bypass UI)
Confirm the API service itself works:
```bash
curl -s 'http://localhost:<port>/market/tw/0050' | python3 -c "import sys, json; data=json.load(sys.stdin); print('Status:', 'OK' if 'data' in data else 'ERROR')"
```
If this returns 200/OK → API is fine, problem is in the UI → API connection path.

### Step 3: Check Dashboard Logs
```bash
docker logs <dashboard-container> --tail 50
```
Look for:
- `[Errno 111] Connection refused` → API not reachable from dashboard container
- `Metadata check failed` → metadata endpoint unreachable
- If logs show connection refused for ALL tickers → systemic network/config issue

### Step 4: Verify Environment Variables in Container
The #1 cause of "Connection refused" in Docker Compose:
```bash
docker exec <container-name> printenv ASSETSENTRY_API_BASE_URL
```
If empty or shows `127.0.0.1` instead of `http://api:8000` → environment variable not injected.

**Root cause pattern:** `constants.py` (or equivalent) defaults to `http://127.0.0.1:<port>` but inside a Docker container, `127.0.0.1` refers to the container itself, not the host or another service.

### Step 5: Fix docker-compose.yml
Add environment variables to the affected service:
```yaml
services:
  dashboard:
    environment:
      - ASSETSENTRY_API_BASE_URL=http://api:8000
```
Docker Compose's internal DNS resolves service names (`api`, `db`, etc.) to container IPs automatically — **no custom network needed**.

### Step 6: Rebuild and Verify
```bash
docker compose up -d dashboard api
```
Wait ~30s then check logs for new errors:
```bash
sleep 10 && docker logs <dashboard-container> --tail 20
```

## Common Pitfalls

1. **`.env` file mounted as volume ≠ environment variables** — `volumes: - ./.env:/app/.env` does NOT set OS environment variables. Must use `environment:` in docker-compose.yml or use `env_file:` directive.

2. **`127.0.0.1` vs service name** — Inside a container, `127.0.0.1` always means "this container". Use `http://<service-name>:<port>` for inter-container communication.

3. **Streamlit cache persistence** — Streamlit caches API responses. After fixing the connection, you may need to force-refresh the page or clear Streamlit's cache.

4. **Container name vs service name** — `docker ps` shows container names like `assetsentry-api-1`, but in docker-compose.yml you reference service names like `api`. The DNS lookup uses the **service name**.

## Verification Checklist
- [ ] API returns 200 when curl'd directly from host
- [ ] Dashboard logs show no "Connection refused" errors
- [ ] `docker exec <container> printenv <VAR>` returns correct value
- [ ] Dashboard UI displays data correctly
- [ ] All services (not just one ticker) work correctly
