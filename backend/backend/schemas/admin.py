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
    PAUSED = "PAUSED"


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


class JobStatusUpdate(BaseModel):
    status: JobStatus

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


# ── HR Results Dashboard (Phase 8D) ─────────────────────────────────────────
# Read-only views over the Phase 8C normalized tables (assessment_criteria/
# evaluations/scores), plus the legacy final_result JSONB's transcript/
# question_records/technical_submission (read-only, unchanged) for the
# per-candidate detail view. Not built from a single ORM model, so these
# are constructed by hand in the endpoint rather than from_attributes.

class CriterionScoreResponse(BaseModel):
    criterion_key: str
    # None if the AssessmentCriterion row was later deleted -- criterion_key
    # above is the durable record of what was actually evaluated.
    criterion_label: Optional[str] = None
    kind: Optional[str] = None
    score: Optional[int] = None
    overview: Optional[str] = None
    strengths: List[str] = []
    improvements: List[str] = []
    evidence_reference: Optional[str] = None
    # Scoring-mechanism upgrade: the weight this criterion carried when
    # weighted_score was computed (resolved via the same criterion join as
    # criterion_label/kind above) -- lets the dashboard show the arithmetic
    # behind the weighted score, not just its result. None under the same
    # circumstances criterion_label is None (criterion row later deleted).
    weight: Optional[int] = None


class QuestionRecordDetail(BaseModel):
    """One question_record from the legacy final_result JSONB, enriched
    with the actual question text resolved from InterviewQuestion -- the
    raw record only ever carried question_id, which is useless for an HR
    reviewer trying to see what was actually asked. title/text/competency
    are None for a question_id the join couldn't resolve (e.g. a legacy
    pre-Phase-7 session using ephemeral, never-persisted questions)."""
    question_id: str
    title: Optional[str] = None
    text: Optional[str] = None
    competency: Optional[str] = None
    order_index: Optional[int] = None
    outcome: str
    hints_used: int = 0
    followups_used: int = 0
    clarifications_used: int = 0


class IntegrityEventResponse(BaseModel):
    """One flagged moment from the integrity timeline -- see admin.py's
    _get_integrity_events for the exact allowlist (INTEGRITY_EVENT_TYPES)
    and the video_offset_seconds approximation this carries."""
    event_type: str  # "FULLSCREEN_EXITED" | "TAB_HIDDEN" | "WINDOW_BLURRED" | "NO_FACE_DETECTED" | "MULTIPLE_FACES_DETECTED" | "HEAD_DOWN_SUSPECTED"
    phase: Optional[str] = None
    metadata: dict = {}
    # Approximate seconds into the session recording -- None if the
    # session never recorded a started_at (legacy/never-started).
    video_offset_seconds: Optional[float] = None


class EvaluationDetailResponse(BaseModel):
    session_id: UUID
    status: str
    completed_at: Optional[datetime] = None
    candidate_name: Optional[str] = None
    candidate_email: Optional[str] = None
    job_title: Optional[str] = None

    # From the legacy final_result JSONB -- read-only, unchanged.
    transcript: List[dict] = []
    question_records: List[QuestionRecordDetail] = []
    technical_submission: dict = {}

    # From the normalized Evaluation/Score tables (Phase 8C).
    overall_score: Optional[int] = None
    recommendation: Optional[str] = None
    evidence_sufficiency: Optional[float] = None
    summary: Optional[str] = None
    detailed_overview: Optional[str] = None
    scores: List[CriterionScoreResponse] = []
    # Evaluation regeneration (2026-09-03): True when this evaluation is
    # the generic _ensure_evaluation_placeholder row -- the session never
    # actually got a real AI evaluation (crashed, lost its lease, or ended
    # via a path that never talks to the agent, e.g. TERMINATED). Drives
    # the frontend's "Regenerate Evaluation" affordance. See
    # CURRENT_DECISIONS.md's "Evaluation regeneration for placeholder
    # sessions" entry.
    is_placeholder: bool = False
    # Scoring-mechanism upgrade: the code-computed weighted aggregate of
    # `scores` above, deliberately separate from overall_score (the LLM's
    # own independent holistic judgment) -- see CURRENT_DECISIONS.md's
    # "Scoring mechanism upgrade" entry. None when no enabled criterion had
    # a scoreable result to average, same convention as overall_score.
    weighted_score: Optional[float] = None

    # Phase 8F: manual override (None = no override, use computed).
    override_suggested: Optional[bool] = None
    override_reason: Optional[str] = None

    # PR-C/PR-F (docs/proctoring-architecture.md): short-lived signed R2 GET
    # URL for the session's recording, computed fresh on every request
    # (never stored) -- None if no recording exists for this session
    # (R2 not configured when the interview ran, camera denied, or Egress
    # never started/failed). See admin.py's get_candidate_result.
    recording_url: Optional[str] = None

    # Aggregation/dashboard pass (2026-09-02): every flagged moment for this
    # session -- fullscreen/tab/focus events (PR-B) and face-presence events
    # (PR-D). Empty list is a legitimate, common state (nothing was ever
    # flagged), not an error.
    integrity_events: List[IntegrityEventResponse] = []


