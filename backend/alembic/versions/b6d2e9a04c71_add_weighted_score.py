"""Scoring mechanism upgrade: evaluations.weighted_score

Revision ID: b6d2e9a04c71
Revises: a4f7c1e83b56
Create Date: 2026-09-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b6d2e9a04c71'
down_revision: Union[str, Sequence[str], None] = 'a4f7c1e83b56'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('evaluations', sa.Column('weighted_score', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('evaluations', 'weighted_score')
