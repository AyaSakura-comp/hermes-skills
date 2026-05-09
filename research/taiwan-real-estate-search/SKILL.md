---
name: taiwan-real-estate-search
title: Taiwan Real Estate Search
description: Efficiently navigate and extract property data from major Taiwan real estate platforms (Sinyi, Yungching) handling UI flakiness.
---

# Taiwan Real Estate Search

Efficiently navigate and extract property data from major Taiwan real estate platforms (Sinyi 信義房屋, Yungching 永慶房屋) while handling UI flakiness and market-specific nuances.

## Trigger Conditions
- User asks for property prices or listings in Taiwan.
- User specifies "second-hand houses" (中古屋), "apartments" (公寓), or "elevator buildings" (電梯大樓).
- Task involves searching near a specific landmark or MRT station.

## Workflow

### 1. Initial Search
- **Sinyi (信義房屋)**: Use the main search box `textbox` with keywords like "南港車站" or "捷運永春站".
- **Yungching (永慶房屋)**: Similarly, use the keyword search.
- **Tip**: If the user provides a landmark, type it directly into the search bar rather than navigating through tiered region menus (it's faster and more accurate).

### 2. Handling Filter Failures & Advanced Navigation
- **The "Direct URL" Strategy**: If UI filters (room count, age) are unresponsive or elements keep changing, construct the URL directly. Platforms like Sinyi use predictable URL structures:
    - `.../buy/list/[Region]/[Landmark]/[Rooms]-rooms/[Age]-years/index.html`
    - Directly navigating to a filtered URL is much faster and bypasses state issues in headless browsers.
- **The "Small Result" Strategy**: If total results are < 20, do not waste turns filtering. Scrape all and filter manually in the summary.
- **Vision Verification**: Use `browser_vision` to confirm if a landmark search (e.g., "Nangang Station") actually applied or if it defaulted back to a broader district (e.g., "Nangang District").

### 3. User Interaction - Visual Feedback
- **Step-by-Step Reporting**: If a user requests visual confirmation (e.g., "send me screenshots"), perform `browser_vision` after every significant action (typing keywords, applying filters) and deliver it via `MEDIA:/path/to/screenshot.png` in the response.

### 3. Data Extraction & Categorization
Taiwan property prices vary wildly based on building type. Always categorize results into these three tiers:
1. **公寓 (Gongyu)**: Walk-up apartments, usually 30-50 years old. Lowest price tier.
2. **電梯大樓/華廈 (Dalu/Huaxia)**: Elevator buildings, 10-30 years old. Middle to high price tier. Often includes "公設" (public facilities).
3. **指標建案/新成屋 (Premium/New)**: New builds or luxury towers. Highest price tier.

### 4. Key Metrics to Capture
- **Price (總價)**: Note if it "含車位" (includes parking).
- **Age (屋齡)**: Critical for determining loan terms and renovation needs.
- **Layout (格局)**: Look for "三房", "兩房", etc. Watch out for "含加蓋" (rooftop additions).
- **Floor (樓層)**: Apartment top floors or ground floors have unique pricing.

## Pitfalls
- **Ref ID Volatility**: Real estate sites update their DOM frequently. Always refresh the snapshot with `browser_snapshot` if a `browser_click` fails with `Unknown ref`.
- **Search Scope**: Sometimes "Nangang Station" search returns results from nearby "Xinyi" or "Songshan" districts. Clarify locations in the summary.
- **Parking Prices**: Parking spaces in Taipei/Nangang can cost 200-400k NTD. If a price is "含車位", the "ping price" (單價) calculation must subtract the parking value.

## Verification
- Cross-reference prices between Sinyi and Yungching to provide a "Market Price Range" (行情) rather than just a single list.
- Check the "关注人数" (number of watchers) on Sinyi to gauge market demand for a specific unit.
