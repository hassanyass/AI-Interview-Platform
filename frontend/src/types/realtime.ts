import type { InterviewPhase } from "./api";

export type AllowedControl = "REQUEST_HINT" | "CHANGE_QUESTION" | "SKIP_QUESTION" | "END_INTERVIEW" | "SUBMIT_CODE" | "SUBMIT_MCQ_ANSWER" | "END_SECTION_EARLY" | "PROCEED_TO_NEXT_SECTION";

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
