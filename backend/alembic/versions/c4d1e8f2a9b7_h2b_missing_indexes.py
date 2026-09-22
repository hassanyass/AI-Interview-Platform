"""H2-B: indexes on the foreign keys and filters the app queries by.

Revision ID: c4d1e8f2a9b7
Revises: b7e2c4d9a1f3
Create Date: 2026-09-22

Additive only (docs/production-hardening-plan.md, ground rule 5). Every
index here backs a real query: session lookups by job / candidate /
application / definition, the idle-disconnect sweep's
(status, disconnected_at) filter, the latest-checkpoint read per result
page, question loading per section, and the per-request admin role lookup
on users_roles. users_roles.user_id also becomes UNIQUE: the live table
was checked for duplicates first (2026-09-22: 260 rows, 0 duplicates;
plan decision U3) -- the lookup uses scalar_one_or_none(), which raises
on a second row.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "c4d1e8f2a9b7"
down_revision: Union[str, Sequence[str], None] = "b7e2c4d9a1f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


INDEXES = [
    # (name, table, columns)
    ("ix_interview_sessions_job_id", "interview_sessions", ["job_id"]),
    ("ix_interview_sessions_candidate_profile_id", "interview_sessions", ["candidate_profile_id"]),
    ("ix_interview_sessions_application_id", "interview_sessions", ["application_id"]),
    ("ix_interview_sessions_definition_id", "interview_sessions", ["definition_id"]),
    ("ix_interview_sessions_status_disconnected_at", "interview_sessions", ["status", "disconnected_at"]),
    ("ix_interview_checkpoints_session_created", "interview_checkpoints", ["session_id", "created_at"]),
    ("ix_interview_questions_section_id", "interview_questions", ["section_id"]),
    ("ix_job_applications_candidate_profile_id", "job_applications", ["candidate_profile_id"]),
    ("ix_interview_invitations_application_id", "interview_invitations", ["application_id"]),
    ("ix_resumes_profile_id", "resumes", ["profile_id"]),
    ("ix_scores_evaluation_id", "scores", ["evaluation_id"]),
    ("ix_scores_criterion_id", "scores", ["criterion_id"]),
]


def upgrade() -> None:
    for name, table, columns in INDEXES:
        op.create_index(name, table, columns, unique=False, if_not_exists=True)
    op.create_index("uq_users_roles_user_id", "users_roles", ["user_id"], unique=True, if_not_exists=True)


def downgrade() -> None:
    op.drop_index("uq_users_roles_user_id", table_name="users_roles", if_exists=True)
    for name, table, _columns in reversed(INDEXES):
        op.drop_index(name, table_name=table, if_exists=True)
