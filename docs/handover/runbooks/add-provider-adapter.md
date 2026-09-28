# Runbook — add or swap a provider adapter

External services sit behind ports in `backend/backend/providers/`:

| port (`base.py`) | adapters today | selected by |
|---|---|---|
| `llm/LLMProvider.complete_json` | `llm/groq.py` | `LLM_PROVIDER` |
| `storage/ObjectStorage` | `storage/s3.py` (recordings), `storage/supabase.py` (CVs) | `RECORDINGS_STORAGE_PROVIDER`, `RESUMES_STORAGE_PROVIDER` |
| `realtime/RealtimeProvider` | `realtime/livekit.py` | `REALTIME_PROVIDER` |
| `email/EmailProvider.send` | `email/null.py` | `EMAIL_PROVIDER` |
| `notifications/NotificationService` | `notifications/console.py`, `notifications/email.py` | `NOTIFICATIONS_PROVIDER` |

`providers/factory.py` builds one instance per port from `settings`
(`lru_cache`), so application code never imports a vendor SDK. Example
below: a real email provider (the open item P1 — pick the vendor first,
`CURRENT_DECISIONS.md`).

## Steps

1. **Adapter** — `backend/backend/providers/email/<vendor>.py`, a class
   implementing the port. Own the wire only: timeouts, bounded retries,
   mapping vendor errors to the port's result/exceptions. Wrap each outbound
   call with `@timed_provider_call("<vendor>", "<op>")` from
   `backend.core.metrics` so it shows up in `provider_call_*`. Do not read
   `settings` inside the adapter; take everything through `__init__`.

2. **Settings** — `backend/backend/core/config.py`: widen the `Literal`
   (`EMAIL_PROVIDER: Literal["null", "<vendor>"]`), add the vendor's
   settings (`<VENDOR>_API_KEY`, timeouts), and add them to the fail-closed
   check that runs outside `local`/`test` when they are required for the
   chosen provider. Document each in `backend/.env.example` with a one-line
   comment.

3. **Factory** — `providers/factory.py::get_email()`: one more `if`
   branch constructing the adapter from `settings`. Nothing else changes;
   `get_notification_service()` already hands the email provider to
   `EmailNotificationService`.

4. **Tests** — `backend/tests/test_providers.py` is the pattern: a fake
   transport (no network), asserting timeout/retry/error mapping and that
   the factory picks the adapter for the setting value. Use
   `reset_providers()` between settings changes. Run `make test-backend`.

5. **Lock file** — if a vendor SDK is added: `backend/requirements.in`,
   then `make lock` (pip-tools), commit both files.

6. **Roll out** — set `EMAIL_PROVIDER=<vendor>` and its keys in `.env`,
   `docker compose --profile app up -d --build backend`, send one
   invitation from the admin UI, confirm the
   `provider_call_duration_seconds_count{provider="<vendor>"}` sample and the
   `INFO` log line for the send. Rollback = `EMAIL_PROVIDER=null` and
   restart.

## Agent side

The worker has its own factory (`agent/agent/providers/factory.py`:
`build_llm`, `build_stt`, `build_tts`, `vad_for`) over LiveKit plugins,
selected by `TTS_PROVIDER` etc. in `agent/agent/config.py`. Same rules:
adapter owns the wire, settings validated in `AgentSettings`, documented in
`agent/.env.example`, tests with fakes under `agent/agent/tests/`. The
interview controller (`agent/agent/interview/controller.py`) is frozen and
never sees vendor types.
