---
name: firecrawl-temp-email-signup
description: Register a Firecrawl account using a temporary email (mail.tm API), verify it via the confirmation link, and complete onboarding to obtain an API key.
---

# Firecrawl Signup with Temporary Email

Automated registration for Firecrawl using a disposable email service, email verification, and onboarding completion.

## When to Use

- User needs a Firecrawl account for quick testing
- No existing credentials available
- Need to bypass manual signup flow

## Step 1: Find a Disposable Email

Try these sources (in order):
1. **temp-mail.org** — but it's Cloudflare-protected; browser DOM clicks are INEFFECTIVE. Skip automation on this site.
2. **mail.tm API** — the reliable fallback. Use REST API for full automation.

## Step 2: Create Mail.tm Account via API

```python
import requests

# Get available domains first
domains = requests.get("https://api.mail.tm/domains").json()["hydra:member"]
domain = domains[0]["domain"]

# Generate random email and password
username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
email = f"{username}@{domain}"
password = "TempPass" + ''.join(random.choices(string.digits, k=6))

# Create account
resp = requests.post("https://api.mail.tm/accounts", json={
    "address": email,
    "password": password
})

# Authenticate (get JWT token)
jwt_token = requests.post("https://api.mail.tm/token", json={
    "address": email,
    "password": password
}).json()["token"]
```

Headers for all subsequent API calls:
```
Authorization: Bearer <jwt_token>
Content-Type: application/json
```

## Step 3: Firecrawl Signup

1. Navigate to `https://firecrawl.com/signup`
2. Enter the temp email and password
3. Click Sign Up → redirects to `/confirm-email`

## Step 4: Extract Verification Email

```python
import time

# Wait a few seconds, then fetch messages
headers = {"Authorization": f"Bearer {jwt_token}"}
msgs = requests.get("https://api.mail.tm/messages", headers=headers).json()["hydra:member"]

for msg in msgs:
    msg_detail = requests.get(f"https://api.mail.tm/messages/{msg['id']}", headers=headers).json()
    body = msg_detail["text"]  # or "html"
    # Extract verification URL from body
    import re
    url_match = re.search(r'https://api\.firecrawl\.dev/verify\?.*?token=[a-zA-Z0-9_-]+', body)
    if url_match:
        verify_url = url_match.group(0)
        break
```

## Step 5: Verify Email

Navigate directly to the verification URL extracted from the email body. This completes email verification.

## Step 6: Complete Onboarding

After verification, you're redirected to the onboarding flow (6 steps):

1. **Step 1** — Welcome/setup (skip optional fields)
2. **Step 2** — Team info (skip)
3. **Step 3** — Usage info (skip)
4. **Step 4** — Scrape your first website (API Key shown here in cURL example)
5. **Step 5** — More examples
6. **Step 6** — Next steps

**Strategy:** Click "Skip" on optional steps, accept Terms of Service when prompted, then "Continue" to reach the dashboard.

## Step 7: Extract API Key

The API Key is displayed in the Step 4 code example:
```bash
curl -X POST 'https://api.firecrawl.dev/v2/scrape' \
-H 'Authorization: Bearer <YOUR_API_KEY>' \
-H 'Content-Type: application/json' \
-d '{"url": "firecrawl.dev"}'
```

Use browser console to extract:
```javascript
document.querySelector('code').textContent
```

Or read it from the page directly via vision/snapshot.

## Key Endpoints

| Purpose | URL |
|---------|-----|
| Signup | `https://firecrawl.com/signup` |
| Verify email | `https://api.firecrawl.dev/verify?token=xxx` |
| Scrape API | `https://api.firecrawl.dev/v2/scrape` |
| Mail.tm accounts | `https://api.mail.tm/accounts` |
| Mail.tm auth | `https://api.mail.tm/token` |
| Mail.tm messages | `https://api.mail.tm/messages` |
| Mail.tm domains | `https://api.mail.tm/domains` |

## Pitfalls

- **temp-mail.org is Cloudflare-blocked** — do NOT attempt browser automation on it; DOM clicks won't work
- **Firecrawl email verification uses a token link**, not an OTP code — extract the full URL from the email body
- **Onboarding has 6 steps** — most are optional; use "Skip" buttons to speed through
- **mail.tm domains change** — always fetch available domains from the API rather than hardcoding `wshu.net`
- **Email delay** — allow 3-5 seconds between signup and checking for messages
- **API Key format** — starts with `fc-` followed by a hex-like string

## Quick Reference: Full Automation Script

```python
import requests
import re
import random
import string
import time

def create_mail_tm_account():
    """Create a disposable mail.tm account and return credentials."""
    # Get available domain
    domains = requests.get("https://api.mail.tm/domains").json()["hydra:member"]
    domain = domains[0]["domain"]
    
    # Generate random email
    username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
    email = f"{username}@{domain}"
    password = "TempPass" + ''.join(random.choices(string.digits, k=6))
    
    # Register
    requests.post("https://api.mail.tm/accounts", json={"address": email, "password": password})
    
    # Get JWT token
    jwt = requests.post("https://api.mail.tm/token", json={"address": email, "password": password}).json()["token"]
    return email, password, jwt

def get_verification_email(jwt, timeout=30):
    """Wait for and extract Firecrawl verification URL."""
    headers = {"Authorization": f"Bearer {jwt}"}
    start = time.time()
    while time.time() - start < timeout:
        msgs = requests.get("https://api.mail.tm/messages", headers=headers).json()["hydra:member"]
        for msg in msgs:
            detail = requests.get(f"https://api.mail.tm/messages/{msg['id']}", headers=headers).json()
            body = detail.get("text", "") + detail.get("html", "")
            url_match = re.search(r'https://api\.firecrawl\.dev/verify\?.*?token=[a-zA-Z0-9_-]+', body)
            if url_match:
                return url_match.group(0)
        time.sleep(3)
    return None
```