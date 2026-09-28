"""Public (no-auth) schemas for Phase 6, Sub-phase 6C — Flow B, public link."""
from pydantic import BaseModel, EmailStr
from typing import Optional
from uuid import UUID

from backend.schemas.public_invitations import RedeemedSessionInfo


class PublicApplyContext(BaseModel):
    """What a candidate sees on the public-apply landing page."""
    job_title: str
    job_description: Optional[str] = None
    seniority: Optional[str] = None
    candidate_instructions: Optional[str] = None
    duration_minutes: int


class PublicRegisterRequest(BaseModel):
    name: str
    email: EmailStr
    resume_id: Optional[UUID] = None


class PublicRegisterResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    session: RedeemedSessionInfo
    # Background subsection step 2: no longer minted here (a room token is
    # only issued once the application has a CV -- see livekit.py). Kept
    # optional so the admin test-drive, which has no CV gate, can still
    # return one through this same shape.
    livekit_token: Optional[str] = None
    livekit_url: Optional[str] = None
