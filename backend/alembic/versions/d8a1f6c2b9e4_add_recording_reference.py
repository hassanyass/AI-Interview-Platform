"""add_recording_reference

Revision ID: d8a1f6c2b9e4
Revises: a3c7f0e91d2b
Create Date: 2026-09-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd8a1f6c2b9e4'
down_revision: Union[str, Sequence[str], None] = 'a3c7f0e91d2b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('interview_sessions', sa.Column('recording_egress_id', sa.String(), nullable=True))
    op.add_column('interview_sessions', sa.Column('recording_storage_path', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('interview_sessions', 'recording_storage_path')
    op.drop_column('interview_sessions', 'recording_egress_id')
