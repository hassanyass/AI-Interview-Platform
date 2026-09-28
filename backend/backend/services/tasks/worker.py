"""The in-process task worker (H2-F).

``TASK_WORKER_CONCURRENCY`` loops run for the lifetime of the backend
(started from main.py's lifespan, same shape as the idle-disconnect
sweep). Each loop claims one task at a time through the queue port --
``FOR UPDATE SKIP LOCKED``, so N loops here and N replicas elsewhere never
run the same row twice -- executes its handler with its own database
session, and records SUCCEEDED or FAILED.

A failed task is **not** retried automatically (owner decision,
2026-09-23): the Groq adapter already retries the transport twice, and
re-running a generation is HR's click, not a machine's. What the loop does
do is mark tasks that a dying process left RUNNING as FAILED once they
pass ``TASK_STALE_MINUTES``, so nobody polls forever.

A handler's own database work is committed by the handler; the worker
never leaves a session open across the LLM call of another task.
"""
from __future__ import annotations

import asyncio
import logging
import time

from backend.core.config import settings
from backend.core.errors import AppError
from backend.core.logging import bind_session
from backend.core.metrics import (
    task_duration_seconds,
    task_queue_depth,
    task_queue_oldest_age_seconds,
    tasks_total,
)
from backend.providers.factory import get_task_queue
from backend.providers.queue.base import TaskQueue, TaskRecord
from backend.services.tasks.registry import handler_for

logger = logging.getLogger(__name__)


async def run_task(task: TaskRecord, *, queue: TaskQueue | None = None) -> str:
    """Execute one claimed task and record its outcome. Returns the final
    status. Never raises: a handler blowing up is a FAILED row, not a dead
    worker."""
    from backend.db.session import AsyncSessionLocal

    queue = queue or get_task_queue()
    handler = handler_for(task.kind)
    if handler is None:
        await queue.fail(task.id, f"No handler registered for task kind {task.kind!r}", code="unknown_task_kind")
        tasks_total.labels(task.kind, "failed").inc()
        logger.error("Task %s has unknown kind %r", task.id, task.kind)
        return "FAILED"

    started = time.perf_counter()
    logger.info("Task %s running (kind=%s)", task.id, task.kind, extra={"event": "task_started", "task_kind": task.kind})
    try:
        async with AsyncSessionLocal() as db:
            result = await handler(db, task.payload)
        await queue.complete(task.id, result)
        tasks_total.labels(task.kind, "succeeded").inc()
        logger.info(
            "Task %s succeeded (kind=%s)", task.id, task.kind,
            extra={"event": "task_succeeded", "task_kind": task.kind,
                   "duration_ms": (time.perf_counter() - started) * 1000},
        )
        return "SUCCEEDED"
    except asyncio.CancelledError:
        # Shutdown mid-task: leave the row RUNNING. The stale sweep reports
        # it honestly once the threshold passes rather than claiming a
        # failure the handler may not have had.
        raise
    except Exception as e:  # noqa: BLE001 -- every handler failure is a FAILED row, whatever it was
        detail = e.detail if isinstance(e, AppError) else "The task failed. Check the backend logs and try again."
        # AppError.code is optional (NotFound and Conflict carry none); the
        # row always gets one so a client can branch on it without guessing.
        code = (e.code or "task_failed") if isinstance(e, AppError) else "task_failed"
        await queue.fail(task.id, detail, code=code)
        tasks_total.labels(task.kind, "failed").inc()
        logger.exception("Task %s failed (kind=%s)", task.id, task.kind, extra={"event": "task_failed", "task_kind": task.kind})
        return "FAILED"
    finally:
        task_duration_seconds.labels(task.kind).observe(time.perf_counter() - started)


async def run_pending_once(*, queue: TaskQueue | None = None, limit: int = 50) -> int:
    """Drain whatever is queued right now, in order, and return how many
    ran. The worker loop uses ``claim`` directly; this is for the CLI and
    for tests that want the queue emptied deterministically."""
    queue = queue or get_task_queue()
    ran = 0
    while ran < limit:
        task = await queue.claim()
        if task is None:
            break
        bind_session(None)
        await run_task(task, queue=queue)
        ran += 1
    return ran


async def _publish_stats(queue: TaskQueue) -> None:
    stats = await queue.stats()
    task_queue_depth.labels("QUEUED").set(stats.queued)
    task_queue_depth.labels("RUNNING").set(stats.running)
    task_queue_oldest_age_seconds.set(stats.oldest_queued_age_seconds)


async def worker_loop(index: int = 0) -> None:
    """One claim-execute loop. Survives any single iteration's failure for
    the same reason the sweep does: the process must keep draining."""
    queue = get_task_queue()
    logger.info("Task worker %d started", index)
    stale_checked_at = 0.0
    while True:
        try:
            # Only one loop needs to publish gauges / reap; loop 0 does it.
            if index == 0:
                now = time.monotonic()
                if now - stale_checked_at >= 60:
                    stale_checked_at = now
                    await queue.reap_stale(settings.TASK_STALE_MINUTES)
                await _publish_stats(queue)

            task = await queue.claim()
            if task is None:
                await asyncio.sleep(settings.TASK_POLL_INTERVAL_SECONDS)
                continue
            await run_task(task, queue=queue)
        except asyncio.CancelledError:
            logger.info("Task worker %d stopping", index)
            raise
        except Exception:  # noqa: BLE001 -- the loop must survive a bad iteration
            logger.exception("Task worker %d iteration failed", index)
            await asyncio.sleep(settings.TASK_POLL_INTERVAL_SECONDS)


def start_workers() -> list[asyncio.Task]:
    """Spawn the configured number of loops. Returns the asyncio tasks so
    the lifespan can cancel them on shutdown."""
    if not settings.TASK_WORKER_ENABLED:
        logger.info("Task worker disabled (TASK_WORKER_ENABLED=false); tasks will queue but not run here")
        return []
    count = max(1, settings.TASK_WORKER_CONCURRENCY)
    return [asyncio.create_task(worker_loop(i), name=f"task-worker-{i}") for i in range(count)]
