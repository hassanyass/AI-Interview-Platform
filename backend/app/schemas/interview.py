from pydantic import BaseModel, ConfigDict, validator
from typing import Optional
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
    
    model_config = ConfigDict(from_attributes=True)

class InterviewResultResponse(BaseModel):
    session_id: UUID
    status: str
    completed_at: Optional[datetime] = None
    final_result: Optional[dict] = None
    
    model_config = ConfigDict(from_attributes=True)
