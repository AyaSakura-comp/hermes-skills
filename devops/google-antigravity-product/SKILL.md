---
name: google-antigravity-product
description: Download and install Google Antigravity 2.0 desktop app and CLI (agy) — separate from the Cloud Code Assist OAuth adapter.
version: 1.1.0
author: Nous Research
license: MIT
metadata:
  hermes:
    tags: [Google, Antigravity, Product, Desktop, CLI, Install]
---

# Google Antigravity 2.0 — Install + Pass-Through Usage

**Google Antigravity 2.0** is an actual desktop application + CLI tool at `https://www.antigravity.google/`. It has nothing to do with Google Cloud Code Assist / Gemini OAuth adapter (that's a separate Hermes provider configured via OAuth PKCE).

## Download URLs (Antigravity 2.0)

| Platform | Architecture | URL |
|----------|-------------|-----|
| macOS | Apple Silicon | `https://storage.googleapis.com/antigravity-public/antigravity-hub/2.0.1-6566078776737792/darwin-arm/Antigravity.dmg` |
| macOS | Intel | `https://storage.googleapis.com/antigravity-public/antigravity-hub/2.0.1-6566078776737792/darwin-x64/Antigravity.dmg` |
| Windows | x64 | `https://storage.googleapis.com/antigravity-public/antigravity-hub/2.0.1-6566078776737792/windows-x64/Antigravity-x64.exe` |
| Windows | ARM64 | `https://storage.googleapis.com/antigravity-public/antigravity-hub/2.0.1-6566078776737792/windows-arm/Antigravity-arm64.exe` |
| Linux | x64 | `https://storage.googleapis.com/antigravity-public/antigravity-hub/2.0.1-6566078776737792/linux-x64/Antigravity.tar.gz` |
| Linux | ARM64 | `https://storage.googleapis.com/antigravity-public/antigravity-hub/2.0.1-6566078776737792/linux-arm/Antigravity.tar.gz` |

## Step 1 — Desktop App (Electron)

```bash
# Download
curl -fsSL -o ~/Downloads/Antigravity.tar.gz "https://storage.googleapis.com/antigravity-public/antigravity-hub/2.0.1-6566078776737792/linux-x64/Antigravity.tar.gz"

# Extract to /opt/
sudo tar -xzf ~/Downloads/Antigravity.tar.gz -C /opt/

# Launch (Linux, sandbox may be needed):
/opt/Antigravity-x64/antigravity --no-sandbox &
```

The binary is already executable in the archive (`rwxr-xr-x`, owned by root).

## Step 2 — CLI (called `agy`)

The CLI is version 1.0.0 (separate versioning from desktop app).

**⚠️ Gotcha**: Piping the install script to `bash` directly can time out. Download first, then run.

```bash
# Step A: Download the installer script
curl -fsSL https://antigravity.google/cli/install.sh -o /tmp/antigravity-install.sh

# Step B: Run it directly
bash /tmp/antigravity-install.sh
```

This installs the binary to `~/.local/bin/agy` and updates `.bashrc`, `.bash_profile`, `.profile`, and `.config/fish/config.fish` with the PATH entry.

**Verify**:
```bash
agy --version   # Should return 1.0.0
```

## Step 3 — IDE (optional)

Antigravity IDE downloads from a different CDN:
```
https://edgedl.me.gvt1.com/edgedl/release2/j0qc3/antigravity/stable/<build-id>/
```

## Authentication

Both the CLI (`agy`) and IDE require authentication before use. Run `agy` — it will prompt for login (likely Google OAuth). The CLI notes on the product page: "Authenticate with Antigravity or Antigravity IDE before using the CLI."

## Pass-Through Usage (Hermes Agent)

**The agent's job is simple: take the user's prompt verbatim and pass it to `agy --prompt`.**

The Hermes agent terminal does NOT provide a controlling TTY, so the interactive TUI mode fails:

```bash
# ❌ FAILS — bubbletea TUI requires a controlling TTY
agy --prompt-interactive "hello"

# ❌ FAILS — tmux new-session also fails in agent environment
```

**Correct usage — pass through the user's exact prompt:**

```bash
agy --prompt "用户原来的提示词"
# Returns the response directly as stdout
```

### Rules for pass-through:

1. **Do NOT modify the prompt** — pass it exactly as the user wrote it.
2. **Do NOT add context, instructions, or system messages** — just `agy --prompt "<original prompt>"`.
3. **Do NOT summarize, rephrase, or translate** — verbatim only.
4. **No persistent conversation state** — each call is single-shot. If the user wants follow-ups, they issue separate prompts.
5. **Return the raw stdout** from `agy` as the response.

### Examples:

```bash
# User says: "What is the capital of France?"
# Agent runs: agy --prompt "What is the capital of France?"
# Agent returns: stdout from agy

# User says: "寫一個 Python 函式來計算費氏數列"
# Agent runs: agy --prompt "寫一個 Python 函式來計算費氏數列"
# Agent returns: stdout from agy
```

## Pitfalls

- **Not the same as Cloud Code Assist**: The "Google Antigravity" OAuth adapter skill (`google-antigravity-auth`) is for `cloudcode-pa.googleapis.com` (Gemini inference). The product at `antigravity.google` is a separate desktop app + CLI. Don't confuse the two.
- **CLI install pipe timeout**: `curl ... | bash` times out on the install script. Download first, then `bash` it.
- **Linux sandbox**: Electron apps may need `--no-sandbox` flag when running as root or in containers.
- **SDK**: Separate GitHub repo at `https://github.com/google-antigravity/antigravity-sdk-python` (not bundled with desktop app or CLI).

## Version Notes

- Desktop app build: `2.0.1-6566078776737792`
- CLI version: `1.0.0`
- Both are under the "Antigravity 2.0" product umbrella
- Build IDs change between releases — check the product page for the latest
