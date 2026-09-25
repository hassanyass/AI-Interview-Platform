# Testing Strategy

What actually runs, where it lives, and what each layer is allowed to touch.
Rewritten during hardening H3 (2026-09-22); the Phase 0 sketch it replaces
named tools that were never adopted (Testcontainers, snapshot prompts).

## One command

```bash
make test            # docker compose up -d --wait postgres-test; pytest -q; cd frontend && npm test
```

```bash
make ci              # everything CI runs, in CI's order, locally
```

Windows: `scripts/dev.ps1 test` / `scripts/dev.ps1 ci`. Per suite:
`make test-backend`, `make test-agent`, `make test-legacy`,
`cd frontend && npm test`. Python linting: `make lint-py` (ruff).

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
| `backend/tests/` | settings fail-closed (`test_settings.py`), RFC7807 errors + request id (`test_errors.py`), provider adapters + factory (`test_providers.py`, fakes in `fakes.py`), service layer (`test_services_extraction.py`), resilience — pool, sweep lock, FOR UPDATE finalize, background tasks, /health vs /ready (`test_resilience.py`), CV gate + extraction (`test_session_cv_gate.py`, `test_resume_profile_extraction.py`), background evaluation, logging/metrics/CLI (`test_observability.py`), the task queue (`test_tasks.py`), migration reversibility + drift (`test_migrations.py`), **the auth matrix over the whole route table** (`test_auth_matrix.py`), token verification with real signed tokens (`test_token_verification.py`), identity linking policy (`test_identity_link.py`), rate limiting (`test_rate_limit.py`), recording-start idempotency under concurrency (`test_egress_claim.py`), generated-documentation drift (`test_docs.py`), data deletion + the admin audit trail (`test_data_deletion.py`), the disabled purge job and CORS fail-closed (`test_purge_and_cors.py`) | `httpx.AsyncClient(ASGITransport(app))` against the real app; real test DB; **no network** — Groq/LiveKit/storage are fakes |
| `agent/agent/tests/` | `AgentSettings` (`test_config.py`), plugin factory (`test_factory.py`), the real `entrypoint` with fakes — crash / lease lost / completion (`test_runtime.py`), `APIPersistence` retry/outbox/lease (`test_persistence_transport.py`), voice-adapter guards (`test_adapter_guards.py`), the H2-C spoken-control confirmation in the frozen controller (`test_controller_h2c.py`), logging + X-Request-ID (`test_observability.py`), **the real `build_context` resume path** (`test_bootstrap_resume.py`), TTS cache (`test_tts_cache.py`), Groq key rotator (`test_key_rotator.py`), LLM timeout + turn-lock release (`test_llm_timeout.py`) | pure asyncio with fakes; no LiveKit server, no backend |
| `agent/test_*.py` (root of `agent/`) | pre-hardening controller/state-machine regressions (`test_skip_regressions.py`, `test_background_subsection.py`) | untouched; still collected |
| `tests/legacy/` | the phase-by-phase integration tests written during the B2C→B2B transition (`test_phase1.py` … `test_phase9b.py`) | moved here in H0 (S2), unchanged; they run against the test DB like everything else |
| `frontend/src/**/*.test.ts(x)` | `lib/api.errors.test.ts` (ApiError, timeout, abort), `lib/tasks.test.ts` (task polling), `components/ErrorBoundary.test.tsx`, `components/ui/ResponsiveTable.test.tsx` (both renderings), `context/RoleContext.test.tsx`, plus earlier pure-logic tests | vitest, jsdom, `@testing-library/react`; no backend |

Counts at the last full run: **pytest 468 passed, 1 skipped; vitest 38/38.**

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

## Gates (H4-A)

| Gate | Command | Where |
|---|---|---|
| Python lint | `ruff check .` | pre-commit + CI |
| Python tests + coverage | `pytest -q --cov=...` | CI (`make test` locally) |
| Migration reversibility | `backend/tests/test_migrations.py` and, on the built image, `alembic upgrade head -> downgrade -1 -> upgrade head` | CI |
| Frontend types | `npm run typecheck` (`strict: true`) | `npm run build` + CI |
| Frontend lint | `npm run lint` (oxlint on `src`) | pre-commit + `npm run build` + CI |
| Frontend tests | `npm test` (vitest + jsdom) | CI |
| Bundle builds | `npm run build:only` | CI |
| Images build | `docker build ./backend`, `./agent` | CI |
| Dependency advisories | `pip-audit` (both lock files), `npm audit --omit=dev` | CI — runtime deps gate, dev-only advisories are reported |
| Hygiene | end-of-file, trailing whitespace, merge conflicts, YAML/JSON validity, large files, private keys, a refusal to commit `.env` | pre-commit |
| Generated docs | `python scripts/generate_docs.py --check` (via `test_docs.py`) | CI — fails when the env matrix or the data model no longer matches the code, or a setting has no docstring |

`.github/workflows/ci.yml` runs on every push to `main`/`master` and every
pull request, in three jobs (python, frontend, images). It needs **no
secrets**: every test runs against fakes and an ephemeral Postgres, and the
Supabase/LiveKit/Groq values in the workflow are placeholders that exist
only because `Settings` has four required fields. If a job ever needs a
real credential, a test has started calling a vendor -- fix the test.

Install the local hook once: `make hooks` (or `scripts/dev.ps1 hooks`).
`ruff.toml` and `.pre-commit-config.yaml` both exclude the frozen
`controller.py` and the legacy suites, for the reasons in `AGENTS.md` §2
and §7 -- a linter may not demand edits to files the rules forbid touching.

Ruff's rule set is deliberately small (`E4`, `E9`, `F`): the defects
pyflakes finds, not style, and no formatter. Widening it is a deliberate
later step, not a silent one.

Coverage is reported (≈75% of `backend/backend` + `agent/agent` at the time
of writing) and uploaded as a CI artifact. **No threshold gate** -- a
number that fails a build teaches people to write tests that raise the
number.

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
- Flaky tests are defects: a gate nobody trusts is worse than no gate.
  `RoleContext.test.tsx` was failing about one run in two (an unstable
  mock re-running the effect under test) and was fixed, not retried,
  while this pipeline was written.
- Auth is tested against the **route table**, not a hand-written list
  (`test_auth_matrix.py`): a route added without an auth dependency fails
  the suite. Route counts are asserted loosely (`>=`) so adding routes is
  fine; removing a whole class is not.
