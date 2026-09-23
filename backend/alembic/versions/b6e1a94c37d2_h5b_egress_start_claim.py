"""H5-B: a claim column so a recording can only be started once.

Revision ID: b6e1a94c37d2
Revises: a3f7d05c1e94
Create Date: 2026-09-23

Additive only (docs/production-hardening-plan.md, ground rule 5): one
nullable column. `recording_egress_id` was doing double duty as both "the
egress we started" and "have we started one", which made the guard
check-then-act -- two concurrent POST /livekit/token calls could each see
NULL and each start a recording, leaving one orphaned and never stopped.
The start is now claimed with a conditional UPDATE on this column.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b6e1a94c37d2"
down_revision: Union[str, Sequence[str], None] = "a3f7d05c1e94"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "interview_sessions",
        sa.Column("recording_egress_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Sessions that already have an egress are backfilled so the claim and
    # the id never disagree; a NULL id stays unclaimed.
    op.execute(
        "UPDATE interview_sessions "
        "SET recording_egress_started_at = COALESCE(started_at, created_at) "
        "WHERE recording_egress_id IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("interview_sessions", "recording_egress_started_at")
