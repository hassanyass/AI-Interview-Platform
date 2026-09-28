import logging
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.api.deps import get_db, current_user_dependency
from backend.core.config import settings
from backend.core.ratelimit import rate_limit
from backend.models.interview import InterviewSession
from backend.services.sessions.room_token import assert_cv_gate_satisfied, issue_candidate_room_token

logger = logging.getLogger(__name__)

router = APIRouter()

class TokenRequest(BaseModel):
    session_id: str

class TokenResponse(BaseModel):
    token: str
    url: str

@router.post(
    "/token",
    response_model=TokenResponse,
    # H5-B: keyed by subject. Each call can schedule a recording, so
    # this is bounded -- but a reconnecting candidate legitimately asks
    # again, hence the generous default.
    dependencies=[Depends(rate_limit("room_token", lambda: settings.RATE_LIMIT_ROOM_TOKEN, by_subject=True))],
)
async def generate_livekit_token(
    request: TokenRequest,
    db: AsyncSession = Depends(get_db),
    current_user: str = current_user_dependency
):
    try:
        user_uuid = UUID(current_user)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid User ID format")

    # Verify interview ownership
    stmt = select(InterviewSession).where(
        (InterviewSession.id == request.session_id) &
        (InterviewSession.candidate_profile_id == user_uuid)
    )
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview session not found or you do not have access."
        )

    # CV gate, LiveKit config check, token minting and recording start live
    # in services/sessions/room_token.py (H2-A2); the ownership check above
    # is this route's own concern.
    await assert_cv_gate_satisfied(db, session)
    issued = await issue_candidate_room_token(session, current_user)
    return TokenResponse(token=issued.token, url=issued.url)
