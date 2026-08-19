"""
InterviewController — the authoritative interview brain.

Manages phase progression, section limits, candidate control actions,
time-aware transitions, and delegates to the LLM for conversational generation.

The controller owns ALL deterministic interview logic.
The LLM produces conversational content within the constraints the controller provides.
"""
import time
import json
import logging
from typing import Awaitable, Callable, Optional, List
from datetime import datetime

from app.interview.models import (
    InterviewRuntimeContext, InterviewPhase, InterviewPlan,
    ActionEnum, CandidateControlAction,
    StructuredAction, Message, Question, EvaluationSignal,
    SectionProgress, SectionLimits, QuestionRecord, QuestionOutcome,
    AssistanceRecord, AssistanceType, DetailedEvaluation,
)
from app.interview.state_machine import (
    is_transition_valid, is_action_valid, is_candidate_control_valid,
    get_allowed_actions, get_allowed_candidate_controls,
)
from app.interview.questions import get_questions_by_competency
from app.llm.provider import LLMProvider
from app.llm.prompts import (
    BRIEFING_PROMPT, WELCOME_PROMPT, BACKGROUND_PROMPT,
    TECHNICAL_INTRO_PROMPT, TECHNICAL_PROMPT, CLOSING_PROMPT,
    EVALUATOR_PROMPT, _INTERVIEWER_IDENTITY,
    LANGUAGE_INSTRUCTIONS, SYSTEM_MESSAGES
)
from app.interview.persistence import InterviewPersistence
from app.interview.input_limits import (
    MAX_HISTORY_CHARS,
    MAX_JOB_DESCRIPTION_CHARS,
    MAX_MESSAGE_CHARS,
    MAX_PROFILE_CHARS,
    truncate_prompt_text,
)

logger = logging.getLogger(__name__)


