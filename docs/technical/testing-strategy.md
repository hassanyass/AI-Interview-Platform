# Testing Strategy

What actually runs, where it lives, and what each layer is allowed to touch.
Rewritten during hardening H3 (2026-09-22); the Phase 0 sketch it replaces
named tools that were never adopted (Testcontainers, snapshot prompts).

## One command

```bash
make test            # docker compose up -d --wait postgres-test; pytest -q; cd frontend && npm test
```

Windows: `scripts/dev.ps1 test`. Per suite: `make test-backend`,
`make test-agent`, `make test-legacy`, `cd frontend && npm test`.

## Database rule

Python tests run against the **disposable** `postgres-test` container
(port 5433, tmpfs). The root `conftest.py` rewrites `DATABASE_URL` to
`TEST_DATABASE_URL`, drops and recreates the `public` schema from the
Alembic chain once per session, and **refuses any Supabase host** — the
suite can never touch a real database by mistake. No test mocks the
database; SQLAlchemy models and migrations are exercised for real.

## Layout (`pytest.ini`: `testpaths = backend/tests agent tests/legacy`)

| Suite | What it covers | Style |
|---|---|---|
| `backend/tests/` | settings fail-closed (`test_settings.py`), RFC7807 errors + request id (`test_errors.py`), provider adapters + factory (`test_providers.py`, fakes in `fakes.py`), service layer (`test_services_extraction.py`), resilience — pool, sweep lock, FOR UPDATE finalize, background tasks, /health vs /ready (`test_resilience.py`), CV gate + extraction (`test_session_cv_gate.py`, `test_resume_profile_extraction.py`), background evaluation, logging/metrics/CLI (`test_observability.py`) | `httpx.AsyncClient(ASGITransport(app))` against the real app; real test DB; **no network** — Groq/LiveKit/storage are fakes |
| `agent/agent/tests/` | `AgentSettings` (`test_config.py`), plugin factory (`test_factory.py`), the real `entrypoint` with fakes — crash / lease lost / completion (`test_runtime.py`), `APIPersistence` retry/outbox/lease (`test_persistence_transport.py`), voice-adapter guards (`test_adapter_guards.py`), the H2-C spoken-control confirmation in the frozen controller (`test_controller_h2c.py`), logging + X-Request-ID (`test_observability.py`) | pure asyncio with fakes; no LiveKit server, no backend |
| `agent/test_*.py` (root of `agent/`) | pre-hardening controller/state-machine regressions (`test_skip_regressions.py`, `test_background_subsection.py`) | untouched; still collected |
| `tests/legacy/` | the phase-by-phase integration tests written during the B2C→B2B transition (`test_phase1.py` … `test_phase9b.py`) | moved here in H0 (S2), unchanged; they run against the test DB like everything else |
| `frontend/src/**/*.test.ts(x)` | `lib/api.errors.test.ts` (ApiError, timeout, abort), `components/ErrorBoundary.test.tsx`, `context/RoleContext.test.tsx`, plus earlier pure-logic tests | vitest, jsdom, `@testing-library/react`; no backend |

Counts at the last full run: **pytest 335 passed, 1 skipped; vitest 22/22.**

## What is deliberately not automated

- **The live voice loop** (LiveKit room + STT/TTS/LLM + browser). It is
  verified by a real spoken interview after each phase that touches it and
  the outcome is recorded in the phase's verify record
  (`docs/production-hardening-plan.md` §8+, `docs/realtime-voice-hardening.md`).
- **Provider contracts** — Groq, LiveKit, Supabase, R2 are never called in
  tests. Adapter behaviour (timeouts, retries, error mapping) is tested with
  fakes; the vendor is trusted to match its SDK.
- **Frontend layout** — `npm run responsive` (`scripts/responsive-shots.cjs`,
  puppeteer) produces screenshots at the breakpoints in
  `docs/responsive-checklist.md` for a human to compare; it is not a pass/fail gate.

## Rules

- Frozen files (`agent/agent/interview/controller.py`, `/internal/*`,
  `InterviewerCharacter.tsx`) get tests **around** them; the files change
  only under an approved sub-phase (`CLAUDE.md` §2).
- Never delete, move or rewrite an existing test file without explicit
  sign-off (`CLAUDE.md` §7) — including anything under `tests/legacy/`.
- A change with no covering test gets one first (`CLAUDE.md` §4.4).
- Tests must not need real credentials: the root `.env` used for local
  runs has `ENVIRONMENT=local`, so the fail-closed settings checks stay off;
  `test_settings.py` exercises them by constructing `Settings` explicitly.
  Nothing in the suites calls a vendor API.
- CI wiring (GitHub Actions running the same `make test`) is H4.
