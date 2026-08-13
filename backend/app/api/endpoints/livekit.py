import os
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from livekit import api

from app.api.deps import get_db, get_current_user
from app.models.interview import InterviewSession

router = APIRouter()

class TokenRequest(BaseModel):
    session_id: str
    
class TokenResponse(BaseModel):
    token: str
    url: str

@router.post("/token", response_model=TokenResponse)
async def generate_livekit_token(
    request: TokenRequest,
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    try:
        from uuid import UUID
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
        
    from app.core.config import settings
    api_key = settings.LIVEKIT_API_KEY
    api_secret = settings.LIVEKIT_API_SECRET
    url = settings.LIVEKIT_URL
    
    if not all([api_key, api_secret, url]):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="LiveKit credentials are not configured on the server."
        )
        
    # Generate room name
    room_name = f"interview-{request.session_id}"
    participant_name = f"Candidate {current_user[:6]}"
    participant_identity = f"candidate-{current_user}"
    
    token = api.AccessToken(api_key, api_secret)
    token.with_identity(participant_identity)
    token.with_name(participant_name)
    token.with_grants(api.VideoGrants(
        room_join=True,
        room=room_name,
    ))
    
    return TokenResponse(
        token=token.to_jwt(),
        url=url
    )
