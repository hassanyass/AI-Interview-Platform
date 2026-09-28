import logging
from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from backend.core.config import settings
from backend.db.session import get_db
from backend.core.logging import bind_session
from backend.core.security import get_current_user_token_data
from backend.models.interview import InterviewSession
from backend.models.profile import CandidateProfile, Resume, UserRole
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError
import uuid
from uuid import UUID

logger = logging.getLogger(__name__)


async def _profile_holds_someone_elses_work(db: AsyncSession, profile_id) -> bool:
    """Whether this profile has anything that adopting it would hand over:
    an interview session or an uploaded CV. A profile HR pre-created for an
    invitation, or one that only exists because an address was recorded,
    holds nothing yet."""
    session_exists = (
        await db.execute(
            select(InterviewSession.id).where(InterviewSession.candidate_profile_id == profile_id).limit(1)
        )
    ).first()
    if session_exists:
        return True
    resume_exists = (
        await db.execute(select(Resume.id).where(Resume.profile_id == profile_id).limit(1))
    ).first()
    return bool(resume_exists)


async def _may_link_by_email(db: AsyncSession, token_data: dict, profile: CandidateProfile) -> bool:
    """Whether this identity may adopt an existing profile that merely
    shares its email address (H5-A).

    The risk is not the link, it is what the link hands over: another
    person's interview sessions, CV and results. So the rule follows the
    data rather than the address.

    - A profile with **no sessions and no CV** is adopted as before. This
      is the normal path and the one the product depends on: HR creates an
      invitation, which creates a profile for that address, and the
      candidate then signs in to redeem it. (That route independently
      requires the JWT's email to equal the invitation's -- see
      public_invitations.py.)
    - A profile that **already holds interview work** is adopted only when
      the token proves the address was verified. Otherwise signing up with
      someone's address would inherit their completed interviews.

    IDENTITY_AUTOLINK overrides the middle ground: `always` restores the
    pre-H5-A behaviour (logged), `never` refuses every adoption.
    `email_verified` is None when the token says nothing either way; that
    is treated as unproven, never as proven.
    """
    policy = settings.IDENTITY_AUTOLINK
    if policy == "never":
        return False
    if policy == "always":
        return True
    if token_data.get("email_verified") is True:
        return True
    return not await _profile_holds_someone_elses_work(db, profile.id)

# Re-export for convenience
db_dependency = Depends(get_db)

async def get_current_candidate_profile_id(
    token_data: dict = Depends(get_current_user_token_data),
    db: AsyncSession = Depends(get_db)
) -> str:
    sub = token_data["sub"]
    token_type = token_data["type"]
    email = token_data.get("email")

    if token_type == "guest":
        return sub
    
    # Supabase token
    try:
        supabase_id = uuid.UUID(sub)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid Supabase subject UUID")

    # 1. Lookup by supabase_user_id
    stmt = select(CandidateProfile).where(CandidateProfile.supabase_user_id == supabase_id)
    result = await db.execute(stmt)
    profile = result.scalar_one_or_none()
    if profile:
        return str(profile.id)

    # 2. An existing profile with the same address -- typically a candidate
    #    who applied through a public link as a guest and is now signing in.
    #    Linking gives this identity that profile's sessions and results, so
    #    it happens only under the configured policy and is always logged.
    if email:
        stmt = select(CandidateProfile).where(CandidateProfile.email == email)
        result = await db.execute(stmt)
        profile = result.scalar_one_or_none()
        if profile:
            if not await _may_link_by_email(db, token_data, profile):
                logger.warning(
                    "Refused to link Supabase identity %s to existing profile %s by email: "
                    "policy=%s email_verified=%s",
                    supabase_id, profile.id, settings.IDENTITY_AUTOLINK,
                    token_data.get("email_verified"),
                    extra={"event": "identity_link_refused", "policy": settings.IDENTITY_AUTOLINK,
                           "email_verified": token_data.get("email_verified")},
                )
                raise HTTPException(
                    status_code=403,
                    detail=(
                        "This email address already has interview history. Confirm the address on "
                        "your account, then sign in again, or contact the hiring team."
                    ),
                )
            profile_id = str(profile.id)
            profile.supabase_user_id = supabase_id
            await db.commit()
            logger.info(
                "Linked Supabase identity %s to existing profile %s by verified email",
                supabase_id, profile_id,
                extra={"event": "identity_linked", "policy": settings.IDENTITY_AUTOLINK},
            )
            return profile_id
    
    # 3. Create (Handling check-then-act race)
    if not email:
        raise HTTPException(status_code=401, detail="Supabase token lacks email for profile resolution")
        
    try:
        new_profile = CandidateProfile(
            supabase_user_id=supabase_id,
            email=email,
            full_name="Candidate"
        )
        db.add(new_profile)
        await db.commit()
        await db.refresh(new_profile)
        return str(new_profile.id)
    except IntegrityError:
        await db.rollback()
        # Someone inserted a profile for this address between the lookup
        # above and this insert. Re-read it -- and apply the same linking
        # rule, because the outcome is identical to branch 2: this identity
        # would adopt a profile it did not create.
        stmt = select(CandidateProfile).where(CandidateProfile.email == email)
        result = await db.execute(stmt)
        profile = result.scalar_one_or_none()
        if profile:
            if not await _may_link_by_email(db, token_data, profile):
                logger.warning(
                    "Refused to link Supabase identity %s to profile %s created concurrently: policy=%s",
                    supabase_id, profile.id, settings.IDENTITY_AUTOLINK,
                    extra={"event": "identity_link_refused", "policy": settings.IDENTITY_AUTOLINK},
                )
                raise HTTPException(
                    status_code=403,
                    detail=(
                        "This email address already has interview history. Confirm the address on "
                        "your account, then sign in again, or contact the hiring team."
                    ),
                )
            profile_id = str(profile.id)
            profile.supabase_user_id = supabase_id
            await db.commit()
            logger.info(
                "Linked Supabase identity %s to profile %s created concurrently",
                supabase_id, profile_id, extra={"event": "identity_linked"},
            )
            return profile_id
        raise HTTPException(status_code=500, detail="Failed to resolve profile identity")

current_user_dependency = Depends(get_current_candidate_profile_id)

async def get_current_admin(
    token_data: dict = Depends(get_current_user_token_data),
    db: AsyncSession = Depends(get_db)
) -> str:
    sub = token_data["sub"]
    try:
        user_uuid = uuid.UUID(sub)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid admin subject UUID")
        
    stmt = select(UserRole).where(UserRole.user_id == user_uuid)
    result = await db.execute(stmt)
    user_role = result.scalar_one_or_none()
    if not user_role or user_role.role != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return sub


async def bind_session_id_from_path(session_id: UUID | None = None):
    """H3: routes with a {session_id} path param get it on every log line
    (core/logging.py). Used as a router-level dependency; routes without the
    param simply bind nothing."""
    if session_id is not None:
        bind_session(session_id)
