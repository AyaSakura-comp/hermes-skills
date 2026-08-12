---
name: firecrawl-temp-email-signup
description: Register a Firecrawl account using a temporary email (Tempail), verify it via the confirmation link, and complete onboarding to obtain an API key.
---

# Firecrawl Signup with Temporary Email

Automated registration for Firecrawl using a disposable email service, email verification, and onboarding completion.

## When to Use

- User needs a Firecrawl account for quick testing
- No existing credentials available
- Need to bypass manual signup flow

## Current Credentials

A working Firecrawl account is already registered. Credentials are stored securely in `~/.pi/agent/auth.json` under the `firecrawl` key. Pi agent reads them automatically — **never expose the API key in shared files or commit them to version control**.

## Step 1: Get a Temporary Email from Tempail

Navigate to `https://tempail.com/en/` — it **no longer requires reCAPTCHA**. The page immediately generates a temporary email address (e.g. `caspecakke@necub.com`) in the `textbox` element. No API calls needed.

> **Note:** Tempail emails expire after 1 hour. The domain is `necub.com`.

### Browser Flow

```bash
browser open https://tempail.com/en/
browser snapshot -i  # find the textbox element (ref like @e31)
browser get text @e31  # read the generated email
```

The email is auto-generated. Copy it for the next step.

### Password

Generate a random password with at least one special character:
```python
import random, string
password = "TempPass" + ''.join(random.choices(string.digits, k=6)) + "!"
# e.g. "TempPass748126!"
```

## Step 2: Firecrawl Signup

1. Navigate to `https://www.firecrawl.dev/signin`
2. Click "Sign Up" tab
3. Enter the temp email and password (must contain a special character)
4. Click "Create Account" → redirects to `/confirm-email?email=...`

```bash
browser open https://www.firecrawl.dev/signin
browser snapshot -i
browser fill @e10 <temp_email>
browser fill @e11 <password_with_special_char>
browser click @e2  # Create Account
```

## Step 3: Verify Email via Tempail

The verification email arrives in the Tempail inbox. Tempail no longer has reCAPTCHA, so we can automate inbox checks.

### Check Tempail Inbox

```bash
browser open https://tempail.com/en/
browser snapshot -i
```

If no inbox items are visible, click "Refresh" (`@e13` or similar) and wait a few seconds. Firecrawl emails typically arrive within 5–10 seconds.

### Open the Verification Email

When the email appears in the inbox, click on it to open and read the verification link. The link looks like:
```
https://www.firecrawl.dev/signin/verify-email?token=...
```

Navigate directly to that URL to complete email verification.

```bash
browser snapshot -i  # find the email item
browser click <email_ref>  # open the email
# read the verification link from the email body
browser open <verification_url>
```

## Step 4: Login to Firecrawl

After email verification, log in:

1. Go to `https://www.firecrawl.dev/signin`
2. Click "Log In" tab
3. Enter email and password
4. Click "Sign in"

```bash
browser open https://www.firecrawl.dev/signin
browser snapshot -i
browser fill @e12 <email>
browser fill @e13 <password>
browser click @e4  # Sign in
```

## Step 5: Complete Onboarding

After login, you'll enter the onboarding flow (up to 5 steps):

| Step | Content | Strategy |
|------|---------|----------|
| 1 | "Let's get you started" (bonus credits tasks) | Skip — all optional |
| 2 | "How did you first hear about us?" | Skip |
| 3 | "Terms of Service & Privacy Policy" | Toggle "I agree" → Continue |
| 4 | "Scrape your first website" (API Key shown) | **← API Key is here** |
| 5 | More examples | Skip |

**Strategy:** Click "Skip" on steps 1–2, toggle agreement on step 3, then **extract the API Key from step 4**.

### Step 3 — Accept Terms

```bash
browser click @e6  # I agree toggle
browser click @e3  # Continue
```

### Step 4 — Extract API Key

The API Key is displayed in the "Connect via CLI" section as part of a `npx` command:

```
npx -v firecrawl-cli@latest init --all -k fc-xxxxxxxxxxxxxxxxxxxxxxxx
```

Read the API Key (starts with `fc-`) from the page:

```bash
browser snapshot -i
# Look for the code block with the npx command containing the API key
# Or use screenshot + vision to extract it
```

## Step 6: Save the API Key

Store the API Key in `~/.pi/agent/auth.json`:

```json
"firecrawl": {
    "type": "api_key",
    "key": "fc-xxxxxxxxxxxxxxxxxxxxxxxx"
}
```

### Update auth.json

```bash
# Read current auth.json
cat ~/.pi/agent/auth.json | python3 -c "import sys, json; d=json.load(sys.stdin); ..."
```

Or use `edit` tool to add the entry to the existing JSON.

> **NOTE:** A working API key is already registered. If you need a new account, follow the full flow above to get a fresh key.

## Step 7: Verify the API Key

Test the key with a quick scrape:

```bash
curl -s -X POST "https://api.firecrawl.dev/v1/scrape" \
  -H "Authorization: Bearer <API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://firecrawl.dev"}'
```

Should return `{"success":true,...}`.

Expected output:
```json
{
  "success": true,
  "data": {
    "markdown": "...",
    "metadata": {
      "creditsUsed": 1
    }
  }
}
```

## Key Endpoints

| Purpose | URL |
|---------|-----|
| Tempail (temp email) | `https://tempail.com/en/` |
| Firecrawl Signup | `https://www.firecrawl.dev/signin` (Sign Up tab) |
| Firecrawl Login | `https://www.firecrawl.dev/signin` (Log In tab) |
| Verify email | `https://www.firecrawl.dev/signin/verify-email?token=...` |
| Onboarding | `https://www.firecrawl.dev/onboarding` |
| Scrape API | `https://api.firecrawl.dev/v1/scrape` |

## Pitfalls

- **Password must contain a special character** — Firecrawl rejects passwords like `TempPass123456`; use `TempPass123456!` or similar
- **Firecrawl email verification uses a token link** — extract the full verification URL from the Tempail inbox
- **Onboarding has up to 5 steps** — most are optional; use "Skip" buttons to speed through
- **Terms of Service must be accepted** — toggle the "I agree" checkbox before continuing
- **API Key is on onboarding step 4** — you need to get through steps 1–3 first
- **API Key format** — starts with `fc-` followed by a hex-like string
- **Tempail email expires after 1 hour** — if you need a longer-lived address, use a different service or a real email
- **Tempail is reCAPTCHA-free** — you can automate inbox checks via browser

## Quick Reference: Full Automation Flow

```bash
# 1. Get temp email
browser open https://tempail.com/en/
browser snapshot -i
EMAIL=$(browser get text @e31)
PASSWORD="TempPass$(python3 -c 'import random; print(random.randint(100000,999999))')!"

# 2. Sign up on Firecrawl
browser open https://www.firecrawl.dev/signin
browser snapshot -i
browser fill @e10 $EMAIL
browser fill @e11 $PASSWORD
browser click @e2  # Create Account

# 3. Wait for verification email, then open Tempail
browser open https://tempail.com/en/
browser snapshot -i
# Click the verification email, get the URL, navigate to it

# 4. Login
browser open https://www.firecrawl.dev/signin
browser snapshot -i
browser fill @e12 $EMAIL
browser fill @e13 $PASSWORD
browser click @e4  # Sign in

# 5. Skip onboarding steps, accept terms, get API key
browser click @e6  # I agree
browser click @e3  # Continue
# Read API key from step 4 page
```
