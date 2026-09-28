"""Candidate room tokens and recording start — shared by POST /livekit/token
and the admin test-drive (which used to call the route function with a
synthetic request). Moved from api/endpoints/livekit.py in H2-A2.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core import background
from backend.core.config import settings
from backend.core.errors import AppError, Conflict
from backend.models.interview import InterviewSession, JobApplication
from backend.providers.factory import get_realtime, get_recordings_storage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IssuedRoomToken:
    token: str
    url: str
    room_name: str


async def assert_cv_gate_satisfied(db: AsyncSession, session: InterviewSession) -> None:
    """Background subsection step 2 (ruling Q2, docs/verbal-background-
    subsection-plan.md §11): a B2B session's room token is only issued
    once its JobApplication carries a CV. Checked at START only (status
    CREATED) -- a resume/reconnect of a session that already began is
    never blocked, and a legacy or admin test-drive session (no
    application) is not gated at all. Register/redeem no longer mint a
    room token for the same reason."""
    if session.status == "CREATED" and session.application_id:
        app_result = await db.execute(
            select(JobApplication).where(JobApplication.id == session.application_id)
        )
        application = app_result.scalar_one_or_none()
        if application is not None and application.resume_id is None:
            raise Conflict("CV_REQUIRED: upload your CV before starting the interview.", code="cv_required")


async def issue_candidate_room_token(session: InterviewSession, candidate_id: str) -> IssuedRoomToken:
    """Mint the candidate's join token for this session's room and, once per
    session, schedule the recording to start (never awaited: the room only
    exists after the candidate's browser connects with this very token)."""
    if not all([settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET, settings.LIVEKIT_URL]):
        # Same status as before the extraction (500), typed.
        raise AppError("LiveKit credentials are not configured on the server.", status=500, code="livekit_unconfigured")

    room_name = f"interview-{session.id}"
    token = get_realtime().mint_participant_token(
        room=room_name,
        identity=f"candidate-{candidate_id}",
        name=f"Candidate {candidate_id[:6]}",
        ttl=timedelta(minutes=settings.LIVEKIT_TOKEN_TTL_MINUTES),
    )

    # PR-C: schedule recording-start as a background task, cheap
    # pre-check here so a reconnect/resume doesn't even schedule redundant
    # work. Not the guard -- that is the conditional UPDATE inside
    # start_recording_egress (H5-B). Scheduled, not awaited: see
    # start_recording_egress's own docstring for why this must run AFTER
    # the token has been returned.
    if not session.recording_egress_id and not session.recording_egress_started_at:
        background.spawn(start_recording_egress(str(session.id), room_name), name=f"egress-start-{session.id}")

    return IssuedRoomToken(token=token, url=settings.LIVEKIT_URL, room_name=room_name)


# PR-C manual-test finding (2026-09-01): the room this needs to attach to
# doesn't exist until the CANDIDATE'S OWN BROWSER actually connects with
# the token this same request is issuing -- calling egress-start
# synchronously, before that token was even returned to the client, was a
# guaranteed race (confirmed live: every real attempt failed with
# ServerError(code=not_found, message="requested room does not exist")).
# Retrying for this long comfortably covers real-world token-receipt +
# room.connect() time (normally 1-3s) without meaningfully delaying when
# a recording actually starts.
# Attempts/delay: settings.EGRESS_START_RETRY_ATTEMPTS / EGRESS_START_RETRY_DELAY_SECONDS.


async def start_recording_egress(session_id: str, room_name: str) -> None:
    """PR-C (docs/proctoring-architecture.md): start full audio+video Room
    Composite Egress to R2. Runs as a BackgroundTask -- scheduled by the
    /token endpoint but only actually executed after that response has
    already been sent to the client, which is what makes the retry loop
    below meaningful (see the race explained above; running this inline,
    awaited, before responding, could only ever fail).

    Idempotent, and by a claim rather than a look (H5-B). One conditional
    UPDATE sets recording_egress_started_at only while it is still NULL;
    whoever changes a row owns the start and everyone else returns. The
    old version read recording_egress_id and then acted on what it read,
    so two concurrent /livekit/token calls could both see NULL, both start
    an egress, and leave one of them orphaned -- running, billed, and
    never stopped at finalization because only one id was ever stored.

    Uses a fresh DB session, not the request-scoped one, which is closed by
    the time a background task runs. The claim is committed before the
    provider call, so no transaction is held across it.

    Deliberately never raises: a recording that fails to start is a
    proctoring-evidence gap, not a reason to affect a candidate's
    interview in any way -- same "never block a legitimate interview"
    principle as PR-C's camera-denial handling and PR-D's
    degrade-gracefully requirement.
    """
    from backend.db.session import AsyncSessionLocal

    storage = get_recordings_storage()
    if not storage.configured:
        logger.warning("Recording storage not configured -- skipping recording for session %s", session_id)
        return

    # The claim. `RETURNING` tells us whether this call is the one that
    # changed the row; a second caller updates nothing and stops here.
    async with AsyncSessionLocal() as db:
        claimed = (
            await db.execute(
                update(InterviewSession)
                .where(
                    InterviewSession.id == session_id,
                    InterviewSession.recording_egress_id.is_(None),
                    InterviewSession.recording_egress_started_at.is_(None),
                )
                .values(recording_egress_started_at=datetime.now(timezone.utc))
                .returning(InterviewSession.id)
            )
        ).first()
        await db.commit()
    if not claimed:
        logger.debug("Recording already claimed for session %s; not starting a second one", session_id)
        return

    storage_path = settings.RECORDING_PATH_TEMPLATE.format(session_id=session_id, timestamp=int(time.time()))

    try:
        # The provider owns the "room not created yet" retry loop.
        started = await get_realtime().start_room_recording(
            room=room_name, output_path=storage_path, destination=storage.egress_destination(),
        )

        # Detectable-now case (per explicit scoping): a bad request/
        # credentials/bucket CAN surface as an immediate EGRESS_FAILED/
        # EGRESS_ABORTED status on this response, not only later mid-
        # recording -- handle that one synchronously-visible case here.
        # Confirmed live (2026-09-01) that bad S3 credentials specifically
        # do NOT surface here -- only at stop time, ~15s later, with a
        # real S3 PutObject error -- so this catches malformed-request-
        # shape failures, not credential failures. That gap needs an
        # egress-completion webhook, deliberately deferred to PR-E.
        if started.failed:
            logger.error(
                "Egress start reported immediate failure for session %s: status=%s error=%s",
                session_id, started.status, started.error,
            )
            await _release_egress_claim(session_id)
            return

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(InterviewSession).where(InterviewSession.id == session_id))
            session = result.scalar_one_or_none()
            if session and not session.recording_egress_id:
                session.recording_egress_id = started.egress_id
                session.recording_storage_path = storage_path
                await db.commit()
                logger.info("Recording egress %s started for session %s -> %s", started.egress_id, session_id, storage_path)
    except Exception:  # noqa: BLE001 -- never raises by design: a recording that fails to start must not touch the interview
        logger.exception("Failed to start recording egress for session %s", session_id)
        await _release_egress_claim(session_id)


async def _release_egress_claim(session_id: str) -> None:
    """Hand the claim back when no egress was actually started, so a
    reconnect can try again. Never raises -- this runs on the failure path
    and must not replace one logged failure with another."""
    from backend.db.session import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(InterviewSession)
                .where(InterviewSession.id == session_id, InterviewSession.recording_egress_id.is_(None))
                .values(recording_egress_started_at=None)
            )
            await db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("Could not release the recording claim for session %s", session_id)
