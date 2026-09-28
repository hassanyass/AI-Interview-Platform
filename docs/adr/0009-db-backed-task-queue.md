# ADR 0009 — Use a database-backed task queue, not Redis or Celery

- **Status:** Accepted — implemented in H2-F
- **Decided:** 2026-09-17
- **Source:** `docs/production-hardening-plan.md` §0, decision S9

## Context

Four admin actions ran a Groq call inline. The browser aborts at 30s while the adapter
allows roughly 90s, so a slow generation looked like a failure while the work carried
on and committed. Something had to run outside the request.

## Decision

A table plus an in-process worker, behind a `TaskQueue` port so it can be replaced.
No new infrastructure to operate.

## Consequences

- One fewer service to run, back up and monitor.
- Throughput is bounded by the database, which at this load is not the constraint.
- The port keeps a Redis or SQS adapter a contained change.

## How it turned out

Implemented as `tasks` — deliberately not `jobs`, since `Job` is the hiring entity.
Claiming uses `FOR UPDATE SKIP LOCKED` rather than the advisory lock this decision
assumed: same exclusivity per row, but workers and replicas run in parallel instead
of serialising on one application-wide lock.
