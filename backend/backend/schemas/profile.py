from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional
from datetime import datetime
from uuid import UUID

class CandidateProfileBase(BaseModel):
    full_name: str
    email: str
    education: Optional[list] = None
    years_of_experience: Optional[int] = None
    skills: Optional[list] = None
    programming_languages: Optional[list] = None
    frameworks: Optional[list] = None
    projects: Optional[list] = None
    professional_title: Optional[str] = None
    recommended_level: Optional[str] = None
    confirmed_level: Optional[str] = None

class CandidateProfileCreate(CandidateProfileBase):
    pass

class CandidateProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    confirmed_level: Optional[str] = None
    # We can also allow other fields to be updated manually
    education: Optional[list] = None
    years_of_experience: Optional[int] = None
    skills: Optional[list] = None
    programming_languages: Optional[list] = None
    frameworks: Optional[list] = None
    projects: Optional[list] = None
    professional_title: Optional[str] = None

class CandidateProfileResponse(CandidateProfileBase):
    id: UUID
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class ResumeResponse(BaseModel):
    id: UUID
    profile_id: UUID
    original_filename: str
    storage_path: str
    mime_type: Optional[str] = None
    file_size: Optional[int] = None
    extraction_status: str
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

# For LLM Structured Output Validation
class ExtractedCandidateProfile(BaseModel):
    professional_title: Optional[str] = Field(default=None, description="Current or most recent professional title")
    education: List[str] = Field(default_factory=list, description="List of degrees and institutions")
    years_of_experience: int = Field(default=0, description="Total years of professional experience")
    skills: List[str] = Field(default_factory=list, description="General professional skills")
    programming_languages: List[str] = Field(default_factory=list, description="Programming languages known")
    frameworks: List[str] = Field(default_factory=list, description="Software frameworks and tools known")
    projects: List[str] = Field(default_factory=list, description="Notable projects worked on")
    recommended_level: str = Field(description="Recommended software engineering level (junior, mid, senior)")
