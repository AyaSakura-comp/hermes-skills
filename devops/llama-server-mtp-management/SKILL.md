---
name: llama-server-mtp-management
description: Manage the systemd-hosted Qwen llama.cpp MTP server on port 8001; defer FlashHead deployment and verification to restart-qwen-mtp.
version: 2.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [llama-server, systemd, mtp, qwen, flashhead, local-llm]
---

# Qwen llama-server MTP management

Qwen MTP now runs under **systemd**. Historical instructions that started `/home/chihmin/llama-mtp/build/bin/llama-server` as a user background process are obsolete and must not be used.

## Current service

| Item | Value |
|---|---|
| Service | `qwen-mtp.service` |
| API | `http://127.0.0.1:8001` |
| Alias | `qwen3.6-35b-q4` |
| Context | 260,000 |
| Unit | `/etc/systemd/system/qwen-mtp.service` |
| Drop-ins | `/etc/systemd/system/qwen-mtp.service.d/*.conf` |
| Log | `/tmp/qwen35-server.log` and systemd journal |

The effective model and binary are selected by lexically ordered systemd drop-ins. Never assume the base unit's `ExecStart` is live; inspect `systemctl show` and `/proc/<pid>`.

## Canonical workflow

For any Qwen start, restart, health problem, or FlashHead request, load and follow:

```text
/home/chihmin/.pi/agent/skills/restart-qwen-mtp/SKILL.md
```

Verified variant selection and restart:

```bash
HELPER=/home/chihmin/.pi/agent/skills/restart-qwen-mtp/scripts/restart-qwen-mtp.sh
$HELPER                  # default: draft + target all-FlashHead
$HELPER flashhead        # explicit all-FlashHead (approximate target)
$HELPER draft-flashhead  # FlashHead draft with dense target verifier
$HELPER f16-baseline     # dense draft and target heads with F16 KV
```

The helper manages the final systemd drop-in and verifies that the live executable, GGUF, HIP library, FlashHead state, and F16 KV match the requested variant.

Basic operations:

```bash
sudo systemctl start qwen-mtp.service
sudo systemctl stop qwen-mtp.service
sudo systemctl restart qwen-mtp.service
systemctl status qwen-mtp.service --no-pager -l
journalctl -u qwen-mtp.service -n 120 --no-pager
```

## Inspect the live server

```bash
systemctl show qwen-mtp.service -p MainPID -p ExecStart -p Environment -p DropInPaths
pid=$(systemctl show -p MainPID --value qwen-mtp.service)
readlink -f /proc/$pid/exe
grep -m1 'libggml-hip' /proc/$pid/maps
curl -fsS http://127.0.0.1:8001/health
curl -fsS http://127.0.0.1:8001/v1/models | jq '.data[0] | {id, context: .meta.n_ctx}'
```

If FlashHead is selected, additionally require:

```bash
grep 'FlashHead tables found' /tmp/qwen35-server.log | tail -1
```

The current verified draft + target FlashHead deployment is:

```text
/home/chihmin/llama-mtp-deploy/gfx1151-all-flashhead-15bd9b0028
```

All-FlashHead requires both `LLAMA_FLASHHEAD_PROBES=256` and `LLAMA_FLASHHEAD_TARGET=1`; the target path is approximate. The selector validates the startup warning and can restore exact dense target verification with `draft-flashhead`.

See `restart-qwen-mtp/SKILL.md` for variant commands, exact drop-ins, immutable-deployment procedure, verification, guardrails, and switching back to the dense F16-KV baseline.

## Guardrails

- Do not use `nohup`, `&`, tmux, or direct `llama-server` launch for production Qwen.
- Do not kill arbitrary `llama-server` PIDs; manage `qwen-mtp.service` explicitly.
- Do not start a standalone server on port 8001.
- Do not infer the running variant from a process name or model alias; verify effective `ExecStart`, mapped HIP library, and FlashHead load line.
- Keep the performance power profile for production Qwen.
