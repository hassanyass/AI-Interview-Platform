"""Scoring mechanism upgrade: assessment_criteria.weight + 3 new seed criteria

Additive only. See CURRENT_DECISIONS.md's "Scoring mechanism upgrade" entry
and the plan that preceded this migration: Phase 8B's fixed-curated-set
decision is NOT reversed, only amended -- a per-criterion weight (used to
compute Evaluation.weighted_score, see the next migration) and 3 additional
curated behavioral criteria, still no free-text/HR-authored criteria.

weight defaults to 5 (equal weighting) on both the column (existing rows
backfill automatically) and every new seed row -- a job that never touches
weighting behaves as if every enabled criterion counted equally.

Revision ID: a4f7c1e83b56
Revises: e7c2a4b6f183
Create Date: 2026-09-01

"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a4f7c1e83b56'
down_revision: Union[str, Sequence[str], None] = 'e7c2a4b6f183'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# The 3 additional behavioral criteria approved alongside this upgrade --
# see the plan's item 4 for the distinctness reasoning against both the
# existing 5 and per-question eval_criteria's content-correctness scope.
SEED_NEW_BEHAVIORAL_CRITERIA = [
    (
        "problem_solving_approach",
        "Problem-Solving Approach",
        "Does the candidate break a problem into parts, weigh tradeoffs, and check their own "
        "reasoning before committing to an answer -- observable in the transcript's process, "
        "not the correctness of any final submitted answer or code.",
    ),
    (
        "adaptability_to_feedback",
        "Adaptability to Feedback",
        "How well does the candidate incorporate a hint, follow-up probe, or redirection from "
        "the interviewer -- do they adjust constructively, or become flustered/defensive/rigid? "
        "Judge the quality of the response to being redirected, not merely whether a hint was used.",
    ),
    (
        "collaboration_teamwork",
        "Collaboration & Teamwork Orientation",
        "How does the candidate talk about working with others -- crediting teammates, "
        "describing real conflict resolution, showing awareness of team dynamics -- as distinct "
        "from the clarity of their individual communication.",
    ),
]


def upgrade() -> None:
    op.add_column(
        'assessment_criteria',
        sa.Column('weight', sa.Integer(), nullable=False, server_default='5'),
    )

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
    op.bulk_insert(assessment_criteria_table, [
        {
            'id': uuid.uuid4(),
            'job_id': None,
            'section_id': None,
            'key': key,
            'label': label,
            'kind': 'behavioral',
            'enabled': True,
            'guidance_text': guidance_text,
            'source': 'TEMPLATE',
            'weight': 5,
        }
        for key, label, guidance_text in SEED_NEW_BEHAVIORAL_CRITERIA
    ])


def downgrade() -> None:
    conn = op.get_bind()
    for key, _, _ in SEED_NEW_BEHAVIORAL_CRITERIA:
        conn.execute(
            sa.text("DELETE FROM assessment_criteria WHERE key = :key AND job_id IS NULL AND section_id IS NULL"),
            {"key": key},
        )
    op.drop_column('assessment_criteria', 'weight')
