import uuid
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text, UniqueConstraint, Boolean
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
    
    # Agent lease fields for ownership/reconnect safety
    active_agent_id = Column(String, nullable=True)
    agent_lease_expires_at = Column(DateTime(timezone=True), nullable=True)
    
    # Final aggregated result (populated when status reaches COMPLETED)
    final_result = Column(JSONB, nullable=True)
    
    profile = relationship("CandidateProfile", back_populates="interviews")
    configuration = relationship("InterviewConfiguration", back_populates="session", uselist=False, cascade="all, delete-orphan")
    messages = relationship("InterviewMessage", back_populates="session", cascade="all, delete-orphan", order_by="InterviewMessage.sequence_number")
    events = relationship("InterviewEvent", back_populates="session", cascade="all, delete-orphan", order_by="InterviewEvent.sequence_number")
    checkpoints = relationship("InterviewCheckpoint", back_populates="session", cascade="all, delete-orphan", order_by="InterviewCheckpoint.created_at.desc()")


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
