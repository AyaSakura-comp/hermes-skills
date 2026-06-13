---
name: add-discord-user
description: Add a Discord user to the gateway allow list and restart the gateway.
---

# Add Discord User to Allow List

Add a Discord user ID to `DISCORD_ALLOWED_USERS` in `~/.hermes/.env` and restart the gateway.

## Steps

1. **Parse the Discord user ID.**
   - Accept a Discord user ID (numeric string, e.g. `123456789012345678`)
   - If the user provides a Discord username/tag (e.g. `user#1234`), note that Discord user IDs must be numeric — ask for clarification if needed.

2. **Read the current allow list.**
   ```bash
   grep '^DISCORD_ALLOWED_USERS=' ~/.hermes/.env
   ```

3. **Update the allow list.**
   - If `DISCORD_ALLOWED_USERS` already has values, append a comma and the new ID:
     ```bash
     sed -i 's/^DISCORD_ALLOWED_USERS=.*/DISCORD_ALLOWED_USERS='"$OLD"',$NEW_ID/' ~/.hermes/.env
     ```
   - If the field is empty or missing, set it directly:
     ```bash
     sed -i 's/^DISCORD_ALLOWED_USERS=.*/DISCORD_ALLOWED_USERS=NEW_ID/' ~/.hermes/.env
     ```

4. **Restart the gateway.**
   ```bash
   kill -TERM $(jq -r .pid ~/.hermes/gateway_state.json)
   hermes gateway &
   sleep 10
   ```

5. **Verify.**
   ```bash
   grep '^DISCORD_ALLOWED_USERS=' ~/.hermes/.env
   tail -n 20 ~/.hermes/logs/agent.log | grep -i discord
   ```

## Pitfalls

- Discord user IDs are numeric (Snowflake format). Usernames/tags are NOT valid IDs.
- After editing `.env`, the gateway MUST be restarted for changes to take effect.
- With 72 skills, use `DISCORD_COMMAND_SYNC_POLICY=bulk` to avoid timeout (already configured).
- The allowlist is a **whitelist of humans** — never put the bot's own ID here.
