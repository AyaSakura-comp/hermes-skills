---
name: llama-server-mtp-management
description: Manage the custom llama-server with MTP (Multi-Token Prediction) running on port 8001.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [llama-server, mtp, qwen, local-llm, process-management]
---

# llama-server MTP Management

This skill provides the procedure for managing the custom `llama-server` instance that uses Multi-Token Prediction (MTP). This instance is run as a standalone process under the user account, NOT as a systemd service.

## Dual Inference Server Architecture

The user runs **two** inference servers simultaneously. This is a common source of confusion:

| Server | Port | What it serves | How to verify |
|---|---|---|---|
| **llama.cpp MTP** (PRIMARY) | `8001` | Qwen3.6-35B-A3B-UD-Q4_K_M.gguf (22 GB) — this is the model actually used by the agent | `curl -s http://127.0.0.1:8001/v1/models` |
| **Ollama** (secondary) | `11434` | Gemma 4 variants (e2b, e4b, 26b, 31b) + Qwen3.6-35B-A3B-Q8_0 | `curl -s http://localhost:11434/api/tags` |

**Pitfall:** Always verify which server is actually serving the model in use. Do NOT assume Ollama is the primary inference engine — llama.cpp MTP on port 8001 is the default for this session.

## Server Specifications
- **Binary Path:** `/home/chihmin/llama-mtp/build/bin/llama-server`
- **Default Port:** `8001`
- **Model Path:** `/home/chihmin/models/Qwen3.6-35B-A3B-UD-Q4_K_M.gguf` (22 GB)
- **MMProj Path:** `/home/chihmin/models/mmproj.gguf` (861 MB, multimodal projector)
- **Log File:** `/tmp/qwen35-server.log`

## Management Workflows

### 1. Check if Server is Running
Since it is not a systemd service, use `ps` to find the process:
```bash
ps aux | grep "[l]lama-server"
```

### 2. Stopping the Server
Identify the PID from the check above and kill it:
```bash
kill <PID>
```

### 3. Starting the Server
Use the following command to start the server with the established MTP and hardware acceleration parameters:
```bash
/home/chihmin/llama-mtp/build/bin/llama-server \
  -m /home/chihmin/models/Qwen3.6-35B-A3B-UD-Q4_K_M.gguf \
  --port 8001 \
  --host 0.0.0.0 \
  -ngl 99 \
  -fit off \
  -fa 1 \
  -c 1048576 \
  -np 4 \
  --mmproj /home/chihmin/models/mmproj.gguf \
  --alias qwen3.6-35b-q4 \
  --spec-type mtp \
  --spec-draft-n-max 3 \
  --log-file /tmp/qwen35-server.log &
```

### 4. Restarting the Server
To restart, combine stop and start:
1. `PID=$(pgrep -f "llama-server")`
2. `kill $PID`
3. Execute the start command above.

## Pitfalls & Notes
- **Systemd Confusion:** The user may attempt `systemctl restart llama-server`, which will fail because the server is a user-level background process, not a systemd unit.
- **Log Inspection:** If the server fails to start or behaves unexpectedly, check the log at `/tmp/qwen35-server.log`.
- **Resource Usage:** This server uses significant VRAM (`-ngl 99`) and a very large context window (`-c 1048576`). Ensure system resources are available before starting.
