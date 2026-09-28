"""Tracked fire-and-forget tasks.

``asyncio.create_task`` keeps only a weak reference: an un-referenced task
can be garbage-collected mid-flight, and nothing waits for it at shutdown.
Schedule through ``spawn`` instead; ``drain`` is awaited from the lifespan
so a recording start in progress gets a bounded chance to finish (H2-B).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Coroutine, Any

logger = logging.getLogger(__name__)

_tasks: set[asyncio.Task] = set()


def spawn(coro: Coroutine[Any, Any, Any], *, name: str | None = None) -> asyncio.Task:
    task = asyncio.create_task(coro, name=name)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return task


def pending() -> int:
    return len(_tasks)


async def drain(timeout: float = 5.0) -> None:
    """Wait up to ``timeout`` for tracked tasks, then cancel the rest."""
    if not _tasks:
        return
    live = set(_tasks)
    done, still = await asyncio.wait(live, timeout=timeout)
    for t in still:
        logger.warning("Background task %s did not finish within %.1fs; cancelling", t.get_name(), timeout)
        t.cancel()
    if still:
        await asyncio.gather(*still, return_exceptions=True)
