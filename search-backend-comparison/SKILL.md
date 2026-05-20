---
name: search-backend-comparison
category: research
description: Compare SearXNG vs Tavily search backends using a structured 6-query, 5-dimension scoring methodology.
---

# Search Backend Comparison (SearXNG vs Tavily)

## When to Use
When the user asks to compare, evaluate, or benchmark SearXNG and Tavily search backends, or wants detailed search result analysis with scoring.

## Prerequisites
- SearXNG running on `http://localhost:8081`
- `tavily-python` SDK installed (`pip install tavily-python`)
- Tavily API key in `/home/chihmin/.hermes/.env` as `TAVILY_API_KEY`

## Comparison Methodology

### Query Selection
Use 6 diverse queries spanning:
1. **Factual/News** (Chinese): e.g., "2025 奧斯卡最佳影片"
2. **Tech/English**: e.g., "Rust vs Go 2025 performance benchmark"
3. **Local/Regional** (Chinese): e.g., "台北 2025 展覽 活動"
4. **Niche/Deep** (Chinese): e.g., "量子計算 量子位元 原理"
5. **Health** (English): e.g., "vitamin D deficiency symptoms recommended intake"
6. **Creative/Visual**: e.g., "most beautiful tabby cat funny"

### Scoring Dimensions (0-10 each, 5 total)
1. 🎯 **Relevance** — How well results match the query intent
2. 🔀 **Diversity** — Number of distinct engines/domains represented
3. 📝 **Snippet Quality** — Average description length (>200 chars = 10, >100 = 7, >50 = 5, else 3)
4. 🕐 **Freshness** — Year indicators present in title/snippet
5. 🏛️ **Domain Authority** — Count of reputable domains (Wiki, NYT, GitHub, StackOverflow, gov sites, etc.)

### Critical Bug: SearXNG Empty Results Pitfall ⚠️
When SearXNG returns **0 results**, it returns an **empty list `[]`** — NOT a list with an error object. This causes `IndexError` if you try `results[0].get('error')`.

**Correct check order:**
```python
if sx_results and not any('error' in r for r in sx_results):
    # process results
elif sx_results and 'error' in sx_results[0]:
    print(f"ERROR: {sx_results[0]['error']}")
else:
    print("⚠️ No results returned")  # empty list case
```

### Output Format
Present results in a detailed block per query showing:
- Response time
- Each result with title, URL, description (first 5 lines), score
- Side-by-side comparison table
- Grand total scores and speed comparison

## Files
- Comparison script: `/tmp/search_compare_detailed.py`
- Raw data: `/tmp/search_comparison_raw.json`

## Typical Results Pattern (as of May 2026)
- **Tavily wins** on relevance (especially for English queries), diversity, snippet quality, and coverage (returns results where SearXNG returns 0)
- **SearXNG wins** on speed (avg 0.39s vs 1.01s) and sometimes domain authority for Chinese queries
- **SearXNG commonly returns 0 results** for English queries, technical topics, and niche subjects
- **Grand score gap**: ~127 points (Tavily ~222 vs SearXNG ~95 out of 300 max)
