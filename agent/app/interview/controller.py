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
from typing import Optional, List
from datetime import datetime

from app.interview.models import (
    InterviewRuntimeContext, InterviewPhase, InterviewPlan,
    ActionEnum, CandidateControlAction,
    StructuredAction, Message, Question, EvaluationSignal,
    SectionProgress, SectionLimits, QuestionRecord, QuestionOutcome,
    AssistanceRecord, AssistanceType,
)
from app.interview.state_machine import (
    is_transition_valid, is_action_valid, is_candidate_control_valid,
    get_allowed_actions, get_allowed_candidate_controls,
)
from app.llm.provider import LLMProvider
from app.llm.prompts import (
    BRIEFING_PROMPT, WELCOME_PROMPT, BACKGROUND_PROMPT,
    TECHNICAL_INTRO_PROMPT, TECHNICAL_PROMPT, CLOSING_PROMPT,
    EVALUATOR_PROMPT, _INTERVIEWER_IDENTITY,
)
from app.interview.persistence import InterviewPersistence

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

    # ─── Lifecycle ─────────────────────────────────────────────────────────

    def start_interview(self):
        """Starts the deterministic interview timer and transitions to BRIEFING."""
        if not self._start_time:
            self._start_time = time.time()
            self.context.interview_started_at = datetime.utcnow()
        self._transition_to(InterviewPhase.BRIEFING)

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
        else:
            raise ValueError(
                f"Invalid transition from {self.context.current_phase} to {target_phase}"
            )

    # ─── Message Management ────────────────────────────────────────────────

    def append_message(self, role: str, content: str):
        self.context.conversation_history.append(
            Message(role=role, content=content)
        )

    def next_message_seq(self) -> int:
        self.context.message_sequence += 1
        return self.context.message_sequence

    def next_event_seq(self) -> int:
        self.context.event_sequence += 1
        return self.context.event_sequence

    # ─── Main Interaction Loop ─────────────────────────────────────────────

    async def process_candidate_input(self, user_text: str) -> StructuredAction:
        """
        The main interaction loop. Accepts candidate text, evaluates time,
        checks for candidate control intents, generates AI response.
        """
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
            handled = await self._handle_candidate_control(control_action)
            if handled:
                return handled

        # Generate LLM response
        action = await self._generate_next_action()

        # Validate action against state machine
        if not is_action_valid(self.context.current_phase, action.action):
            action.action = ActionEnum.ACKNOWLEDGE
            action.response = "I understand. Let's continue."

        # Check for section completion before applying the action
        if action.action == ActionEnum.TRANSITION or action.should_transition:
            if self._should_allow_transition():
                action.action = ActionEnum.TRANSITION
                action.should_transition = True
            else:
                # LLM wanted to transition but section isn't done yet
                action.action = ActionEnum.ASK
                action.should_transition = False

        # Check for LLM-detected candidate control
        if action.detected_candidate_control:
            if is_candidate_control_valid(
                self.context.current_phase, action.detected_candidate_control
            ):
                handled = await self._handle_candidate_control(
                    action.detected_candidate_control
                )
                if handled:
                    return handled

        # Apply action effects
        await self._apply_action(action)

        # Append AI message
        self.append_message("assistant", action.response)

        # Checkpoint
        await self.persistence.save_checkpoint(self.context)

        return action

    # ─── Candidate Control Detection ──────────────────────────────────────

    def _detect_candidate_control(self, text: str) -> Optional[CandidateControlAction]:
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
            "move to the next", "let's skip this"
        ]):
            return CandidateControlAction.SKIP_QUESTION

        # Move to technical
        if any(phrase in lower for phrase in [
            "move to technical", "go to technical", "skip to technical",
            "start the technical", "let's do technical",
            "move to the technical part", "move to the technical section"
        ]):
            return CandidateControlAction.MOVE_TO_TECHNICAL

        # Skip section
        if any(phrase in lower for phrase in [
            "skip this section", "skip the background", "skip background",
            "let's move on", "move on to the next section"
        ]):
            return CandidateControlAction.SKIP_SECTION

        # Hint
        if any(phrase in lower for phrase in [
            "give me a hint", "can i get a hint", "i need a hint",
            "hint please", "help me"
        ]):
            return CandidateControlAction.REQUEST_HINT

        # Repeat
        if any(phrase in lower for phrase in [
            "repeat the question", "say that again", "can you repeat",
            "repeat please", "what was the question"
        ]):
            return CandidateControlAction.REPEAT_QUESTION

        # Clarification
        if any(phrase in lower for phrase in [
            "explain the question", "what does that mean",
            "can you clarify", "i don't understand the question",
            "what exactly", "explain what"
        ]):
            return CandidateControlAction.REQUEST_CLARIFICATION

        return None

    # ─── Candidate Control Handlers ───────────────────────────────────────

    async def _handle_candidate_control(
        self, control: CandidateControlAction
    ) -> Optional[StructuredAction]:
        """Deterministically handles candidate control actions."""
        phase = self.context.current_phase

        if not is_candidate_control_valid(phase, control):
            return None

        if control == CandidateControlAction.END_INTERVIEW:
            self._transition_to(InterviewPhase.CLOSING)
            return StructuredAction(
                action=ActionEnum.TRANSITION,
                response="Understood. I'll wrap up the interview now. Thank you for your time today.",
                reason="Candidate requested early end.",
                should_transition=True,
                detected_candidate_control=control,
            )

        if control == CandidateControlAction.SKIP_QUESTION:
            self._record_question_skip()
            return StructuredAction(
                action=ActionEnum.ACKNOWLEDGE,
                response="No problem, let's move on to the next question.",
                reason="Candidate skipped question.",
                detected_candidate_control=control,
            )

        if control in (
            CandidateControlAction.SKIP_SECTION,
            CandidateControlAction.MOVE_TO_TECHNICAL,
        ):
            if phase == InterviewPhase.BACKGROUND:
                self.context.background_progress.completed = True
                self._transition_to(InterviewPhase.TECHNICAL_INTRO)
                return StructuredAction(
                    action=ActionEnum.TRANSITION,
                    response="Absolutely. Let's move on to the technical portion.",
                    reason=f"Candidate requested {control.value}.",
                    should_transition=True,
                    detected_candidate_control=control,
                )

        if control == CandidateControlAction.REQUEST_HINT:
            return await self._provide_hint()

        if control == CandidateControlAction.REPEAT_QUESTION:
            if self.context.current_question:
                return StructuredAction(
                    action=ActionEnum.CLARIFY,
                    response=f"Sure, the question is: {self.context.current_question.problem_statement}",
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
        max_hints = 4
        if self.context.interview_plan:
            max_hints = self.context.interview_plan.technical_limits.max_hints_per_question

        if self.context.hints_used >= max_hints:
            return StructuredAction(
                action=ActionEnum.ACKNOWLEDGE,
                response="I've already provided the maximum number of hints for this question. Try your best with what we've discussed.",
                reason="Max hints reached.",
            )

        hint_level = self.context.hints_used + 1
        hint_text = ""

        if q and q.hints and hint_level <= len(q.hints):
            hint_text = q.hints[hint_level - 1]
        else:
            # Generate hint via LLM if pre-defined hints are exhausted
            hint_text = f"Think about what data structure would give you efficient lookups here."

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

        if phase in (InterviewPhase.TECHNICAL, InterviewPhase.CODING):
            progress = self.context.technical_progress
            limits = progress.limits

            if progress.questions_completed + progress.questions_skipped >= limits.max_questions:
                return True
            if progress.questions_completed >= limits.target_questions:
                return True
            if remaining < 120:
                return True

            return False

        # For other phases (BRIEFING, WELCOME, TECHNICAL_INTRO, CLOSING), always allow
        return True

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

        # Reset per-question counters
        self.context.hints_used = 0
        self.context.followups_used = 0
        self.context.assistance_records = []
        self.context.current_question = None

    def _record_question_completion(self, evaluation: Optional[EvaluationSignal] = None):
        """Records a completed question with its evaluation."""
        q = self.context.current_question
        if q:
            record = QuestionRecord(
                question_id=q.id,
                outcome=QuestionOutcome.COMPLETED,
                hints_used=self.context.hints_used,
                followups_used=self.context.followups_used,
                assistance_records=list(self.context.assistance_records),
                evaluation=evaluation,
            )
            self.context.question_records.append(record)
            self.context.technical_progress.questions_completed += 1

        self.context.hints_used = 0
        self.context.followups_used = 0
        self.context.assistance_records = []
        self.context.current_question = None

    def load_question(self, question: Question):
        self.context.current_question = question
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

        profile_str = json.dumps(self.context.candidate_profile, indent=2, default=str)
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
            system_prompt = WELCOME_PROMPT.format(
                identity=_INTERVIEWER_IDENTITY,
                candidate_name=candidate_name,
                role=self.context.role,
                allowed_actions=allowed_actions,
            )

        elif phase == InterviewPhase.BACKGROUND:
            bg = self.context.background_progress
            system_prompt = BACKGROUND_PROMPT.format(
                identity=_INTERVIEWER_IDENTITY,
                profile=profile_str,
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
            system_prompt = TECHNICAL_INTRO_PROMPT.format(
                identity=_INTERVIEWER_IDENTITY,
                role=self.context.role,
                level=self.context.confirmed_level,
                allowed_actions=allowed_actions,
            )

        elif phase in (InterviewPhase.TECHNICAL, InterviewPhase.CODING):
            q = self.context.current_question
            problem_text = q.problem_statement if q else "No problem loaded."
            flow_state = "APPROACH_DISCUSSION" if phase == InterviewPhase.TECHNICAL else "CODING"
            tech = self.context.technical_progress

            system_prompt = TECHNICAL_PROMPT.format(
                identity=_INTERVIEWER_IDENTITY,
                problem=problem_text,
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

        # Convert history for LLM (last 10 messages)
        messages = [
            {"role": msg.role, "content": msg.content}
            for msg in self.context.conversation_history[-10:]
        ]

        structured_action = await self.llm.generate_structured(
            system_prompt=system_prompt,
            messages=messages,
            response_model=StructuredAction,
        )

        return structured_action

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

        if action.action == ActionEnum.TRANSITION:
            self._handle_automatic_transition()

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
            # Question done — record and potentially move to next question or closing
            self._record_question_completion()
            remaining = self.get_remaining_time()
            tech = self.context.technical_progress

            if (
                tech.questions_completed >= tech.limits.target_questions
                or tech.questions_completed + tech.questions_skipped >= tech.limits.max_questions
                or remaining < 120
            ):
                self._transition_to(InterviewPhase.CLOSING)
            else:
                self._transition_to(InterviewPhase.TECHNICAL)
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
