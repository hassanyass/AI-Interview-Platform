# Runbook — apply a database migration

Migrations live in `backend/alembic/versions/`; they are additive-only
(new tables, nullable columns) unless the plan phase says otherwise.

## Compose stack

The `migrate` service applies `alembic upgrade head` on every
`docker compose --profile app up`. **It uses the image built at that time**
— after pulling code with a new revision, rebuild it or the old image runs
and the backend starts against an old schema:

```bash
docker compose --profile app build migrate backend
docker compose --profile app up migrate          # runs and exits; read its output
docker compose --profile app up -d backend agent
```

Check the applied head against the code's head:

```bash
docker compose --profile app run --rm migrate alembic current
docker compose --profile app run --rm migrate alembic heads
```

Both must print the same revision id.

## Local / manual

```bash
make migrate                      # = cd backend && alembic upgrade head against DATABASE_URL
```

or on Windows `scripts/dev.ps1 migrate`.

## Managed database (Supabase)

`DATABASE_URL` in `.env` is the migration target; run the same command with
that URL from a machine that can reach it. Never point the test suite at
it — `conftest.py` refuses Supabase hosts on purpose.

## `RUN_MIGRATIONS_ON_START`

The backend image's entrypoint can run `alembic upgrade head` itself
(`RUN_MIGRATIONS_ON_START=true`). Off by default: with several backend
replicas each would race to migrate. Use the one-shot `migrate` service or a
deploy step instead.

## If it fails

- `Can't locate revision …` — the DB has a revision the code does not know
  (someone applied a newer branch). Do not `stamp`; find the revision in git history first.
- `relation already exists` — a previous run half-applied. Inspect the DB,
  fix by hand, then `alembic stamp <rev>` for that one revision only.
- Never fix by deleting `alembic_version` rows on a database with data.
