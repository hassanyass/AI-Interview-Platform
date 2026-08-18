"""
Interview state machine — defines allowed transitions and actions per phase.
"""
from typing import List
from app.interview.models import InterviewPhase, ActionEnum, CandidateControlAction

# ─── Phase Transitions ─────────────────────────────────────────────────────────

VALID_TRANSITIONS = {
    InterviewPhase.CREATED: [InterviewPhase.BRIEFING, InterviewPhase.CLOSING],
    InterviewPhase.BRIEFING: [InterviewPhase.WELCOME, InterviewPhase.TECHNICAL_INTRO, InterviewPhase.CLOSING],
    InterviewPhase.WELCOME: [InterviewPhase.BACKGROUND, InterviewPhase.TECHNICAL_INTRO, InterviewPhase.CLOSING],
    InterviewPhase.BACKGROUND: [InterviewPhase.TECHNICAL_INTRO, InterviewPhase.CLOSING],
    InterviewPhase.TECHNICAL_INTRO: [InterviewPhase.TECHNICAL, InterviewPhase.CLOSING],
    InterviewPhase.TECHNICAL: [InterviewPhase.CODING, InterviewPhase.TECHNICAL, InterviewPhase.CLOSING],
    InterviewPhase.CODING: [InterviewPhase.TECHNICAL, InterviewPhase.CLOSING],
    InterviewPhase.CLOSING: [InterviewPhase.COMPLETED],
    InterviewPhase.COMPLETED: []
}

# ─── Allowed LLM Actions Per Phase ─────────────────────────────────────────────

VALID_ACTIONS_PER_PHASE = {
    InterviewPhase.CREATED: [],
    InterviewPhase.BRIEFING: [
        ActionEnum.ASK,
        ActionEnum.ACKNOWLEDGE,
        ActionEnum.TRANSITION
    ],
    InterviewPhase.WELCOME: [
        ActionEnum.ACKNOWLEDGE,
        ActionEnum.ASK,
        ActionEnum.TRANSITION
    ],
    InterviewPhase.BACKGROUND: [
        ActionEnum.ASK,
        ActionEnum.FOLLOW_UP,
        ActionEnum.CLARIFY,
        ActionEnum.ACKNOWLEDGE,
        ActionEnum.TRANSITION
    ],
    InterviewPhase.TECHNICAL_INTRO: [
        ActionEnum.ASK,
        ActionEnum.ACKNOWLEDGE,
        ActionEnum.TRANSITION
    ],
    InterviewPhase.TECHNICAL: [
        ActionEnum.ASK,
        ActionEnum.LISTEN,
        ActionEnum.FOLLOW_UP,
        ActionEnum.CLARIFY,
        ActionEnum.HINT,
        ActionEnum.EVALUATE,
        ActionEnum.TRANSITION
    ],
    InterviewPhase.CODING: [
        ActionEnum.ASK,
        ActionEnum.LISTEN,
        ActionEnum.FOLLOW_UP,
        ActionEnum.CLARIFY,
        ActionEnum.HINT,
        ActionEnum.EVALUATE,
        ActionEnum.TRANSITION
    ],
    InterviewPhase.CLOSING: [
        ActionEnum.ACKNOWLEDGE,
        ActionEnum.END
    ],
    InterviewPhase.COMPLETED: []
}

# ─── Allowed Candidate Control Actions Per Phase ───────────────────────────────

VALID_CANDIDATE_CONTROLS_PER_PHASE = {
    InterviewPhase.CREATED: [],
    InterviewPhase.BRIEFING: [
        CandidateControlAction.END_INTERVIEW,
        CandidateControlAction.MOVE_TO_TECHNICAL,
        CandidateControlAction.REPEAT_QUESTION,
        CandidateControlAction.SKIP_QUESTION,
    ],
    InterviewPhase.WELCOME: [
        CandidateControlAction.END_INTERVIEW,
        CandidateControlAction.MOVE_TO_TECHNICAL,
        CandidateControlAction.REPEAT_QUESTION,
        CandidateControlAction.SKIP_QUESTION,
    ],
    InterviewPhase.BACKGROUND: [
        CandidateControlAction.SKIP_SECTION,
        CandidateControlAction.MOVE_TO_TECHNICAL,
        CandidateControlAction.END_INTERVIEW,
        CandidateControlAction.REPEAT_QUESTION,
        CandidateControlAction.SKIP_QUESTION,
    ],
    InterviewPhase.TECHNICAL_INTRO: [
        CandidateControlAction.END_INTERVIEW,
        CandidateControlAction.MOVE_TO_TECHNICAL,
        CandidateControlAction.REPEAT_QUESTION,
        CandidateControlAction.SKIP_QUESTION,
    ],
    InterviewPhase.TECHNICAL: [
        CandidateControlAction.SKIP_QUESTION,
        CandidateControlAction.CHANGE_QUESTION,
        CandidateControlAction.END_INTERVIEW,
        CandidateControlAction.REPEAT_QUESTION,
        CandidateControlAction.REQUEST_CLARIFICATION,
        CandidateControlAction.REQUEST_HINT,
    ],
    InterviewPhase.CODING: [
        CandidateControlAction.SKIP_QUESTION,
        CandidateControlAction.END_INTERVIEW,
        CandidateControlAction.REQUEST_HINT,
        CandidateControlAction.REQUEST_CLARIFICATION,
        CandidateControlAction.REPEAT_QUESTION,
    ],
    InterviewPhase.CLOSING: [
        CandidateControlAction.END_INTERVIEW,
    ],
    InterviewPhase.COMPLETED: [],
}


def is_transition_valid(current_phase: InterviewPhase, target_phase: InterviewPhase) -> bool:
    """Validate if a state transition is legal."""
    return target_phase in VALID_TRANSITIONS.get(current_phase, [])


def is_action_valid(phase: InterviewPhase, action: ActionEnum) -> bool:
    """Validate if an LLM action is allowed in the current phase."""
    return action in VALID_ACTIONS_PER_PHASE.get(phase, [])


def is_candidate_control_valid(phase: InterviewPhase, control: CandidateControlAction) -> bool:
    """Validate if a candidate control action is allowed in the current phase."""
    return control in VALID_CANDIDATE_CONTROLS_PER_PHASE.get(phase, [])


def get_allowed_actions(phase: InterviewPhase) -> List[str]:
    """Get the list of allowed LLM action values for a phase."""
    return [a.value for a in VALID_ACTIONS_PER_PHASE.get(phase, [])]


def get_allowed_candidate_controls(phase: InterviewPhase) -> List[str]:
    """Get the list of allowed candidate control action values for a phase."""
    return [c.value for c in VALID_CANDIDATE_CONTROLS_PER_PHASE.get(phase, [])]
