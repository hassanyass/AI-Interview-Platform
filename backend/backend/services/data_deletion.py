"""Deleting a person's data, all of it (H5-C).

The gap this closes: `ResumeService.delete_object` has existed since the
CV feature shipped and had **no callers**, so no path in the system ever
removed a CV from object storage. Deleting an interview session removes
its rows and its recording, and deliberately stops there -- a profile is
shared across every job the same person applied to, and clearing one job's
dashboard must not erase them everywhere. Which left nothing at all that
could honour "delete this candidate's data": the row, their CVs and their
recordings simply stayed.

So deletion has two scopes, and they are different on purpose:

- `delete_session_artifacts` -- one interview. Its recording goes; the
  person's CV does not, because the CV belongs to their application and
  may still back another session.
- `delete_candidate` -- the person. Every recording of every session they
  had, every CV object, then the profile row, which cascades to the
  sessions, applications, invitations and resume rows in the database.

Both are best-effort about object storage and exact about the database: a
storage failure is reported, never raised, because refusing to delete the
row would leave an administrator unable to remove the person at all. What
could not be deleted is named in the returned report so it can be finished
by hand -- and, for an audit trail, recorded.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.interview import InterviewSession
from backend.models.profile import CandidateProfile, Resume
from backend.providers.factory import get_recordings_storage, get_resumes_storage

logger = logging.getLogger(__name__)


@dataclass
class DeletionReport:
    """What went, and what refused to."""

    recordings_deleted: int = 0
    resumes_deleted: int = 0
    sessions_removed: int = 0
    orphaned: list[str] = field(default_factory=list)
    """Storage keys that survived a failed delete. Each one is an object
    holding personal data that the database no longer points at."""

    @property
    def complete(self) -> bool:
        return not self.orphaned

    def as_details(self) -> dict:
        return {
            "recordings_deleted": self.recordings_deleted,
            "resumes_deleted": self.resumes_deleted,
            "sessions_removed": self.sessions_removed,
            "orphaned_objects": self.orphaned,
        }


async def _delete_object(storage, key: str | None, report: DeletionReport, kind: str) -> bool:
    if not key:
        return True
    if not storage.configured:
        # Not configured in this environment: there is no object to delete,
        # which is a real and tolerated state rather than a failure.
        return True
    try:
        await storage.delete(key)
        return True
    except Exception:  # noqa: BLE001 -- best-effort by contract; the caller's DB delete must still proceed
        logger.exception("Failed to delete %s object %s", kind, key)
        report.orphaned.append(key)
        return False


async def delete_session_artifacts(session: InterviewSession, report: DeletionReport | None = None) -> DeletionReport:
    """The recording of one interview. Call before the row is deleted --
    afterwards the path is gone."""
    report = report or DeletionReport()
    if await _delete_object(get_recordings_storage(), session.recording_storage_path, report, "recording"):
        if session.recording_storage_path:
            report.recordings_deleted += 1
    return report


async def delete_candidate(db: AsyncSession, profile_id: UUID) -> tuple[CandidateProfile | None, DeletionReport]:
    """Remove a person and everything of theirs, objects included.

    Returns (profile, report) with the profile already deleted from the
    session but not committed -- the caller commits, so the audit row and
    the deletion land together.
    """
    report = DeletionReport()
    profile = (
        await db.execute(select(CandidateProfile).where(CandidateProfile.id == profile_id))
    ).scalar_one_or_none()
    if profile is None:
        return None, report

    sessions = list(
        (await db.execute(
            select(InterviewSession).where(InterviewSession.candidate_profile_id == profile_id)
        )).scalars().all()
    )
    resumes = list(
        (await db.execute(select(Resume).where(Resume.profile_id == profile_id))).scalars().all()
    )

    # Objects first, while the rows that name them still exist. A crash
    # between the two leaves rows pointing at deleted objects, which is
    # recoverable; the other order leaves objects nothing points at, which
    # is the failure that matters when someone asks for their data to be
    # erased.
    recordings_storage = get_recordings_storage()
    for session in sessions:
        if session.recording_storage_path and await _delete_object(
            recordings_storage, session.recording_storage_path, report, "recording"
        ):
            report.recordings_deleted += 1

    resumes_storage = get_resumes_storage()
    for resume in resumes:
        if await _delete_object(resumes_storage, resume.storage_path, report, "resume"):
            report.resumes_deleted += 1

    report.sessions_removed = len(sessions)
    await db.delete(profile)      # cascades: sessions, applications, invitations, resumes
    return profile, report
