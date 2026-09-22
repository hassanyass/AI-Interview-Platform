# Runbook — start, stop, upgrade

Applies to the Docker Compose stack (`docker-compose.yml`, profile `app`).
Root `.env` must exist and pass the boot checks (`backend/.env.example`,
`agent/.env.example` list every setting).

## Start

```bash
docker compose --profile app up -d --build
```

Order is enforced by `depends_on`: `migrate` runs `alembic upgrade head`
and must exit 0 → `backend` starts and must pass `/ready` → `agent` starts.
`frontend` is independent (dev server).

Confirm:

```bash
docker compose --profile app ps                      # backend "healthy", migrate "exited (0)"
curl -s localhost:8001/ready                         # {"status":"ready","checks":{"database":"ok"},...}
docker compose logs agent | grep -i "registered worker"
```

If `backend` never turns healthy: `docker compose logs backend` — a
fail-closed settings error names the missing variable on the first lines.

## Stop

```bash
docker compose --profile app down          # keeps the postgres_data and agent_state volumes
docker compose --profile app down -v       # ALSO deletes the database — only after a backup
```

Live interviews: stopping the agent mid-interview marks the session
`DISCONNECTED` (teardown writes a `SESSION_DISCONNECTED` event and a
checkpoint); the idle-disconnect sweep finalizes it after
`DISCONNECT_AUTO_FINALIZE_MINUTES`. Prefer to stop when
`http_requests_total{route="/api/v1/internal/interviews/{session_id}/renew-lease"}`
has stopped increasing.

## Upgrade

1. Back up first: `runbooks/restore-from-backup.md` §"Take a backup".
2. Pull/checkout the new code.
3. Rebuild and restart; migrations apply through the `migrate` service:

```bash
docker compose --profile app build
docker compose --profile app up -d
```

4. Verify: `curl -s localhost:8001/version`, `/ready` is 200, an agent
   worker registered, `docker compose logs --since 5m backend agent | grep -i '"level": "ERROR"'` is empty.
5. If the new backend fails on `alembic` errors: `runbooks/apply-migration.md`.

Rollback = check out the previous commit and repeat step 3. Migrations are
additive-only (`CLAUDE.md` §3), so the previous code runs against the newer
schema; only run `alembic downgrade` if the release notes say the migration
is reversible.

## Without Docker (three-terminal dev)

See `docs/LOCAL_DEMO_SETUP.md`; the same env applies. `scripts/dev.ps1`
(Windows) / `Makefile` (Linux/macOS) wrap the commands.
