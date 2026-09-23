"""Task queue port (H2-F, plan decision S9).

The queue is Postgres today. The port exists so it can become Redis/SQS/
Celery later without touching a router or a handler: nothing outside
``providers/queue/`` knows how a row is claimed. Methods return
``TaskRecord`` dataclasses, not ORM objects, so an adapter that has no
SQLAlchemy session can satisfy the same contract.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class TaskRecord:
    id: UUID
    kind: str
    status: str
    payload: dict[str, Any]
    result: dict[str, Any] | None
    error: str | None
    error_code: str | None
    attempts: int
    requested_by: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


@dataclass(frozen=True)
class QueueStats:
    queued: int
    running: int
    oldest_queued_age_seconds: float
    """0.0 when nothing is queued."""


class TaskQueue(ABC):
    """Every method owns its own transaction: a task's lifecycle is
    independent of the HTTP request or worker iteration around it."""

    @abstractmethod
    async def enqueue(self, kind: str, payload: dict[str, Any], *, requested_by: str | None = None) -> TaskRecord:
        """Record a unit of work as QUEUED and return it. Never runs it."""
        raise NotImplementedError

    @abstractmethod
    async def get(self, task_id: UUID) -> TaskRecord | None:
        raise NotImplementedError

    @abstractmethod
    async def claim(self) -> TaskRecord | None:
        """Atomically take the oldest QUEUED task and mark it RUNNING.
        Returns None when the queue is empty. Concurrent callers -- in this
        process or another replica -- never receive the same row."""
        raise NotImplementedError

    @abstractmethod
    async def complete(self, task_id: UUID, result: dict[str, Any] | None) -> None:
        raise NotImplementedError

    @abstractmethod
    async def fail(self, task_id: UUID, error: str, *, code: str | None = None) -> None:
        raise NotImplementedError

    @abstractmethod
    async def reap_stale(self, older_than_minutes: int) -> int:
        """Fail RUNNING tasks abandoned by a process that died mid-flight,
        so a poller is never left waiting forever. Returns how many.
        Not a retry: the owner's decision (2026-09-23) is that a failed
        task is reported, and re-running it is the admin's click."""
        raise NotImplementedError

    @abstractmethod
    async def stats(self) -> QueueStats:
        raise NotImplementedError
