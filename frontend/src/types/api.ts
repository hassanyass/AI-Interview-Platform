export type InterviewPhase = 
  | "CREATED"
  | "BRIEFING"
  | "WELCOME"
  | "TECHNICAL_INTRO"
  | "CODING"
  | "BOOTSTRAP"
  | "SETUP"
  | "GREETING"
  | "BACKGROUND"
  | "TECHNICAL"
  | "CLOSING"
  | "COMPLETED"
  | "TERMINATED"
  | "FAILED";

export type InterviewStatus = "PENDING" | "IN_PROGRESS" | "COMPLETED" | "TERMINATED" | "FAILED";

export type QuestionOutcome = "UNASKED" | "COMPLETED" | "SKIPPED" | "CHANGED";

export interface QuestionRecord {
  question_id: string;
  outcome: QuestionOutcome;
  started_at?: string;
  ended_at?: string;
}

export interface SectionLimits {
  target_questions: number;
  max_questions: number;
  max_followups_per_question: number;
  max_hints_per_question: number;
}

export interface InterviewPlan {
  role: string;
  level: string;
  duration_minutes: number;
  technical_limits: SectionLimits;
}

export interface FinalResult {
  session_id: string;
  role: string;
  level: string;
  total_questions: number;
  completed: number;
  skipped: number;
  changed: number;
  question_records: QuestionRecord[];
  competencies_evaluated: any[];
}

export interface InterviewSessionResponse {
  id: string;
  role?: string;
  level?: string;
  candidate_id: string;
  config_id?: string;
  resume_id?: string;
  status: InterviewStatus;
  started_at?: string;
  completed_at?: string;
  created_at: string;
  updated_at: string;
}

export interface InterviewResultResponse {
  session_id: string;
  status: InterviewStatus;
  completed_at?: string;
  final_result: FinalResult;
}
