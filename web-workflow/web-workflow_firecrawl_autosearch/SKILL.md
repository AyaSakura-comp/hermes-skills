---
name: web-workflow_firecrawl_autosearch
description: "Automated pipeline: Tavly Search, then Firecrawl Scrape, then Synthesis."
---

# Firecrawl AutoSearch

This skill implements an automated research pipeline. It follows a "Search, Scrape, Summarize" workflow to provide deep, high-quality information on any topic.

## Workflow

1.  **Step 1: Discovery (Tavily)**
    *   Use `web_search` (powered by Tavily) to find the most relevant and recent URLs related to the user's query.
    *   Extract the top 3-5 URLs from the search results.

2.  **Step 2: Deep Scrape (Firecrawl)**
    *   Iterate through the discovered URLs.
    *   For each URL, use the `firecrawl-cli-preferred` method (using `npx firecrawl-cli scrape <url> --only-main-content`) to extract the clean, markdown-formatted content of the page.
    *   Handle potential errors (e.g., 403 Forbidden, 404 Not Found) gracefully.

3.  **Step 3: Synthesis (LLM)**
    *   Compile all the extracted markdown contents into a single context.
    *   Generate a comprehensive, software-structured summary that answers the user's original query.
    *   Organize the summary with clear headings and include citations/references to the URLs scraped.

## Requirements

-   **Tavily API Key**: Must be available in the environment (`TAVILY_API_KEY`).
-   **Firecrawl API Key**: Must be available in the environment (`FIRECRAWL_API_KEY`).
-   **Firecrawl CLI**: Accessible via `npx firecrawl-cli`.

## Usage Example

**User Input**: `/fc What are the latest advancements in room-temperature superconductivity?`

**Agent Action**:
1.  `web_search("latest advancements in room-temperature superconductivity")` $\to$ returns list of URLs.
2.  `npx firecrawl-cli scrape <url1> ...` $\to$ returns Markdown.
3.  `npx firecrawl-cli scrape <url2> ...` $\to$ returns Markdown.
4.  **Final Response**: "Recent breakthroughs in room-temperature superconductivity include... [Source: URL1] [Source: URL2]"

## Pitfalls

-   **Context Window Limits**: If too many URLs are scraped, the total text might exceed the model's context window. The agent should prioritize the top-most relevant URLs and potentially summarize them incrementally if necessary.
-   **Rate Limiting**: Rapid-fire scraping can trigger Firecrawl's rate limits. The agent should implement a small delay if performing many scrapes in a single session.
