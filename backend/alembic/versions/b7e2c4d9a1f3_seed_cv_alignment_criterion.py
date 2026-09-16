"""Verbal Background subsection: seed the cv_alignment TEMPLATE criterion

docs/verbal-background-subsection-plan.md §2 "Evaluation", §9, ruling Q4.
Additive only: one new curated TEMPLATE assessment_criteria row, the same
pattern as the existing seeds (d1f4a8c93b21, a4f7c1e83b56). kind
"content" -- it judges what was said against the CV, not a trait.
Weight 5 (equal weighting) like every other seed; HR toggles/weights it
per job in the existing CriteriaEditor, and Evaluation.weighted_score
picks it up with no mechanism change.

NOTE: TEMPLATE rows apply to every job that has no job-scoped criteria
(internal.py's _resolve_criteria_for_job), so this row is visible to all
environments sharing the database as soon as it is applied.

Revision ID: b7e2c4d9a1f3
Revises: c3f9a72e4d18
Create Date: 2026-09-16

"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b7e2c4d9a1f3'
down_revision: Union[str, Sequence[str], None] = 'c3f9a72e4d18'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CV_ALIGNMENT_KEY = "cv_alignment"
CV_ALIGNMENT_LABEL = "CV & Experience Alignment"
CV_ALIGNMENT_GUIDANCE = (
    "Does the candidate's spoken account of their experience substantiate and align with "
    "their CV, and is that experience relevant to the role? Flag gaps between what the CV "
    "claims and what the candidate could actually discuss."
)


def upgrade() -> None:
    assessment_criteria_table = sa.table(
        'assessment_criteria',
        sa.column('id', sa.UUID()),
        sa.column('job_id', sa.UUID()),
        sa.column('section_id', sa.UUID()),
        sa.column('key', sa.String()),
        sa.column('label', sa.String()),
        sa.column('kind', sa.String()),
        sa.column('enabled', sa.Boolean()),
        sa.column('guidance_text', sa.Text()),
        sa.column('source', sa.String()),
        sa.column('weight', sa.Integer()),
    )
    op.bulk_insert(assessment_criteria_table, [{
        'id': uuid.uuid4(),
        'job_id': None,
        'section_id': None,
        'key': CV_ALIGNMENT_KEY,
        'label': CV_ALIGNMENT_LABEL,
        'kind': 'content',
        'enabled': True,
        'guidance_text': CV_ALIGNMENT_GUIDANCE,
        'source': 'TEMPLATE',
        'weight': 5,
    }])


def downgrade() -> None:
    op.get_bind().execute(
        sa.text("DELETE FROM assessment_criteria WHERE key = :key AND job_id IS NULL AND section_id IS NULL"),
        {"key": CV_ALIGNMENT_KEY},
    )
