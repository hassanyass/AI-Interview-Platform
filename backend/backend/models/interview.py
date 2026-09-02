import uuid
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Text, UniqueConstraint, Boolean, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from backend.db.session import Base
from sqlalchemy.orm import relationship


class Job(Base):
    __tablename__ = "jobs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    seniority = Column(String, nullable=True)
    location = Column(String, nullable=True)
    instructions = Column(Text, nullable=True)
    
    required_skills = Column(JSONB, nullable=True)
    preferred_skills = Column(JSONB, nullable=True)
    responsibilities = Column(JSONB, nullable=True)
    
    status = Column(String, nullable=False, default="DRAFT") # DRAFT, PUBLISHED, CLOSED
    language = Column(String, nullable=False, default="en", server_default="en") # en, ar — set by Admin at job creation, applies to all candidates for this Job

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    definition = relationship("InterviewDefinition", back_populates="job", uselist=False, cascade="all, delete-orphan")
    applications = relationship("JobApplication", back_populates="job", cascade="all, delete-orphan")


class InterviewDefinition(Base):
    __tablename__ = "interview_definitions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, unique=True)
    
    duration_minutes = Column(Integer, nullable=False, default=15)
    is_public = Column(Boolean, nullable=False, default=False)
    public_access_token = Column(String, unique=True, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    job = relationship("Job", back_populates="definition")
    sections = relationship("InterviewSection", back_populates="definition", cascade="all, delete-orphan", order_by="InterviewSection.order_index")


class InterviewSection(Base):
    __tablename__ = "interview_sections"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    definition_id = Column(UUID(as_uuid=True), ForeignKey("interview_definitions.id", ondelete="CASCADE"), nullable=False)
    
    section_type = Column(String, nullable=False) # VERBAL, CODING, MCQ
    order_index = Column(Integer, nullable=False)
    config = Column(JSONB, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    definition = relationship("InterviewDefinition", back_populates="sections")
    questions = relationship("InterviewQuestion", back_populates="section", cascade="all, delete-orphan", order_by="InterviewQuestion.order_index")
    
    __table_args__ = (
        UniqueConstraint("definition_id", "section_type", name="uq_section_type_per_definition"),
    )


class InterviewQuestion(Base):
    __tablename__ = "interview_questions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    section_id = Column(UUID(as_uuid=True), ForeignKey("interview_sections.id", ondelete="CASCADE"), nullable=False)
    
    order_index = Column(Integer, nullable=False)
    title = Column(String, nullable=False)
    competency = Column(String, nullable=True)
    text = Column(Text, nullable=False)
    eval_criteria = Column(JSONB, nullable=True)
    config = Column(JSONB, nullable=True)  # Type-specific structured data (CODING/MCQ)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    section = relationship("InterviewSection", back_populates="questions")


class JobApplication(Base):
    __tablename__ = "job_applications"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    candidate_profile_id = Column(UUID(as_uuid=True), ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False)
    resume_id = Column(UUID(as_uuid=True), ForeignKey("resumes.id", ondelete="SET NULL"), nullable=True)
    
    professional_title = Column(String, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    job = relationship("Job", back_populates="applications")
    profile = relationship("CandidateProfile", back_populates="applications")
    invitations = relationship("InterviewInvitation", back_populates="application", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("job_id", "candidate_profile_id", name="uq_job_application_job_candidate"),
    )


class InterviewInvitation(Base):
    __tablename__ = "interview_invitations"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id = Column(UUID(as_uuid=True), ForeignKey("job_applications.id", ondelete="CASCADE"), nullable=False)
    
    candidate_email = Column(String, nullable=False)
    status = Column(String, nullable=False, default="INVITED") # INVITED, OPENED, VERIFIED, STARTED
    
    token = Column(String, unique=True, nullable=False)
    otp_hash = Column(String, nullable=True)
    otp_expires_at = Column(DateTime(timezone=True), nullable=True)
    otp_attempt_count = Column(Integer, nullable=False, default=0)
    
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    application = relationship("JobApplication", back_populates="invitations")


class InterviewSession(Base):
    __tablename__ = "interview_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_profile_id = Column(UUID(as_uuid=True), ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False)
    
    # New B2B Foreign Keys (nullable to support legacy configurations)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True)
    definition_id = Column(UUID(as_uuid=True), ForeignKey("interview_definitions.id", ondelete="SET NULL"), nullable=True)
    application_id = Column(UUID(as_uuid=True), ForeignKey("job_applications.id", ondelete="SET NULL"), nullable=True)
    
    role = Column(String, nullable=False)
    level = Column(String, nullable=False) # junior, mid, senior
    language = Column(String, nullable=False) # en, ar
    
    status = Column(String, nullable=False, default="CREATED")
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    # Session-finalization-contract fix (2026-09-01): set only when status
    # transitions to DISCONNECTED, cleared on a resume back to IN_PROGRESS.
    # Lets the idle-disconnect auto-finalize sweep (internal.py) know
    # precisely how long a session has been abandoned, instead of
    # reverse-engineering it from the agent lease's rolling expiry.
    disconnected_at = Column(DateTime(timezone=True), nullable=True)
    
    # Agent lease fields for ownership/reconnect safety
    active_agent_id = Column(String, nullable=True)
    agent_lease_expires_at = Column(DateTime(timezone=True), nullable=True)

    # PR-C (docs/proctoring-architecture.md): LiveKit Egress full audio+
    # video recording reference. Plain nullable columns, not a dedicated
    # table -- same 1:1/operational shape as active_agent_id above, no
    # audit-trail need the way InterviewConsent had. recording_storage_path
    # is the R2 object key we choose ourselves at egress-start time (known
    # immediately, not dependent on a completion webhook).
    recording_egress_id = Column(String, nullable=True)
    recording_storage_path = Column(String, nullable=True)

    # Final aggregated result (populated when status reaches COMPLETED)
    final_result = Column(JSONB, nullable=True)
    
    profile = relationship("CandidateProfile", back_populates="interviews")
    configuration = relationship("InterviewConfiguration", back_populates="session", uselist=False, cascade="all, delete-orphan")
    messages = relationship("InterviewMessage", back_populates="session", cascade="all, delete-orphan", order_by="InterviewMessage.sequence_number")
    events = relationship("InterviewEvent", back_populates="session", cascade="all, delete-orphan", order_by="InterviewEvent.sequence_number")
    checkpoints = relationship("InterviewCheckpoint", back_populates="session", cascade="all, delete-orphan", order_by="InterviewCheckpoint.created_at.desc()")
    evaluation = relationship("Evaluation", back_populates="session", uselist=False, cascade="all, delete-orphan")
    consent = relationship("InterviewConsent", back_populates="session", uselist=False, cascade="all, delete-orphan")


class InterviewConfiguration(Base):
    __tablename__ = "interview_configurations"
    
    session_id = Column(UUID(as_uuid=True), ForeignKey("interview_sessions.id", ondelete="CASCADE"), primary_key=True)
    
    role = Column(String, nullable=False)
    level = Column(String, nullable=False)
    language = Column(String, nullable=False)
    job_description = Column(Text, nullable=True)
    
    duration = Column(Integer, nullable=False, default=15)
    thinking_time = Column(Integer, nullable=False, default=60)
    
    configuration_metadata = Column(JSONB, nullable=True)
    
    session = relationship("InterviewSession", back_populates="configuration")


class InterviewMessage(Base):
    """Durable transcript entry — stores finalized candidate/agent utterances."""
    __tablename__ = "interview_messages"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("interview_sessions.id", ondelete="CASCADE"), nullable=False)
    
    sequence_number = Column(Integer, nullable=False)
    speaker = Column(String, nullable=False)  # "candidate", "agent", "system"
    text = Column(Text, nullable=False)
    phase = Column(String, nullable=True)
    metadata_ = Column("metadata", JSONB, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    session = relationship("InterviewSession", back_populates="messages")
    
    __table_args__ = (
        UniqueConstraint("session_id", "sequence_number", name="uq_message_session_seq"),
    )


class InterviewEvent(Base):
    """Meaningful interview lifecycle events."""
    __tablename__ = "interview_events"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("interview_sessions.id", ondelete="CASCADE"), nullable=False)
    
    event_type = Column(String, nullable=False)
    phase = Column(String, nullable=True)
    sequence_number = Column(Integer, nullable=False)
    metadata_ = Column("metadata", JSONB, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    session = relationship("InterviewSession", back_populates="events")
    
    __table_args__ = (
        UniqueConstraint("session_id", "sequence_number", name="uq_event_session_seq"),
    )


class InterviewConsent(Base):
    """PR-A: recording/monitoring consent disclosure, one per session.

    Deliberately NOT modeled as an InterviewEvent row: InterviewEvent.
    sequence_number is a per-session counter owned exclusively by the agent
    runtime (seeded from checkpoint's last_event_sequence, incremented only
    inside controller.py/voice_adapter.py). Consent is recorded pre-agent,
    from the candidate-facing REST API, so a backend-inserted event row
    here would be invisible to that counter and could collide with the
    agent's own first event on the same session. This table sidesteps that
    entirely -- additive, standalone, no interaction with agent sequencing.

    disclosure_text stores the literal copy shown to the candidate (not a
    version pointer) since this repo has no versioning scheme for i18n
    strings to hang a pointer off -- this is the durable evidence of
    exactly what was disclosed, per docs/proctoring-architecture.md's PR-A.
    """
    __tablename__ = "interview_consents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("interview_sessions.id", ondelete="CASCADE"), nullable=False, unique=True)

    disclosure_language = Column(String, nullable=False)
    disclosure_text = Column(Text, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("InterviewSession", back_populates="consent")


class InterviewCheckpoint(Base):
    """
    Versioned recovery checkpoint. Contains only the minimal state
    required to restore an interrupted interview, NOT the full transcript.
    """
    __tablename__ = "interview_checkpoints"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("interview_sessions.id", ondelete="CASCADE"), nullable=False)
    
    schema_version = Column(Integer, nullable=False, default=1)
    
    # Recovery-relevant state only
    current_phase = Column(String, nullable=False)
    current_question_id = Column(String, nullable=True)
    question_index = Column(Integer, nullable=False, default=0)
    section = Column(String, nullable=True)
    hints_used = Column(Integer, nullable=False, default=0)
    followups_used = Column(Integer, nullable=False, default=0)
    background_questions_asked = Column(Integer, nullable=False, default=0)
    competencies_evaluated = Column(JSONB, nullable=True)  # List of competency strings
    time_remaining_seconds = Column(Integer, nullable=False, default=0)
    last_message_sequence = Column(Integer, nullable=False, default=0)
    last_event_sequence = Column(Integer, nullable=False, default=0)
    
    current_question_snapshot = Column(JSONB, nullable=True)
    section_progress = Column(JSONB, nullable=True)
    question_records = Column(JSONB, nullable=True)
    evaluation_signals = Column(JSONB, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("InterviewSession", back_populates="checkpoints")


# ─── Phase 8B/8C: Assessment Criteria & Structured Evaluation ──────────────────
# Additive, replaces nothing -- InterviewSession.final_result stays exactly as
# it is for every existing session (per the explicit "leave legacy read-only,
# no auto-backfill" decision). These tables are the new, queryable home for
# every session evaluated from Phase 8C onward.

class AssessmentCriterion(Base):
    """HR-configured criterion the evaluator scores independently.
    job_id/section_id NULL together = a system TEMPLATE row (the 5 seeded
    behavioral criteria) -- a menu of criteria, not tied to any one job.
    job_id set = a real, job-instantiated criterion (created by 8E's
    authoring UI, cloned from a template or fully custom); section_id set on
    top of that scopes it to one specific InterviewSection instead of the
    whole job. Until 8E ships, no job-scoped rows exist yet -- /load resolves
    every job to the enabled TEMPLATE rows as its default set (see
    internal.py's load_session_for_agent), a deliberate, explicitly-flagged
    interim behavior, not a permanent design decision on its own."""
    __tablename__ = "assessment_criteria"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=True)
    section_id = Column(UUID(as_uuid=True), ForeignKey("interview_sections.id", ondelete="CASCADE"), nullable=True)

    key = Column(String, nullable=False)
    label = Column(String, nullable=False)
    kind = Column(String, nullable=False)  # "behavioral" | "content"
    enabled = Column(Boolean, nullable=False, default=True, server_default="true")
    guidance_text = Column(Text, nullable=True)
    source = Column(String, nullable=False, default="CUSTOM", server_default="CUSTOM")  # "TEMPLATE" | "CUSTOM"
    # Scoring-mechanism upgrade (2026-09-01, see CURRENT_DECISIONS.md's
    # "Scoring mechanism upgrade" entry): relative importance of this
    # criterion when computing Evaluation.weighted_score. 1-10, defaults to
    # 5 (equal weighting) so a job that never touches weighting behaves as
    # if every enabled criterion counted equally -- no silent skew.
    # Independent per-criterion values, renormalized at compute time
    # (submit_evaluation) -- deliberately NOT required to sum to any fixed
    # total, so toggling a criterion on/off never forces HR to rebalance
    # the others.
    weight = Column(Integer, nullable=False, default=5, server_default="5")

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        # Real per-job/per-section duplicate keys are meaningfully caught here.
        UniqueConstraint("job_id", "section_id", "key", name="uq_criterion_job_section_key"),
        # Postgres treats NULL != NULL, so the constraint above does NOT catch
        # duplicate template keys (job_id/section_id both NULL) -- a partial
        # index closes that gap specifically for the template tier.
        Index(
            "uq_criterion_template_key", "key",
            unique=True,
            postgresql_where=(job_id.is_(None) & section_id.is_(None)),
        ),
    )


class Evaluation(Base):
    """One per CandidateInterviewSession/InterviewSession -- created the
    first time generate_final_evaluation() succeeds for that session (Phase
    8C), regardless of whether any criteria were resolved (an empty `scores`
    list is a legitimate state: legacy session, or a job with nothing
    configured -- not an error). Upserted, not blindly inserted, by
    POST /internal/interviews/{id}/evaluation, so a retry from the agent's
    teardown safety net can never create a duplicate row."""
    __tablename__ = "evaluations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("interview_sessions.id", ondelete="CASCADE"), nullable=False, unique=True)

    overall_score = Column(Integer, nullable=True)
    recommendation = Column(String, nullable=True)  # "Hire" | "Consider / Mixed" | "No Hire"
    evidence_sufficiency = Column(Float, nullable=True)
    summary = Column(Text, nullable=True)
    detailed_overview = Column(Text, nullable=True)

    # Scoring-mechanism upgrade (2026-09-01): a real, code-computed weighted
    # aggregate of this evaluation's criterion_scores (Score rows), using
    # each criterion's AssessmentCriterion.weight -- deliberately separate
    # from overall_score, which stays the LLM's own independent holistic
    # judgment, unchanged. Computed once by submit_evaluation (POST
    # /internal/interviews/{id}/evaluation) using the weights in effect at
    # that moment, then frozen -- matches overall_score/evidence_sufficiency's
    # existing "recorded fact about this evaluation event" precedent, not
    # live-recomputed on every dashboard read. Null when no enabled
    # criterion had a non-null score (nothing to average), same
    # insufficient-evidence convention as overall_score itself -- never 0.
    weighted_score = Column(Float, nullable=True)

    # Phase 8F: admin manual override of the computed "suggested" status.
    # None = no override (use computed evidence_sufficiency + recommendation),
    # True = HR says yes (override to suggested), False = HR says no.
    # Both the computed and overridden values stay visible/auditable.
    override_suggested = Column(Boolean, nullable=True)
    override_reason = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    session = relationship("InterviewSession", back_populates="evaluation")
    scores = relationship("Score", back_populates="evaluation", cascade="all, delete-orphan")


class Score(Base):
    """One per criterion actually scored for one Evaluation."""
    __tablename__ = "scores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    evaluation_id = Column(UUID(as_uuid=True), ForeignKey("evaluations.id", ondelete="CASCADE"), nullable=False)
    # Nullable + denormalized key: a criterion can be edited/deleted later by
    # HR without corrupting or cascading into a historical score. criterion_key
    # is the durable record of what was actually evaluated at the time.
    criterion_id = Column(UUID(as_uuid=True), ForeignKey("assessment_criteria.id", ondelete="SET NULL"), nullable=True)
    criterion_key = Column(String, nullable=False)

    score = Column(Integer, nullable=True)
    overview = Column(Text, nullable=True)
    strengths = Column(JSONB, nullable=True)
    improvements = Column(JSONB, nullable=True)
    evidence_reference = Column(Text, nullable=True)

    evaluation = relationship("Evaluation", back_populates="scores")
    # Phase 8D: read-only join for display (criterion_label/kind) — one-
    # directional, no back_populates needed. None if the criterion was
    # later edited/deleted (ondelete="SET NULL" above) — criterion_key
    # stays the durable record either way.
    criterion = relationship("AssessmentCriterion", viewonly=True)
