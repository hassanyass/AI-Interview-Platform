import asyncio
import logging
import time
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from livekit import api

from backend.api.deps import get_db, current_user_dependency
from backend.models.interview import InterviewSession
from backend.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

class TokenRequest(BaseModel):
    session_id: str

class TokenResponse(BaseModel):
    token: str
    url: str

# PR-C manual-test finding (2026-09-01): the room this needs to attach to
# doesn't exist until the CANDIDATE'S OWN BROWSER actually connects with
# the token this same request is issuing -- calling egress-start
# synchronously, before that token was even returned to the client, was a
# guaranteed race (confirmed live: every real attempt failed with
# ServerError(code=not_found, message="requested room does not exist")).
# Retrying for this long comfortably covers real-world token-receipt +
# room.connect() time (normally 1-3s) without meaningfully delaying when
# a recording actually starts.
_EGRESS_START_RETRY_ATTEMPTS = 10
_EGRESS_START_RETRY_DELAY_SECONDS = 1.0


async def _start_recording_egress(session_id: str, room_name: str) -> None:
    """PR-C (docs/proctoring-architecture.md): start full audio+video Room
    Composite Egress to R2. Runs as a BackgroundTask -- scheduled by the
    /token endpoint but only actually executed after that response has
    already been sent to the client, which is what makes the retry loop
    below meaningful (see the race explained above; running this inline,
    awaited, before responding, could only ever fail).

    Idempotent -- re-checks recording_egress_id itself (via a fresh DB
    session, not the request-scoped one, which is closed by the time a
    background task runs) so a reconnect/resume re-requesting a token
    can't start a second recording.

    Deliberately never raises: a recording that fails to start is a
    proctoring-evidence gap, not a reason to affect a candidate's
    interview in any way -- same "never block a legitimate interview"
    principle as PR-C's camera-denial handling and PR-D's
    degrade-gracefully requirement.
    """
    from backend.db.session import AsyncSessionLocal

    if not all([settings.R2_ACCOUNT_ID, settings.R2_ACCESS_KEY_ID, settings.R2_SECRET_ACCESS_KEY,
                settings.R2_BUCKET_NAME, settings.R2_ENDPOINT]):
        logger.warning("R2 storage not configured -- skipping recording for session %s", session_id)
        return

    storage_path = f"interviews/{session_id}/{int(time.time())}.mp4"

    lkapi = api.LiveKitAPI(url=settings.LIVEKIT_URL, api_key=settings.LIVEKIT_API_KEY, api_secret=settings.LIVEKIT_API_SECRET)
    try:
        req = api.RoomCompositeEgressRequest(
            room_name=room_name,
            layout="speaker",
            file_outputs=[
                api.EncodedFileOutput(
                    file_type=api.EncodedFileType.MP4,
                    filepath=storage_path,
                    s3=api.S3Upload(
                        access_key=settings.R2_ACCESS_KEY_ID,
                        secret=settings.R2_SECRET_ACCESS_KEY,
                        bucket=settings.R2_BUCKET_NAME,
                        region="auto",
                        endpoint=settings.R2_ENDPOINT,
                        force_path_style=True,
                    ),
                )
            ],
        )

        info = None
        for attempt in range(1, _EGRESS_START_RETRY_ATTEMPTS + 1):
            try:
                info = await lkapi.egress.start_room_composite_egress(req)
                break
            except api.ServerError as e:
                if e.code != "not_found" or attempt == _EGRESS_START_RETRY_ATTEMPTS:
                    raise
                logger.info(
                    "Egress start attempt %d/%d: room %s not ready yet, retrying",
                    attempt, _EGRESS_START_RETRY_ATTEMPTS, room_name,
                )
                await asyncio.sleep(_EGRESS_START_RETRY_DELAY_SECONDS)

        # Detectable-now case (per explicit scoping): a bad request/
        # credentials/bucket CAN surface as an immediate EGRESS_FAILED/
        # EGRESS_ABORTED status on this response, not only later mid-
        # recording -- handle that one synchronously-visible case here.
        # Confirmed live (2026-09-01) that bad S3 credentials specifically
        # do NOT surface here -- only at stop time, ~15s later, with a
        # real S3 PutObject error -- so this catches malformed-request-
        # shape failures, not credential failures. That gap needs an
        # egress-completion webhook, deliberately deferred to PR-E.
        if info.status in (api.EgressStatus.EGRESS_FAILED, api.EgressStatus.EGRESS_ABORTED):
            logger.error(
                "Egress start reported immediate failure for session %s: status=%s error=%s",
                session_id, api.EgressStatus.Name(info.status), info.error,
            )
            return

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(InterviewSession).where(InterviewSession.id == session_id))
            session = result.scalar_one_or_none()
            if session and not session.recording_egress_id:
                session.recording_egress_id = info.egress_id
                session.recording_storage_path = storage_path
                await db.commit()
                logger.info("Recording egress %s started for session %s -> %s", info.egress_id, session_id, storage_path)
    except Exception:
        logger.exception("Failed to start recording egress for session %s", session_id)
    finally:
        await lkapi.aclose()


@router.post("/token", response_model=TokenResponse)
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

    # PR-C: schedule recording-start as a background task, cheap
    # pre-check here so a reconnect/resume doesn't even schedule redundant
    # work -- the background task itself re-checks with a fresh row
    # regardless, so this is an optimization, not the real idempotency
    # guard. Scheduled, not awaited: see _start_recording_egress's own
    # docstring for why this must run AFTER this response is sent.
    if not session.recording_egress_id:
        asyncio.create_task(_start_recording_egress(str(session.id), room_name))

    return TokenResponse(
        token=token.to_jwt(),
        url=url
    )
