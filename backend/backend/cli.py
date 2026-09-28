"""Operational commands for the backend (H3):

    python -m backend.cli make-admin <email>
    python -m backend.cli finalize-stuck-sessions [--dry-run]
    python -m backend.cli backfill-evaluations [--dry-run]
    python -m backend.cli create-demo-admin <email> <password>
    python -m backend.cli seed-demo-data

Run from the repo root with the venv active (the root `scripts/*.py` files
are thin shims onto these). Each command uses the application's own
engine, settings and services -- no copied logic (the old
backfill script carried its own copy of resolve_criteria_for_job).
Exit code 0 on success, 1 on a handled failure.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone

from sqlalchemy import or_, select, text

from backend.core.config import settings
from backend.core.logging import configure_logging
import backend.db.base  # noqa: F401 -- registers every model with the mapper (profile + interview)
from backend.db.session import AsyncSessionLocal
from backend.models.interview import Evaluation, InterviewSession, Score
from backend.services.evaluations.upsert import resolve_criteria_for_job
from backend.services.sessions.finalization import finalize_live_session

logger = logging.getLogger("backend.cli")


# ── commands ──────────────────────────────────────────────────────────────

async def cmd_make_admin(email: str) -> int:
    """Grant the admin role to an existing Supabase user (auth.users row)."""
    async with AsyncSessionLocal() as db:
        row = (await db.execute(text("SELECT id FROM auth.users WHERE email = :email"), {"email": email})).fetchone()
        if not row:
            print(f"User '{email}' not found in auth.users. Log into the frontend once so Supabase creates the account.")
            return 1
        user_uuid = row[0]
        existing = (await db.execute(text("SELECT 1 FROM users_roles WHERE user_id = :u AND role = 'admin'"), {"u": user_uuid})).fetchone()
        if existing:
            print(f"{email} is already an admin.")
            return 0
        await db.execute(text("INSERT INTO users_roles (id, user_id, role) VALUES (gen_random_uuid(), :u, 'admin')"), {"u": user_uuid})
        await db.commit()
        print(f"{email} ({user_uuid}) is now an admin. Refresh the browser to see /admin.")
        return 0


async def cmd_finalize_stuck_sessions(dry_run: bool) -> int:
    """Force-finalize sessions that are IN_PROGRESS/DISCONNECTED with no live
    agent lease -- the manual counterpart of the idle-disconnect sweep,
    for sessions the sweep cannot reach (IN_PROGRESS with a dead agent)."""
    finalized = skipped = 0
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(InterviewSession).where(
                InterviewSession.status.in_(["IN_PROGRESS", "DISCONNECTED"]),
                or_(InterviewSession.agent_lease_expires_at.is_(None), InterviewSession.agent_lease_expires_at < now),
            )
        )
        sessions = list(result.scalars().all())
        print(f"Found {len(sessions)} stuck session(s) with no active agent lease.")
        for s in sessions:
            print(f"  {s.id}  status={s.status}  role={s.role}")
            if dry_run:
                finalized += 1
                continue
            if await finalize_live_session(db, s, target_status="TERMINATED"):
                finalized += 1
            else:
                skipped += 1
    print(f"Finalized: {finalized}{' (dry run - no writes)' if dry_run else ''}; skipped (already terminal): {skipped}")
    return 0


async def cmd_backfill_evaluations(dry_run: bool) -> int:
    """Copy the legacy final_result.evaluation JSON of COMPLETED sessions into
    the normalized Evaluation/Score rows where no row exists yet."""
    backfilled = had_row = no_data = errored = 0
    async with AsyncSessionLocal() as db:
        sessions = list((await db.execute(select(InterviewSession).where(InterviewSession.status == "COMPLETED"))).scalars().all())
        print(f"Found {len(sessions)} COMPLETED session(s) to check.")
        for s in sessions:
            final_result = s.final_result or {}
            data = final_result.get("evaluation")
            if not data or final_result.get("evaluation_status") != "COMPLETED":
                no_data += 1
                continue
            if (await db.execute(select(Evaluation).where(Evaluation.session_id == s.id))).scalar_one_or_none() is not None:
                had_row += 1
                continue
            print(f"  backfilling {s.id} ({s.role}, {s.level})")
            if dry_run:
                backfilled += 1
                continue
            try:
                evaluation = Evaluation(
                    session_id=s.id,
                    overall_score=data.get("overall_score"),
                    recommendation=data.get("recommendation"),
                    evidence_sufficiency=data.get("evidence_sufficiency"),
                    summary=data.get("summary"),
                    detailed_overview=data.get("detailed_overview"),
                )
                db.add(evaluation)
                await db.flush()
                criterion_scores = data.get("criterion_scores") or []
                if criterion_scores:
                    key_to_id = {c.key: c.id for c in await resolve_criteria_for_job(db, s.job_id)}
                    for cs in criterion_scores:
                        db.add(Score(
                            evaluation_id=evaluation.id,
                            criterion_id=key_to_id.get(cs.get("criterion_key")),
                            criterion_key=cs.get("criterion_key"),
                            score=cs.get("score"),
                            overview=cs.get("overview"),
                            strengths=cs.get("strengths") or [],
                            improvements=cs.get("improvements") or [],
                            evidence_reference=cs.get("evidence_reference"),
                        ))
                await db.commit()
                backfilled += 1
            except Exception as e:  # noqa: BLE001 -- one bad session must not stop the batch; it is reported
                await db.rollback()
                print(f"  ERROR backfilling {s.id}: {e}")
                errored += 1
    print(f"Backfilled: {backfilled}{' (dry run - no writes)' if dry_run else ''}; already had a row: {had_row}; "
          f"no evaluation to copy: {no_data}; errored: {errored}")
    return 1 if errored else 0


async def cmd_create_demo_admin(email: str, password: str) -> int:
    from scripts.create_demo_admin import create_demo_admin  # demo one-off, kept where it is
    await create_demo_admin(email, password)
    return 0


async def cmd_seed_demo_data() -> int:
    from scripts import seed_demo_data  # demo one-off, kept where it is
    await seed_demo_data.seed()
    return 0


# ── entry ──────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m backend.cli", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    a = sub.add_parser("make-admin", help="grant the admin role to an existing Supabase user")
    a.add_argument("email")
    f = sub.add_parser("finalize-stuck-sessions", help="finalize IN_PROGRESS/DISCONNECTED sessions with no live agent lease")
    f.add_argument("--dry-run", action="store_true")
    b = sub.add_parser("backfill-evaluations", help="copy legacy final_result evaluations into Evaluation/Score rows")
    b.add_argument("--dry-run", action="store_true")
    c = sub.add_parser("create-demo-admin", help="(demo) create the shared demo admin account")
    c.add_argument("email")
    c.add_argument("password")
    sub.add_parser("seed-demo-data", help="(demo) seed demo jobs and fabricated results")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging(log_format=settings.log_format, level=settings.LOG_LEVEL, environment=settings.ENVIRONMENT)
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    if args.command == "make-admin":
        coro = cmd_make_admin(args.email)
    elif args.command == "finalize-stuck-sessions":
        coro = cmd_finalize_stuck_sessions(args.dry_run)
    elif args.command == "backfill-evaluations":
        coro = cmd_backfill_evaluations(args.dry_run)
    elif args.command == "create-demo-admin":
        coro = cmd_create_demo_admin(args.email, args.password)
    else:
        coro = cmd_seed_demo_data()
    return asyncio.run(coro)


if __name__ == "__main__":
    sys.exit(main())
