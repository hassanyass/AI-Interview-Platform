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
    livekit_token: str
    livekit_url: str
