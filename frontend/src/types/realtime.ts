import type { InterviewPhase } from "./api";

export type AllowedControl = "REQUEST_HINT" | "CHANGE_QUESTION" | "SKIP_QUESTION" | "END_INTERVIEW" | "SUBMIT_CODE" | "SUBMIT_MCQ_ANSWER" | "END_SECTION_EARLY" | "PROCEED_TO_NEXT_SECTION";

/** PR-B/PR-D/Part 2: browser-detected integrity telemetry — always-on,
 *  never gated by allowed_controls (unlike AllowedControl above, which is
 *  server-permitted UI buttons). Kept as a separate type so that
 *  distinction stays explicit. NO_FACE_DETECTED/MULTIPLE_FACES_DETECTED
 *  (PR-D, 2026-09-02) are the client-side face-presence signals;
 *  HEAD_DOWN_SUSPECTED (Part 2, 2026-09-02) is the head-pose signal —
 *  all three debounced and edge-triggered by useFaceDetectionMonitor.ts
 *  before ever reaching this transport — see that file for the full
 *  reasoning. */
export type ProctoringEventCommand = "FULLSCREEN_EXITED" | "TAB_HIDDEN" | "WINDOW_BLURRED" | "NO_FACE_DETECTED" | "MULTIPLE_FACES_DETECTED" | "HEAD_DOWN_SUSPECTED";

export interface ActiveQuestion {
  id: string;
  title: string;
  problem_statement: string;
  difficulty: string;
  competency: string;
  expected_concepts: string[];
  hints: string[];
  follow_up_topics: string[];
  time_budget_minutes: number;
  coding_required: boolean;
  examples: Array<Record<string, unknown>>;
  constraints: string[];
  starter_code: Record<string, string>;
  test_cases: Array<Record<string, unknown>>;
  supported_languages: string[];
  hints_used: number;
  source?: "LLM_GENERATED" | "CONTEXTUAL_FALLBACK" | "QUESTION_BANK";
  // Part 1 (rebrand work): the real, un-coerced CodingConfig/MCQConfig dict
  // for an ordered-flow CODING/MCQ question (empty {} for VERBAL/legacy).
  // starter_code/constraints here are STRINGS (CodingConfig's real shape),
  // unlike the legacy Dict[str,string]/string[] fields above. MCQ has no
  // typed fields at all — options/correct_answers/is_multi_select only
  // ever arrive here.
  config?: {
    // CODING
    starter_code?: string;
    constraints?: string;
    supported_languages?: string[];
    hints?: string[];
    // MCQ
    options?: Array<{ id: string; text: string }>;
    correct_answers?: string[];
    is_multi_select?: boolean;
  };
}

export interface StateUpdatePayload {
  session_id: string;
  phase: InterviewPhase;
  sub_phase: string | null;
  current_question: ActiveQuestion | null;
  question_index: number;
  total_questions: number;
  questions_completed: number;
  questions_skipped: number;
  hints_used: number;
  max_hints: number;
  last_question_outcome: string | null;
  allowed_controls: AllowedControl[];
  time_remaining_seconds: number | null;
  sections_progress?: {
    total: number;
    completed: number;
    current_index: number | null; // 1-based
    current_section_type: string | null;
  };
}

export interface RealtimeMessage<T> {
  type: string;
  data: T;
}

export interface ControlIntentPayload {
  intent: AllowedControl;
  payload?: any;
}

export interface TranscriptionPayload {
  id: string;
  speaker: string;
  text: string;
  isFinal: boolean;
}

/** Broadcast on the "tts_status" data-channel topic whenever a TTS 429
 *  retry is in flight, resolves, or gives up (see voice_adapter.py's
 *  _broadcast_tts_status). Distinct from StateUpdatePayload — this is the
 *  audio pipeline's own transient state, not interview state.
 *  "switching_key" (2026-08-27, follow-up): Groq multi-key rotation —
 *  fires the instant a configured key hits its daily quota and the agent
 *  is switching to the next one (attempt/max here are the 1-based key
 *  position and total key count, e.g. "2 of 7", not a retry counter).
 *  text/language are only ever populated on "gave_up" — the browser's own
 *  Web Speech API fallback speaks this turn client-side since server-side
 *  TTS has definitively failed for it (not just mid-retry/mid-rotation). */
export interface TtsStatusPayload {
  status: "retrying" | "switching_key" | "ok" | "gave_up";
  attempt?: number | null;
  max?: number | null;
  text?: string | null;
  language?: string | null;
}
