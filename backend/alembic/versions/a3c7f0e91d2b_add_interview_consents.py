"""add_interview_consents

Revision ID: a3c7f0e91d2b
Revises: f4f1cb53b84c
Create Date: 2026-09-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a3c7f0e91d2b'
down_revision: Union[str, Sequence[str], None] = 'f4f1cb53b84c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('interview_consents',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('session_id', sa.UUID(), nullable=False),
    sa.Column('disclosure_language', sa.String(), nullable=False),
    sa.Column('disclosure_text', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['session_id'], ['interview_sessions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('session_id', name='uq_consent_session')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('interview_consents')
