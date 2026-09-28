"""H2-F: the durable task queue's table.

Revision ID: a3f7d05c1e94
Revises: c4d1e8f2a9b7
Create Date: 2026-09-23

Additive only (docs/production-hardening-plan.md, ground rule 5): one new
table, nothing existing is touched. Named `tasks`, not `jobs` -- `jobs` is
the hiring entity (AGENTS.md §1).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a3f7d05c1e94"
down_revision: Union[str, Sequence[str], None] = "c4d1e8f2a9b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="QUEUED"),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("requested_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    # The claim query (oldest QUEUED first), the stale-RUNNING sweep and the
    # depth/age gauges all filter on status and order by created_at.
    op.create_index("ix_tasks_status_created_at", "tasks", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_tasks_status_created_at", table_name="tasks")
    op.drop_table("tasks")