class JobCandidateRow(BaseModel):
    session_id: UUID
    candidate_name: Optional[str] = None
    candidate_email: Optional[str] = None
    status: str
    completed_at: Optional[datetime] = None
    overall_score: Optional[int] = None
    recommendation: Optional[str] = None
    evidence_sufficiency: Optional[float] = None
    # recommendation == "Hire" AND evidence_sufficiency >= settings.
    # SUGGESTED_EVIDENCE_SUFFICIENCY_FLOOR (8B mechanism B). If
    # override_suggested is not None, it takes precedence over computed.
    suggested: bool = False
    override_suggested: Optional[bool] = None
    # Aggregation/dashboard pass: option A per the confirmed decision --
    # ANY integrity event at all (no severity/count threshold) means
    # flagged. Surfaces evidence for HR to judge, same philosophy as the
    # scoring override rather than a system pre-judging via a threshold.
    flagged_for_review: bool = False


class JobResultsResponse(BaseModel):
    job_id: UUID
    job_title: str
    total_candidates: int
    completed_count: int
    in_progress_count: int
    suggested_count: int
    flagged_count: int = 0
    candidates: List[JobCandidateRow] = []


# ── Manual Override (Phase 8F — Part 1) ──────────────────────────────────────

class SuggestedOverrideRequest(BaseModel):
    # True = HR says yes, False = HR says no, None = clear override (revert
    # to computed value). Deliberately Optional[bool], not just bool, per
    # the user's clarification — an admin must be able to un-override.
    override_suggested: Optional[bool] = None
    reason: Optional[str] = None


class SuggestedOverrideResponse(BaseModel):
    session_id: UUID
    override_suggested: Optional[bool] = None
    override_reason: Optional[str] = None
    # Echo the computed value so the UI can show both side by side.
    computed_suggested: bool = False


# ── Assessment Criteria Authoring (Phase 8E) ──────────────────────────────────

class AssessmentCriterionResponse(BaseModel):
    key: str
    label: str
    kind: str
    enabled: bool
    guidance_text: Optional[str] = None
    source: str  # "TEMPLATE" | "CUSTOM"
    # Scoring-mechanism upgrade: 1-10, default 5 (equal weighting).
    weight: int = 5


class CriterionWeightSetting(BaseModel):
    """One criterion's configured state for a job -- replaces the previous
    bare enabled_keys list now that weight needs to travel alongside
    enabled/disabled in the same save."""
    key: str
    enabled: bool
    weight: int = Field(5, ge=1, le=10)


class CriteriaToggleRequest(BaseModel):
    """Per-criterion enabled/weight settings for this job's behavioral
    criteria. Any template key NOT present in this list is disabled.
    Independent per-criterion weights, renormalized at compute time
    (submit_evaluation) -- deliberately NOT required to sum to any fixed
    total, so enabling/disabling a criterion never forces re-balancing
    the others."""
    criteria: List[CriterionWeightSetting]

