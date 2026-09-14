"""Add inferred professional title to candidate profiles."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b7d6e0f1a2c3"
down_revision: Union[str, Sequence[str], None] = "56d311f765da"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("candidate_profiles", sa.Column("professional_title", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("candidate_profiles", "professional_title")
