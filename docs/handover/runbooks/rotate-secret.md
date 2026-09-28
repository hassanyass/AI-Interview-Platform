# Runbook — rotate a secret or API key

All secrets are environment variables in the root `.env`; nothing is stored
in the database or the images. Rotation = change the value, restart the
service(s) that read it.

| Secret | Read by | Restart | Notes |
|---|---|---|---|
| `AGENT_API_SECRET` | backend + agent (must match) | both, agent first then backend, or expect 403s in between | Every `/internal/*` call carries it. A mismatch shows in backend logs as 403 on `…/renew-lease` with the agent's `request_id` |
| `SECRET_KEY` | backend | backend | signs guest JWTs — rotating it invalidates outstanding candidate links in flight |
| `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` | backend + agent | both | rotate in the LiveKit project first, keep the old pair valid until both services restarted |
| `GROQ_API_KEY`, `GROQ_API_KEY_n` | backend (`GROQ_API_KEY`) + agent (all) | both | the agent's TTS rotator persists per-key state in `AGENT_STATE_DIR`; a removed key is simply no longer rotated to |
| `SUPABASE_SECRET_KEY` | backend | backend | service-role key; never in the frontend |
| `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` | backend | backend | recordings storage |
| `AZURE_TTS_*` | agent | agent | only when `TTS_PROVIDER=azure` |

## Procedure

1. Create the new credential at the provider (keep the old one active).
2. Edit `.env`.
3. Restart the readers:

```bash
docker compose --profile app up -d --force-recreate agent backend
```

   (`up -d` alone does not re-read `env_file` for an already-created container.)
4. Verify: `curl -s localhost:8001/ready` is 200; for `AGENT_API_SECRET`,
   start one interview or watch `docker compose logs -f backend | grep renew-lease`
   for `200`s; for Groq, an admin "generate questions" call succeeds.
5. Revoke the old credential at the provider.

## Timing

Live interviews: the agent renews its lease every
`LEASE_RENEWAL_INTERVAL_SECONDS` (default 300). Restarting the agent drops
running interviews (they end `DISCONNECTED`, the candidate sees the
reconnect screen and the sweep finalizes after
`DISCONNECT_AUTO_FINALIZE_MINUTES`). Rotate outside interview hours or accept
that.

Placeholders like `change-me` are refused at boot outside `ENVIRONMENT=local|test`.
