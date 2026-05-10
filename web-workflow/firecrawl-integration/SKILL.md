---
name: firecrawl-integration
description: Install, configure, and use Firecrawl SDK in hermes-agent for web scraping and crawling.
tags: [firecrawl, scraping, web, sdk]
---

# Firecrawl Integration

## Prerequisites

- Firecrawl API key from https://firecrawl.dev/dashboard
- hermes-agent Python venv at `~/Desktop/hermes-agent/venv/`

## Setup

### 1. Install the SDK

The hermes-agent venv does NOT have a `pip` binary. Use `uv` instead:

```bash
cd ~/Desktop/hermes-agent
uv pip install firecrawl-py --python venv/bin/python
```

### 2. Store the API key

Add the key to `~/.hermes/.env`:

```
FIRECRAWL_API_KEY=fc-YOUR-KEY
```

Verify with `grep FIRECRAWL ~/.hermes/.env`. Avoid duplicate entries — if duplicates exist, keep only one.

### 3b. (Optional) Install CLI via npm — needed for some protected sites

The Python SDK v2 sometimes fails with `InternalServerError` on sites with aggressive anti-bot protection (notably **X.com/Twitter**). The CLI (`firecrawl-cli` via npx) uses a different rendering backend and may succeed where the SDK fails.

```bash
npx firecrawl-cli@latest --version   # auto-installs the latest version
```

No global install needed — `npx` caches it. No Python/uv required.

## Two Installation Paths (CLI vs SDK)

| | Python SDK | CLI (npx) |
|---|---|---|
| Install | `uv pip install firecrawl-py` | `npx firecrawl-cli@latest` |
| Auth key | Pass `api_key=...` explicitly in code | Auto-reads `FIRECRAWL_API_KEY` env var |
| Protected sites (X.com, etc.) | Often fails (`InternalServerError`) | Works — different rendering backend |
| Best for | Programmatic processing in Python scripts | Quick scraping, crawling, search from CLI |
| JSON output | `doc.json` attr (Pydantic) | `-f 'type:json,prompt:X,schema:...'` |
| Results saved to | In memory / returned object | `.firecrawl/` directory |
| AI agent support | Yes (`app.extract()`) | `firecrawl agent "prompt"` |

## CLI Quick Reference

```bash
# Basic scrape (saves to .firecrawl/)
npx firecrawl-cli@latest scrape https://example.com

# Scrape with full API key flag (if env not set)
npx firecrawl-cli@latest scrape -k fc-xxxx https://example.com

# Scrape multiple URLs (concurrent)
npx firecrawl-cli@latest scrape "https://x.com/a" "https://x.com/b"

# Crawl a site
npx firecrawl-cli@latest crawl https://example.com

# Map URLs on a site
npx firecrawl-cli@latest map https://example.com

# Search the web
npx firecrawl-cli@latest search "query"

# AI agent extraction from a scraped page
npx firecrawl-cli@latest agent "Extract all product prices and names"

# Parse local file (HTML/PDF/DOCX/XLSX)
npx firecrawl-cli@latest parse myfile.html

# Status / remaining credits
npx firecrawl-cli@latest --status

# View config
npx firecrawl-cli@latest view-config

# JSON output with schema (note: single-quoted, comma-separated params)
npx firecrawl-cli@latest scrape -f 'type:json,prompt:Extract article info,schema:...

### 3. Verify installation

```python
from firecrawl import FirecrawlApp
app = FirecrawlApp(api_key='fc-xxx')
result = app.scrape(url='https://example.com', formats=['markdown'])
print(result.markdown[:200])
```

## Important: SDK v2 API differences

The version installed via `uv pip install firecrawl-py` is v2, which differs from the v0.0.16 docs. Key differences:

| v0.0.16 (docs) | v2 (actual) |
|---|---|
| `app.scrape_url('https://...')` | `app.scrape(url='https://...', formats=['markdown'])` |
| `result['markdown']` (dict) | `result.markdown` (Pydantic `Document` attr) |
| Auto-reads `FIRECRAWL_API_KEY` from env | Must pass `api_key=...` explicitly |
| `app.crawl_url('https://...')` | `app.crawl(url='https://...', formats=['markdown'])` |

### Common v2 API patterns

```python
from firecrawl import FirecrawlApp

app = FirecrawlApp(api_key='fc-xxx')

# Scrape a single URL
doc = app.scrape(url='https://example.com', formats=['markdown'])
print(doc.markdown)        # str
print(doc.metadata)        # dict
print(doc.html)            # str
print(doc.links)           # list of urls found
print(doc.metadata.get('title'))

# Crawl a site
result = app.crawl(url='https://example.com', limit=5, formats=['markdown'])
for doc in result:
    print(doc.markdown[:200])

# Search
sr = app.search('query', limit=3)
# sr.web is a list of result objects with .title and .url attrs

# Get credit usage
usage = app.get_credit_usage()  # returns remaining_credits, plan_credits, etc.

# Async operations (crawl, batch scrape, extract start async)
crawl_id = app.start_crawl(url='https://...', limit=10)
status = app.get_crawl_status(crawl_id)
```

### Loading API key from .env in scripts

```python
import os
api_key = None
with open(os.path.expanduser('~/.hermes/.env')) as f:
    for line in f:
        if line.startswith('FIRECRAWL_API_KEY='):
            api_key = line.split('=', 1)[1].strip()
            break
app = FirecrawlApp(api_key=api_key)
```

## Troubleshooting

- **"No API key provided"** — v2 doesn't read env vars automatically. Pass `api_key=...` explicitly or source from `.env` manually.
- **AttributeError: no scrape_url** — You're on v2. Use `app.scrape(url=...)` instead.
- **TypeError: 'Document' object is not subscriptable** — `result` is a Pydantic object, not a dict. Use `result.markdown` not `result['markdown']`.
- **pip: command not found in venv** — Use `uv pip install ... --python venv/bin/python` instead.
- **SDK returns `InternalServerError` on X.com/Twitter** — The Python SDK's rendering backend (playwright/puppeteer) gets blocked by X's anti-bot systems. Use the CLI instead: `npx firecrawl-cli@latest scrape https://x.com/...`. The CLI uses a different rendering pipeline that bypasses certain protections.
- **CLI JSON format error: `json format must be an object with { type: 'json', prompt, schema }`** — The `-f` flag requires a single-quoted, comma-separated string with at least `type`, `prompt`, and `schema` fields. Example: `-f 'type:json,prompt:Extract product name and price,schema:{...}'`.
- **Deduplicated `FIRECRAWL_API_KEY` in `~/.hermes/.env`** — Multiple setup attempts may create duplicate key lines. Firecrawl CLI reads the first match; SDK script (in the examples above) reads the first match. Remove extras to avoid confusion.
- **CLI not found after first `npx`** — `npx` caches the package. If the first run fails (network issue), retry. The package is `firecrawl-cli` on npm.
