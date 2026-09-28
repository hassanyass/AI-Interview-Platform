# Runbook — a background task is stuck or failed

## What uses the queue

Four admin actions (H2-F). Each answers `202` with a task id and runs in
the backend's task worker; the browser polls `GET /api/v1/admin/tasks/{id}`:

| Action | `kind` |
|---|---|
| Generate questions for a section | `generate_questions` |
| Regenerate one question | `regenerate_question` |
| Draft an invitation message | `generate_invitation_message` |
| Regenerate an evaluation | `regenerate_evaluation` |

Nothing else is queued — a candidate's CV extraction still runs inside its
upload request.

## Symptoms and where to look

HR reports a spinner that never finishes, or "This is taking longer than
expected" (the browser's 3-minute poll timeout — the task itself keeps
running).

```bash
curl -s localhost:8001/metrics | grep -E 'task_queue|tasks_total'
```

- `task_queue_depth{status="QUEUED"}` climbing and
  `task_queue_oldest_age_seconds` growing past a minute → **nothing is
  draining**. Check the worker started:

```bash
docker compose logs backend | grep "Task worker"
```

  Expect `Task worker 0 started` per `TASK_WORKER_CONCURRENCY`. If instead
  you see `Task worker disabled`, `TASK_WORKER_ENABLED` is false for this
  process.
- `task_queue_depth{status="RUNNING"}` stuck at 1 with nothing finishing →
  a handler is hanging on a provider. See `runbooks/provider-outage.md`;
  `TASK_STALE_MINUTES` (default 15) bounds it — the row is then marked
  FAILED with `task_interrupted` so the poller stops waiting.
- `tasks_total{outcome="failed"}` rising → the work is running and
  failing. The reason is on the row and in the log.

## Inspect one task

```bash
docker compose exec backend python -c "
import asyncio, backend.db.base
from backend.providers.factory import get_task_queue
async def main():
    t = await get_task_queue().get(__import__('uuid').UUID('<task-id>'))
    print(t.kind, t.status, t.attempts, t.error_code, t.error)
asyncio.run(main())"
```

Or in the logs, which carry `task_kind` and the task id:

```bash
docker compose logs backend | grep '<task-id>'
```

## Fix

- **Failed task** — the row holds the handler's own message (`error`,
  `error_code`). There is **no automatic retry by design**: re-running a
  generation is HR's click. Tell them to press the button again once the
  cause is cleared. Common codes: `llm_generation_failed` (provider),
  `task_failed` (anything else, message tells you), `task_interrupted`
  (the backend restarted mid-task), `unknown_task_kind` (a queued row from
  a newer version than the running code — deploy the matching version).
- **Nothing draining** — restart the backend so the worker starts:

```bash
docker compose --profile app up -d --force-recreate backend
```

  Queued rows survive the restart; that is the point of the table. Any row
  left `RUNNING` by the old process is failed after `TASK_STALE_MINUTES`.
- **Backlog after an outage** — raise `TASK_WORKER_CONCURRENCY` (each task
  is one LLM call; this raises provider load, it does not make one task
  faster) and restart.

## What is never lost

The result of a finished task stays on the row — finished rows are kept
deliberately (owner decision, 2026-09-23). If HR's browser gave up
waiting, the work still completed: reload the page. For an invitation
draft, whose text exists nowhere else, read `result` with the inspect
command above.
