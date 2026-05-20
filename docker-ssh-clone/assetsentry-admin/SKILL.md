---
name: assetsentry-admin
description: Administer AssetSentry portfolio tracker — create/delete users, update passwords, inspect DB, manage sessions.
---

# AssetSentry Administration

## Overview

AssetSentry is a portfolio tracking dashboard running via Docker. Admin tasks (user management, DB inspection) are done on the API container.

## Key Ports

- Dashboard (Streamlit UI): **8501**
- API Server: **8000**

## Container Names

- API: `assetsentry-api-1` (also accessible as `assetsentry-api`)
- Dashboard: `assetsentry-dashboard-1` (also accessible as `assetsentry-dashboard`)

Use `docker ps --format '{{.Names}}'` to discover current names if unsure.

## ⚠️ Critical: Use the venv Python

The container's system Python (`docker exec ... python3`) is **missing** pydantic-settings and other deps. Always use:

```bash
docker exec assetsentry-api-1 /app/.venv/bin/python3 -c "..."
```

If the venv Python fails or the container doesn't have Python in its path, fall back to raw SQLite access:

```bash
# Find the DB first
docker exec assetsentry-dashboard-1 find / -name "users.db" 2>/dev/null

# Then reset password by writing scrypt hash directly (bypasses Python entirely)
docker exec assetsentry-dashboard-1 python3 -c "
import hashlib, secrets
salt = secrets.token_bytes(16)
phash = hashlib.scrypt('newpassword'.encode(), salt=salt, n=16384, r=8, p=1)
hashed = f'{salt.hex()}:{phash.hex()}'
import sqlite3
conn = sqlite3.connect('/app/data/users/users.db')
conn.execute('UPDATE users SET password_hash = ? WHERE username = ?', (hashed, 'admin'))
conn.commit()
conn.close()
print('Password reset to: newpassword')
"
```

## ⚠️ Docker Rebuild: Always Use `--no-cache` for Code Changes

When you modify source code (e.g., `database.py`, `config.py`), the Docker image **caches** the old layers. Code changes will NOT take effect without:

```bash
cd /home/chihmin/Assetsentry/AssetSentry && docker compose build --no-cache && docker compose up -d
```

If `docker compose up -d` returns exit -1, just run it again in background mode — Docker may be waiting for resources.

## Database

- Path inside container: `/app/data/users/users.db`
- SQLite database with `users` and `sessions` tables

## Creating an Admin User (CLI)

When no users exist (database starts empty), create one programmatically:

```bash
docker exec assetssentry-api /app/.venv/bin/python3 -c "
import sys
sys.path.insert(0, '/app/src')
from user_manager import UserManager
from models.user import UserRole

um = UserManager('/app/data/users/users.db')
uid = um.create_user('admin', '<password>', role=UserRole.ADMIN, must_change_password=False)
print(f'Created id={uid}')
"
```

Parameters:
- `username`: alphanumeric, starts with a letter (validated by pydantic)
- `password`: minimum 6 characters
- `role`: `UserRole.ADMIN` or `UserRole.USER`
- `must_change_password`: set `False` to skip forced reset on first login

## Creating Users via Web UI

If already logged in as admin, go to Dashboard (port 8501) → **User Management** page:
1. Click **"➕ Create New User"** popover
2. Enter username, temporary password, and select role (Admin/User)
3. Click "Create User"

New users are created with `must_change_password=True` by default, forcing a password reset on first login.

## Listing Users (CLI)

```bash
docker exec assetssentry-api /app/.venv/bin/python3 -c "
import sys
sys.path.insert(0, '/app/src')
from user_manager import UserManager
um = UserManager('/app/data/users/users.db')
for u in um.list_users():
    print(f'{u.username} | {u.role} | must_change={u.must_change_password}')
"
```

## Deleting a User (CLI)

```bash
docker exec assetssentry-api /app/.venv/bin/python3 -c "
import sys
sys.path.insert(0, '/app/src')
from user_manager import UserManager
um = UserManager('/app/data/users/users.db')
# First get user id
for u in um.list_users():
    if u.username == 'USERNAME':
        um.delete_user(u.id)
        print(f'Deleted user id={u.id}')
"
```

⚠️ Deleting a user permanently removes their account record AND all associated data directory.

## Updating Password (CLI)

```bash
docker exec assetssentry-api /app/.venv/bin/python3 -c "
import sys
sys.path.insert(0, '/app/src')
from user_manager import UserManager
um = UserManager('/app/data/users/users.db')
user = um.get_user_by_username('USERNAME')
if user:
    um.update_password(user.id, 'NEW_PASSWORD')
    print('Password updated')
"
```

## Configuration (.env)

The `.env` file at `/home/chihmin/Assetsentry/AssetSentry/.env` is **bind-mounted read-only** into the container. To modify it:

```bash
# 1. Edit on the HOST (file may be root-owned)
sudo sh -c 'echo "FINMIND_TOKEN=<your-token>" > /home/chihmin/Assetsentry/AssetSentry/.env'

# 2. Rebuild + restart for changes to take effect
cd /home/chihmin/Assetsentry/AssetSentry && docker compose build --no-cache && docker compose up -d
```

Available config keys (defined in `/app/src/config.py`):
- `FINMIND_TOKEN` — Finmind financial data API token
- `TELEGRAM_BOT_TOKEN` — Telegram bot token for notifications
- `TIINGO_API_KEY` — Tiingo stock data API key

## Database (Market Data)

Stock data is stored in `/app/data/market/` inside the container:

- Path: `/app/data/market/taiwan_market.db`
- Tables: one per ticker (e.g., `0050`, `2330`)
- FinMind fetches data on startup if tables don't exist yet

⚠️ If the `data/market/` directory doesn't exist on the host (volume mount point), the DB files are never created. The fix is in `database.py` `__init__` — it auto-creates the directory now.

To inspect market data:

```bash
docker exec assetsentry-api-1 /app/.venv/bin/python3 -c "
import sqlite3
conn = sqlite3.connect('/app/data/market/taiwan_market.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute(\"SELECT name FROM sqlite_master WHERE type='table'\")
for t in cur.fetchall():
    cur.execute(f'SELECT COUNT(*) FROM \"{t[0]}\"')
    print(f'{t[0]}: {cur.fetchone()[0]} rows')
conn.close()
"
```

## Troubleshooting

- **Port conflicts**: The launcher script (`/app/src/launcher.py`) checks ports 8000 and 8501 on startup and can terminate conflicting processes.
- **Login fails**: Check that the user exists in the DB; verify password (it's hashed with scrypt, can't be recovered — must update). Use raw SQLite access as fallback.
- **Session issues**: Clear all sessions via the admin page's DB Inspector → sessions table → "Clear All Sessions" button.
- **Config not taking effect**: `.env` is bind-mounted read-only. Edit on the host, then **rebuild** (`--no-cache`) + restart containers.
- **Container name not found** (`No such container`): Docker Compose v2 names containers as `project-service-number`. Use `docker ps --format '{{.Names}}'` to check actual names.
- **Code changes not picking up**: Docker caches image layers. Always `docker compose build --no-cache` after modifying source code.
- **Stock data missing (e.g., 0050 returns "Ticker not found")**: The `data/market/` directory may not exist on the host volume mount. The fix is in `database.py` `__init__` which auto-creates the directory. Rebuild after the fix.
- **Market data fetching but not writing to DB**: Check if the `data/market/` directory exists. Also verify FinMind token is valid — fetch errors silently. Check API logs: `docker logs assetsentry-api-1 | grep -i "finmind\|fetch\|error"`.
