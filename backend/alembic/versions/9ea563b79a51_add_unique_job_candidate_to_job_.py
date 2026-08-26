"""add_unique_job_candidate_to_job_applications

Revision ID: 9ea563b79a51
Revises: 8e55ee7764a7
Create Date: 2026-08-24 11:13:14.472675

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9ea563b79a51'
down_revision: Union[str, Sequence[str], None] = '8e55ee7764a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_unique_constraint(
        "uq_job_application_job_candidate",
        "job_applications",
        ["job_id", "candidate_profile_id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "uq_job_application_job_candidate",
        "job_applications",
        type_="unique",
    )
