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

from agent.interview.models import (
    InterviewRuntimeContext, InterviewPhase, InterviewPlan,
    ActionEnum, CandidateControlAction,
    StructuredAction, Message, Question, EvaluationSignal,
    SectionProgress, SectionLimits, QuestionRecord, QuestionOutcome,
    AssistanceRecord, AssistanceType, DetailedEvaluation,
    OrderedSectionProgress,
)
from agent.interview.state_machine import (
    is_transition_valid, is_action_valid, is_candidate_control_valid,
    get_allowed_actions, get_allowed_candidate_controls,
)
from agent.interview.questions import get_questions_by_competency
from agent.llm.provider import LLMProvider
from agent.llm.prompts import (
    BRIEFING_PROMPT, WELCOME_PROMPT, BACKGROUND_PROMPT, CORE_QUESTION_PROMPT,
    CORE_CODING_QUESTION_PROMPT, CORE_MCQ_QUESTION_PROMPT,
    TECHNICAL_INTRO_PROMPT, TECHNICAL_PROMPT, CLOSING_PROMPT,
    EVALUATOR_PROMPT, _INTERVIEWER_IDENTITY,
    LANGUAGE_INSTRUCTIONS, SYSTEM_MESSAGES
)
from agent.interview.persistence import InterviewPersistence
from agent.interview.input_limits import (
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
        from agent.interview.questions import QUESTION_BANK
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

    def _start_section_clock(self, section: OrderedSectionProgress) -> None:
        """WR-A (docs/section-pacing-architecture.md): reseed the timer to
        the given core section's own budget, so get_remaining_time()/
        _time_tier() — unchanged below, byte-identical formulas — operate
        per-section instead of whole-interview. NOT CALLED ANYWHERE YET:
        this is the mechanism only. WR-C is the one that calls it, at the
        exact section-boundary point where the new waiting-room phase exits
        back into BACKGROUND for the next section (mirroring
        start_interview()'s own lazy-_start_time pattern below). Until
        WR-B/C build that phase and wire this in, every currently-running
        session — legacy or B2B — is completely unaffected: dead code with
        no call site changes nothing.

        Falls back to the CURRENT remaining whole-interview time if the
        section has no budget set (None) — should not happen for a
        published B2B session (publish_job requires it), but this method
        must not silently zero out the clock for a legacy/malformed
        session that reaches it by mistake.
        """
        if section.time_budget_minutes is None:
            return
        self._total_duration_sec = section.time_budget_minutes * 60
        self._start_time = None

    async def _transition_out_of_waiting_room(self, auto: bool) -> None:
        """WR-C: the single effect of leaving WAITING_ROOM, shared by the
        candidate-initiated PROCEED_TO_NEXT_SECTION handler and the
        auto-timeout callback (voice_adapter.py) — same underlying outcome
        (advance into the next section with a freshly reseeded clock),
        logged distinctly (auto vs candidate) so a future transcript/event
        view can tell "candidate was ready" from "candidate went AFK and
        got auto-advanced" apart, rather than both looking identical.

        _active_core_section() is only called AFTER _transition_to(
        BACKGROUND) — it's phase-gated to only return non-None while
        current_phase == BACKGROUND by design (see its own docstring);
        calling it before the transition here would silently reseed
        nothing, exactly the bug caught by WR-A's own live verification.
        """
        self._transition_to(InterviewPhase.BACKGROUND)
        next_section = self._active_core_section()
        if next_section is not None:
            self._start_section_clock(next_section)

        self.context.event_sequence += 1
        await self.persistence.save_event(
            session_id=self.context.session_id,
            sequence=self.context.event_sequence,
            event_type="WAITING_ROOM_AUTO_PROCEED" if auto else "WAITING_ROOM_CANDIDATE_PROCEED",
            phase=self.context.current_phase.value,
        )

    # ─── Phase Transitions ─────────────────────────────────────────────────

    def _transition_to(self, target_phase: InterviewPhase):
        if is_transition_valid(self.context.current_phase, target_phase):
            logger.info(f"Phase transition: {self.context.current_phase.value} -> {target_phase.value}")
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
        from agent.interview.questions import QUESTION_BANK
        
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
        from agent.interview.questions import rank_questions_for_context
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
            CandidateControlAction.END_SECTION_EARLY,
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

        # WR-C: WAITING_ROOM is deliberately silent — VALID_ACTIONS_PER_PHASE
        # for it is empty by design (no LLM generation happens in this
        # phase at all). Incidental candidate speech while waiting
        # (background noise, chit-chat) must not reach LLM generation built
        # for conversational phases, and critically must NOT be subject to
        # the time-expired check below either — the waiting room is
        # explicitly free/unclocked (CURRENT_DECISIONS.md), and the just-
        # finished section's clock is deliberately left stale/unreseeded
        # until the candidate actually leaves (_transition_out_of_waiting_
        # room), so it could easily already read as "expired" while
        # legitimately waiting. The only two ways out are
        # PROCEED_TO_NEXT_SECTION (via the UI-command path, not this one)
        # and the auto-timeout (voice_adapter.py, not this method at all).
        if self.context.current_phase == InterviewPhase.WAITING_ROOM:
            return StructuredAction(
                action=ActionEnum.ACKNOWLEDGE,
                response="",
                reason="WAITING_ROOM is non-conversational; awaiting PROCEED_TO_NEXT_SECTION or the auto-timeout.",
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

        # Bug fix (2026-09-03, real-evidence report): a 1-question VERBAL
        # section produced 6 questions in a live test before a human had to
        # manually end the session. Root cause -- an ASK past the first turn
        # of a core question is functionally a follow-up, but the follow-up
        # cap below only ever checked action.action == FOLLOW_UP. A model
        # that drifts into tagging a deep-dive as "another question" (ASK,
        # which has no count-based limit of its own -- valid throughout all
        # of BACKGROUND per state_machine.py) sails straight past the cap
        # entirely, and _must_force_transition() offers no backstop for the
        # ordered core-question flow either (purely time-tier-based, so a
        # section with a comfortable time budget never forces a move on).
        # Reclassifying here, before the existing cap check, means a
        # mislabeled ASK gets caught by that same already-proven enforcement
        # rather than needing a second, parallel cap. Scoped to the ordered
        # core-question flow specifically (core_section is not None) --
        # the legacy free-form BACKGROUND path has no per-question
        # first-turn/subsequent-turn tracking to key this off of.
        if action.action == ActionEnum.ASK:
            core_section = self._active_core_section()
            if core_section is not None and core_section.current_question_asked:
                logger.info(
                    "ASK past the first turn of core question id=%s -- "
                    "reclassifying as FOLLOW_UP so the cap below applies.",
                    core_section.current_question.id if core_section.current_question else None,
                )
                action.action = ActionEnum.FOLLOW_UP

        # Enforce the follow-up cap deterministically (Phase 7C). Previously
        # advisory-only: the LLM was only ever told the current count and max
        # via prompt text and could exceed it. This now hard-blocks a further
        # FOLLOW_UP once the effective cap is reached, for BOTH the legacy
        # BACKGROUND/TECHNICAL/CODING flow and (once Phase 7D populates
        # context.sections) the new ordered core-question flow.
        if action.action == ActionEnum.FOLLOW_UP:
            max_followups = self._current_max_followups()
            if self.context.followups_used >= max_followups:
                logger.info(
                    f"Follow-up cap reached ({self.context.followups_used}/{max_followups}) "
                    f"in phase {self.context.current_phase.value}. Downgrading FOLLOW_UP to ACKNOWLEDGE."
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

                # 7F-scoping addendum: for the ordered core-question flow,
                # _should_allow_transition() only ever says no because the
                # current question hasn't been asked yet (its whole check is
                # `current_question_asked`) — so we know exactly what should
                # be said instead of trusting whatever text the LLM
                # generated for its (rejected) TRANSITION attempt. Unlike
                # legacy free-form BACKGROUND, a core question's exact text
                # is always known, so this deterministic fallback is safe
                # here specifically.
                core_section = self._active_core_section()
                if core_section is not None and core_section.current_question is not None:
                    action.response = self._question_problem_text(core_section.current_question)


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

        # Part 1 (rebrand work, 2026-08-26): mirrors _provide_hint()'s exact
        # core_section-aware pattern. The legacy single-question flow keeps
        # current_question on self.context; the Phase 9 ordered flow (all
        # three section types, asked during phase BACKGROUND via
        # _active_core_section()) never populates that field — only
        # core_section.current_question does. Without this, a CODING/MCQ
        # ordered-flow question never reached the frontend's current_question
        # at all — see docs/phase9-architecture.md's 9H section.
        core_section = self._active_core_section()
        q = core_section.current_question if core_section is not None else ctx.current_question

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
        if q:
            # Audit fix (2026-08-27): q.config is the real, un-coerced
            # CodingConfig/MCQConfig dict, and for MCQ that dict includes
            # correct_answers (needed server-side for SUBMIT_MCQ_ANSWER
            # grading — see process_ui_command's MCQ branch). It must never
            # reach the candidate's own data channel — this strips it from
            # the copy that goes into the wire payload below, unconditionally
            # (not gated on section-type detection: correct_answers never
            # legitimately belongs in anything sent to the candidate, and
            # non-MCQ configs never carry that key anyway, so this is a
            # no-op for VERBAL/CODING/legacy questions).
            sanitized_config = {
                k: v for k, v in (q.config or {}).items() if k != "correct_answers"
            }
            q_data = {
                "id": q.id,
                "title": self._question_title_text(q),
                "problem_statement": self._question_problem_text(q),
                "difficulty": q.difficulty,
                "competency": q.competency,
                "expected_concepts": q.expected_concepts,
                "hints": q.hints,
                "follow_up_topics": q.follow_up_topics,
                "time_budget_minutes": q.time_budget_minutes,
                "coding_required": q.coding_required,
                "examples": q.examples,
                "constraints": q.constraints,
                "starter_code": q.starter_code,
                "test_cases": q.test_cases,
                "supported_languages": q.supported_languages,
                "hints_used": ctx.hints_used,
                "source": q.source,
                # Part 1: the real, un-coerced CodingConfig/MCQConfig dict
                # (empty {} for VERBAL/legacy questions). MCQ has no typed
                # home on Question at all (no options/correct_answers
                # fields) — this is the only way MCQ data reaches the
                # frontend. For CODING, this is now the source of truth for
                # starter_code/supported_languages/constraints (the typed
                # fields above stay at their legacy Dict[str,str]/List[str]
                # defaults for ordered-flow questions — see
                # build_core_sections() in main.py and Part 3's frontend
                # rewrite, which reads from here instead).
                "config": sanitized_config,
            }
            
        allowed_controls = list(get_allowed_candidate_controls(ctx.current_phase))

        # Audit fix (2026-08-27): the phase-only lookup above has no
        # awareness of the active core section type, unlike `q` above (the
        # 9H fix). VALID_CANDIDATE_CONTROLS_PER_PHASE[BACKGROUND] carries
        # SKIP_SECTION/MOVE_TO_TECHNICAL for the legacy single-question
        # BACKGROUND flow, where they're meaningful — but
        # process_ui_command's SKIP_SECTION/MOVE_TO_TECHNICAL branches
        # reject both outright for any ordered core section (VERBAL/CODING/
        # MCQ; see _has_pending_core_content()'s docstring). Those two stay
        # stripped here so their buttons don't invite a click that silently
        # no-ops. SKIP_QUESTION is deliberately NOT in this list — the
        # 2026-08-27 policy reversal (see process_ui_command's
        # SKIP_QUESTION/SKIP_SECTION branch and CURRENT_DECISIONS.md) made
        # it a real, working per-question skip for ordered core sections
        # too, so it stays advertised. REQUEST_HINT is excluded specifically
        # for MCQ, which is 0-hints by design (CURRENT_DECISIONS.md) —
        # _provide_hint() already degrades gracefully to a "no hints
        # available" response there, but the button shouldn't invite the
        # click in the first place.
        if core_section is not None:
            for stale_control in (
                CandidateControlAction.SKIP_SECTION,
                CandidateControlAction.MOVE_TO_TECHNICAL,
            ):
                if stale_control.value in allowed_controls:
                    allowed_controls.remove(stale_control.value)
            if core_section.section_type == "MCQ" and CandidateControlAction.REQUEST_HINT.value in allowed_controls:
                allowed_controls.remove(CandidateControlAction.REQUEST_HINT.value)

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

        # WR-D: Progress label for the core sections
        ordered_sections = list(ctx.sections.values())
        completed_count = sum(1 for s in ordered_sections if s.completed)
        active = self._active_core_section()
        
        sections_progress = {
            "total": len(ordered_sections),
            "completed": completed_count,
            "current_index": completed_count + 1 if active is not None else None,
            "current_section_type": active.section_type if active is not None else None,
        }

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
            "sections_progress": sections_progress,
            # WR-C: WAITING_ROOM is explicitly free/unclocked
            # (CURRENT_DECISIONS.md) — the just-finished section's clock is
            # deliberately left stale/unreseeded until the candidate
            # actually leaves, so get_remaining_time() would otherwise
            # report a number ticking down toward (and clamped at) zero
            # while the candidate is legitimately on a break. None here,
            # not a decaying/misleading figure — the frontend shows a
            # waiting-room screen instead of a countdown for this phase.
            "time_remaining_seconds": (
                None if ctx.current_phase == InterviewPhase.WAITING_ROOM
                else self.get_remaining_time()
            )
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

        # PR-B/PR-D/Part 2 (docs/proctoring-architecture.md): browser-detected
        # integrity telemetry — fullscreen-exit-past-grace, tab-hidden,
        # window-blurred (PR-B), PR-D's face-presence signals, plus Part 2's
        # head-pose signal HEAD_DOWN_SUSPECTED (2026-09-02, signed-off
        # one-line extension of this existing branch — no new logic, the
        # client-side useFaceDetectionMonitor.ts already debounces/
        # edge-triggers before this ever fires).
        # Purely additive: logged through the exact same InterviewEvent
        # mechanism/sequence counter every other in-session event already
        # uses (see _transition_out_of_waiting_room's WAITING_ROOM_AUTO_
        # PROCEED for the identical pattern), no LLM turn, no state change,
        # no ack — these feed the later aggregate flag, not a verdict.
        # Defensively no-op post-COMPLETED (a late/duplicate message after
        # teardown), same spirit as the END_INTERVIEW special case above.
        if command in ("FULLSCREEN_EXITED", "TAB_HIDDEN", "WINDOW_BLURRED", "NO_FACE_DETECTED", "MULTIPLE_FACES_DETECTED", "HEAD_DOWN_SUSPECTED"):
            if self.context.current_phase == InterviewPhase.COMPLETED:
                return None
            metadata = payload.get("payload") if isinstance(payload, dict) else None
            await self.persistence.save_event(
                session_id=self.context.session_id,
                sequence=self.next_event_seq(),
                event_type=command,
                phase=self.context.current_phase.value,
                metadata=metadata if isinstance(metadata, dict) else None,
            )
            return None

        if command == "SUBMIT_CODE":
            # Phase 9C: the ordered core-question flow runs a CODING question
            # under phase BACKGROUND (same as VERBAL/MCQ — see
            # _active_core_section()), not TECHNICAL/CODING. Detect that case
            # explicitly rather than only ever accepting the legacy phases,
            # which is what this guard did before 9C (silently returning
            # None -- dropping the submission -- for any ordered CODING
            # question).
            core_section = self._active_core_section()
            is_ordered_coding = core_section is not None and core_section.section_type == "CODING"
            if not is_ordered_coding and self.context.current_phase not in (
                InterviewPhase.TECHNICAL, InterviewPhase.CODING
            ):
                return None

            submission = payload.get("payload", payload or {}) if isinstance(payload, dict) else {}
            if isinstance(submission, dict):
                self.context.technical_submission = {
                    "code": str(submission.get("code", ""))[:12000],
                    "language": str(submission.get("language", ""))[:40],
                }
            response = SYSTEM_MESSAGES.get(self.context.language, SYSTEM_MESSAGES["en"])["submit_code"]

            if is_ordered_coding:
                # A submission is the deterministic "this core question is
                # done" signal for CODING -- equivalent to a VERBAL
                # TRANSITION. Reuses _advance_core_question() (9B) rather
                # than _record_question_completion(), which only knows
                # about the legacy self.context.current_question field.
                # Advances to the NEXT core question (or CLOSING once none
                # remain) instead of jumping straight to CLOSING regardless
                # of what's left -- the legacy branch's behavior is only
                # correct there because CODING is always its last phase.
                submitted_id = core_section.current_question.id if core_section.current_question else None
                core_section.current_question_asked = True
                # WR-C: same section-boundary branching as
                # _handle_automatic_transition()'s BACKGROUND case — a
                # submission can exhaust a section exactly the same way a
                # VERBAL TRANSITION can, and must not silently walk into
                # the next section (9B's invisible behavior) when one
                # remains.
                just_finished = core_section
                self._advance_core_question()
                next_section = self._active_core_section()
                ends_interview = next_section is None
                if ends_interview:
                    self._transition_to(InterviewPhase.CLOSING)
                elif just_finished.completed:
                    self._transition_to(InterviewPhase.WAITING_ROOM)
                logger.info("[CODING] Submitted ordered core question id=%s", submitted_id)
                handled = StructuredAction(
                    action=ActionEnum.ACKNOWLEDGE,
                    # Audit fix (2026-08-27): when this submission is the
                    # very last thing in the interview, speaking the
                    # generic "submit_code" ack ("Got it, let's continue")
                    # immediately before the chained CLOSING turn's real
                    # goodbye produced two back-to-back agent messages —
                    # not smooth. Empty response here lets voice_adapter.py
                    # go straight to the one real goodbye instead. Mid-
                    # interview (next question, same or different section),
                    # the ack stays exactly as before — CODING remains a
                    # normal, conversational flow throughout solving.
                    response="" if ends_interview else response,
                    reason="Candidate submitted the ordered CODING core question.",
                    should_transition=False,
                )
            else:
                submitted_id = self.context.current_question.id if self.context.current_question else None
                self._record_question_completion()
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

        if command == "SUBMIT_MCQ_ANSWER":
            # Phase 9C: MCQ answer submission. Per CURRENT_DECISIONS.md, MCQ
            # is "0 -- binary right/wrong, submit and grade. No live
            # interaction during answering beyond selecting an option" --
            # deterministic, not an LLM judgment call, so this mirrors
            # SUBMIT_CODE's explicit-data-channel-command shape rather than
            # routing through the free-form conversational/LLM path (which
            # can't guarantee a gradeable, unambiguous answer). No new
            # schema: the grading result is recorded as an EvaluationSignal,
            # the same slot _advance_core_question() already reads for every
            # other section type.
            core_section = self._active_core_section()
            if core_section is None or core_section.section_type != "MCQ" or core_section.current_question is None:
                return None

            question = core_section.current_question
            submission = payload.get("payload", payload or {}) if isinstance(payload, dict) else {}
            raw_selected = submission.get("selected_option_ids") if isinstance(submission, dict) else None
            selected_ids = [str(s) for s in raw_selected][:10] if isinstance(raw_selected, list) else []

            correct_ids = set(question.config.get("correct_answers") or [])
            is_correct = bool(selected_ids) and set(selected_ids) == correct_ids

            self.context.evaluation_signals.append(EvaluationSignal(
                evidence=(
                    f"MCQ answer submitted for question_id={question.id}: "
                    f"selected={selected_ids}, correct_answers={sorted(correct_ids)}, "
                    f"result={'CORRECT' if is_correct else 'INCORRECT'}."
                ),
            ))

            core_section.current_question_asked = True
            # WR-C: same section-boundary branching as SUBMIT_CODE above
            # and _handle_automatic_transition()'s BACKGROUND case.
            just_finished = core_section
            self._advance_core_question()
            next_section = self._active_core_section()
            if next_section is None:
                self._transition_to(InterviewPhase.CLOSING)
            elif just_finished.completed:
                self._transition_to(InterviewPhase.WAITING_ROOM)
            logger.info("[MCQ] Submitted answer question_id=%s correct=%s", question.id, is_correct)

            handled = StructuredAction(
                action=ActionEnum.ACKNOWLEDGE,
                # Audit fix (2026-08-27): MCQ is 0-live-interaction by
                # design (CURRENT_DECISIONS.md) — the candidate submits via
                # the on-screen UI and immediately sees it recorded there;
                # no verbal confirmation is needed. Previously this always
                # spoke a "Got it, recorded" ack and then unconditionally
                # chained into another LLM turn — which, mid-section,
                # re-announced "this is a multiple-choice question" on
                # every single question instead of only the section's
                # first, and at the section's end spoke a redundant ack
                # immediately before the real transition/goodbye message.
                # Empty response here + voice_adapter.py's phase-gated
                # chain (only fires when this submission actually ends the
                # interview, i.e. current_phase is now CLOSING) makes MCQ
                # fully silent between questions and WAITING_ROOM, and
                # exactly one clean message when it's genuinely the end.
                response="",
                reason="Candidate submitted an MCQ answer.",
                should_transition=False,
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

    def _handle_end_section_early(self) -> Optional[StructuredAction]:
        # During BRIEFING or WELCOME, _active_core_section() returns None due to phase-gate.
        # Find the first incomplete section directly from context.sections.
        core_section = None
        for section in self.context.sections.values():
            if not section.completed:
                core_section = section
                break

        if core_section is None:
            return None  # no active section — ignore silently

        # Record all remaining questions (including the current one) as NOT_ATTEMPTED
        while core_section.current_question is not None:
            current_q = core_section.current_question
            is_active_q = core_section.current_index == 0  # first iteration
            self.context.question_records.append(QuestionRecord(
                question_id=current_q.id,
                outcome=QuestionOutcome.NOT_ATTEMPTED,
                hints_used=self.context.hints_used if is_active_q else 0,
                followups_used=self.context.followups_used if is_active_q else 0,
            ))
            core_section.current_index += 1
            self.context.hints_used = 0
            self.context.followups_used = 0

        core_section.completed = True

        # Check if any sections remain, bypassing phase-gates (unlike _active_core_section())
        has_next_section = any(not s.completed for s in self.context.sections.values())
        if not has_next_section:
            self._transition_to(InterviewPhase.CLOSING)
        else:
            self._transition_to(InterviewPhase.WAITING_ROOM)

        # Event log
        self.context.event_sequence += 1

        return StructuredAction(
            action=ActionEnum.ACKNOWLEDGE,
            response="",
            reason="Candidate ended section early. Remaining questions recorded as NOT_ATTEMPTED.",
            should_transition=False,
            detected_candidate_control=CandidateControlAction.END_SECTION_EARLY,
        )

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
            if self.context.current_phase in (InterviewPhase.CLOSING, InterviewPhase.COMPLETED):
                return StructuredAction(
                    action=ActionEnum.END,
                    response="",
                    reason="Closing turn already exists; completing idempotently.",
                    should_transition=False,
                    detected_candidate_control=control,
                )
            self._transition_to(InterviewPhase.CLOSING)
            return StructuredAction(
                action=ActionEnum.ACKNOWLEDGE,
                response="",
                reason="Candidate explicitly ended interview. Yielding to LLM for closing.",
                should_transition=True,
                detected_candidate_control=control,
            )

        if control in (CandidateControlAction.SKIP_QUESTION, CandidateControlAction.SKIP_SECTION):
            core_section = self._active_core_section()

            # 2026-08-27 policy reversal (explicit, confirmed with the user
            # — partially reverses Issue 6's "core question integrity: never
            # skipped live", the same way END_SECTION_EARLY already
            # partially reversed the original "no section skipping" rule;
            # see CURRENT_DECISIONS.md). SKIP_QUESTION now genuinely skips
            # the CURRENT ordered core question — marked SKIPPED (not
            # COMPLETED/TIME_EXPIRED/NOT_ATTEMPTED: a real, deliberate
            # candidate choice, distinct from all three) — and advances to
            # the next one, or ends the section/interview exactly the same
            # way SUBMIT_CODE/SUBMIT_MCQ_ANSWER already do when it's the
            # last question. Scoped narrowly: only fires once a core
            # question is actually active (_active_core_section() is
            # phase-gated to BACKGROUND, so this can't fire during
            # BRIEFING/WELCOME before any real question exists — that case
            # still falls through to the rejection below, Issue 6's
            # original repro). SKIP_SECTION stays fully blocked here — this
            # is a per-QUESTION skip, not a new "skip the whole section"
            # escape hatch (END_SECTION_EARLY already covers that).
            if control == CandidateControlAction.SKIP_QUESTION and core_section is not None and core_section.current_question is not None:
                skipped_id = core_section.current_question.id
                just_finished = core_section
                self._advance_core_question(outcome_override=QuestionOutcome.SKIPPED)
                next_section = self._active_core_section()
                if next_section is None:
                    self._transition_to(InterviewPhase.CLOSING)
                elif just_finished.completed:
                    self._transition_to(InterviewPhase.WAITING_ROOM)
                logger.info("[SKIP] Skipped ordered core question id=%s", skipped_id)
                return StructuredAction(
                    action=ActionEnum.TRANSITION,
                    response=msgs["skip_question"],
                    reason="Candidate skipped the ordered core question.",
                    should_transition=False,
                    detected_candidate_control=control,
                )

            # Issue 6 fix: HR-approved, ordered core sections/questions
            # (context.sections) can never be skipped/replaced/reordered
            # live (CURRENT_DECISIONS.md, Phase 7 spec) — this is the
            # remaining case: no real question is active yet (BRIEFING/
            # WELCOME) or this is SKIP_SECTION, neither of which the real-
            # skip branch above handles. This branch predates Phase 7D/9B's
            # core-question walk and jumps straight to the legacy
            # TECHNICAL_INTRO/TECHNICAL phase below without knowing sections
            # exist at all — checked BEFORE any of that legacy logic runs.
            # Deliberately uses _has_pending_core_content(), NOT
            # _active_core_section() — the real repro skips during
            # BRIEFING/WELCOME, before BACKGROUND (and therefore
            # _active_core_section()) ever engages; see that method's
            # docstring. Legacy sessions (context.sections empty) are
            # completely unaffected — falls through unchanged.
            if self._has_pending_core_content():
                return StructuredAction(
                    action=ActionEnum.ACKNOWLEDGE,
                    response=msgs["core_section_no_skip"],
                    reason="Core question/section skip rejected — core content is HR-approved and cannot be skipped live.",
                    should_transition=False,
                    detected_candidate_control=control,
                )

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
            # Issue 6 fix: once a session has HR-approved ordered sections
            # (context.sections non-empty), "the technical portion" isn't a
            # legacy-flow concept that exists for it to jump to — disabled
            # regardless of which section types are configured or whether
            # any are still active (per product decision), not just while a
            # section is currently in progress. Legacy sessions (sections
            # empty) fall through to the unchanged existing behavior below.
            if self.context.sections:
                return StructuredAction(
                    action=ActionEnum.ACKNOWLEDGE,
                    response=msgs["core_move_to_technical_unavailable"],
                    reason="MOVE_TO_TECHNICAL rejected — session uses HR-approved ordered core sections; no legacy technical phase exists to move to.",
                    should_transition=False,
                    detected_candidate_control=control,
                )

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

        if control == CandidateControlAction.PROCEED_TO_NEXT_SECTION:
            # WR-C: reached only via the UI-command path (voice_adapter.py's
            # _handle_ui_command -> here), which already re-validates
            # is_candidate_control_valid-equivalent gating before calling in
            # (get_allowed_candidate_controls, above in this same file) —
            # this guard is defense-in-depth, not the only thing standing
            # between this branch and an out-of-phase call, matching the
            # "belt and suspenders" discipline the auto-timeout side also
            # uses (see _transition_out_of_waiting_room).
            if self.context.current_phase != InterviewPhase.WAITING_ROOM:
                return None
            await self._transition_out_of_waiting_room(auto=False)
            return StructuredAction(
                action=ActionEnum.ACKNOWLEDGE,
                response="",
                reason="Candidate proceeded from the waiting room.",
                # The handler already performed the transition (and the
                # section-clock reseed) itself — same "don't transition
                # twice" pattern as SKIP_QUESTION/MOVE_TO_TECHNICAL above.
                should_transition=False,
                detected_candidate_control=control,
            )

        if control == CandidateControlAction.END_SECTION_EARLY:
            return self._handle_end_section_early()

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

    def _effective_max_hints(self, question: Optional[Question]) -> int:
        """The actual number of hints available for a question: the plan-
        level cap, further capped by however many predefined hints the
        question itself actually carries. Extracted in 9E from _provide_hint()
        (its only caller before this) so the new CORE_CODING_QUESTION_PROMPT
        can display the same number without a second, potentially drifting
        copy of this calculation."""
        plan_max = 4
        if self.context.interview_plan:
            plan_max = self.context.interview_plan.technical_limits.max_hints_per_question
        predefined_hints_count = len(question.hints) if question and question.hints else 0
        return min(plan_max, predefined_hints_count)

    async def _provide_hint(self) -> StructuredAction:
        """Provides the next structured hint level.

        Phase 9C: ported to the ordered core-question flow. The legacy
        single-question flow keeps current_question on self.context; the
        ordered flow (CODING core questions, asked during phase BACKGROUND
        via _active_core_section()) never populates that field — only
        core_section.current_question does. Preferring the active core
        section when one exists covers both without ambiguity: it is only
        non-None while current_phase == BACKGROUND, which the legacy flow
        never uses for hint requests."""
        core_section = self._active_core_section()
        q = core_section.current_question if core_section is not None else self.context.current_question
        max_hints = self._effective_max_hints(q)

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
            core_section = self._active_core_section()
            if core_section is not None:
                # 9E: CODING/MCQ core questions complete ONLY via their
                # explicit submission commands (SUBMIT_CODE / SUBMIT_MCQ_
                # ANSWER, both in process_ui_command()), which call
                # _advance_core_question() directly and never reach this
                # gate at all. A plain LLM-emitted TRANSITION must never be
                # allowed to complete them on its own judgment -- unlike
                # VERBAL, there is no "the LLM decided the answer was
                # sufficient" completion signal for these two types. The
                # hard time-boundary override (_must_force_transition()) is
                # a separate, unaffected path and still applies to every
                # type, including these.
                if core_section.section_type in ("CODING", "MCQ"):
                    return False

                # 7F-scoping addendum: a core question must actually have
                # been asked at least once before TRANSITION can complete/
                # advance past it. Previously this unconditionally trusted
                # the LLM's TRANSITION judgment (matching the TECHNICAL
                # branch below) — but that let an adversarial or malformed
                # first turn silently mark a never-asked question COMPLETED.
                # Ordered core questions aren't adaptively counted against a
                # target/max otherwise; this is the only gate for them.
                return core_section.current_question_asked

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
            if self._active_core_section() is not None:
                # Phase 7D: use the time-tier mechanism (7B/7C) consistently
                # rather than the legacy 180s constant — "very_limited" is
                # exactly the spec's "skip straight to next core question".
                return self._time_tier() == "very_limited"

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
            core_section = self._active_core_section()
            if core_section is not None:
                # Phase 7D: this phrasing must not promise a "technical
                # portion" that doesn't exist for B2B sessions — say the
                # correct thing depending on whether this is the last
                # core question (current_index hasn't advanced yet here).
                if core_section.current_index >= len(core_section.questions) - 1:
                    return "Alright, in the interest of time, let's wrap things up."
                return "Alright, in the interest of time, let's move on to the next question."
            return "Anyway, let's move on to the technical portion of our interview."
        if phase in (InterviewPhase.TECHNICAL, InterviewPhase.CODING):
            return "Alright, in the interest of time, let's wrap up this question and move on."
        return "Let's move on to the next part."

    # ─── Follow-Up Cap & Time-Tier Throttle (Phase 7C) ─────────────────────

    def _time_tier(self) -> str:
        """Classifies remaining interview time into 'normal' / 'limited' /
        'very_limited', per the reconstructed Verbal AI Follow-Up spec
        (docs/phase7-architecture.md). Only consulted for the new ordered
        core-question flow — the legacy BACKGROUND/TECHNICAL/CODING flow
        keeps its existing untouched 180s/120s must-transition logic above."""
        remaining = self.get_remaining_time()
        tiers = self.context.interview_plan.time_tiers
        if remaining >= tiers.normal_min_seconds:
            return "normal"
        if remaining >= tiers.limited_min_seconds:
            return "limited"
        return "very_limited"

    def _active_core_section(self) -> Optional[OrderedSectionProgress]:
        """The ordered, HR-approved core-question section active right now,
        or None. Reuses the BACKGROUND phase for the new core-question flow (Phase
        7C decision — see docs/phase7-architecture.md's 7D open item for the
        completion-transition follow-up this implies). Returns None for
        every session until Phase 7D starts populating context.sections —
        dormant by construction until then.
        Phase 9B: Iterates over all sections (VERBAL, CODING, MCQ) to support a
        generalized ordered core-question walk."""
        if self.context.current_phase != InterviewPhase.BACKGROUND:
            return None
        for section in self.context.sections.values():
            if not section.completed:
                return section
        return None

    def _has_pending_core_content(self) -> bool:
        """Whether context.sections has any incomplete HR-approved core
        section, independent of the candidate's CURRENT phase.

        Deliberately distinct from _active_core_section(): that method is
        phase-gated on purpose (it answers "what's active right now", for
        the automatic TRANSITION-driven walk, which only ever asks while
        already in BACKGROUND). Candidate-control handlers need the answer
        BEFORE that phase cascade happens — e.g. Issue 6: SKIP_QUESTION
        issued during BRIEFING/WELCOME, before BACKGROUND has even started,
        where _active_core_section() trivially (and correctly, for its own
        purpose) returns None regardless of what's waiting in
        context.sections. Using _active_core_section() here was the exact
        bug in this fix's first attempt — caught by live verification, not
        the unit tests (which all seeded phase=BACKGROUND directly and
        never exercised the BRIEFING-cascade path)."""
        return any(not section.completed for section in self.context.sections.values())

    def _current_max_followups(self) -> int:
        """Effective follow-up cap for the currently active question.

        New ordered core-question flow: flat max-2 decision from
        CURRENT_DECISIONS.md, throttled by the time tier, and forced to 0 if
        the current core question has no competency set (Phase 7B decision —
        no competency means no way to bound follow-up relevance).

        Legacy BACKGROUND/TECHNICAL/CODING flow: existing configured
        SectionLimits.max_followups_per_question, not time-tier throttled.
        This is now a genuinely enforced hard cap rather than advisory-only
        prompt text — see this sub-phase's completion report."""
        core_section = self._active_core_section()
        if core_section is not None:
            if core_section.section_type in ("MCQ", "CODING"):
                # MCQ: binary right/wrong, no live interaction beyond
                # selecting an option (CURRENT_DECISIONS.md).
                # CODING: 0 POST-SUBMISSION follow-ups per the resolved
                # decision — this is NOT the same as "no live interaction";
                # in-flight hint requests during solving are handled by the
                # (separately ported, 9C/9D) REQUEST_HINT mechanism, not by
                # FOLLOW_UP/the follow-up cap this method governs.
                return 0
            current_q = core_section.current_question
            if current_q is None or current_q.competency is None:
                return 0
            return {"normal": 2, "limited": 1, "very_limited": 0}[self._time_tier()]

        phase = self.context.current_phase
        if phase == InterviewPhase.BACKGROUND:
            return self.context.background_progress.limits.max_followups_per_question
        if phase in (InterviewPhase.TECHNICAL, InterviewPhase.CODING):
            return self.context.technical_progress.limits.max_followups_per_question
        return 0

    def _advance_core_question(self, outcome_override: Optional[QuestionOutcome] = None):
        """Phase 7D: snapshot the just-finished core question into a
        QuestionRecord (reusing the same record type/reset pattern as the
        legacy load_question()/_record_question_completion() flow) and move
        the ordered-list pointer to the next one, or mark the section
        complete if none remain. Does NOT call _transition_to() — moving
        from core question N to N+1 does not change current_phase (both are
        BACKGROUND), and BACKGROUND -> BACKGROUND is not a modeled
        state_machine transition.

        7F-scoping addendum: by the time this runs, current_question_asked
        being False can only mean _must_force_transition()'s time-pressure
        override fired before the question was ever posed — the normal
        TRANSITION path is now blocked by _should_allow_transition() until
        it's actually asked. Recorded as TIME_EXPIRED rather than COMPLETED
        in that case, so evaluation/reporting doesn't treat an unasked
        question as answered.

        outcome_override: set explicitly by SKIP_QUESTION's real-skip path
        (2026-08-27 policy reversal — see CURRENT_DECISIONS.md) to record
        SKIPPED instead of inferring COMPLETED/TIME_EXPIRED from
        current_question_asked, which would otherwise mislabel a
        genuinely-skipped core question as answered."""
        core_section = self._active_core_section()
        if core_section is None:
            return
        current_q = core_section.current_question
        if current_q is not None:
            outcome = outcome_override or (
                QuestionOutcome.COMPLETED
                if core_section.current_question_asked
                else QuestionOutcome.TIME_EXPIRED
            )
            self.context.question_records.append(QuestionRecord(
                question_id=current_q.id,
                outcome=outcome,
                hints_used=self.context.hints_used,
                followups_used=self.context.followups_used,
                assistance_records=list(self.context.assistance_records),
                evaluation=self.context.evaluation_signals[-1] if self.context.evaluation_signals else None,
            ))
        core_section.current_index += 1
        core_section.current_question_asked = False
        self.context.hints_used = 0
        self.context.followups_used = 0
        self.context.assistance_records = []
        self.context.evaluation_signals = []
        if core_section.current_index >= len(core_section.questions):
            core_section.completed = True

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

        # Whether there's a real name to say out loud at all. No real name
        # covers two lazy-create fallbacks: the generic placeholder
        # full_name written by get_current_candidate_profile_id (backend
        # deps.py), and a bare email address written by
        # get_or_create_candidate_profile's no-name fallback (an invitation
        # created from just an email).
        #
        # Deliberately NOT done by handing the LLM a "Candidate" sentinel
        # and an instruction to skip it when it sees that exact string — an
        # earlier version did that and the model didn't reliably comply (it
        # would say the word "Candidate" out loud mid-sentence, including in
        # Arabic interviews). Building two fully-formed instruction strings
        # in Python instead means the word never appears in the prompt at
        # all when there's no real name, so there's nothing for the model to
        # misread or ignore.
        raw_full_name = (self.context.candidate_profile.get("full_name") or "").strip()
        has_real_name = bool(raw_full_name) and raw_full_name != "Candidate" and "@" not in raw_full_name
        candidate_name = raw_full_name if has_real_name else ""
        candidate_context_line = f"Candidate name: {candidate_name}\n" if has_real_name else ""

        # profile_str (embedded in BACKGROUND/TECHNICAL/CORE_* prompts below)
        # is a raw JSON dump of the candidate profile — without this, a
        # placeholder/email full_name would leak into those phases' context
        # the same way it used to leak into BRIEFING/WELCOME/CLOSING.
        profile_for_prompt = dict(self.context.candidate_profile)
        if not has_real_name:
            profile_for_prompt.pop("full_name", None)
        profile_str = truncate_prompt_text(
            json.dumps(profile_for_prompt, indent=2, default=str),
            MAX_PROFILE_CHARS,
        )

        system_prompt = ""

        if phase == InterviewPhase.BRIEFING:
            greeting_instruction = (
                f'Greet the candidate warmly BY THEIR NAME, "{candidate_name}", as the very '
                f'first thing you say (e.g. "Hi {candidate_name}, ...").'
                if has_real_name else
                'Greet the candidate warmly — you do not know their name, so greet them '
                'generically (e.g. "Hi there," / "Welcome,") without inventing or using any '
                'name or placeholder word for them.'
            )
            system_prompt = BRIEFING_PROMPT.format(
                identity=_INTERVIEWER_IDENTITY,
                greeting_instruction=greeting_instruction,
                candidate_context_line=candidate_context_line,
                role=self.context.role,
                level=self.context.confirmed_level,
                duration_minutes=self._total_duration_sec // 60,
                allowed_actions=allowed_actions,
            )

        elif phase == InterviewPhase.WELCOME:
            interview_focus = self.context.role
            if self.context.job_description:
                interview_focus = f"{self.context.role} role aligned to the provided job description"
            welcome_instruction = (
                f'Welcome the candidate by name ("{candidate_name}").'
                if has_real_name else
                'Welcome the candidate warmly and generically — you do not know their name, '
                'so do not use any name or placeholder word for them.'
            )
            system_prompt = WELCOME_PROMPT.format(
                identity=_INTERVIEWER_IDENTITY,
                candidate_context_line=candidate_context_line,
                welcome_instruction=welcome_instruction,
                role=self.context.role,
                interview_focus=interview_focus,
                allowed_actions=allowed_actions,
            )

        elif phase == InterviewPhase.BACKGROUND:
            core_section = self._active_core_section()
            if core_section is not None and core_section.current_question is not None:
                # Phase 7D/9E: ordered, HR-approved core-question flow.
                # Routes to a type-specific prompt template by section_type
                # — VERBAL keeps using CORE_QUESTION_PROMPT exactly as
                # before (byte-for-byte unchanged); CODING/MCQ get their
                # own 9E templates. Any future/unknown section_type falls
                # back to CORE_QUESTION_PROMPT rather than crashing.
                q = core_section.current_question
                job_desc = truncate_prompt_text(
                    self.context.job_description,
                    MAX_JOB_DESCRIPTION_CHARS,
                ) or "No specific job description was provided."

                if core_section.section_type == "CODING":
                    config = q.config or {}
                    system_prompt = CORE_CODING_QUESTION_PROMPT.format(
                        identity=_INTERVIEWER_IDENTITY,
                        question_number=core_section.current_index + 1,
                        total_questions=core_section.total_questions,
                        question_text=q.problem_statement,
                        competency=q.competency or "General",
                        starter_code=config.get("starter_code") or "(none provided)",
                        supported_languages=", ".join(config.get("supported_languages") or []) or "(unspecified)",
                        constraints=config.get("constraints") or "(none specified)",
                        hints_used=self.context.hints_used,
                        max_hints=self._effective_max_hints(q),
                        profile=profile_str,
                        role=self.context.role,
                        job_description=job_desc,
                        time_remaining=remaining,
                        candidate_controls=candidate_controls,
                        allowed_actions=allowed_actions,
                    )
                elif core_section.section_type == "MCQ":
                    config = q.config or {}
                    options = config.get("options") or []
                    options_text = "\n".join(
                        f"{opt.get('id', '?')}) {opt.get('text', '')}" for opt in options
                    ) or "(no options provided)"
                    selection_type = (
                        "Select ALL options that apply (multiple correct answers)."
                        if config.get("is_multi_select")
                        else "Select ONE option (single correct answer)."
                    )
                    system_prompt = CORE_MCQ_QUESTION_PROMPT.format(
                        identity=_INTERVIEWER_IDENTITY,
                        question_number=core_section.current_index + 1,
                        total_questions=core_section.total_questions,
                        question_text=q.problem_statement,
                        competency=q.competency or "General",
                        options_text=options_text,
                        selection_type=selection_type,
                        profile=profile_str,
                        role=self.context.role,
                        job_description=job_desc,
                        time_remaining=remaining,
                        candidate_controls=candidate_controls,
                        allowed_actions=allowed_actions,
                    )
                else:
                    system_prompt = CORE_QUESTION_PROMPT.format(
                        identity=_INTERVIEWER_IDENTITY,
                        question_number=core_section.current_index + 1,
                        total_questions=core_section.total_questions,
                        question_text=q.problem_statement,
                        competency=q.competency or "General",
                        max_followups=self._current_max_followups(),
                        followups_used=self.context.followups_used,
                        profile=profile_str,
                        role=self.context.role,
                        job_description=job_desc,
                        time_remaining=remaining,
                        candidate_controls=candidate_controls,
                        allowed_actions=allowed_actions,
                    )
            else:
                # Legacy flow — unchanged.
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
            closing_instruction = (
                f'Thank the candidate for their time, by name ("{candidate_name}").'
                if has_real_name else
                'Thank the candidate for their time — you do not know their name, so do not '
                'use any name or placeholder word for them.'
            )
            system_prompt = CLOSING_PROMPT.format(
                identity=_INTERVIEWER_IDENTITY,
                closing_instruction=closing_instruction,
                candidate_context_line=candidate_context_line,
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

        # Phase 9D: HR-authored eval_criteria, keyed by question_id, for
        # every ordered core question (any section type). Empty for legacy
        # (pre-Phase-7 / non-B2B) sessions, whose Question objects never
        # carry eval_criteria at all -- the evaluator degrades gracefully
        # to the pre-9D behavior (transcript/records only) in that case.
        question_eval_criteria = {
            q.id: q.eval_criteria
            for section in self.context.sections.values()
            for q in section.questions
            if q.eval_criteria is not None
        }

        # Phase 8C: HR-configured assessment criteria resolved for this
        # session's job (today: only the 5 seeded behavioral ones; empty for
        # a legacy session or a job with nothing resolved). Distinct from
        # question_eval_criteria above -- see AssessmentCriterionData's
        # docstring in models.py.
        criteria = [c.model_dump(mode="json") for c in self.context.criteria]

        evidence = {
            "role": self.context.role,
            "level": self.context.confirmed_level,
            "technical_submission": self.context.technical_submission,
            "question_records": [r.model_dump(mode="json") for r in self.context.question_records],
            "question_eval_criteria": question_eval_criteria,
            "criteria": criteria,
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
        except Exception as e:
            logger.exception(f"[EVALUATION] generation_failed: {e}")
            evaluation = DetailedEvaluation(
                overall_score=1,
                recommendation="Consider / Mixed",
                evidence_sufficiency=1,
                summary="Session ended early or evaluation generation failed due to insufficient evidence.",
                detailed_overview="The interview was disconnected or terminated before a proper evaluation could be completed."
            )
            self.context.final_evaluation = evaluation
            return evaluation

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
            core_section = self._active_core_section()
            if core_section is not None:
                core_section.current_question_asked = True

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
            core_section = self._active_core_section()
            if core_section is not None:
                # Phase 7D/9B: ordered core-question flow. Advancing to the next
                # question stays in BACKGROUND (no phase change); only once
                # ALL sections are exhausted does the interview move on — straight
                # to CLOSING, skipping the legacy TECHNICAL_INTRO/TECHNICAL/
                # CODING phases entirely for B2B sessions.
                #
                # WR-C: _advance_core_question() itself is untouched — only
                # what happens after it runs changes. just_finished.completed
                # is exactly true iff that call just exhausted this section
                # (not just moved to its next question). If another section
                # remains, stop at WAITING_ROOM instead of silently walking
                # straight into it — this is the exact boundary 9B built as
                # invisible; only the last section's completion still goes
                # straight to CLOSING, unchanged.
                just_finished = core_section
                self._advance_core_question()
                next_section = self._active_core_section()
                if next_section is None:
                    self._transition_to(InterviewPhase.CLOSING)
                elif just_finished.completed:
                    self._transition_to(InterviewPhase.WAITING_ROOM)
            else:
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
