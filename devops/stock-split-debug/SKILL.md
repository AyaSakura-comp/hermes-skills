---
name: stock-split-debug
description: Debug split-adjusted pricing errors in AssetSentry (0050崩盤、價格斷層等)
---

# Stock Split Debugging — AssetSentry

When chart shows a vertical crash (e.g. 0050 from ~750 to ~47), this is almost always a split-adjustment bug, NOT actual market data.

## Symptoms

- Price line drops vertically from ~700+ to ~40-50 in mid-2025
- Price before split is HIGHER than price after split (inverted)
- Chart looks like a catastrophic crash that never happened

## Root Causes (in order of likelihood)

### 1. Wrong arithmetic in `_apply_split_adjustments()`

File: `src/database.py` — method `_apply_split_adjustments()`

```python
# WRONG: multiply by split_ratio
df.loc[mask, col] = df.loc[mask, col] * split_ratio

# CORRECT: divide by split_ratio
df.loc[mask, col] = df.loc[mask, col] / split_ratio
```

**Split ratio definition:** FinMind returns `before_price / after_price`.
- For 0050: before=10, after=2 → ratio=5.0 (actual ~4.0002 due to partial shares)
- **Pre-split prices should be DIVIDED by ratio** to get post-split-equivalent values
- If data is 188.65 and ratio is 4.0002, result should be 188.65 / 4.0002 = 47.16

### 2. API called without `adjusted=true`

`market_client.py` fetches from `/market/{market}/{ticker}` without `?adjusted=true`.
Fix: add `params={"adjusted": "true"}` to the requests call.

### 3. Stale cache

Streamlit `@st.cache_data` caches old unadjusted data. Restart Streamlit dashboard to clear.

## Debugging Steps

### Step 1: Verify raw data from API

```bash
curl -s "http://localhost:8000/market/tw/0050?adjusted=true" | \
  python3 -c "
import sys, json
data = json.load(sys.stdin)
for r in data['data']:
    if r['Date'] in ['2025-06-10', '2025-06-18', '2025-06-19']:
        print(f'{r[\"Date\"]}  O:{r[\"Open\"]:.2f}  C:{r[\"Close\"]:.2f}')
"
```

**Expected** (after fix):
- 2025-06-10 (pre-split): Close ~47-48 (adjusted, same scale as post-split)
- 2025-06-18 (split day): Close ~47-48
- 2025-06-19 (post-split): Close ~47-48

**Before fix** (broken):
- 2025-06-10: Close ~754 (multiplied by ratio → inflated)
- 2025-06-18: Close ~47 (raw, unadjusted)
- Result: vertical crash from 754 → 47

### Step 2: Check split ratio in DB

```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('/home/chihmin/Assetsentry/AssetSentry/data/market/taiwan_market.db')
row = conn.execute(\"SELECT split_ratio, event_date FROM split_info WHERE ticker='0050'\").fetchone()
print(f'Split ratio: {row[0]}, Date: {row[1]}')
"
```

0050 should have ratio ~4.0002 on 2025-06-18.

### Step 3: Apply fix

Edit `src/database.py`:
```python
# Line ~869, change:
df.loc[mask, col] = df.loc[mask, col] / split_ratio
```

Then rebuild and restart:
```bash
cd /home/chihmin/Assetsentry/AssetSentry
docker compose build api
docker compose up -d
```

### Step 4: Verify fix

Wait ~10 seconds for API to start, then:
```bash
curl -s "http://localhost:8000/market/tw/0050?adjusted=true" | \
  python3 -c "
import sys, json
data = json.load(sys.stdin)
rows = data['data']
# Verify prices are continuous (no gap > 20%)
for i in range(len(rows)-5):
    a, b = rows[i]['Close'], rows[i+5]['Close']
    gap = abs(a - b) / a
    if gap > 0.2:
        print(f'WARNING: {rows[i][\"Date\"]} to {rows[i+5][\"Date\"]} gap: {gap:.1%}')
print('Price continuity check complete')
"
```

### Step 5: Clear Streamlit cache

- Reload dashboard page (`Ctrl+R`)
- Or restart dashboard container: `docker compose restart dashboard`

## Notes

- FinMind SDK's `taiwan_stock_split_price()` may return ALL stocks — filter by stock_id column
- Column name varies: could be `stock_id` or `stock_code` — auto-detect by looking for columns containing both "stock" and "id" in the name
- After any database fix, always rebuild the Docker image (not just restart) since source code is baked in during build