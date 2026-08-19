import type { InterviewPhase } from "./api";

export type AllowedControl = "REQUEST_HINT" | "CHANGE_QUESTION" | "SKIP_QUESTION" | "END_INTERVIEW" | "SUBMIT_CODE";

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
  time_remaining_seconds: number;
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
