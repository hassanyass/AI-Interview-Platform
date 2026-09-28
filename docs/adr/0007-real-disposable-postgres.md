# ADR 0007 — Test against a real disposable Postgres, not mocks

- **Status:** Accepted — implemented in H0-A
- **Decided:** 2026-09-17
- **Source:** `docs/production-hardening-plan.md` §0, decision S7

## Context

The suites ran against whatever `DATABASE_URL` pointed at — the shared Supabase
project — and cleaned up afterwards with a regex fixture. By 2026-09-16 that database
held 721 fixture jobs and ~257 sessions, some of them published and publicly
reachable.

## Decision

A disposable Postgres container (`postgres-test`, tmpfs, port 5433). The root
`conftest.py` redirects `DATABASE_URL` to it before any application import, rebuilds
the schema from the real Alembic chain once per session, and **refuses to run against
a Supabase host**. No test mocks the database. No browser end-to-end tests in CI.

## Consequences

- Migrations are exercised on every run, so a broken one fails before any test does.
- Tests need Docker, which is now a documented prerequisite.
- The live voice loop stays a manual check, recorded per phase.

## How it turned out

The refusal has earned its place: it is the reason no later phase could point the
suite at production by accident. 461 tests now run this way, and the migration
reversibility check added in H4-A rides on the same foundation.
