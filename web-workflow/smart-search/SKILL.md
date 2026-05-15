---
name: smart-search
description: "Intelligent multi-stage search: Expands query via web search, finds related URLs, and deep-scrapes content using the FC workflow."
category: web-workflow
---

**Description**: An advanced research workflow that prevents information silos. Instead of searching just one term, it uses the initial query to discover related concepts and then performs deep-content extraction on the architecture of relevant URLs.

**Trigger**: Slash command `/smart-search <query>` where `<query>` is the initial topic.

**Prerequisites**:
- `fc` skill must be available to handle the scraping phase.
- `web_search` tool must be functional.

**Steps**:
1. **Phase 1: Keyword Expansion (The "Tavily/DDG" way)**
   - **Task A**: Execute `web_search(query=<query>)`. Analyze the titles and descriptions of the top 5 results to extract 3-5 "Expansion Keywords" (e.g., related technologies, specific brands, or sub-topics).
   - **Task B**: Execute a second `web_search` using a broader, more general query pattern (e.g., "latest trends in <query>" or "<query> related topics") to simulate DuckDuckGo's breadth. Extract another 3-5 keywords.

2. **Phase 2: URL Discovery**
   - For each keyword identified in Phase 1:
     - Run `web_search(query=<keyword>)`.
     - Collect the `url` of the top 2 results per keyword.
   - Create a deduplicated master list of all identified URLs.

3. **Phase 3: Deep Content Extraction (The "FC" Integration)**
   - For every URL in the master list:
     - Execute the `fc` workflow: Perform `firecrawl_scrape` (using the SDK or CLI fallback) to get the full markdown content.
   - **Note**: If the list is too large (>10 URLs), priority should be given to the most recent or most relevant URLs to prevent timeout.

4. **Phase 4: Synthesis & Reporting**
   - **Aggregation**: Combine all scraped Markdown sections.
   - **Structure**:
     - `# Smart Search Report: <original_query>`
     - `## 🧠 Expansion Strategy` (List the keywords used for expansion)
     - `## 🌐 Discovered Sources` (List all URLs processed)
     - `## 📄 Detailed Findings` (The concatenated content from all scrapes, with `## Source: <url>` headers)
   - **References**: Include the original search URLs as per user preference.

**Pitfalls**:
- **Token Overload**: Deep scraping many URLs can lead to extremely large responses. The agent should summarize if the content exceeds context limits.
- **Redundancy**: Avoid scraping the same URL multiple times by using a set for URL collection.
- **Search Loops**: Ensure the expansion phase does not recursively generate more searches indefinitely.

**Example**:
`/smart-search 台灣製造固態電池`
1. 擴展出「鋰硫電池」、「電池安全認證」、「固態電解質技術」。
2. 搜尋這些關鍵字並收集相關網頁。
3. 使用 `fc` 爬取並整合成一份完整的技術與市場研究報告。
