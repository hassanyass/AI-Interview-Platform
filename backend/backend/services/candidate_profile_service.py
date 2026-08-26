"""
Shared CandidateProfile resolve-or-create logic — Phase 6.

Extracted so Phase 6's new admin-invitation and (future) public-apply /
personalized-redeem endpoints don't each reimplement email-based dedup.
Mirrors the dedup pattern already used in Phase 3's
POST /api/v1/interviews/public/register (backend/backend/api/endpoints/
interviews.py) — that existing endpoint is untouched; this is a shared
extraction for new Phase 6 call sites, not a replacement for it.

Atomicity: this function does NOT commit. It uses a SAVEPOINT
(db.begin_nested()) around the insert attempt so a unique-constraint race
only rolls back to the savepoint, leaving the caller's outer transaction
(and any other work already staged on `db`, e.g. a JobApplication insert
in the same request) uncommitted and intact. The caller is responsible for
committing once, after every step in its own flow has succeeded — see
backend/backend/api/endpoints/invitations.py for the pattern.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError

from backend.models.profile import CandidateProfile


async def get_or_create_candidate_profile(
    db: AsyncSession,
    *,
    email: str,
    full_name: str | None = None,
) -> CandidateProfile:
    """Find a CandidateProfile by email, or create one.

    Does not commit — see module docstring. `full_name` is only used if a
    new profile is created; an existing profile's name is left as-is (the
    caller doesn't necessarily know the candidate's real name yet — e.g.
    an admin creating an invitation from just an email address).
    """
    normalized_email = email.lower()

    result = await db.execute(
        select(CandidateProfile).where(CandidateProfile.email == normalized_email)
    )
    profile = result.scalar_one_or_none()
    if profile:
        return profile

    try:
        async with db.begin_nested():
            profile = CandidateProfile(
                email=normalized_email,
                full_name=full_name or normalized_email,
            )
            db.add(profile)
            await db.flush()
    except IntegrityError:
        # Lost a race against a concurrent creator for the same email.
        result = await db.execute(
            select(CandidateProfile).where(CandidateProfile.email == normalized_email)
        )
        profile = result.scalar_one_or_none()
        if not profile:
            raise

    return profile
