from pydantic import BaseModel, ConfigDict, validator, EmailStr
from typing import Optional, List
from datetime import datetime
from uuid import UUID

class InterviewConfigurationCreate(BaseModel):
    role: str
    level: str
    language: str
    job_description: Optional[str] = None
    duration: int = 15
    thinking_time: int = 60
    
    @validator('level')
    def validate_level(cls, v):
        if v not in ['junior', 'mid', 'senior']:
            raise ValueError("Level must be 'junior', 'mid', or 'senior'")
        return v
        
    @validator('language')
    def validate_language(cls, v):
        if v not in ['en', 'ar']:
            raise ValueError("Language must be 'en' or 'ar'")
        return v

    @validator('job_description')
    def validate_job_description(cls, v):
        if v is not None and len(v) > 12000:
            raise ValueError("Job description must be 12,000 characters or fewer")
        return v.strip() if v else v
        
    @validator('duration')
    def validate_duration(cls, v):
        if v <= 0 or v > 120:
            raise ValueError("Duration must be positive and reasonable (<= 120)")
        return v

    @validator('thinking_time')
    def validate_thinking_time(cls, v):
        if v <= 0 or v > 300:
            raise ValueError("Thinking time must be positive and reasonable (<= 300)")
        return v

class InterviewConfigurationResponse(InterviewConfigurationCreate):
    session_id: UUID
    model_config = ConfigDict(from_attributes=True)

class InterviewSessionCreate(BaseModel):
    configuration: InterviewConfigurationCreate

class InterviewSessionResponse(BaseModel):
    id: UUID
    candidate_profile_id: UUID
    role: str
    level: str
    language: str
    status: str
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    configuration: Optional[InterviewConfigurationResponse] = None

    # Candidate-facing intro-screen + waiting-room fields. Populated by
    # get_interview() from the session's Job/InterviewDefinition (via
    # job_id/definition_id) when present — None for legacy sessions with no
    # B2B FKs. `sections` is the definition's ordered core-section-type
    # list (VERBAL/CODING/MCQ, in InterviewSection.order_index order), used
    # client-side to compute the waiting room's "next section" label since
    # the live realtime state only reports the CURRENTLY active section
    # (None while WAITING_ROOM itself is active).
    candidate_instructions: Optional[str] = None
    sections: Optional[List[str]] = None
    candidate_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class InterviewHistoryResponse(BaseModel):
    items: List[InterviewSessionResponse]
    total: int 

class PublicRegistrationRequest(BaseModel):
    public_access_token: str
    name: str
    email: EmailStr

class PublicRegistrationResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    job_id: str

class ConsentCreate(BaseModel):
    disclosure_language: str
    disclosure_text: str

    @validator('disclosure_language')
    def validate_disclosure_language(cls, v):
        if v not in ['en', 'ar']:
            raise ValueError("disclosure_language must be 'en' or 'ar'")
        return v

    @validator('disclosure_text')
    def validate_disclosure_text(cls, v):
        if not v or not v.strip():
            raise ValueError("disclosure_text must not be empty")
        return v

class ConsentResponse(BaseModel):
    id: UUID
    session_id: UUID
    disclosure_language: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class InterviewResultResponse(BaseModel):
    session_id: UUID
    status: str
    completed_at: Optional[datetime] = None
    final_result: Optional[dict] = None
    
    model_config = ConfigDict(from_attributes=True)
