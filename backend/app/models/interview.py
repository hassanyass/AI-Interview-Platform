import uuid
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text
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
    
    profile = relationship("CandidateProfile", back_populates="interviews")
    configuration = relationship("InterviewConfiguration", back_populates="session", uselist=False, cascade="all, delete-orphan")


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
