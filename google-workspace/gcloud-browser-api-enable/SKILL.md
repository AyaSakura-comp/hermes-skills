---
name: gcloud-browser-api-enable
description: Browser-driven workflow for enabling Google Workspace APIs in Google Cloud Console. Use when the google-workspace skill requires manual API enablement in the browser (Step 2), or when enabling additional APIs that the setup.py SCOPES list doesn't cover.
version: 1.0.0
author: Nous Research
license: MIT
metadata:
  hermes:
    tags: [Google, Cloud, API, Enable, Browser, OAuth]
    related_skills: [google-workspace]
---

# Google Cloud Browser API Enablement

Use this skill when you need to enable Google Workspace APIs via the Google Cloud Console browser UI. This complements the `google-workspace` skill's Step 2 which says "Enable the required APIs from the API Library" without detailing how.

## Prerequisites

- User must have selected the correct project in Google Cloud Console first.
- Use the `Claw` project (`gen-lang-client-0782792232`) unless told otherwise.

## Browser API Enablement Flow

For **each API** to enable (Gmail, Calendar, Drive, Sheets, Docs, People):

### Step 1: Navigate to API Library and search

```
URL: https://console.cloud.google.com/apis/library
```

1. Click the search box in the center of the page (placeholder: "Search for APIs & Services")
2. Type the API name (e.g., "Gmail API", "Calendar API", "People API")
3. Press Enter

### Step 2: Select the correct API from results

Results typically show:
- **[Product Name] API** — the main one you want (e.g., "Google Calendar API")
- Related APIs from other providers (ignore these)

**Click the main result** — it's almost always the first one.

### Step 3: Click Enable

On the API details page:
- A blue **"Enable" button** is to the left of "Try this API" link
- If already enabled, the button says **"Disable API"** (stop here for this API)

### Step 4: Verify

After clicking Enable:
- The button changes to **"Disable API"**
- A notification count may appear in the top-right (bell icon showing "1" or more)
- This means the API is now active ✅

## APIs to Enable for Google Workspace

| API Name to Search | Purpose |
|---|---|
| Gmail API | Read/send emails |
| Google Calendar API | Calendar read/write |
| Google Drive API | File read/write |
| Google Sheets API | Spreadsheet read/write |
| Google Docs API | Document read/write |
| Google People API | Contacts (OPTIONAL — ask user first) |
| Google Tasks API | Tasks (OPTIONAL) |

⚠ **People API / Tasks API** — These are optional. Only enable if the user explicitly wants Contacts or Tasks functionality.

## Common Pitfalls

1. **Wrong project active**: Always confirm the correct project is selected (top-left project picker). The URL should end with `?project=<project-id>`.
2. **"Search for APIs" not clicking**: The search box is a `combobox` element. Click it, then type, then press Enter. It may not show results immediately — wait a moment or press Enter if needed.
3. **API already enabled**: If the details page shows "Disable API" instead of "Enable", the API is already active. Move to the next one.
4. **Notifications count**: After enabling each API, the bell icon shows a count. Clicking it shows what was just enabled. Useful for verification.
5. **Google account redirect**: If you get redirected to a Google account login instead of the API page, this is expected. Sign in and the API library will load.
6. **OAuth consent after enabling**: Enabling APIs does NOT trigger OAuth consent. The consent screen is configured separately under "APIs & Services → OAuth consent screen".

## After Enabling All APIs

Proceed to the google-workspace skill's Step 2 continuation:
1. Create OAuth 2.0 Client ID credentials
2. Run `setup.py --client-secret`
3. Continue with Steps 3-5 (auth URL, code exchange, verify)

## Element Locator Tips

When using browser tools:
- Search box is typically a `combobox` with role related to search
- The "Enable" button appears on the API details page (not the search results)
- Use `browser_snapshot` to find the exact ref if the first guess is wrong
- The snapshot of the API details page will show the "Enable" or "Disable API" button directly
