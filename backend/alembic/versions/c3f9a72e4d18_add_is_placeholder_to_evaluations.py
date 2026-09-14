"""Evaluation regeneration: evaluations.is_placeholder

Revision ID: c3f9a72e4d18
Revises: b6d2e9a04c71
Create Date: 2026-09-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c3f9a72e4d18'
down_revision: Union[str, Sequence[str], None] = 'b6d2e9a04c71'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'evaluations',
        sa.Column('is_placeholder', sa.Boolean(), nullable=False, server_default='false'),
    )
    # One-time backfill for existing rows using the known placeholder
    # sentinel text (_ensure_evaluation_placeholder's exact summary) --
    # the boolean is the source of truth for every row created from here
    # on, but this corrects the 149 real placeholder rows that already
    # existed before this column did (see CURRENT_DECISIONS.md's
    # "Evaluation regeneration for placeholder sessions" entry for the
    # real counts this was scoped against).
    op.execute(
        "UPDATE evaluations SET is_placeholder = true "
        "WHERE summary = 'Session ended before a full evaluation could be generated.'"
    )


def downgrade() -> None:
    op.drop_column('evaluations', 'is_placeholder')
