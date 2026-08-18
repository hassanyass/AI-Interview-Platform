import uuid
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from app.db.session import Base
from sqlalchemy.orm import relationship


class InterviewSession(Base):
    __tablename__ = "interview_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_profile_id = Column(UUID(as_uuid=True), ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False)
    
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
