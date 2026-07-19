---
name: llama-mtp-service-switcher
description: Start, stop, restart, or inspect the mutually exclusive Qwen MTP and Gemma MTP llama.cpp services on port 8001. Use when asked to switch local inference between Qwen and Gemma, restart either MTP service, or check which MTP model is serving.
metadata:
  hermes:
    tags: [llama-cpp, systemd, mtp, qwen, gemma, turboquant]
---

# llama.cpp MTP Service Switcher

Both services bind port `8001` and are mutually exclusive through systemd `Conflicts=`:

| Model | systemd service | Alias | Context | Runtime |
|---|---|---|---:|---|
| Qwen 3.6 35B-A3B UD Q4 | `qwen-mtp.service` | `qwen3.6-35b-q4` | 260,000 | `/home/chihmin/llama-mtp` |
| Gemma 4 26B-A4B QAT Q4 | `gemma-mtp.service` | `gemma-4-26b-a4b-qat-q4` | 262,144 | TurboQuant + MTP |

## Switch or manage a model

Run the helper; it uses `sudo systemctl`, switches safely, waits for the OpenAI-compatible API, and prints the loaded model:

```bash
/home/chihmin/.pi/agent/skills/llama-mtp-service-switcher/scripts/mtp-service.sh start gemma
/home/chihmin/.pi/agent/skills/llama-mtp-service-switcher/scripts/mtp-service.sh start qwen
/home/chihmin/.pi/agent/skills/llama-mtp-service-switcher/scripts/mtp-service.sh restart gemma
/home/chihmin/.pi/agent/skills/llama-mtp-service-switcher/scripts/mtp-service.sh stop qwen
/home/chihmin/.pi/agent/skills/llama-mtp-service-switcher/scripts/mtp-service.sh status
```

`start` or `restart` of either model stops the other automatically. Do not launch a standalone `llama-server` on `8001` while either service is active.

## Verify

```bash
curl -fsS http://127.0.0.1:8001/v1/models | jq '.data[0] | {id, context: .meta.n_ctx}'
sudo systemctl status gemma-mtp.service --no-pager
```

## Logs

```bash
sudo journalctl -u gemma-mtp.service -f
sudo journalctl -u qwen-mtp.service -f
```
