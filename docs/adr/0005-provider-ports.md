# ADR 0005 — Fix the stack at FastAPI and React; put every vendor behind a port

- **Status:** Accepted — implemented in H1
- **Decided:** 2026-09-17
- **Source:** `docs/production-hardening-plan.md` §0, decision S5

## Context

Python/FastAPI and React/Vite/TypeScript are fixed. Supabase, LiveKit, Groq, object
storage and email are not — they were chosen for a prototype and may be replaced by
whoever operates this.

## Decision

One port (abstract base) per external capability under `backend/backend/providers/`,
with the implementation selected by a `*_PROVIDER` setting and built by a factory.
No vendor is switched as part of this work.

## Consequences

- Application code never imports a vendor SDK; timeouts and retries live in one place
  per vendor rather than at every call site.
- Adding a vendor is an adapter, a settings value and a factory branch — the recipe
  is `docs/handover/runbooks/add-provider-adapter.md`.
- A little indirection for capabilities that have exactly one implementation today.

## How it turned out

Six ports: llm, storage, realtime, email, notifications, queue. The value showed up
in unrelated phases — `@timed_provider_call` gave every vendor call latency and
failure metrics in one line each (H3), and the fakes in `backend/tests/fakes.py` are
why the test suite makes no network calls at all.
