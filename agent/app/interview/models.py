"""
Agent-side domain models for the interview engine.
These are independent Pydantic models — they do NOT import backend ORM.
"""
import enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


# ─── Interview Phases ──────────────────────────────────────────────────────────

class InterviewPhase(str, enum.Enum):
    CREATED = "CREATED"
    BRIEFING = "BRIEFING"
    WELCOME = "WELCOME"
    BACKGROUND = "BACKGROUND"
    TECHNICAL_INTRO = "TECHNICAL_INTRO"
    TECHNICAL = "TECHNICAL"
    CODING = "CODING"
    CLOSING = "CLOSING"
    COMPLETED = "COMPLETED"


# ─── LLM Conversational Actions ───────────────────────────────────────────────

class ActionEnum(str, enum.Enum):
    ASK = "ASK"
    LISTEN = "LISTEN"
    ACKNOWLEDGE = "ACKNOWLEDGE"
    FOLLOW_UP = "FOLLOW_UP"
    CLARIFY = "CLARIFY"
    HINT = "HINT"
    TRANSITION = "TRANSITION"
    EVALUATE = "EVALUATE"
    END = "END"


# ─── Candidate Control Actions ────────────────────────────────────────────────

class CandidateControlAction(str, enum.Enum):
    SKIP_QUESTION = "SKIP_QUESTION"
    CHANGE_QUESTION = "CHANGE_QUESTION"
    SKIP_SECTION = "SKIP_SECTION"
    MOVE_TO_TECHNICAL = "MOVE_TO_TECHNICAL"
    END_INTERVIEW = "END_INTERVIEW"
    REPEAT_QUESTION = "REPEAT_QUESTION"
    REQUEST_CLARIFICATION = "REQUEST_CLARIFICATION"
    REQUEST_HINT = "REQUEST_HINT"


# ─── Assistance Tracking ──────────────────────────────────────────────────────

class AssistanceType(str, enum.Enum):
    CLARIFICATION = "CLARIFICATION"
    HINT = "HINT"


class AssistanceRecord(BaseModel):
    assistance_type: AssistanceType
    level: int  # 0-4
    question_id: Optional[str] = None
    candidate_requested: bool = True
    reason: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ─── Technical Question ───────────────────────────────────────────────────────

class Question(BaseModel):
    id: str
    title: str
    problem_statement: str
    difficulty: str  # junior, mid, senior
    competency: str
    expected_concepts: List[str]
    hints: List[str]  # Ordered from level 1 to level 4
    follow_up_topics: List[str]
    time_budget_minutes: int
    coding_required: bool
    examples: List[Dict[str, Any]] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    starter_code: Dict[str, str] = Field(default_factory=dict)
    test_cases: List[Dict[str, Any]] = Field(default_factory=list)
    supported_languages: List[str] = Field(default_factory=list)
    title_ar: Optional[str] = None
    problem_statement_ar: Optional[str] = None
    hints_ar: List[str] = Field(default_factory=list)
    source: str = "QUESTION_BANK"


class QuestionOutcome(str, enum.Enum):
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"
    CHANGED = "CHANGED"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    TIME_EXPIRED = "TIME_EXPIRED"


class QuestionRecord(BaseModel):
    """Tracks the outcome and evidence for a completed/skipped question."""
    question_id: str
    outcome: QuestionOutcome
    hints_used: int = 0
    followups_used: int = 0
    clarifications_used: int = 0
    assistance_records: List[AssistanceRecord] = []
    evaluation: Optional["EvaluationSignal"] = None


# ─── Section Progress ─────────────────────────────────────────────────────────

class SectionLimits(BaseModel):
    target_questions: int = 2
    max_questions: int = 3
    max_followups_per_question: int = 3
    max_hints_per_question: int = 4


class SectionProgress(BaseModel):
    name: str
    questions_asked: int = 0
    questions_completed: int = 0
    questions_skipped: int = 0
    limits: SectionLimits = Field(default_factory=SectionLimits)
    evidence_sufficient: bool = False
    completed: bool = False


# ─── Interview Plan ────────────────────────────────────────────────────────────

