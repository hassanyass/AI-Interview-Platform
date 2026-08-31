"""Phase 8C: assessment_criteria/evaluations/scores tables + 5 seed behavioral criteria

Additive only -- InterviewSession.final_result is untouched. Nothing existing
is backfilled into these tables (explicit decision: leave legacy final_result
read-only). The 5 seed rows are system TEMPLATE criteria (job_id/section_id
both NULL) -- see AssessmentCriterion's docstring in backend/backend/models/
interview.py for what that tier means and the interim /load-resolution
behavior around it.

Revision ID: d1f4a8c93b21
Revises: c9a1f0e2d3b4
Create Date: 2026-08-31

"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd1f4a8c93b21'
down_revision: Union[str, Sequence[str], None] = 'c9a1f0e2d3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# The 5 fixed behavioral criteria approved in 8B, seeded as TEMPLATE rows.
SEED_BEHAVIORAL_CRITERIA = [
    (
        "clarity_of_thought",
        "Clarity of Thought",
        "Does the candidate's reasoning follow a clear, logical thread the listener can "
        "follow, or is it disorganized, meandering, or hard to follow across the whole interview?",
    ),
    (
        "organization_structure",
        "Organization & Structure",
        "Does the candidate structure their answers (e.g. state an approach before diving in, "
        "signpost steps, summarize), or do their answers ramble without a discernible structure?",
    ),
    (
        "communication",
        "Communication",
        "How clearly and effectively does the candidate express technical and non-technical "
        "ideas -- precision of language, avoiding unexplained jargon, checking for understanding.",
    ),
    (
        "confidence_composure",
        "Confidence & Composure",
        "Does the candidate handle uncertainty, mistakes, or difficult questions calmly and "
        "constructively, or do they become flustered, defensive, or give up easily?",
    ),
    (
        "professionalism",
        "Professionalism",
        "Overall professional conduct throughout the interview -- respectful engagement, "
        "appropriate tone, taking the process seriously.",
    ),
]


def upgrade() -> None:
    op.create_table(
        'assessment_criteria',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('job_id', sa.UUID(), nullable=True),
        sa.Column('section_id', sa.UUID(), nullable=True),
        sa.Column('key', sa.String(), nullable=False),
        sa.Column('label', sa.String(), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('guidance_text', sa.Text(), nullable=True),
        sa.Column('source', sa.String(), nullable=False, server_default='CUSTOM'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['section_id'], ['interview_sections.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_id', 'section_id', 'key', name='uq_criterion_job_section_key'),
    )
    # Postgres treats NULL != NULL, so the UniqueConstraint above does not
    # catch duplicate template keys (job_id/section_id both NULL) -- a
    # partial index closes that gap specifically for the template tier.
    op.create_index(
        'uq_criterion_template_key', 'assessment_criteria', ['key'],
        unique=True,
        postgresql_where=sa.text('job_id IS NULL AND section_id IS NULL'),
    )

    op.create_table(
        'evaluations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('session_id', sa.UUID(), nullable=False),
        sa.Column('overall_score', sa.Integer(), nullable=True),
        sa.Column('recommendation', sa.String(), nullable=True),
        sa.Column('evidence_sufficiency', sa.Float(), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('detailed_overview', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['session_id'], ['interview_sessions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session_id', name='uq_evaluation_session'),
    )

    op.create_table(
        'scores',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('evaluation_id', sa.UUID(), nullable=False),
        sa.Column('criterion_id', sa.UUID(), nullable=True),
        sa.Column('criterion_key', sa.String(), nullable=False),
        sa.Column('score', sa.Integer(), nullable=True),
        sa.Column('overview', sa.Text(), nullable=True),
        sa.Column('strengths', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('improvements', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('evidence_reference', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['evaluation_id'], ['evaluations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['criterion_id'], ['assessment_criteria.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )

    # ─── Seed data: the 5 approved behavioral criteria, as TEMPLATE rows ───
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
        }
        for key, label, guidance_text in SEED_BEHAVIORAL_CRITERIA
    ])


def downgrade() -> None:
    op.drop_table('scores')
    op.drop_table('evaluations')
    op.drop_index('uq_criterion_template_key', table_name='assessment_criteria')
    op.drop_table('assessment_criteria')
