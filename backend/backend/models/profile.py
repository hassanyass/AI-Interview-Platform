import uuid
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from backend.db.session import Base
from sqlalchemy.orm import relationship

class CandidateProfile(Base):
    __tablename__ = "candidate_profiles"

    # UUID matches Supabase auth.users.id
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Added in Phase 3 for Supabase decoupling
    supabase_user_id = Column(UUID(as_uuid=True), unique=True, nullable=True)
    
    full_name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)
    education = Column(JSONB, nullable=True)
    years_of_experience = Column(Integer, nullable=True)
    skills = Column(JSONB, nullable=True)
    programming_languages = Column(JSONB, nullable=True)
    frameworks = Column(JSONB, nullable=True)
    projects = Column(JSONB, nullable=True)
    professional_title = Column(String, nullable=True)
    
    recommended_level = Column(String, nullable=True)
    confirmed_level = Column(String, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    resumes = relationship("Resume", back_populates="profile", cascade="all, delete-orphan")
    interviews = relationship("InterviewSession", back_populates="profile", cascade="all, delete-orphan")
    applications = relationship("JobApplication", back_populates="profile", cascade="all, delete-orphan")

class UserRole(Base):
    __tablename__ = "users_roles"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False) # Maps to Supabase auth.users.id
    role = Column(String, nullable=False) # e.g. "admin", "candidate"
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Resume(Base):
    __tablename__ = "resumes"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id = Column(UUID(as_uuid=True), ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False)
    
    original_filename = Column(String, nullable=False)
    storage_path = Column(String, nullable=False)
    mime_type = Column(String, nullable=True)
    file_size = Column(Integer, nullable=True)
    
    extracted_text = Column(Text, nullable=True)
    extraction_status = Column(String, nullable=False, default="UPLOADED") # UPLOADED, PROCESSING, COMPLETED, FAILED
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    profile = relationship("CandidateProfile", back_populates="resumes")
