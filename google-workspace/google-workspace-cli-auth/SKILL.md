---
name: google-workspace-cli-auth
description: Use `gws` CLI for Google Workspace authentication when browser-based API enablement is unreliable. Handles OAuth 2.0 setup, credential management, and verifying API enablement via gws test calls.
version: 1.0.0
author: Nous Research
tags: [Google, Workspace, CLI, OAuth, gws]
related_skills: [google-workspace, gcloud-browser-api-enable]
---

# Google Workspace CLI Authentication (gws)

Use the `gws` CLI (Google Workspace CLI, v0.22.5) for Google Workspace authentication — **prefer this over browser-based API enablement** when the user already has project access or when the Google Cloud Console UI is unreliable.

## When to Prefer `gws` CLI Over Browser

- The Google Cloud Console browser UI shows inconsistent states
- Clicks on "Enable" buttons don't persist state
- User has a known project ID and just needs credentials
- You need to quickly verify which APIs are actually accessible (run `gws <service> ...` calls instead of checking status pages)

## Prerequisites

- `gws` must be installed: `gws --help` (typically at `~/.local/bin/gws`)
- User has a Google Cloud project ID

## Auth Flow

### 1. Check Existing State

```bash
gws --help 2>&1 | head -5
test -f ~/.hermes/google_token.json && echo "Token exists" || echo "No token"
gws drive about get --format json 2>&1 | head -20
```

### 2. Initial OAuth Login

```bash
gws auth login
```

This opens the browser for Google OAuth 2.0 consent. User must:
- Sign in with their Google account
- Grant the requested scopes
- Copy the authorization code back and paste it into the CLI

### 3. If `gws auth login` Hangs

Set credentials explicitly:

```bash
export GOOGLE_WORKSPACE_CLI_CLIENT_ID="<client-id>"
export GOOGLE_WORKSPACE_CLI_CLIENT_SECRET="<client-secret>"
gws auth login
```

Or point to a downloaded credentials JSON:

```bash
export GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE=/path/to/credentials.json
gws auth login
```

### 4. Verify API Access

Test each API with a simple read call:

```bash
gws drive about get --format json
gws calendar calendarList get --format json
gws gmail users profile --format json
```

Exit code 2 = auth error, exit code 4 = API likely not enabled.

### 5. Token Management

```bash
# Force refresh
rm -f ~/.hermes/google_token.json
gws auth login

# Set token directly (advanced)
export GOOGLE_WORKSPACE_CLI_TOKEN="ya29.<access-token>"
```

## Service Reference

| Service | Example Command |
|---------|---------|
| drive | `gws drive files list --params '{"pageSize": 10}'` |
| sheets | `gws sheets spreadsheets get --params '{"spreadsheetId": "..."}'` |
| gmail | `gws gmail users profile` |
| calendar | `gws calendar events list` |
| docs | `gws docs documents get --params '{"documentId": "..."}'` |
| slides | `gws slides presentations get` |
| people | `gws people people.get --params '{"resourceName": "people/me"}'` |
| tasks | `gws tasks tasklists list` |

## Exit Codes

| Code | Meaning | Fix |
|------|---------|---|
| 0 | Success | — |
| 1 | Google API error | Check API enabled, correct scope |
| 2 | Auth error | Run `gws auth login` |
| 3 | Bad arguments | Check --params JSON syntax |
| 4 | Discovery error | API not enabled for this project |
| 5 | Internal error | Try `gws auth login` |

## Known Issues (from experience)

- **Browser API enablement is unreliable**: Clicking "Enable" often doesn't persist. Dashboard may show "1 of 5" enabled while individual API pages show "Enable" button. Always verify with `gws` test calls.
- **Dark mode tables unreadable**: "Enabled APIs & services" list is black/unreadable in dark mode. Use individual API URL checks: `https://console.cloud.google.com/apis/api/<api>.googleapis.com`.
- **Only 1 of 3+ Enable clicks persists**: Re-enable all required APIs.