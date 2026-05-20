---
name: docker-stock-split-debug
description: Debug stock split adjustment issues in AssetSentry deployed on Docker — diagnose why adjusted prices aren't different from raw prices.
---

## Stock Split Debug Workflow (AssetSentry Docker)

### Step 1: Verify API endpoint works
```bash
# Test adjusted=true
docker exec assetsentry-api-1 curl -s http://localhost:8000/market/tw/0050?adjusted=true | head -c 500

# Test adjusted=false
docker exec assetsentry-api-1 curl -s http://localhost:8000/market/tw/0050?adjusted=false | head -c 500
```
Expected: Both return HTTP 200 with data arrays. If both show identical prices, proceed to Step 2.

### Step 2: Write inspection script to file (DO NOT use one-liners)
Docker exec Python one-liners fail with `SyntaxError: '(' was never closed` due to nested quote escaping. Always use this pattern:

```bash
# 1. Write script to a temp file on host
# 2. Copy into container
docker cp /tmp/check_split.py assetsentry-api-1:/tmp/check_split.py
# 3. Execute inside container
docker exec assetsentry-api-1 /app/.venv/bin/python /tmp/check_split.py
```

### Step 3: Key diagnostics to check

**3a. Does split_info table exist?**
```python
import sqlite3
conn = sqlite3.connect('/app/data/market_data.db')
c = conn.cursor()

# List all tables
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
print('Tables:', [t[0] for t in c.fetchall()])

# Check split_info content
c.execute('SELECT * FROM split_info')
rows = c.fetchall()
print(f'split_info rows: {len(rows)}')
for row in rows[:20]:
    print(row)
conn.close()
```

**3b. Are split event dates in the price data?**
```python
# 0050 had splits on 2018-04-20 and 2020-04-20
conn = sqlite3.connect('/app/data/market_data.db')
c = conn.cursor()
c.execute('SELECT * FROM "0050" WHERE Date IN ("2018-04-20", "2020-04-20")')
print('Split event dates in data:', c.fetchall())
conn.close()
```

**3c. Compare adjusted vs unadjusted ratios**
```python
# Fetch both datasets, zip together, check ratio column
# If all ratios are 1.0000, split_info is empty
```

### Step 4: Root cause diagnosis

| Symptom | Likely Cause |
|---------|-------------|
| split_info table doesn't exist | `database.py` changes not deployed to Docker |
| split_info exists but empty | FinMind split data not fetched or DB write failed |
| split_info has data but ratios are 1.0 | Adjustment logic not triggered (check `get_split_adjusted_data()` is called) |
| Date in split_info doesn't match price data | Date format mismatch between FinMind and DB |

### Step 5: Fix — populate split_info
```python
from src.database import TwStockDB
db = TwStockDB()
# Fetch and save split info for a ticker
splits = db.get_split_info('0050')
print(f'Fetched {len(splits)} split events')
```

### Key Paths & Facts
- Docker container: `assetsentry-api-1`
- DB path inside container: `/app/data/market_data.db`
- Python venv inside container: `/app/.venv/bin/python`
- API base URL: `http://localhost:8000`
- API parameter: `?adjusted=true/false` (default `true`)
- Key method: `TwStockDB.get_split_adjusted_data(ticker)`
- Common split dates for 0050: 2018-04-20, 2020-04-20 (1→1.1 splits)

### Pitfalls
1. **Never use Python one-liners in Docker exec** — always write file → docker cp → docker exec python file.py
2. **FinMind split data may not be pre-fetched** — the database needs `get_split_info()` called at least once
3. **Docker changes require rebuild** — `docker compose up -d --build` after code changes
4. **Check `split_info` table exists** — the CREATE TABLE happens in `TwStockDB.__init__()` or migration logic
