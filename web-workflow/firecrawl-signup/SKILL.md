---
name: firecrawl-signup
description: Create a new Firecrawl account using a temporary email address (mail.tm API) for quick API key access.
tags: [firecrawl, signup, temp-email, registration]
---

# Firecrawl Account Signup via Temp Email

## Prerequisites

- `requests` library available in Python (standard in hermes-agent venv)
- Internet access

## Workflow

### Step 1 — Create a temp email via mail.tm API

```python
import requests
import random
import string

base_url = "https://api.mail.tm"

# Generate random email
username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
domain_resp = requests.get(f"{base_url}/domains", timeout=10)
domain = domain_resp.json()["hydra:member"][0]["domain"]
email = f"{username}@{domain}"
password = "SecurePass123!"

# Create account
resp = requests.post(
    f"{base_url}/accounts",
    json={"address": email, "password": password},
    timeout=10
)
# resp.status_code == 201 means success

print(f"Email: {email}")
print(f"Password: {password}")
```

### Step 2 — Register on Firecrawl

Navigate to `https://www.firecrawl.com/signup` in the browser and fill in:
- Email: the temp email from Step 1
- Password: any password (doesn't matter since we have the temp email)

Click **Create Account** or press Enter.

### Step 3 — Extract verification token from email

```python
import requests
import time
import re

# Get auth token for the temp email
token_resp = requests.post(
    f"{base_url}/token",
    json={"address": email, "password": password},
    timeout=10
)
auth_token = token_resp.json()["token"]
headers = {"Authorization": f"Bearer {auth_token}"}

# Wait for email to arrive
time.sleep(5)

# Check mailbox for Firecrawl email
for attempt in range(10):
    mail_resp = requests.get(f"{base_url}/messages", headers=headers, timeout=10)
    messages = mail_resp.json().get("hydra:member", [])
    
    if messages:
        # Find the Firecrawl verification email
        firecrawl_msg = [m for m in messages if "Firecrawl" in m.get("subject", "")][0]
        msg_id = firecrawl_msg["id"]
        
        # Get full message content
        msg_detail = requests.get(f"{base_url}/messages/{msg_id}", headers=headers, timeout=10)
        msg_data = msg_detail.json()
        body = msg_data.get("text", "")
        
        # Extract the verify token from URL
        verify_url = re.search(r'https://service\.firecrawl\.dev/auth/v1/verify\?token=[^&]+', body)
        if verify_url:
            actual_token = re.search(r'token=([^&]+)', verify_url.group(0)).group(1)
            print(f"*** Verification token: {actual_token} ***")
            break
    
    print(f"Waiting for email... (attempt {attempt+1})")
    time.sleep(3)
```

### Step 4 — Verify email in browser

Navigate to the verification URL:
```
https://service.firecrawl.dev/auth/v1/verify?token=<ACTUAL_TOKEN>&type=signup&redirect_to=https://www.firecrawl.dev/auth/callback
```

This will redirect to `https://www.firecrawl.dev/onboarding` with email verified.

### Step 5 — Skip onboarding to get API key

The onboarding flow has 6 steps. Click **Skip** or **Continue** to bypass the tutorial steps:

1. "Let's get you started" → Click **Continue**
2. "How did you first hear about us?" → Click **Skip**
3. "Terms of Service & Privacy Policy" → Toggle the agreement switch, then click **Continue**
4. "Scrape your first website" (Step 4/6) → **API Key is visible here!**

The API key appears in the cURL code example under the "Code examples" section:
```
Authorization: Bearer fc-xxxxxxxxxxxxxxxxxxxxxxxx
```

Extract it via:
```python
# Get the API key from the code block on the page
api_key = browser_console(expression="document.querySelector('code')?.textContent || ''")
# Parse the Bearer token from the output
```

## Notes

- **mail.tm** is preferred over temp-mail.org because its API is fully accessible (no Cloudflare block) and supports programmatic email reading.
- The temp email expires after a period — if you need to log in again later, save the credentials.
- The Firecrawl free tier includes a limited number of API credits per month.
- After getting the API key, store it in `~/.hermes/.env` as `FIRECRAWL_API_KEY=<key>` for use with the `firecrawl-setup` and `firecrawl-integration` skills.

## Pitfalls

- **temp-mail.org API is blocked by Cloudflare** — do NOT try to use it programmatically. Use mail.tm instead.
- **mail.tm requires account creation first** — you can't just read any mailbox; you must register an account for the domain you want.
- **The verification is a URL token, not a numeric code** — don't look for a 6-digit OTP; look for the `token=` parameter in the verification URL.
- **Onboarding step 3 requires toggling** — the "I agree" toggle is a switch button, not a checkbox. Must be clicked to turn ON before "Continue" works.
- **The API key shown in onboarding is the production key** — it starts with `fc-` and can be used immediately with the SDK or CLI.

## Related Skills

- `firecrawl-setup` — Install SDK and configure API key
- `firecrawl-integration` — Use Firecrawl SDK/CLI for scraping
- `firecrawl` (web-workflow skill) — Search + scrape pipeline
