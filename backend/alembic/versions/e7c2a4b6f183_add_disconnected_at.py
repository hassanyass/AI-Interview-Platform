"""add_disconnected_at

Revision ID: e7c2a4b6f183
Revises: d8a1f6c2b9e4
Create Date: 2026-09-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e7c2a4b6f183'
down_revision: Union[str, Sequence[str], None] = 'd8a1f6c2b9e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Real-issue investigation (2026-09-01, docs/CURRENT_DECISIONS.md /
    "Session finalization contract"): the idle-disconnect auto-finalize
    sweep needs to know precisely WHEN a session became DISCONNECTED, not
    just whether its agent lease has lapsed (agent_lease_expires_at is a
    10-minute rolling lease renewed every 5 minutes -- reusing its expiry
    as a disconnect timestamp would be an imprecise, undocumented
    heuristic, and it's also NULL for a session no agent has ever claimed
    yet). A dedicated nullable timestamp, set only on the DISCONNECTED
    transition and cleared on resume, is the honest signal.
    """
    op.add_column('interview_sessions', sa.Column('disconnected_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('interview_sessions', 'disconnected_at')
