"""What must be true of an InterviewDefinition before its Job goes live.
One implementation for POST /admin/jobs/{id}/publish and PATCH
/admin/jobs/{id}/status -> PUBLISHED (they carried identical copies until
H2-A2). Messages are unchanged: tests/legacy/test_phase5_publish_validation.py
asserts on them.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.core.errors import Conflict
from backend.models.interview import InterviewSection


def assert_sections_publishable(sections: list[InterviewSection]) -> None:
    """Content-completeness check, not an editability rule (that's
    _require_draft's job in the other direction). A section that exists
    with zero questions would otherwise publish silently and reach a
    candidate with nothing to answer. Deliberately narrow: does NOT
    require at least one section to exist at all."""
    empty_sections = [s.section_type for s in sections if not s.questions]
    if empty_sections:
        raise Conflict(
            f"Cannot publish: section(s) with no questions: {', '.join(empty_sections)}",
            code="sections_without_questions",
        )

    # WR-A: time_budget_minutes is optional while a section is being built
    # (mirrors questions being addable after section creation) but required
    # once it's actually going live — a published section with no time
    # budget would derive a 0-minute contribution to duration_minutes and
    # leave WR-C's waiting-room/clock logic with nothing to seed from.
    unbudgeted_sections = [
        s.section_type for s in sections
        if not (s.config or {}).get("time_budget_minutes")
    ]
    if unbudgeted_sections:
        raise Conflict(
            f"Cannot publish: section(s) with no time budget set: {', '.join(unbudgeted_sections)}",
            code="sections_without_time_budget",
        )


async def assert_definition_publishable(db: AsyncSession, definition_id: UUID) -> None:
    result = await db.execute(
        select(InterviewSection)
        .options(selectinload(InterviewSection.questions))
        .where(InterviewSection.definition_id == definition_id)
    )
    assert_sections_publishable(list(result.scalars().all()))
