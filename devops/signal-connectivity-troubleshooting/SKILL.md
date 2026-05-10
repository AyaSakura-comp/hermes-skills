---
name: signal-connectivity-troubleshooting
description: Diagnose and resolve issues where Hermes Agent is not responding to Signal messages, specifically involving signal-cli-rest-api.
category: devops
---

# Signal Connectivity Troubleshooting for Hermes Agent

This skill provides a systematic approach to diagnose and resolve issues where Hermes Agent is not responding to messages from Signal, specifically focusing on the `signal-cli-rest-api` backend.

## Trigger Conditions
- User reports that Signal is not responding despite the gateway showing "Connected".
- Log messages showing `cannot reach signal-cli at http://127.0.0.1:8085`.

## Diagnostic Steps

1. **Check Agent Logs**
   Search for Signal-specific errors in the agent log to confirm if the failure is at the adapter level.
   ```bash
   grep -i "signal" ~/.hermes/logs/agent.log | tail -n 50
   ```
   - If you see `All connection attempts failed`, the problem is the connection to the REST API.
   - If you see `Giving up reconnecting signal after 20 attempts`, the agent has stopped trying to connect.

2. **Verify Backend Status**
   Check if the `signal-cli-rest-api` is actually listening on the expected port (default 8085).
   ```bash
   ss -tulpn | grep :8085
   ```

3. **Check Container/Service Health**
   If using Docker, verify the container status:
   ```bash
   docker ps | grep signal
   ```
   Ensure the status is `Up` and `healthy`.

## Resolution Workflow

### Case 1: Backend is DOWN
If the service is not running:
- **Docker**: `docker start signal-cli-rest-api` (or use the specific container name).
- **Systemd**: `sudo systemctl start signal-cli-rest-api`.

### Case 2: Backend is UP but Agent is "Giving up"
If the backend is healthy but the logs show the agent has stopped reconnecting:
- **Action**: Restart the Hermes Gateway to force a fresh connection attempt.
- **Command**:
  ```bash
  kill -TERM $(jq -r .pid ~/.hermes/gateway_state.json)
  hermes gateway &
  ```

## Pitfalls
- **False Positive "Connected"**: The gateway may report the Signal platform as "Connected" if the module is loaded, even if the underlying REST API connection is severed. Always check the logs for `inbound message: platform=signal` to confirm actual connectivity.
- **Retry Limit**: Hermes has a hard limit on reconnection attempts (e.g., 20). Once reached, it will not try again until the gateway is restarted.
