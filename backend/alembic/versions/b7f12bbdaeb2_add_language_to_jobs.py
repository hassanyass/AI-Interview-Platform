"""add_language_to_jobs

Revision ID: b7f12bbdaeb2
Revises: 9ea563b79a51
Create Date: 2026-08-24 11:46:49.204218

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7f12bbdaeb2'
down_revision: Union[str, Sequence[str], None] = '9ea563b79a51'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'jobs',
        sa.Column('language', sa.String(), nullable=False, server_default='en'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('jobs', 'language')