class InterviewPlan(BaseModel):
    role: str
    level: str
    duration_minutes: int
    competencies: List[str] = []
    
    background_limits: SectionLimits = Field(
        default_factory=lambda: SectionLimits(target_questions=2, max_questions=3, max_followups_per_question=2, max_hints_per_question=0)
    )
    technical_limits: SectionLimits = Field(
        default_factory=lambda: SectionLimits(target_questions=2, max_questions=3, max_followups_per_question=3, max_hints_per_question=4)
    )


# ─── Evaluation Signal ────────────────────────────────────────────────────────

class EvaluationSignal(BaseModel):
    # General competencies (1-5)
    problem_understanding: Optional[int] = Field(None, ge=1, le=5)
    approach_quality: Optional[int] = Field(None, ge=1, le=5)
    technical_reasoning: Optional[int] = Field(None, ge=1, le=5)
    complexity_analysis: Optional[int] = Field(None, ge=1, le=5)
    communication: Optional[int] = Field(None, ge=1, le=5)
    independence: Optional[int] = Field(None, ge=1, le=5)
    
    # Detailed technical evidence
    data_structure_choice: Optional[str] = None
    algorithm_choice: Optional[str] = None
    edge_cases_considered: Optional[bool] = None
    
    evidence: str = ""
    missing: Optional[str] = None


class EvaluationCategory(BaseModel):
    score: Optional[int] = Field(None, ge=1, le=5)
    overview: str = "Not enough evidence was recorded to evaluate this category."
    strengths: List[str] = Field(default_factory=list)
    improvements: List[str] = Field(default_factory=list)


class DetailedEvaluation(BaseModel):
    overall_score: Optional[int] = Field(None, ge=1, le=5)
    recommendation: str = "Consider / Mixed"
    summary: str = "The interview did not contain enough evidence for a detailed assessment."
    communication: EvaluationCategory = Field(default_factory=EvaluationCategory)
    technical: EvaluationCategory = Field(default_factory=EvaluationCategory)
    problem_solving: EvaluationCategory = Field(default_factory=EvaluationCategory)
    technical_submission: EvaluationCategory = Field(default_factory=EvaluationCategory)
    background: EvaluationCategory = Field(default_factory=EvaluationCategory)
    strengths: List[str] = Field(default_factory=list)
    areas_for_improvement: List[str] = Field(default_factory=list)
    detailed_overview: str = ""


# ─── Structured LLM Output ────────────────────────────────────────────────────

class StructuredAction(BaseModel):
    action: ActionEnum
    response: str
    reason: str
    should_transition: bool = False
    detected_candidate_control: Optional[CandidateControlAction] = None
    evaluation: Optional[EvaluationSignal] = None


# ─── Message ──────────────────────────────────────────────────────────────────

class Message(BaseModel):
    role: str  # "system", "assistant", "user"
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ─── Interview Runtime Context ────────────────────────────────────────────────

class InterviewRuntimeContext(BaseModel):
    session_id: str
    candidate_id: str
    role: str
    confirmed_level: str
    language: str
    job_description: Optional[str] = None
    candidate_profile: Dict[str, Any] = {}
    
    # Phase state
    current_phase: InterviewPhase = InterviewPhase.CREATED
    current_question: Optional[Question] = None
    question_index: int = 0
    competencies_evaluated: List[str] = []
    
    # Timing
    interview_started_at: Optional[datetime] = None
    thinking_started_at: Optional[datetime] = None
    time_remaining_seconds: int = 0
    
    # Current question tracking
    hints_used: int = 0
    followups_used: int = 0
    
    # Section tracking
    interview_plan: Optional[InterviewPlan] = None
    background_progress: SectionProgress = Field(
        default_factory=lambda: SectionProgress(name="background")
    )
    technical_progress: SectionProgress = Field(
        default_factory=lambda: SectionProgress(name="technical")
    )
    
    # Records of completed/skipped questions
    question_records: List[QuestionRecord] = []
    assistance_records: List[AssistanceRecord] = []
    technical_question_ids_seen: List[str] = []
    technical_question_ids_skipped: List[str] = []
    technical_question_id_submitted: Optional[str] = None
    technical_submission: Dict[str, Any] = {}
    
    # Conversation history (in-memory only, NOT bulk-persisted per checkpoint)
    conversation_history: List[Message] = []
    evaluation_signals: List[EvaluationSignal] = []
    final_evaluation: Optional[DetailedEvaluation] = None
    
    # Persistence sequence counters
    message_sequence: int = 0
    event_sequence: int = 0
