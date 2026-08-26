"""Public (no-auth / candidate-JWT) schemas for Phase 6, Sub-phase 6B."""
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from uuid import UUID


class InvitationPublicContext(BaseModel):
    """What a candidate sees on the invite landing page — deliberately not
    the full admin JobResponse shape, to avoid leaking internal fields."""
    job_title: str
    job_description: Optional[str] = None
    seniority: Optional[str] = None
    candidate_instructions: Optional[str] = None
    duration_minutes: int
    invitation_status: str
    candidate_email: str


class RedeemedSessionInfo(BaseModel):
    id: UUID
    job_id: Optional[UUID] = None
    definition_id: Optional[UUID] = None
    status: str
    created_at: Optional[datetime] = None


class RedeemResponse(BaseModel):
    session: RedeemedSessionInfo
    livekit_token: str
    livekit_url: str
