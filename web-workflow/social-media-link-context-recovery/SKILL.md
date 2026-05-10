---
name: social-media-link-context-recovery
description: A strategy for analyzing links from dynamic or protected social media platforms (X, Instagram, Threads) when standard web tools fail.
---

# social-media-link-context-recovery

A strategy for summarizing or analyzing links from highly dynamic or protected social media platforms (like X/Twitter, Instagram, or Threads) when standard browser automation tools (like `browser_navigate` or `web_extract`) fail due to SPA architecture or anti-scraping measures.

## Trigger
When a user provides a URL to a social media platform and the agent encounters `Failed to fetch url` or `Connection refused` errors using standard web tools.

## Workflow

1. **Initial Attempt**: Try `web_extract` on the URL.
2. **Metadata Extraction**: If `web_extract` fails, use `web_search` with the exact URL as the search query. This leverages search engine indexes (which often cache the text content of the post) to find descriptions and snippets.
3. **Connectivity Verification**: Use `execute_code` with `curl` to determine if the URL is reachable and to inspect the raw HTML structure for any clues or metadata.
4. **Contextual Analysis**: Analyze the search engine results and `curl` output to reconstruct as much of the post's content as possible.
5. **User Request**: If the content is still unavailable, explicitly inform the user of the technical limitation (e.g., "the page is dynamic/protected") and request a **screenshot** or a **manual text copy** of the post.

## Pitfalls
- **Raw HTML Limitation**: Do not rely on `curl` for content extraction on modern SPAs, as the primary content is injected via JavaScript after the initial load. Use it only for reachability checks.
- **Search Engine Latency**: Search snippets might be outdated compared to the live post.
