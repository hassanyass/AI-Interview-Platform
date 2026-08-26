"""Add config JSONB to InterviewQuestion (Phase 9A)

Revision ID: c9a1f0e2d3b4
Revises: b7f12bbdaeb2
Create Date: 2026-08-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c9a1f0e2d3b4'
down_revision: Union[str, Sequence[str], None] = 'b7f12bbdaeb2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add nullable config JSONB column to interview_questions."""
    op.add_column('interview_questions', sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    """Remove config column from interview_questions."""
    op.drop_column('interview_questions', 'config')