class InterviewController:
    def __init__(
        self,
        llm: LLMProvider,
        persistence: InterviewPersistence,
        context: InterviewRuntimeContext,
    ):
        self.llm = llm
        self.persistence = persistence
        self.context = context

        # Timer
        self._start_time: Optional[float] = None
        self._total_duration_sec = context.time_remaining_seconds
        self._custom_question: Optional[Question] = None
        self._question_generator: Optional[Callable[[], Awaitable[Question]]] = None
        self._question_fallback_builder: Optional[Callable[[], Question]] = None
        self._question_history: List[Question] = []
        if context.current_question:
            self._question_history.append(context.current_question)

        # Build interview plan from context if not already set
        if not context.interview_plan:
            context.interview_plan = InterviewPlan(
                role=context.role,
                level=context.confirmed_level,
                duration_minutes=context.time_remaining_seconds // 60,
            )
            # Propagate limits to section progress objects
            context.background_progress.limits = context.interview_plan.background_limits
            context.technical_progress.limits = context.interview_plan.technical_limits

        # One technical problem is submitted per interview. A skip may select
        # one replacement, but counters must never trigger normal progression.
        context.interview_plan.technical_limits.target_questions = 1
        context.interview_plan.technical_limits.max_questions = 1
        context.technical_progress.limits.target_questions = 1
        context.technical_progress.limits.max_questions = 1

        # Verify unknown/retired questions safely
        from app.interview.questions import QUESTION_BANK
        bank_ids = {q.id for q in QUESTION_BANK}
        
        # Check historical records
        for record in self.context.question_records:
            if record.question_id not in bank_ids:
                logger.warning(f"Historical record references question_id '{record.question_id}' which is not in the current QUESTION_BANK. Treating as retired but intact.")
                
        # Check active question
        if self.context.current_question and self.context.current_question.id not in bank_ids:
            logger.warning(f"Active question '{self.context.current_question.id}' is not in the current QUESTION_BANK. Continuing execution using the persisted question snapshot.")

    # ─── Lifecycle ─────────────────────────────────────────────────────────

    def start_interview(self):
        """Starts the deterministic interview timer and transitions to BRIEFING."""
        if not self._start_time:
            self._start_time = time.time()
            self.context.interview_started_at = datetime.utcnow()
        self._transition_to(InterviewPhase.BRIEFING)

    def resume_timer(self):
        """Resume countdown from a checkpoint without changing the current phase."""
        if not self._start_time:
            self._start_time = time.time()
            if not self.context.interview_started_at:
                self.context.interview_started_at = datetime.utcnow()

    def set_custom_question(self, question: Question):
        """Set the one generated question to load when technical work begins."""
        self._custom_question = question

    def set_question_generator(self, generator: Callable[[], Awaitable[Question]]):
        """Register the per-session generator for initial and skipped questions."""
        self._question_generator = generator

    def set_question_fallback(self, builder: Callable[[], Question]):
        self._question_fallback_builder = builder

    def previous_question_summaries(self) -> List[str]:
        return [f"{question.title}: {question.problem_statement}" for question in self._question_history]

    async def _generate_personalized_question(self) -> Optional[Question]:
        if not self._question_generator:
            return None
        try:
            question = await self._question_generator()
            logger.info("[TECH-GEN] Generated personalized question id=%s title=%s source=%s", question.id, question.title, question.source)
            return question
        except Exception:
            logger.exception("[TECH-GEN] Personalized generation FAILED during replacement")
            if self._question_fallback_builder:
                question = self._question_fallback_builder()
                logger.warning("[TECH-GEN] FALLBACK=CONTEXTUAL_FALLBACK id=%s title=%s", question.id, question.title)
                return question
            return None

    def get_remaining_time(self) -> int:
        if not self._start_time:
            return self._total_duration_sec
        elapsed = time.time() - self._start_time
        remaining = int(self._total_duration_sec - elapsed)
        self.context.time_remaining_seconds = max(0, remaining)
        return self.context.time_remaining_seconds

    def is_time_expired(self) -> bool:
        return self.get_remaining_time() <= 0

    # ─── Phase Transitions ─────────────────────────────────────────────────

    def _transition_to(self, target_phase: InterviewPhase):
        if is_transition_valid(self.context.current_phase, target_phase):
            logger.info(f"Phase transition: {self.context.current_phase.value} → {target_phase.value}")
            self.context.current_phase = target_phase
            
            if target_phase in (InterviewPhase.TECHNICAL_INTRO, InterviewPhase.TECHNICAL):
                if not self.context.current_question:
                    self._load_next_technical_question()
            elif target_phase == InterviewPhase.COMPLETED:
                if self.context.current_question:
                    self._record_question_completion()
        else:
            raise ValueError(
                f"Invalid transition from {self.context.current_phase} to {target_phase}"
            )

    def _load_next_technical_question(self):
        """Loads the next appropriate technical question into the state machine."""
        from app.interview.questions import QUESTION_BANK
        
        plan = self.context.interview_plan
        level = (self.context.confirmed_level or "junior").lower()
        used_ids = set(self.context.technical_question_ids_seen)
        used_ids.update(r.question_id for r in self.context.question_records)
        logger.info("[TECHNICAL] Previously attempted ids=%s", sorted(used_ids))

        if self._custom_question and self._custom_question.id not in used_ids:
            question = self._custom_question
            self._custom_question = None
            self.load_question(question)
            logger.info("[TECH-GEN] Final selected question id=%s title=%s source=%s", question.id, question.title, question.source)
            return question

        if self._question_generator and self._question_fallback_builder:
            question = self._question_fallback_builder()
            self.load_question(question)
            logger.warning("[TECH-GEN] FALLBACK=CONTEXTUAL_FALLBACK reason=pending personalized question was unavailable id=%s", question.id)
            return question
        
        # Rank the bank against the role, CV, and job description before using
        # the generic competency fallback.
        from app.interview.questions import rank_questions_for_context
        contextual_questions = rank_questions_for_context(
            role=self.context.role,
            job_description=self.context.job_description,
            candidate_profile=self.context.candidate_profile,
            difficulty=level,
        )
        for q in contextual_questions:
            if q.id not in used_ids:
                self.load_question(q)
                logger.warning("[TECH-GEN] FALLBACK=QUESTION_BANK reason=no personalized question available id=%s title=%s", q.id, q.title)
                return q

        # Try matching competency + level from the generated plan.
        if plan and plan.competencies:
            idx = len(used_ids)
            comp = plan.competencies[idx % len(plan.competencies)]
            questions = get_questions_by_competency(comp, level)
            for q in questions:
                if q.id not in used_ids:
                    self.load_question(q)
                    return q
        
        # Fallback: any unused question matching the level
        for q in QUESTION_BANK:
            if q.id not in used_ids and q.difficulty == level:
                self.load_question(q)
                return q
        
        # Last resort: any unused question at all
        for q in QUESTION_BANK:
            if q.id not in used_ids:
                self.load_question(q)
                return q
        
        logger.warning("[TECHNICAL] Question bank exhausted; no replacement selected")
        return None

    def _question_problem_text(self, question: Optional[Question]) -> str:
        """Returns the candidate-facing problem in the selected language."""
        if not question:
            return "لا يوجد سؤال محمّل حالياً." if self.context.language == "ar" else "No problem loaded."
        if self.context.language == "ar" and question.problem_statement_ar:
            return question.problem_statement_ar
        return question.problem_statement

    def _question_title_text(self, question: Optional[Question]) -> str:
        if not question:
            return ""
        if self.context.language == "ar" and question.title_ar:
            return question.title_ar
        return question.title

    # ─── Message Management ────────────────────────────────────────────────

    def append_message(self, role: str, content: str):
        self.context.conversation_history.append(
            Message(role=role, content=content)
        )

    def _append_control_response(self, action: StructuredAction):
        """Keep skip acknowledgements out of the next LLM conversation turn."""
        if not action.response:
            return
        if action.detected_candidate_control in (
            CandidateControlAction.SKIP_QUESTION,
            CandidateControlAction.SKIP_SECTION,
        ):
            return
        self.append_message("assistant", action.response)

    def next_message_seq(self) -> int:
        self.context.message_sequence += 1
        return self.context.message_sequence

    def next_event_seq(self) -> int:
        self.context.event_sequence += 1
        return self.context.event_sequence

    # ─── Main Interaction Loop ─────────────────────────────────────────────

    async def process_candidate_input(self, user_text: Optional[str] = None) -> StructuredAction:
        """
        Core turn processing. Appends message, 
        checks for candidate control intents, generates AI response.
        """
        if self.context.current_phase == InterviewPhase.COMPLETED:
            return StructuredAction(
                action=ActionEnum.END,
                response="The interview has already been completed.",
                reason="Phase is COMPLETED, no further inputs allowed.",
                should_transition=False,
            )

        # Time check
        if self.is_time_expired() and self.context.current_phase not in (
            InterviewPhase.CLOSING, InterviewPhase.COMPLETED
        ):
            self._transition_to(InterviewPhase.CLOSING)
            return StructuredAction(
                action=ActionEnum.TRANSITION,
                response="We are out of time for today's interview. Let me wrap things up.",
                reason="Time expired.",
                should_transition=True,
            )

        # Append candidate message
        if user_text:
            self.append_message("user", user_text)

        # Check for candidate control intent BEFORE sending to LLM
        control_action = self._detect_candidate_control(user_text)
        if control_action:
            logger.info(f"Detected Candidate Control (Voice): {control_action.value}")
            handled = await self._handle_candidate_control(control_action)
            if handled:
                await self._apply_action(handled)
                self._append_control_response(handled)
                await self.persistence.save_checkpoint(self.context)
                return handled

        # Generate LLM response
        try:
            action = await self._generate_next_action()
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            action = StructuredAction(
                action=ActionEnum.ASK,
                response="I'm sorry, I didn't quite catch that. Could you repeat?",
                reason="LLM generation failed, using safe fallback."
            )
        
        # Validate action against state machine
        if not is_action_valid(self.context.current_phase, action.action):
            logger.warning(
                f"LLM generated invalid action {action.action.value} for phase {self.context.current_phase.value}. Defaulting to ACKNOWLEDGE."
            )
            action.action = ActionEnum.ACKNOWLEDGE

        # Check for section completion before applying the action
        if action.action == ActionEnum.TRANSITION or action.should_transition:
            if self._should_allow_transition():
                action.action = ActionEnum.TRANSITION
                action.should_transition = True
            else:
                # LLM wanted to transition but section isn't done yet
                action.action = ActionEnum.ASK
                action.should_transition = False
                
        # Enforce hard boundaries if LLM tries to continue indefinitely
        if not action.should_transition and self._must_force_transition():
            logger.info("Hard phase boundary reached. Forcing transition.")
            action.action = ActionEnum.TRANSITION
            action.should_transition = True
            action.response += " " + self._get_forced_transition_message()

        # Check for LLM-detected candidate control
        if action.detected_candidate_control:
            # State-changing controls must come from the deterministic intent
            # detector. LLM control fields are advisory only; accepting an
            # uncertain END/SKIP classification can create phantom turns.
            llm_control = action.detected_candidate_control
            llm_control_is_safe = llm_control in (
                CandidateControlAction.REQUEST_HINT,
                CandidateControlAction.REQUEST_CLARIFICATION,
                CandidateControlAction.REPEAT_QUESTION,
            )
            if llm_control_is_safe and is_candidate_control_valid(
                self.context.current_phase, llm_control
            ):
                handled = await self._handle_candidate_control(
                    llm_control
                )
                if handled:
                    await self._apply_action(handled)
                    self._append_control_response(handled)
                    await self.persistence.save_checkpoint(self.context)
                    return handled

        # Apply action effects (transitions, evaluation tracking, etc.)
        await self._apply_action(action)

        # Append AI message to conversation history
        self.append_message("assistant", action.response)

        # Checkpoint
        await self.persistence.save_checkpoint(self.context)

        return action
        
    # ─── UI / Data Channel Helpers ──────────────────────────────────────────

    def generate_ui_state(self) -> dict:
        """
        Generates a JSON-serializable dictionary representing the authoritative 
        interview state for the React UI.
        """
        ctx = self.context
        
        # Infer technical sub-phase
        sub_phase = None
        if ctx.current_phase in (InterviewPhase.TECHNICAL_INTRO, InterviewPhase.TECHNICAL, InterviewPhase.CODING):
            if not ctx.current_question:
                sub_phase = "READING"
            elif ctx.current_phase == InterviewPhase.CODING:
                sub_phase = "CODING"
            elif ctx.hints_used > 0 or ctx.followups_used > 0:
                sub_phase = "APPROACH"
            else:
                sub_phase = "THINKING"
                
        # Current question details
        q_data = None
        if ctx.current_question:
            q_data = {
                "id": ctx.current_question.id,
                "title": self._question_title_text(ctx.current_question),
                "problem_statement": self._question_problem_text(ctx.current_question),
                "difficulty": ctx.current_question.difficulty,
                "competency": ctx.current_question.competency,
                "expected_concepts": ctx.current_question.expected_concepts,
                "hints": ctx.current_question.hints,
                "follow_up_topics": ctx.current_question.follow_up_topics,
                "time_budget_minutes": ctx.current_question.time_budget_minutes,
                "coding_required": ctx.current_question.coding_required,
                "examples": ctx.current_question.examples,
                "constraints": ctx.current_question.constraints,
                "starter_code": ctx.current_question.starter_code,
                "test_cases": ctx.current_question.test_cases,
                "supported_languages": ctx.current_question.supported_languages,
                "hints_used": ctx.hints_used,
                "source": ctx.current_question.source,
            }
            
        allowed_controls = list(get_allowed_candidate_controls(ctx.current_phase))
        # UI-specific explicit control injection
        if sub_phase in ("READING", "THINKING", "APPROACH", "CODING"):
            if CandidateControlAction.REQUEST_CLARIFICATION.value not in allowed_controls:
                allowed_controls.append(CandidateControlAction.REQUEST_CLARIFICATION.value)
            if CandidateControlAction.REQUEST_HINT.value not in allowed_controls:
                allowed_controls.append(CandidateControlAction.REQUEST_HINT.value)
        
        # Make sure END_INTERVIEW is always available via UI
        if CandidateControlAction.END_INTERVIEW.value not in allowed_controls:
            allowed_controls.append(CandidateControlAction.END_INTERVIEW.value)
            
        last_outcome = None
        if ctx.question_records:
            last_outcome = ctx.question_records[-1].outcome.value
            
        max_hints = 4
        if ctx.interview_plan:
            max_hints = ctx.interview_plan.technical_limits.max_hints_per_question

            return {
            "session_id": ctx.session_id,
            "phase": ctx.current_phase.value,
            "sub_phase": sub_phase,
            "current_question": q_data,
            "question_index": ctx.question_index,
            "total_questions": ctx.interview_plan.technical_limits.target_questions if ctx.interview_plan else 2,
            "questions_completed": ctx.technical_progress.questions_completed,
            "questions_skipped": ctx.technical_progress.questions_skipped,
            "hints_used": ctx.hints_used,
            "max_hints": max_hints,
            "last_question_outcome": last_outcome,
            "allowed_controls": allowed_controls,
            "time_remaining_seconds": self.get_remaining_time()
        }
        
    async def process_ui_command(self, command: str, payload: dict = None) -> Optional[StructuredAction]:
        """
        Processes an explicit candidate control command sent via UI data channel.
        """
        logger.info(f"Received UI Command: {command}")

        # A queued End command can arrive after the submit flow has already
        # produced the closing turn. Treat it as an idempotent completion
        # request instead of emitting a second assistant message.
        if command == "END_INTERVIEW" and self.context.current_phase == InterviewPhase.COMPLETED:
            return StructuredAction(
                action=ActionEnum.END,
                response="",
                reason="Interview was already completed.",
                should_transition=False,
                detected_candidate_control=CandidateControlAction.END_INTERVIEW,
            )

        if command == "SUBMIT_CODE":
            if self.context.current_phase not in (InterviewPhase.TECHNICAL, InterviewPhase.CODING):
                return None

            submission = payload.get("payload", payload or {}) if isinstance(payload, dict) else {}
            if isinstance(submission, dict):
                self.context.technical_submission = {
                    "code": str(submission.get("code", ""))[:12000],
                    "language": str(submission.get("language", ""))[:40],
                }
            submitted_id = self.context.current_question.id if self.context.current_question else None
            self._record_question_completion()
            response = SYSTEM_MESSAGES.get(self.context.language, SYSTEM_MESSAGES["en"])["submit_code"]
            self._transition_to(InterviewPhase.CLOSING)
            logger.info("[TECHNICAL] Submitted question id=%s", submitted_id)
            logger.info("[TECHNICAL] Technical phase complete; transitioning to CLOSING")
            handled = StructuredAction(
                action=ActionEnum.ACKNOWLEDGE,
                response=response,
                reason="Candidate submitted the single technical answer.",
                should_transition=True,
            )

            await self._apply_action(handled)
            self._append_control_response(handled)
            await self.persistence.save_checkpoint(self.context)
            return handled

        # Explicit mapping
        try:
            control_action = CandidateControlAction(command)
        except ValueError:
            # Special UI-only commands like "IM_READY" to transition out of Thinking
            if command == "IM_READY":
                # Transition from TECHNICAL_INTRO → TECHNICAL
                if (
                    self.context.current_phase == InterviewPhase.TECHNICAL_INTRO
                    and current != InterviewPhase.BACKGROUND
                ):
                    self._transition_to(InterviewPhase.TECHNICAL)
                return StructuredAction(
                    action=ActionEnum.ACKNOWLEDGE,
                    response="Great. Walk me through how you would approach this problem.",
                    reason="Candidate indicated they are ready.",
                    should_transition=True,
                )
            logger.warning(f"Unknown UI Command received: {command}")
            return None
            
        # Ensure it's valid for the current phase (with some leniency for explicit UI buttons)
        allowed = get_allowed_candidate_controls(self.context.current_phase)
        # We always allow ending the interview
        if control_action != CandidateControlAction.END_INTERVIEW and control_action not in allowed:
            # For technical subphases, we explicitly allow Hints/Clarify in the UI state
            if self.context.current_phase in (InterviewPhase.TECHNICAL_INTRO, InterviewPhase.TECHNICAL, InterviewPhase.CODING) and control_action in (
                CandidateControlAction.REQUEST_HINT, CandidateControlAction.REQUEST_CLARIFICATION
            ):
                pass
            else:
                logger.warning(f"Control {control_action.value} not allowed in {self.context.current_phase.value}")
                return None
            
        handled = await self._handle_candidate_control(control_action, payload)
        if handled:
            await self._apply_action(handled)
            self._append_control_response(handled)
            await self.persistence.save_checkpoint(self.context)
        return handled

    # ─── Candidate Control Detection ──────────────────────────────────────

    def _detect_candidate_control(self, text: Optional[str]) -> Optional[CandidateControlAction]:
        """
        Simple keyword-based detection for unambiguous candidate intents.
        The LLM also detects control intents in ambiguous cases via structured output.
        """
        if not text:
            return None
        lower = text.lower().strip()

        # End interview
        if any(phrase in lower for phrase in [
            "end the interview", "i want to stop", "let's stop",
            "i'm done", "end interview", "stop the interview"
        ]):
            return CandidateControlAction.END_INTERVIEW

        # Skip question
        if any(phrase in lower for phrase in [
            "skip this question", "skip question", "next question",
            "move to the next", "let's skip this", "تخطي", "تجاوز السؤال", "السؤال اللي بعده"
        ]):
            return CandidateControlAction.SKIP_QUESTION

        # Change question
        if any(phrase in lower for phrase in [
            "change the question", "different problem", "another question",
            "another problem", "change question"
        ]):
            return CandidateControlAction.CHANGE_QUESTION

        # Move to technical
        if any(phrase in lower for phrase in [
            "move to technical", "go to technical", "skip to technical",
            "start the technical", "let's do technical",
            "move to the technical part", "move to the technical section"
            , "الجزء التقني", "نبدأ التقني", "ننتقل للتقني"
        ]):
            return CandidateControlAction.MOVE_TO_TECHNICAL

        # Skip section
        if any(phrase in lower for phrase in [
            "skip this section", "skip the background", "skip background",
            "let's move on", "move on to the next section"
            , "تخطي القسم", "نتجاوز الخلفية", "ننتقل للجزء الثاني"
        ]):
            return CandidateControlAction.SKIP_SECTION

        # Hint
        if any(phrase in lower for phrase in [
            "give me a hint", "can i get a hint", "i need a hint",
            "hint please", "help me"
            , "تلميح", "مساعدة"
        ]):
            return CandidateControlAction.REQUEST_HINT

        # Repeat
        if any(phrase in lower for phrase in [
            "repeat the question", "say that again", "can you repeat",
            "repeat please", "what was the question"
            , "كرر السؤال", "أعد السؤال", "وش السؤال"
        ]):
            return CandidateControlAction.REPEAT_QUESTION

        # Clarification
        if any(phrase in lower for phrase in [
            "explain the question", "what does that mean",
            "can you clarify", "i don't understand the question",
            "what exactly", "explain what"
            , "وضح السؤال", "ممكن توضح", "أحتاج توضيح"
        ]):
            return CandidateControlAction.REQUEST_CLARIFICATION

        return None

    # ─── Candidate Control Handlers ───────────────────────────────────────

    async def _handle_candidate_control(
        self, control: CandidateControlAction, payload: dict = None
    ) -> Optional[StructuredAction]:
        """
        Executes immediate state transitions for unambiguous controls.
        """
        lang = getattr(self.context, "language", "en")
        msgs = SYSTEM_MESSAGES.get(lang, SYSTEM_MESSAGES["en"])
        
        if control == CandidateControlAction.END_INTERVIEW:
            if self.context.current_phase == InterviewPhase.CLOSING:
                return StructuredAction(
                    action=ActionEnum.END,
                    response="",
                    reason="Closing turn already exists; completing idempotently.",
                    should_transition=True,
                    detected_candidate_control=control,
                )
            self._transition_to(InterviewPhase.CLOSING)
            return StructuredAction(
                action=ActionEnum.ACKNOWLEDGE,
                response=msgs["end_interview"],
                reason="Candidate explicitly ended interview.",
                should_transition=True,
                detected_candidate_control=control,
            )

        if control in (CandidateControlAction.SKIP_QUESTION, CandidateControlAction.SKIP_SECTION):
            current = self.context.current_phase
            new_phase = current
            if current in (InterviewPhase.TECHNICAL, InterviewPhase.CODING):
                skipped_id = self.context.current_question.id if self.context.current_question else None
                self._record_question_skip()
                logger.info("[TECHNICAL] Skipping question id=%s", skipped_id)
                replacement = await self._generate_personalized_question()
                if replacement:
                    self.load_question(replacement)
                else:
                    replacement = self._load_next_technical_question()
                if replacement:
                    logger.info("[TECH-GEN] Replacement question id=%s title=%s source=%s", replacement.id, replacement.title, replacement.source)
                else:
                    logger.info("[TECHNICAL] No replacement available; transitioning to CLOSING")
                    self._transition_to(InterviewPhase.CLOSING)
                new_phase = self.context.current_phase
            else:
                # A background question skip stays in BACKGROUND until the
                # existing asked-question maximum is reached. SKIP_SECTION
                # remains the explicit escape hatch to technical work.
                if current == InterviewPhase.BACKGROUND:
                    progress = self.context.background_progress
                    if (
                        control == CandidateControlAction.SKIP_SECTION
                        or progress.questions_asked >= progress.limits.max_questions
                    ):
                        progress.completed = True
                        self._transition_to(InterviewPhase.TECHNICAL_INTRO)
                elif current == InterviewPhase.BRIEFING:
                    self._transition_to(InterviewPhase.WELCOME)
                if self.context.current_phase == InterviewPhase.WELCOME:
                    self._transition_to(InterviewPhase.BACKGROUND)
                if (
                    self.context.current_phase == InterviewPhase.BACKGROUND
                    and current != InterviewPhase.BACKGROUND
                ):
                    self.context.background_progress.completed = True
                    self._transition_to(InterviewPhase.TECHNICAL_INTRO)
                if (
                    self.context.current_phase == InterviewPhase.TECHNICAL_INTRO
                    and current != InterviewPhase.BACKGROUND
                ):
                    self._transition_to(InterviewPhase.TECHNICAL)
                new_phase = self.context.current_phase

            return StructuredAction(
                action=ActionEnum.TRANSITION,
                response=msgs["transition_technical"] if new_phase == InterviewPhase.TECHNICAL and current not in (InterviewPhase.TECHNICAL, InterviewPhase.CODING) else msgs["skip_question"],
                reason="Candidate skipped to the technical interview." if current not in (InterviewPhase.TECHNICAL, InterviewPhase.CODING) else "Candidate skipped question.",
                # The control handler has already performed any phase change.
                # Applying this flag again would transition twice.
                should_transition=False,
                detected_candidate_control=control,
            )

        if control == CandidateControlAction.CHANGE_QUESTION:
            if self.context.current_phase in (InterviewPhase.TECHNICAL, InterviewPhase.CODING):
                changes_used = sum(1 for r in self.context.question_records if r.outcome == QuestionOutcome.CHANGED)
                if changes_used >= 1:
                    return StructuredAction(
                        action=ActionEnum.ACKNOWLEDGE,
                        response=msgs["change_question_limit"],
                        reason="Max question changes reached.",
                        detected_candidate_control=control,
                    )
                else:
                    self._record_question_change()
                    self._load_next_technical_question()
                    return StructuredAction(
                        action=ActionEnum.ACKNOWLEDGE,
                        response=msgs["change_question_success"],
                        reason="Candidate changed question.",
                        should_transition=False,
                        detected_candidate_control=control,
                    )

        if control == CandidateControlAction.MOVE_TO_TECHNICAL:
            if self.context.current_phase in (InterviewPhase.BACKGROUND, InterviewPhase.BRIEFING, InterviewPhase.WELCOME, InterviewPhase.TECHNICAL_INTRO):
                if self.context.current_phase != InterviewPhase.TECHNICAL_INTRO:
                    self._transition_to(InterviewPhase.TECHNICAL_INTRO)
                else:
                    self._transition_to(InterviewPhase.TECHNICAL)
                return StructuredAction(
                    action=ActionEnum.ACKNOWLEDGE,
                    response=msgs["transition_technical"],
                    reason=f"Candidate requested {control.value}.",
                    should_transition=True,
                    detected_candidate_control=control,
                )

        if control == CandidateControlAction.REQUEST_HINT:
            return await self._provide_hint()

        if control == CandidateControlAction.REPEAT_QUESTION:
            # Find the last message spoken by the interviewer
            last_agent_msg = None
            for msg in reversed(self.context.conversation_history):
                if msg.role == "assistant":
                    last_agent_msg = msg.content
                    break
                    
            if last_agent_msg:
                return StructuredAction(
                    action=ActionEnum.CLARIFY,
                    response=last_agent_msg,
                    reason="Candidate requested repeat of last interviewer message.",
                    detected_candidate_control=control,
                )
            elif self.context.current_question:
                # Fallback if history is empty but we have a question
                return StructuredAction(
                    action=ActionEnum.CLARIFY,
                    response=self._question_problem_text(self.context.current_question),
                    reason="Candidate requested question repeat.",
                    detected_candidate_control=control,
                )

        if control == CandidateControlAction.REQUEST_CLARIFICATION:
            # Let the LLM handle clarification — but mark it as CLARIFY not HINT
            return None  # Fall through to LLM generation


        return None

    # ─── Hint System ──────────────────────────────────────────────────────

    async def _provide_hint(self) -> StructuredAction:
        """Provides the next structured hint level."""
        q = self.context.current_question
        
        # Calculate limits based on plan and available predefined hints
        plan_max = 4
        if self.context.interview_plan:
            plan_max = self.context.interview_plan.technical_limits.max_hints_per_question
            
        predefined_hints_count = len(q.hints) if q and q.hints else 0
        max_hints = min(plan_max, predefined_hints_count)

        lang = getattr(self.context, "language", "en")
        msgs = SYSTEM_MESSAGES.get(lang, SYSTEM_MESSAGES["en"])
        
        if self.context.hints_used >= max_hints:
            return StructuredAction(
                action=ActionEnum.ACKNOWLEDGE,
                response=msgs["no_hints"],
                reason="Max hints reached or no predefined hints available.",
            )

        hint_level = self.context.hints_used + 1
        hint_text = q.hints[hint_level - 1]
        if lang == "ar" and len(q.hints_ar) >= hint_level:
            hint_text = q.hints_ar[hint_level - 1]

        self.context.hints_used += 1

        # Record assistance
        self.context.assistance_records.append(
            AssistanceRecord(
                assistance_type=AssistanceType.HINT,
                level=hint_level,
                question_id=q.id if q else None,
                candidate_requested=True,
                reason=f"Level {hint_level} hint provided.",
            )
        )

        return StructuredAction(
            action=ActionEnum.HINT,
            response=hint_text,
            reason=f"Hint level {hint_level}/{max_hints}.",
            detected_candidate_control=CandidateControlAction.REQUEST_HINT,
        )

    # ─── Section Completion Policy ────────────────────────────────────────

    def _should_allow_transition(self) -> bool:
        """Determines whether the current section's transition is permitted."""
        phase = self.context.current_phase
        remaining = self.get_remaining_time()

        if phase == InterviewPhase.BACKGROUND:
            progress = self.context.background_progress
            limits = progress.limits

            # Hard maximum reached
            if progress.questions_asked >= limits.max_questions:
                return True
            # Target reached and evidence sufficient
            if progress.questions_asked >= limits.target_questions:
                return True
            # Time pressure: <3 min remaining
            if remaining < 180:
                return True

            return False

        if phase == InterviewPhase.TECHNICAL:
            # TECHNICAL is the approach discussion for the active question.
            # Moving that question into CODING must not depend on how many
            # previous questions were completed or skipped.
            return True

        if phase == InterviewPhase.CODING:
            if remaining < 120:
                return True

            return False

        # For other phases (BRIEFING, WELCOME, TECHNICAL_INTRO, CLOSING), always allow
        return True

    def _must_force_transition(self) -> bool:
        """Determines whether the current section MUST transition due to hard limits."""
        phase = self.context.current_phase
        remaining = self.get_remaining_time()

        if phase == InterviewPhase.BACKGROUND:
            progress = self.context.background_progress
            if progress.questions_asked >= progress.limits.max_questions:
                return True
            if remaining < 180:
                return True

        if phase in (InterviewPhase.TECHNICAL, InterviewPhase.CODING):
            if remaining < 120:
                return True

        return False

    def _get_forced_transition_message(self) -> str:
        """Returns a natural transition append string based on the phase."""
        phase = self.context.current_phase
        if phase == InterviewPhase.BACKGROUND:
            return "Anyway, let's move on to the technical portion of our interview."
        if phase in (InterviewPhase.TECHNICAL, InterviewPhase.CODING):
            return "Alright, in the interest of time, let's wrap up this question and move on."
        return "Let's move on to the next part."

    # ─── Question Management ──────────────────────────────────────────────

    def _record_question_skip(self):
        """Records a skipped question WITHOUT scoring it as incorrect."""
        q = self.context.current_question
        if q:
            record = QuestionRecord(
                question_id=q.id,
                outcome=QuestionOutcome.SKIPPED,
                hints_used=self.context.hints_used,
                followups_used=self.context.followups_used,
                assistance_records=list(self.context.assistance_records),
            )
            self.context.question_records.append(record)
            self.context.technical_progress.questions_skipped += 1
            if q.id not in self.context.technical_question_ids_skipped:
                self.context.technical_question_ids_skipped.append(q.id)

        # Reset per-question counters
        self.context.hints_used = 0
        self.context.followups_used = 0
        self.context.assistance_records = []
        self.context.current_question = None

    def _record_question_change(self):
        """Records a question change, maintaining a strict limit of 1 per interview."""
        q = self.context.current_question
        if q:
            record = QuestionRecord(
                question_id=q.id,
                outcome=QuestionOutcome.CHANGED,
                hints_used=self.context.hints_used,
                followups_used=self.context.followups_used,
                assistance_records=list(self.context.assistance_records),
            )
            self.context.question_records.append(record)

        # Reset per-question counters
        self.context.hints_used = 0
        self.context.followups_used = 0
        self.context.assistance_records = []
        self.context.current_question = None

    def _record_question_completion(self, evaluation: Optional[EvaluationSignal] = None):
        """Records a completed question with its evaluation."""
        q = self.context.current_question
        
        # Select final evaluation (latest from in-flight if not explicitly provided)
        final_eval = evaluation
        if not final_eval and self.context.evaluation_signals:
            final_eval = self.context.evaluation_signals[-1]

        if q:
            record = QuestionRecord(
                question_id=q.id,
                outcome=QuestionOutcome.COMPLETED,
                hints_used=self.context.hints_used,
                followups_used=self.context.followups_used,
                assistance_records=list(self.context.assistance_records),
                evaluation=final_eval,
            )
            self.context.question_records.append(record)
            self.context.technical_question_id_submitted = q.id
            self.context.technical_progress.questions_completed += 1

        self.context.hints_used = 0
        self.context.followups_used = 0
        self.context.assistance_records = []
        self.context.evaluation_signals = []
        self.context.current_question = None

    def load_question(self, question: Question):
        if question.id in self.context.technical_question_ids_seen:
            if self.context.current_question and self.context.current_question.id == question.id:
                return
            raise ValueError(f"Technical question {question.id} was already used in this interview")
        logger.info("[TECH-GEN] Final selected question id=%s title=%s source=%s", question.id, question.title, question.source)
        self.context.current_question = question
        self._question_history.append(question)
        self.context.technical_question_ids_seen.append(question.id)
        self.context.question_index += 1
        self.context.hints_used = 0
        self.context.followups_used = 0
        self.context.assistance_records = []
        self.context.thinking_started_at = datetime.utcnow()

    # ─── LLM Generation ──────────────────────────────────────────────────

    async def _generate_next_action(self) -> StructuredAction:
        """Constructs structured context and prompts for the LLM."""
        phase = self.context.current_phase
        remaining = self.get_remaining_time()
        allowed_actions = get_allowed_actions(phase)
        candidate_controls = get_allowed_candidate_controls(phase)

        profile_str = truncate_prompt_text(
            json.dumps(self.context.candidate_profile, indent=2, default=str),
            MAX_PROFILE_CHARS,
        )
        candidate_name = self.context.candidate_profile.get("full_name", "Candidate")

        system_prompt = ""

        if phase == InterviewPhase.BRIEFING:
            system_prompt = BRIEFING_PROMPT.format(
                identity=_INTERVIEWER_IDENTITY,
                candidate_name=candidate_name,
                role=self.context.role,
                level=self.context.confirmed_level,
                duration_minutes=self._total_duration_sec // 60,
                allowed_actions=allowed_actions,
            )

        elif phase == InterviewPhase.WELCOME:
            interview_focus = self.context.role
            if self.context.job_description:
                interview_focus = f"{self.context.role} role aligned to the provided job description"
            system_prompt = WELCOME_PROMPT.format(
                identity=_INTERVIEWER_IDENTITY,
                candidate_name=candidate_name,
                role=self.context.role,
                interview_focus=interview_focus,
                allowed_actions=allowed_actions,
            )

        elif phase == InterviewPhase.BACKGROUND:
            bg = self.context.background_progress
            system_prompt = BACKGROUND_PROMPT.format(
                identity=_INTERVIEWER_IDENTITY,
                profile=profile_str,
                role=self.context.role,
                job_description=truncate_prompt_text(
                    self.context.job_description,
                    MAX_JOB_DESCRIPTION_CHARS,
                ) or "No specific job description was provided.",
                questions_asked=bg.questions_asked,
                target_questions=bg.limits.target_questions,
                max_questions=bg.limits.max_questions,
                followups_used=self.context.followups_used,
                max_followups=bg.limits.max_followups_per_question,
                time_remaining=remaining,
                candidate_controls=candidate_controls,
                allowed_actions=allowed_actions,
            )

        elif phase == InterviewPhase.TECHNICAL_INTRO:
            q = self.context.current_question
            problem_text = self._question_problem_text(q)
            relevance = (
                f"This {q.competency.replace('_', ' ')} problem was selected for the {self.context.role} role "
                "using the candidate profile and job description."
                if q else "This problem was selected for the interview focus."
            )
            system_prompt = TECHNICAL_INTRO_PROMPT.format(
                identity=_INTERVIEWER_IDENTITY,
                role=self.context.role,
                level=self.context.confirmed_level,
                problem=problem_text,
                relevance=relevance,
                allowed_actions=allowed_actions,
            )

        elif phase in (InterviewPhase.TECHNICAL, InterviewPhase.CODING):
            q = self.context.current_question
            problem_text = self._question_problem_text(q)
            flow_state = "APPROACH_DISCUSSION" if phase == InterviewPhase.TECHNICAL else "CODING"
            tech = self.context.technical_progress

            system_prompt = TECHNICAL_PROMPT.format(
                identity=_INTERVIEWER_IDENTITY,
                problem=problem_text,
                role=self.context.role,
                candidate_context=truncate_prompt_text(profile_str, 1800),
                job_description=truncate_prompt_text(self.context.job_description, 1800) or "No specific job description was provided.",
                flow_state=flow_state,
                hints_used=self.context.hints_used,
                max_hints=tech.limits.max_hints_per_question,
                tech_completed=tech.questions_completed,
                tech_target=tech.limits.target_questions,
                tech_max=tech.limits.max_questions,
                followups_used=self.context.followups_used,
                max_followups=tech.limits.max_followups_per_question,
                time_remaining=remaining,
                candidate_controls=candidate_controls,
                allowed_actions=allowed_actions,
            )

        elif phase == InterviewPhase.CLOSING:
            total_completed = len([
                r for r in self.context.question_records
                if r.outcome == QuestionOutcome.COMPLETED
            ])
            system_prompt = CLOSING_PROMPT.format(
                identity=_INTERVIEWER_IDENTITY,
                candidate_name=candidate_name,
                total_completed=total_completed,
                allowed_actions=allowed_actions,
            )

        else:
            system_prompt = (
                f"{_INTERVIEWER_IDENTITY}\n\n"
                f"CURRENT PHASE: {phase.value}\n"
                f"Allowed actions: {allowed_actions}\n"
                f"Guide the conversation."
            )

        # Voice brevity
        system_prompt += (
            "\n\nVOICE CONSTRAINT: You are speaking via a real-time voice pipeline. "
            "Keep responses to 1-2 concise sentences. Do NOT monologue."
        )

        lang = getattr(self.context, "language", "en")
        language_instruction = LANGUAGE_INSTRUCTIONS.get(lang)
        if not language_instruction:
            logger.warning(f"Unsupported language '{lang}', falling back to 'en'.")
            language_instruction = LANGUAGE_INSTRUCTIONS["en"]
            
        system_prompt += f"\n\n{language_instruction}"

        # Convert history for LLM (last 10 messages)
        messages = []
        history_chars = 0
        for msg in reversed(self.context.conversation_history[-10:]):
            content = truncate_prompt_text(msg.content, MAX_MESSAGE_CHARS)
            if history_chars + len(content) > MAX_HISTORY_CHARS:
                break
            messages.append({"role": msg.role, "content": content})
            history_chars += len(content)
        messages.reverse()

        structured_action = await self.llm.generate_structured(
            system_prompt=system_prompt,
            messages=messages,
            response_model=StructuredAction,
        )

        return structured_action

    async def generate_final_evaluation(self) -> Optional[DetailedEvaluation]:
        """Evaluate only the evidence captured in this interview session."""
        if self.context.final_evaluation is not None:
            return self.context.final_evaluation

        evidence = {
            "role": self.context.role,
            "level": self.context.confirmed_level,
            "technical_submission": self.context.technical_submission,
            "question_records": [r.model_dump(mode="json") for r in self.context.question_records],
            "transcript": [
                {"speaker": m.role, "text": truncate_prompt_text(m.content, MAX_MESSAGE_CHARS)}
                for m in self.context.conversation_history
                if m.role in ("user", "assistant")
            ][-40:],
        }
        prompt = (
            EVALUATOR_PROMPT
            + "\n\nUse only the supplied evidence. Distinguish explicit statements from inference. "
            + "When evidence is missing, say so and leave the score null. Return a concise structured report."
        )
        try:
            evaluation = await self.llm.generate_structured(
                system_prompt=prompt,
                messages=[{"role": "user", "content": json.dumps(evidence, ensure_ascii=False)}],
                response_model=DetailedEvaluation,
            )
            self.context.final_evaluation = evaluation
            logger.info("[EVALUATION] generated status=COMPLETED")
            return evaluation
        except Exception:
            logger.exception("[EVALUATION] generation_failed")
            return None

    # ─── Apply Action Effects ─────────────────────────────────────────────

    async def _apply_action(self, action: StructuredAction):
        """Updates runtime state based on the LLM's selected action."""
        phase = self.context.current_phase

        if action.action == ActionEnum.HINT:
            if action.detected_candidate_control != CandidateControlAction.REQUEST_HINT:
                # LLM spontaneously gave a hint
                self.context.hints_used += 1

        if action.action == ActionEnum.FOLLOW_UP:
            self.context.followups_used += 1

        if action.action == ActionEnum.ASK and phase == InterviewPhase.BACKGROUND:
            self.context.background_progress.questions_asked += 1

        if action.evaluation:
            self.context.evaluation_signals.append(action.evaluation)

        if action.action == ActionEnum.TRANSITION and action.should_transition:
            self._handle_automatic_transition()
            
        if action.action == ActionEnum.END:
            if self.context.current_phase != InterviewPhase.COMPLETED:
                self._transition_to(InterviewPhase.COMPLETED)

    def _handle_automatic_transition(self):
        """Advances the state machine forward when TRANSITION is selected."""
        current = self.context.current_phase

        if current == InterviewPhase.BRIEFING:
            self._transition_to(InterviewPhase.WELCOME)
        elif current == InterviewPhase.WELCOME:
            self._transition_to(InterviewPhase.BACKGROUND)
        elif current == InterviewPhase.BACKGROUND:
            self.context.background_progress.completed = True
            self._transition_to(InterviewPhase.TECHNICAL_INTRO)
        elif current == InterviewPhase.TECHNICAL_INTRO:
            self._transition_to(InterviewPhase.TECHNICAL)
        elif current == InterviewPhase.TECHNICAL:
            self._transition_to(InterviewPhase.CODING)
        elif current == InterviewPhase.CODING:
            # There is one technical problem. Any deterministic completion of
            # the coding stage ends technical work; it never loads another.
            self._record_question_completion()
            self._transition_to(InterviewPhase.CLOSING)
        elif current == InterviewPhase.CLOSING:
            self._transition_to(InterviewPhase.COMPLETED)

    # ─── Exposed Contract ─────────────────────────────────────────────────

    def get_interview_state_contract(self) -> dict:
        """Returns the current interview state for the frontend/UI."""
        return {
            "phase": self.context.current_phase.value,
            "question_id": self.context.current_question.id if self.context.current_question else None,
            "allowed_actions": get_allowed_actions(self.context.current_phase),
            "allowed_controls": get_allowed_candidate_controls(self.context.current_phase),
            "time_remaining_seconds": self.get_remaining_time(),
            "background_progress": {
                "asked": self.context.background_progress.questions_asked,
                "target": self.context.background_progress.limits.target_questions,
                "max": self.context.background_progress.limits.max_questions,
                "completed": self.context.background_progress.completed,
            },
            "technical_progress": {
                "completed": self.context.technical_progress.questions_completed,
                "skipped": self.context.technical_progress.questions_skipped,
                "target": self.context.technical_progress.limits.target_questions,
                "max": self.context.technical_progress.limits.max_questions,
            },
        }
