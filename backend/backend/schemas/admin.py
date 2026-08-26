from pydantic import BaseModel, ConfigDict, Field, ValidationError as PydanticValidationError
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from enum import Enum


# ── Enums ──────────────────────────────────────────────────────────────────

class SectionType(str, Enum):
    VERBAL = "VERBAL"
    CODING = "CODING"
    MCQ = "MCQ"


class JobStatus(str, Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"


# ── Type-Specific Question Config ──────────────────────────────────────────

class CodingConfig(BaseModel):
    starter_code: str
    supported_languages: list[str]
    constraints: str
    # Phase 9A addendum: graduated hints for the live, LeetCode-interview-
    # style solving flow (candidate can REQUEST_HINT while thinking aloud,
    # same mechanism the legacy engine's _provide_hint() already uses for
    # its single hardcoded question). Ordered weakest -> strongest; must
    # never simply reveal the answer outright. Schema/validation only here —
    # wiring this into the live CODING experience is 9C/9D's job.
    hints: list[str] = []


class MCQOption(BaseModel):
    id: str
    text: str


class MCQConfig(BaseModel):
    options: list[MCQOption]
    correct_answers: list[str]  # References MCQOption.id values
    is_multi_select: bool


def validate_question_config(section_type: str, config: dict | None) -> dict | None:
    """Validate and normalize config JSONB for a given section type.

    Returns the normalized dict on success, raises ValueError on failure.
    Callers catch ValueError and raise HTTPException(422).
    """
    if section_type == "VERBAL":
        if config:
            raise ValueError("VERBAL questions must not carry a config payload.")
        return None

    if section_type == "CODING":
        if not config:
            raise ValueError("CODING questions require a config payload.")
        try:
            parsed = CodingConfig(**config)
        except PydanticValidationError as e:
            raise ValueError(f"Invalid CODING config: {e}") from e
        return parsed.model_dump()

    if section_type == "MCQ":
        if not config:
            raise ValueError("MCQ questions require a config payload.")
        try:
            parsed = MCQConfig(**config)
        except PydanticValidationError as e:
            raise ValueError(f"Invalid MCQ config: {e}") from e
        # Referential integrity: every correct_answer must be a valid option ID
        valid_ids = {opt.id for opt in parsed.options}
        dangling = [a for a in parsed.correct_answers if a not in valid_ids]
        if dangling:
            raise ValueError(
                f"correct_answers references non-existent option IDs: {dangling}"
            )
        return parsed.model_dump()

    raise ValueError(f"Unknown section type: {section_type}")


# ── Section Timing Config (WR-A: Section Pacing & Waiting Room) ────────────
# See docs/section-pacing-architecture.md. Not type-specific like question
# config above — every section type (VERBAL/CODING/MCQ) carries the same
# shape, since a time budget applies uniformly regardless of content type.

class SectionConfig(BaseModel):
    time_budget_minutes: int = Field(gt=0)


def validate_section_config(config: dict | None) -> dict | None:
    """Validate and normalize a section's timing config.

    Optional at section creation (a bare section can exist before its
    budget is set, same as questions being addable after section creation)
    — None passes through unchanged. Required at publish time; see
    publish_job's own check for that enforcement. Returns the normalized
    dict on success, raises ValueError on failure. Callers catch ValueError
    and raise HTTPException(422).
    """
    if config is None:
        return None
    try:
        parsed = SectionConfig(**config)
    except PydanticValidationError as e:
        raise ValueError(f"Invalid section config: {e}") from e
    return parsed.model_dump()


class JobLanguage(str, Enum):
    EN = "en"
    AR = "ar"


class InvitationStatus(str, Enum):
    INVITED = "INVITED"
    OPENED = "OPENED"
    VERIFIED = "VERIFIED"
    STARTED = "STARTED"


# ── Job Schemas ────────────────────────────────────────────────────────────

class JobCreate(BaseModel):
    title: str
    description: Optional[str] = None
    seniority: Optional[str] = None
    location: Optional[str] = None
    instructions: Optional[str] = None
    required_skills: Optional[List[str]] = None
    preferred_skills: Optional[List[str]] = None
    responsibilities: Optional[List[str]] = None
    language: Optional[JobLanguage] = None


class JobUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    seniority: Optional[str] = None
    location: Optional[str] = None
    instructions: Optional[str] = None
    required_skills: Optional[List[str]] = None
    preferred_skills: Optional[List[str]] = None
    responsibilities: Optional[List[str]] = None
    language: Optional[JobLanguage] = None


class JobPublish(BaseModel):
    """Explicit action to move a Job from DRAFT to PUBLISHED."""
    pass


# ── InterviewDefinition Schemas ────────────────────────────────────────────

class InterviewDefinitionUpdate(BaseModel):
    duration_minutes: Optional[int] = None
    is_public: Optional[bool] = None


class InterviewDefinitionResponse(BaseModel):
    id: UUID
    job_id: UUID
    duration_minutes: int
    is_public: bool
    public_access_token: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ── InterviewSection Schemas ───────────────────────────────────────────────

class SectionCreate(BaseModel):
    definition_id: UUID
    section_type: SectionType
    order_index: int = 0
    config: Optional[dict] = None


class SectionUpdate(BaseModel):
    order_index: Optional[int] = None
    config: Optional[dict] = None


class SectionResponse(BaseModel):
    id: UUID
    definition_id: UUID
    section_type: str
    order_index: int
    config: Optional[dict] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ── InterviewQuestion Schemas ──────────────────────────────────────────────

class QuestionCreate(BaseModel):
    title: str
    competency: Optional[str] = None
    text: str
    eval_criteria: Optional[dict] = None
    config: Optional[dict] = None


class QuestionUpdate(BaseModel):
    title: Optional[str] = None
    competency: Optional[str] = None
    text: Optional[str] = None
    eval_criteria: Optional[dict] = None
    config: Optional[dict] = None


class QuestionResponse(BaseModel):
    id: UUID
    section_id: UUID
    order_index: int
    title: str
    competency: Optional[str] = None
    text: str
    eval_criteria: Optional[dict] = None
    config: Optional[dict] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ── AI Generation Schemas ──────────────────────────────────────────────────

class QuestionGenerateRequest(BaseModel):
    """Request body for AI question generation."""
    num_questions: int = Field(default=5, ge=1, le=20)


class GeneratedQuestion(BaseModel):
    """A single question produced by the AI generator."""
    title: str
    competency: Optional[str] = None
    text: str
    eval_criteria: Optional[dict] = None
    config: Optional[dict] = None


# ── Composite Response Schemas ─────────────────────────────────────────────

class SectionWithQuestionsResponse(SectionResponse):
    questions: List[QuestionResponse] = []


class DefinitionWithSectionsResponse(InterviewDefinitionResponse):
    sections: List[SectionWithQuestionsResponse] = []


class JobResponse(BaseModel):
    id: UUID
    title: str
    description: Optional[str] = None
    seniority: Optional[str] = None
    location: Optional[str] = None
    instructions: Optional[str] = None
    required_skills: Optional[List[str]] = None
    preferred_skills: Optional[List[str]] = None
    responsibilities: Optional[List[str]] = None
    status: str
    language: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    definition: Optional[InterviewDefinitionResponse] = None

    model_config = ConfigDict(from_attributes=True)


class JobDetailResponse(BaseModel):
    id: UUID
    title: str
    description: Optional[str] = None
    seniority: Optional[str] = None
    location: Optional[str] = None
    instructions: Optional[str] = None
    required_skills: Optional[List[str]] = None
    preferred_skills: Optional[List[str]] = None
    responsibilities: Optional[List[str]] = None
    status: str
    language: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    definition: Optional[DefinitionWithSectionsResponse] = None

    model_config = ConfigDict(from_attributes=True)


# ── InterviewInvitation Schemas ────────────────────────────────────────────

class InvitationCreate(BaseModel):
    candidate_email: str


class InvitationResponse(BaseModel):
    id: UUID
    application_id: UUID
    candidate_email: str
    status: InvitationStatus
    token: str
    expires_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
