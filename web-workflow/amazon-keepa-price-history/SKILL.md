---
name: amazon-keepa-price-history
description: Workflow for retrieving Amazon price history using Keepa, including a fallback method using the search bar when direct ASIN links fail.
---

# Amazon Price History Tracking via Keepa

This skill provides a reliable workflow for retrieving Amazon price history using Keepa, specifically addressing pitfalls where direct ASIN URLs or Amazon links may fail to load.

## Trigger Conditions
- User wants to check the price history of an Amazon product.
- User provides an Amazon URL (including shortened `amzn.asia` or `amzn.to` links).
- Standard `keepa.com/#!product/[ASIN]` navigation returns "Invalid ASIN" or a blank page.

## Tool Selection: Prefer MCP Chrome DevTools

When accessing Keepa, the Hermes browser tools (`browser_navigate`/`browser_snapshot`) often return empty accessibility trees despite a fully rendered page. **Use the Chrome DevTools MCP tools instead** (`mcp_chrome_devtools_new_page`, `mcp_chrome_devtools_take_snapshot`, `mcp_chrome_devtools_click`, `mcp_chrome_devtools_fill`, `mcp_chrome_devtools_press_key`) for all Keepa interactions.

## Workflow Steps

1. **Extract ASIN from URL**
   - Navigate to the provided Amazon URL first to resolve any redirects.
   - Extract the 10-character alphanumeric ASIN (Amazon Standard Identification Number) from the resulting URL (e.g., `B0F48L8TKK`).

2. **Primary Attempt: Direct ASIN Link**
   - Open a new page with the direct ASIN URL: `https://keepa.com/#!product/[ASIN]`.
   - Take a snapshot to check if the product page loaded successfully.
   - If a price chart is visible, the task is complete.

3. **Secondary Attempt: Keepa Search Bar (The "URL Paste" Method)**
   - If the direct link fails or shows "Invalid ASIN", stay on the current page (it already has the search button visible).
   - **Click the 検索 (Search) magnifying glass link** — this reveals a hidden search textbox ("商品の検索").
   - **Key Finding:** Paste the **full Amazon product URL** (e.g. `https://www.amazon.co.jp/dp/B0D4TH6D4T`) into the search bar and press Enter.
   - Keepa's internal search handler is more robust than its direct URL routing and resolves products that `#!product/` fails to find. The resulting URL changes to `keepa.com/#!product/5-[ASIN]` (the `5-` prefix indicates Amazon Japan).
   - Take a screenshot of the chart and share it with the user via `MEDIA:` path.

4. **Verification**
   - Confirm the product name matches the original Amazon listing.
   - Read the "Buy Box", "Amazon", and "New" price points from the summary table.
   - Check the "All time" (全期間) duration to determine how long the product has been tracked.

## Companion Research: Regional Compatibility & Shipping

When the user is comparing prices on Amazon Japan for electronics/appliances, they may also want to know if the item works in their country and if it ships internationally.

### Regional Compatibility (Voltage / Certification / Region Lock)

Dyson hair dryers sold in Japan have a **voltage lock** mechanism — they are designed for Japan's 100V standard and may fail (show error lights, become unresponsive, or sustain permanent damage) when used at 110V–120V (Taiwan, USA). This is a hardwired protection, not a simple plug adapter issue. Travel versions (supporting 100V–240V) are the exception.

**Research workflow:**
1. Search `site:ptt.cc <product> 電壓` for Taiwan-specific user reports
2. Search `site:reddit.com <product> Japan voltage` for English-language experiences
3. Search `site:reddit.com <product> Japan "bought in"` for import/region-lock stories
4. Extract and summarize findings — look for: error indicators (flashing lights), "not compatible" messages from customer support, and confirmed working/not-working anecdotes at the target voltage

### International Shipping Check
- On Amazon Japan product pages, look for the shipping eligibility section (配送先: 台湾).
- If ambiguous, use the item's "Add to Cart" flow to check delivery address options.
- Note that Amazon Japan uses ASINs prefixed with `5-` in Keepa (e.g., `5-B0D4TH6D4T` for Japan marketplace).

### Presenting Results
When presenting price + compatibility research:
- Lead with the **price data** (current, low, chart image via MEDIA:).
- Follow with the **risk assessment** — summarize the voltage/lock reality and user anecdotes.
- Conclude with a clear **recommendation** (buy / avoid / look for travel version / wait for local release).

## Pitfalls & Tips
- **Use MCP over Hermes browser tools:** The Hermes `browser_navigate`/`browser_snapshot` tools often return empty accessibility trees for Keepa pages. Always prefer MCP Chrome DevTools tools (`mcp_chrome_devtools_new_page`, `mcp_chrome_devtools_take_snapshot`, etc.) for Keepa.
- **URL Routing vs. Search:** `keepa.com/#!product/[ASIN]` is a direct route and may fail if the ASIN index is fresh or cached differently. The search bar uses a different resolution mechanism that handles full URLs better.
- **Search button is initially hidden:** The textbox only appears after clicking the 検索 (magnifying glass) link (`javascript:void(0)`). The uid is typically `1_13` in the snapshot.
- **Bot Detection:** Keepa may use aggressive bot detection. If the page is blank, try checking via `mcp_chrome_devtools_take_screenshot` with vision to see if a CAPTCHA or error message is present.
- **New Products:** If both methods fail, the product may be too new for Keepa's database. Inform the user that the product has no available history.
