---
name: docker-uv-deploy
description: Deploy Python projects that use `uv` for dependency management inside Docker — handles uv installation inside containers, Dockerfile building, and running FastAPI/Streamlit services manually.
tags:
  - docker
  - uv
  - deployment
  - python
---

# Docker Deployment for Python + uv Projects

Deploy a Python project that uses `uv` (astral) for dependency management inside Docker.

## Steps

### 1. Install uv inside container

**Preferred: pip install from host's pypi**
```bash
docker exec <container> pip3 install --break-system-packages uv
```

**Fallback: curl install (may time out)**
```bash
docker exec <container> curl -LsSf https://astral.sh/uv/install.sh | sh
# After install, uv is at /root/.local/bin/uv
```

### 2. Install dependencies

```bash
docker exec <container> sh -c "export PATH=\"/root/.local/bin:$PATH\" && cd /path/to/project && uv sync --frozen"
```

### 3. Build and deploy using the project's Dockerfile

**Check if docker compose is available:**
```bash
docker compose version   # or docker-compose version
# If unavailable, use manual docker run commands
```

**Build the image:**
```bash
cd /path/to/project
docker build -t <image-name>:latest .
```

**Run services (manual docker run, no compose):**

API (FastAPI):
```bash
docker run -d --name <service-name> \
  -v ~/MountDir/project/data:/app/data \
  -v ~/MountDir/project/.env:/app/.env:ro \
  -p 8000:8000 \
  --restart unless-stopped \
  <image-name>:latest \
  uv run python main_api.py
```

Dashboard (Streamlit):
```bash
docker run -d --name <dashboard-name> \
  -v ~/MountDir/project/data:/app/data \
  -v ~/MountDir/project/.env:/app/.env:ro \
  -p 8501:8501 \
  --restart unless-stopped \
  <image-name>:latest \
  uv run streamlit run dashboard.py --server.address 0.0.0.0
```

### 4. Verify deployment

```bash
docker ps --filter name=<service-name>
curl -s http://localhost:8000/docs   # FastAPI docs
curl -s http://localhost:8501       # Streamlit page
docker logs <service-name> | tail -20
```

## Pitfalls

- **`pip3 install uv` fails with PEP 668** — need `--break-system-packages` flag (common in Ubuntu-based images)
- **`curl` install script times out** — use pip fallback instead
- **`docker compose` unavailable** — the host may not have the compose plugin installed; always have a fallback with manual `docker run`
- **`docker cp` fails** if target directory doesn't exist in container — always `mkdir -p` first
- **.env file not auto-mounted** — explicitly mount it as read-only (`:ro`) if the app reads from `.env`
- **UV_LINK_MODE warning** — if cache and target are on different filesystems, set `export UV_LINK_MODE=copy`
- **Container restart behavior** — set `--restart unless-stopped` so services come back after host reboot

## Management Commands

```bash
# Logs
docker logs <service-name> -f

# Restart
docker restart <service-name>

# Stop all
docker stop assetssentry-api assetssentry-dashboard

# Remove containers
docker rm -f assetssentry-api assetssentry-dashboard
```

## When to Use

- Deploying Python projects with `uv` dependency management
- Projects with multiple services (API + Dashboard, worker + API, etc.)
- When docker compose is not available on the host
- When you need direct control over container configuration