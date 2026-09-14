"""
One-off cleanup: force-finalize interview sessions that are already stuck
today because of the session-finalization-contract bug (2026-09-01 real-
issue investigation — see docs/CURRENT_DECISIONS.md).

Root cause (fixed going forward by backend/backend/api/endpoints/
internal.py's _finalize_live_session/_ensure_evaluation_placeholder and the
new disconnect_auto_finalize_sweep_loop): ending an interview used to be
three independently-triggered side effects (stop the LiveKit Egress
recording, disconnect the room, write the Evaluation row) with no shared
guarantee. A session could get stuck IN_PROGRESS or DISCONNECTED forever —
no active agent lease, no Evaluation row, and (if it still had a live room)
a recording that never stopped — showing up in the HR dashboard as "not
evaluated yet" with no way to resolve it. The fix above prevents this for
NEW sessions; this script cleans up the backlog that already exists.

Distinct from scripts/backfill_evaluations.py, which only copies an
already-saved final_result.evaluation into the normalized Evaluation/Score
tables for sessions already COMPLETED — it does nothing for a session stuck
at IN_PROGRESS/DISCONNECTED, which is exactly this script's target.

Selects sessions where:
  - status is IN_PROGRESS or DISCONNECTED, AND
  - no agent currently holds the lease (agent_lease_expires_at is NULL or
    already in the past) — i.e. nothing is actively running this session
    right now, so it's safe to finalize without racing a real live agent.

For each: forces status -> TERMINATED, guarantees a (placeholder, if no
real one exists) Evaluation row, stops any recording egress, and best-
effort deletes the LiveKit room. Safe to re-run — every affected session
becomes TERMINATED after the first pass, and _finalize_live_session is a
no-op on an already-terminal session.

Usage:
    python scripts/finalize_stuck_sessions.py            # do it
    python scripts/finalize_stuck_sessions.py --dry-run   # report only
"""
import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.path.insert(0, "./backend")
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, or_

from backend.db.session import engine
from backend.models.interview import InterviewSession
from backend.api.endpoints.internal import _finalize_live_session


async def run(dry_run: bool = False):
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    finalized = 0
    skipped_active = 0

    async with async_session() as db:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)

        result = await db.execute(
            select(InterviewSession).where(
                InterviewSession.status.in_(["IN_PROGRESS", "DISCONNECTED"]),
                or_(
                    InterviewSession.agent_lease_expires_at.is_(None),
                    InterviewSession.agent_lease_expires_at < now,
                ),
            )
        )
        sessions = list(result.scalars().all())
        print(f"Found {len(sessions)} stuck session(s) with no active agent lease.\n")

        for session in sessions:
            print(f"Finalizing session {session.id} (status={session.status}, role={session.role})...")
            if dry_run:
                finalized += 1
                continue
            did_finalize = await _finalize_live_session(db, session, target_status="TERMINATED")
            if did_finalize:
                finalized += 1
            else:
                skipped_active += 1

    print("\n--- Summary ---")
    print(f"Finalized: {finalized}{' (dry run — no writes made)' if dry_run else ''}")
    print(f"Skipped (already terminal by the time we got to it): {skipped_active}")


if __name__ == "__main__":
    asyncio.run(run(dry_run="--dry-run" in sys.argv))
