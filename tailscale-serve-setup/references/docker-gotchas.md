# Tailscale Serve + Cert Setup (Docker Gotchas)

## CRITICAL: Docker Environment

### `tailscale cert` FAILS inside Docker
```
# Inside Docker container — this ALWAYS fails:
tailscale cert searxng.crayfish-monitor.ts.net
# → 500 Internal Server Error: acme.GetReg: dial tcp: lookup acme-v02...
#    on [fd7a:115c:a1e0::53]:53: server misbehaving
```

**Why:** Tailscale MagicDNS overwrites `/etc/resolv.conf` → only uses `100.100.100.100` (MagicDNS) → external DNS (ACME servers) is UNRESOLVABLE.

**Solution:** Use `tailscale serve --bg` instead — it handles HTTPS/ACME internally without needing external DNS queries for certificate generation.

```bash
# Correct approach inside Docker:
tailscale serve --bg "http://${FQDN} http://backend:8080"
```

### External DNS must be added BEFORE Tailscale starts
```bash
# In entrypoint.sh — BEFORE tailscaled:
echo "nameserver 8.8.8.8" >> /etc/resolv.conf
echo "nameserver 8.8.4.4" >> /etc/resolv.conf
```

### Never use `wait $PID` in Docker entrypoint
```bash
# WRONG — blocks docker compose up -d:
wait $TAILSCALED_PID

# CORRECT:
sleep infinity
```

### `tailscale serve --https=` is deprecated
```bash
# OLD (broken):
tailscale serve --https="${FQDN}" http://service:8080

# NEW (correct):
tailscale serve --bg "http://${FQDN} http://service:8080"
```