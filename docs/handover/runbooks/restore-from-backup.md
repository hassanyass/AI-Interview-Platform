# Runbook — back up and restore the database

The database is the only stateful store this stack owns. Recordings live in
R2, CVs in the Supabase bucket, the agent's key-rotation state and TTS cache
in the `agent_state` volume (both rebuildable).

## Take a backup

Compose Postgres (`postgres` service, volume `postgres_data`):

```bash
docker compose exec -T postgres pg_dump -U postgres -Fc ai_interview > backup-$(date +%Y%m%d-%H%M).dump
```

Managed Postgres (Supabase): use the project's scheduled backups / PITR, or
`pg_dump -Fc postgresql://<user>:<password>@<host>:5432/<db>` (the
`DATABASE_URL` without the `+asyncpg` driver suffix) from a machine that
can reach it. Store
dumps outside the host that runs the stack; they contain candidate PII.

Take one **before every upgrade** (`runbooks/start-stop-upgrade.md`).

## Restore

1. Stop the readers so nothing writes during the restore:

```bash
docker compose --profile app stop backend agent
```

2. Restore into a fresh database, then swap — never restore over the live
   one while it might still be in use:

```bash
docker compose exec -T postgres psql -U postgres -c 'CREATE DATABASE ai_interview_restore;'
docker compose exec -T postgres pg_restore -U postgres -d ai_interview_restore --no-owner < backup-XXXX.dump
```

   Inspect (`psql -U postgres -d ai_interview_restore -c 'select status, count(*) from interview_sessions group by 1'`),
   then rename:

```bash
docker compose exec -T postgres psql -U postgres -c 'ALTER DATABASE ai_interview RENAME TO ai_interview_old;'
docker compose exec -T postgres psql -U postgres -c 'ALTER DATABASE ai_interview_restore RENAME TO ai_interview;'
```

3. Bring the schema up to the running code (a dump from before a release
   is missing that release's migrations):

```bash
docker compose --profile app up migrate
```

4. Start the readers and check:

```bash
docker compose --profile app up -d backend agent
curl -s localhost:8001/ready
```

5. Sessions that were live at the time of the backup are now stale
   `IN_PROGRESS` rows: `make cli ARGS="finalize-stuck-sessions --dry-run"`
   then without `--dry-run` (`runbooks/stuck-session.md`).
6. Drop `ai_interview_old` once satisfied.

## What a restore loses

Everything written after the dump: sessions, transcripts, evaluations,
invitations, jobs edited since. Recordings and CVs uploaded after the dump
still exist in object storage but the rows pointing at them are gone; they
are orphaned, not deleted (retention is undecided — U1).

## Disposable test DB

`postgres-test` (port 5433, tmpfs) is never backed up; `conftest.py`
rebuilds its schema from Alembic on every pytest run.
