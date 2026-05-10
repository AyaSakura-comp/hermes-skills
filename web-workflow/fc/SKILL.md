---
name: fc
description: Perform web search then firecrawl scrape each result and combine.
category: web-workflow
---

**Description**: Perform a web search for a given query, then scrape each result URL using Firecrawl, and combine the extracted content into a single response.

**Trigger**: Slash command `/fc <query>` where `<query>` is the search term.

**Prerequisites**:
- Firecrawl API key in `~/.hermes/.env` as `FIRECRAWL_API_KEY`.
- Firecrawl SDK installed in the venv: `uv pip install firecrawl-py --python venv/bin/python`.

**Steps**:
1. **Parse Input**: Capture the user-provided query after `/fc`.
2. **Web Search**:
   - Call `web_search` with the query, requesting up to 5 results.
   - Extract the `url` field from each result.
3. **Firecrawl Scrape** (for each URL):
   - Use the Firecrawl SDK to scrape the content.
   - **Python Implementation Pattern**:
     ```python
     from firecrawl import FirecrawlApp
     import os

     # Load API key from .env
     api_key = None
     with open(os.path.expanduser('~/.hermes/.env')) as f:
         for line in f:
             if line.startswith('FIRECRAWL_API_KEY='):
                 api_key = line.split('=', 1)[1].strip()
                 break

     app = FirecrawlApp(api_key=api_key)
     doc = app.scrape(url=target_url, formats=['markdown'])
     content = doc.markdown
     ```
   - **Fallback**: If the SDK returns `InternalServerError` (common on X.com/Twitter), use the CLI:
     `npx firecrawl-cli@latest scrape <url>`
4. **Combine Results**:
   - Concatenate all scraped markdown sections, separating each with a heading indicating the source URL (e.g., `## Source: <url>`).
   - If any URL fails to scrape, note the error and continue.
5. **Output**:
   - Return the combined markdown to the user.
   - Include the original web search URLs as references (per user preference).

**Pitfalls**:
- **SDK v2 API**: Remember that `app.scrape_url` is deprecated; use `app.scrape(url=..., formats=['markdown'])`.
- **Pydantic Objects**: The SDK returns a `Document` object; use `result.markdown`, not `result['markdown']`.
- **Auth**: The SDK does NOT auto-read `FIRECRAWL_API_KEY` from env; it must be passed explicitly.
- **Anti-Bot Protection**: Some sites block the SDK's playwright backend. The `npx firecrawl-cli` is the recommended workaround for these cases.

**Verification**:
- After running `/fc test query`, verify that:
  - The response contains sections for each successfully scraped URL.
  - Each section starts with `## Source: <url>`.
  - The combined content is in markdown format.

**Example**:
```
/fc latest AI advancements 2024
```
Will search the web, scrape the top result pages via Firecrawl, and return a consolidated markdown summary.
