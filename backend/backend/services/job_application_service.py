"""
Shared JobApplication find-or-create logic — Phase 6, Sub-phase 6A.

Both Flow A (personalized invitation, 6B) and Flow B (public link, 6C) are
required to resolve/create a JobApplication the same way — this is that one
shared implementation. Do not duplicate this logic in 6B or 6C's endpoints;
import and call this function.

Atomicity: this function does NOT commit — see
backend/backend/services/candidate_profile_service.py's module docstring
for the full rationale (SAVEPOINT-scoped insert, caller commits once).
"""
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError

from backend.models.interview import JobApplication


async def get_or_create_job_application(
    db: AsyncSession,
    *,
    job_id: UUID,
    candidate_profile_id: UUID,
    resume_id: UUID | None = None,
) -> JobApplication:
    """Find a JobApplication by (job_id, candidate_profile_id), or create one.

    Relies on the uq_job_application_job_candidate DB constraint (migration
    9ea563b79a51) to make the create-on-race path safe — does not rely on
    check-then-create alone. Does not commit — see module docstring.
    """
    result = await db.execute(
        select(JobApplication).where(
            JobApplication.job_id == job_id,
            JobApplication.candidate_profile_id == candidate_profile_id,
        )
    )
    application = result.scalar_one_or_none()
    if application:
        return application

    try:
        async with db.begin_nested():
            application = JobApplication(
                job_id=job_id,
                candidate_profile_id=candidate_profile_id,
                resume_id=resume_id,
            )
            db.add(application)
            await db.flush()
    except IntegrityError:
        # Lost a race against a concurrent creator for the same pair.
        result = await db.execute(
            select(JobApplication).where(
                JobApplication.job_id == job_id,
                JobApplication.candidate_profile_id == candidate_profile_id,
            )
        )
        application = result.scalar_one_or_none()
        if not application:
            raise

    return application
