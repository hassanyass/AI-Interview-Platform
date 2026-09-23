"""Postgres-backed task queue (H2-F).

``SELECT ... FOR UPDATE SKIP LOCKED`` is the claim: the row is locked for
the duration of one short transaction, every other claimer skips it, and
the status flips to RUNNING before the lock is released. That is why two
workers -- or two backend replicas -- can poll the same table and still
run each task exactly once. (The plan's S9 wording said "advisory lock";
SKIP LOCKED gives the same exclusivity per row while letting workers run
in parallel, which an app-wide advisory lock would not.)
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.task import FAILED, QUEUED, RUNNING, SUCCEEDED, Task
from backend.providers.queue.base import QueueStats, TaskQueue, TaskRecord

logger = logging.getLogger(__name__)


def _record(task: Task) -> TaskRecord:
    return TaskRecord(
        id=task.id,
        kind=task.kind,
        status=task.status,
        payload=task.payload or {},
        result=task.result,
        error=task.error,
        error_code=task.error_code,
        attempts=task.attempts,
        requested_by=task.requested_by,
        created_at=task.created_at,
        started_at=task.started_at,
        finished_at=task.finished_at,
    )


class PostgresTaskQueue(TaskQueue):
    def __init__(self, session_factory: Callable[[], AsyncSession]) -> None:
        self._session_factory = session_factory

    async def enqueue(self, kind: str, payload: dict[str, Any], *, requested_by: str | None = None) -> TaskRecord:
        async with self._session_factory() as db:
            task = Task(id=uuid4(), kind=kind, status=QUEUED, payload=payload, requested_by=requested_by)
            db.add(task)
            await db.commit()
            await db.refresh(task)
            logger.info("Task %s queued (kind=%s)", task.id, kind, extra={"event": "task_queued", "task_kind": kind})
            return _record(task)

    async def get(self, task_id: UUID) -> TaskRecord | None:
        async with self._session_factory() as db:
            task = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
            return _record(task) if task else None

    async def claim(self) -> TaskRecord | None:
        async with self._session_factory() as db:
            task = (
                await db.execute(
                    select(Task)
                    .where(Task.status == QUEUED)
                    .order_by(Task.created_at)
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
            ).scalar_one_or_none()
            if task is None:
                await db.rollback()
                return None
            task.status = RUNNING
            task.started_at = datetime.now(timezone.utc)
            task.attempts = (task.attempts or 0) + 1
            await db.commit()
            await db.refresh(task)
            return _record(task)

    async def complete(self, task_id: UUID, result: dict[str, Any] | None) -> None:
        await self._finish(task_id, SUCCEEDED, result=result)

    async def fail(self, task_id: UUID, error: str, *, code: str | None = None) -> None:
        await self._finish(task_id, FAILED, error=error, code=code)

    async def _finish(
        self, task_id: UUID, status: str, *,
        result: dict[str, Any] | None = None, error: str | None = None, code: str | None = None,
    ) -> None:
        async with self._session_factory() as db:
            await db.execute(
                update(Task)
                .where(Task.id == task_id)
                .values(status=status, result=result, error=error, error_code=code,
                        finished_at=datetime.now(timezone.utc))
            )
            await db.commit()

    async def reap_stale(self, older_than_minutes: int) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=older_than_minutes)
        async with self._session_factory() as db:
            result = await db.execute(
                update(Task)
                .where(Task.status == RUNNING, Task.started_at.is_not(None), Task.started_at < cutoff)
                .values(
                    status=FAILED,
                    error="The backend stopped while this task was running. Start it again.",
                    error_code="task_interrupted",
                    finished_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()
            count = result.rowcount or 0
        if count:
            logger.warning("Failed %d task(s) abandoned mid-flight (older than %dm)", count, older_than_minutes)
        return count

    async def stats(self) -> QueueStats:
        async with self._session_factory() as db:
            rows = (
                await db.execute(select(Task.status, func.count()).where(Task.status.in_((QUEUED, RUNNING))).group_by(Task.status))
            ).all()
            counts = {status: n for status, n in rows}
            oldest = (
                await db.execute(select(func.min(Task.created_at)).where(Task.status == QUEUED))
            ).scalar_one_or_none()
        age = (datetime.now(timezone.utc) - oldest).total_seconds() if oldest else 0.0
        return QueueStats(
            queued=counts.get(QUEUED, 0),
            running=counts.get(RUNNING, 0),
            oldest_queued_age_seconds=max(age, 0.0),
        )
