"""Pydantic schemas for Phase 5 persistence API contracts."""
from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Any
from datetime import datetime
from uuid import UUID


# ─── Message Schemas ───────────────────────────────────────────────────────────

class MessageCreate(BaseModel):
    sequence_number: int
    speaker: str  # "candidate", "agent", "system"
    text: str
    phase: Optional[str] = None
    metadata: Optional[dict] = None


from pydantic import BaseModel, ConfigDict, Field, AliasChoices

class MessageResponse(BaseModel):
    id: UUID
    session_id: UUID
    sequence_number: int
    speaker: str
    text: str
    phase: Optional[str] = None
    metadata: Optional[dict] = Field(default=None, validation_alias=AliasChoices("metadata_", "metadata"))
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ─── Event Schemas ─────────────────────────────────────────────────────────────

class EventCreate(BaseModel):
    event_type: str
    phase: Optional[str] = None
    sequence_number: int
    metadata: Optional[dict] = None


class EventResponse(BaseModel):
    id: UUID
    session_id: UUID
    event_type: str
    phase: Optional[str] = None
    sequence_number: int
    metadata: Optional[dict] = Field(default=None, validation_alias=AliasChoices("metadata_", "metadata"))
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ─── Checkpoint Schemas ────────────────────────────────────────────────────────

class CheckpointCreate(BaseModel):
    schema_version: int = 1
    current_phase: str
    current_question_id: Optional[str] = None
    question_index: int = 0
    section: Optional[str] = None
    hints_used: int = 0
    followups_used: int = 0
    background_questions_asked: int = 0
    competencies_evaluated: Optional[List[str]] = None
    time_remaining_seconds: int = 0
    last_message_sequence: int = 0
    last_event_sequence: int = 0
    current_question_snapshot: Optional[dict] = None
    section_progress: Optional[dict] = None


class CheckpointResponse(BaseModel):
    id: UUID
    session_id: UUID
    schema_version: int
    current_phase: str
    current_question_id: Optional[str] = None
    question_index: int
    section: Optional[str] = None
    hints_used: int
    followups_used: int
    background_questions_asked: int
    competencies_evaluated: Optional[List[str]] = None
    time_remaining_seconds: int
    last_message_sequence: int
    last_event_sequence: int
    current_question_snapshot: Optional[dict] = None
    section_progress: Optional[dict] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ─── Status Update Schema ─────────────────────────────────────────────────────

class StatusUpdate(BaseModel):
    status: str  # CREATED, IN_PROGRESS, DISCONNECTED, COMPLETED, TERMINATED


# ─── Session Load Response (for agent bootstrap) ──────────────────────────────

class SessionLoadResponse(BaseModel):
    """Complete session data needed by the agent to start or resume an interview."""
    session_id: UUID
    candidate_profile_id: UUID
    role: str
    level: str
    language: str
    status: str
    started_at: Optional[datetime] = None
    
    # Configuration
    job_description: Optional[str] = None
    duration_minutes: int = 15
    thinking_time: int = 60
    
    # Candidate profile data
    candidate_profile: dict = {}
    
    # Latest checkpoint for recovery
    latest_checkpoint: Optional[CheckpointResponse] = None
    
    # Recent messages for context restoration (last N)
    recent_messages: List[MessageResponse] = []
    
    # Agent lease
    active_agent_id: Optional[str] = None
    agent_lease_expires_at: Optional[datetime] = None
