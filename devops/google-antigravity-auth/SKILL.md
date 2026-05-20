---
name: google-antigravity-auth
description: Setup and authentication for the Google Cloud Code Assist (often referred to as 'Antigravity') inference provider using OAuth 2.0 PKCE.
version: 1.0.0
author: Nous Research
license: MIT
metadata:
  hermes:
    tags: [Google, Gemini, Antigravity, OAuth, PKCE, Inference, Cloud Code]
---

# Google Antigravity (Cloud Code Assist) Auth

This skill covers the **OAuth authentication flow** for using Google Cloud Code Assist as an inference provider in Hermes (OAuth 2.0 PKCE to `cloudcode-pa.googleapis.com`).

⚠️ **Important distinction**: Do NOT confuse this with **Google Antigravity 2.0**, which is a separate, actual desktop application (Electron app + CLI called `agy`). That product lives at `https://www.antigravity.google/` and is downloaded from `storage.googleapis.com/antigravity-public/`. For that product's installation, see `google-antigravity-product` skill.

## Setup Process

### 1. Verification
Check if the user already has credentials stored:
```bash
ls ~/.hermes/auth/google_oauth.json
```

### 2. Authentication Flow
The authentication is handled via `agent/google_oauth.py`. It requires a browser-based approval on the local machine.

- **Port**: Defaults to `8085`. Ensure this port is open.
- **Headless**: If the user is on a headless server (SSH), they must set `HERMES_HEADLESS=true` to trigger the manual code entry flow instead of automatic browser opening.

### 3. Configuration
Add the provider to `~/.hermes/config.yaml`:

```yaml
providers:
  google-cloud-code:
    api_key: 'ollama' # Placeholder, auth handled via oauth.json
    base_url: 'https://cloudcode-pa.googleapis.com/v1internal'
    provider: custom
    models:
      - gemini-3.1-pro
      - gemini-3-flash
```

## Pitfalls & Policy

- **Policy Violation (IMPORTANT)**: Google considers using their official desktop OAuth Client ID (sourced from the `gemini-cli` package) with third-party software like Hermes a violation of their Terms of Service. 
  - **Reason**: Hermes uses the public Client ID and Secret baked into Google's open-source CLI.
  - **Risk**: While widely done in the agent community (e.g., OpenCode), Google may revoke the Client ID or flag accounts for non-official API usage. 
  - **Action**: Always explicitly confirm with the user and suggest **Google AI Studio (API Key)** or **Vertex AI** as the fully compliant alternatives.
- **Browser Redirect**: After approval, the browser will redirect to `http://localhost:8085`. On a remote server, the user may need to copy the full redirect URL and paste it back into the terminal.
- **VPC-SC**: Enterprise accounts under VPC Service Controls may require explicit standard-tier forcing (handled automatically by `agent/google_code_assist.py`).

## Troubleshooting
- **429 (Rate Limit)**: Code Assist has a generous but strict daily quota. Use `/gquota` (if available via plugin) to check remaining buckets.
- **Expired Tokens**: If inference fails with 401, the refresh token rotation may have failed. Delete `~/.hermes/auth/google_oauth.json` and re-authenticate.
