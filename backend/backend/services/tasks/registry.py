"""kind -> handler (H2-F).

The only place that knows which kinds exist. A handler takes a database
session the worker owns and the task's JSON payload, and returns a
JSON-serializable result (stored on the row for the poller to read) or
``None``. It may raise: ``AppError`` subclasses carry a ``code`` that
reaches the admin verbatim, anything else becomes a generic failure.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.tasks import handlers

TaskHandler = Callable[[AsyncSession, dict[str, Any]], Awaitable[dict[str, Any] | None]]

HANDLERS: dict[str, TaskHandler] = {
    handlers.GENERATE_QUESTIONS: handlers.generate_questions,
    handlers.REGENERATE_QUESTION: handlers.regenerate_question,
    handlers.GENERATE_INVITATION_MESSAGE: handlers.generate_invitation_message,
    handlers.REGENERATE_EVALUATION: handlers.regenerate_evaluation,
    handlers.PURGE_EXPIRED_DATA: handlers.purge_expired_data,
}

KINDS = tuple(HANDLERS)


def handler_for(kind: str) -> TaskHandler | None:
    return HANDLERS.get(kind)
