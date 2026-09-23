"""Durable background work (H2-F).

One row per unit of work an HTTP request refuses to wait for. Named
``Task``, deliberately not ``Job``: ``Job`` is the hiring entity
(``models/interview.py``) and AGENTS.md §1 fixes that name.

Lifecycle: ``QUEUED`` -> ``RUNNING`` -> ``SUCCEEDED`` | ``FAILED``. The
worker (``services/tasks/worker.py``) claims rows with ``FOR UPDATE SKIP
LOCKED``, so several workers -- and several backend replicas -- can drain
the same queue without ever running one row twice. Finished rows are
kept (owner decision, 2026-09-23): the result of an AI generation is the
audit trail of what HR was shown.
"""
import uuid

from sqlalchemy import Column, DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from backend.db.session import Base

QUEUED = "QUEUED"
RUNNING = "RUNNING"
SUCCEEDED = "SUCCEEDED"
FAILED = "FAILED"
TERMINAL_STATUSES = (SUCCEEDED, FAILED)


class Task(Base):
    __tablename__ = "tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind = Column(String, nullable=False)
    """Selects the handler in services/tasks/registry.py."""
    status = Column(String, nullable=False, default=QUEUED, server_default=QUEUED)
    payload = Column(JSONB, nullable=False, server_default="{}")
    """Handler input. JSON only -- the row outlives the request that wrote it."""
    result = Column(JSONB, nullable=True)
    """Handler output, read by the poller. The invitation draft lives only here."""
    error = Column(Text, nullable=True)
    error_code = Column(String, nullable=True)
    attempts = Column(Integer, nullable=False, default=0, server_default="0")
    requested_by = Column(String, nullable=True)
    """Admin user id from the request that enqueued it; null for internal work."""

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # The claim query: oldest QUEUED first. Also serves the stale-RUNNING
        # sweep and the depth/age gauges.
        Index("ix_tasks_status_created_at", "status", "created_at"),
    )
