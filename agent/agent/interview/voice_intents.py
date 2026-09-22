"""Spoken control intents that need a confirmation turn (H2-C, decision S12).

controller._detect_candidate_control matches substrings of the candidate's
speech ("i'm done", "let's move on", "next question"...). Some of those
matches change the interview irreversibly. Since H2-C the controller does
not execute those on the spot: it asks (SYSTEM_MESSAGES["confirm_<intent>"])
and executes only if the next utterance is an affirmative. Everything here
is data + one pure function so the frozen controller's diff stays minimal.
"""
from __future__ import annotations

import re

from agent.interview.models import CandidateControlAction

# Executed immediately today; confirmed first from H2-C on.
CONFIRM_BEFORE_EXECUTING = frozenset({
    CandidateControlAction.END_INTERVIEW,
    CandidateControlAction.SKIP_QUESTION,
    CandidateControlAction.CHANGE_QUESTION,
    CandidateControlAction.MOVE_TO_TECHNICAL,
    CandidateControlAction.SKIP_SECTION,
})

CONFIRM_MESSAGE_KEY = {
    CandidateControlAction.END_INTERVIEW: "confirm_end_interview",
    CandidateControlAction.SKIP_QUESTION: "confirm_skip_question",
    CandidateControlAction.CHANGE_QUESTION: "confirm_change_question",
    CandidateControlAction.MOVE_TO_TECHNICAL: "confirm_move_to_technical",
    CandidateControlAction.SKIP_SECTION: "confirm_skip_section",
}

_AFFIRMATIVE = {
    "en": ("yes", "yeah", "yep", "yup", "sure", "confirm", "confirmed", "go ahead", "do it",
           "please do", "correct", "that's right", "end it", "skip it", "absolutely", "of course"),
    "ar": ("نعم", "ايه", "إيه", "أيوه", "ايوه", "اي", "أي", "أكيد", "اكيد", "تمام", "موافق",
           "خلاص", "طبعا", "طبعاً", "صح", "انهيها", "أنهيها", "تخطاه", "غيره"),
}
_NEGATION = {
    "en": ("no", "nope", "not", "don't", "dont", "never", "cancel", "wait", "continue", "keep going"),
    "ar": ("لا", "لأ", "مو", "ما ", "كمل", "كمّل", "استمر", "خليني", "خلني", "انتظر", "لحظة"),
}

_MAX_WORDS = 8  # a confirmation is a short utterance; a long answer is an answer


def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[ً-ْ]", "", text)          # Arabic diacritics
    text = re.sub(r"[^\w\s']", " ", text, flags=re.UNICODE)  # punctuation
    return re.sub(r"\s+", " ", text).strip()


def is_affirmative(text: str | None, language: str) -> bool:
    """True only for a short utterance that contains an affirmative and no
    negation -- "yes", "yeah end it", "نعم", "أكيد خلاص". Anything long or
    hedged is treated as "not confirmed" and processed as ordinary speech."""
    if not text:
        return False
    norm = _normalize(text)
    if not norm or len(norm.split()) > _MAX_WORDS:
        return False
    lang = language if language in _AFFIRMATIVE else "en"
    padded = f" {norm} "
    for neg in _NEGATION[lang] + (_NEGATION["en"] if lang != "en" else ()):
        if f" {neg.strip()} " in padded or padded.startswith(f" {neg.strip()}"):
            return False
    for yes in _AFFIRMATIVE[lang] + (_AFFIRMATIVE["en"] if lang != "en" else ()):
        if f" {yes} " in padded:
            return True
    return False
