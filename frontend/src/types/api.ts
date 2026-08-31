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
  | "FAILED"
  // WR-B: candidate-visible section break phase
  | "WAITING_ROOM";


export type InterviewStatus = "PENDING" | "IN_PROGRESS" | "DISCONNECTED" | "COMPLETED" | "TERMINATED" | "FAILED";

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
  technical_submission?: { code?: string; language?: string };
  transcript?: Array<{ speaker: "candidate" | "agent"; text: string }>;
  evaluation_status?: "COMPLETED" | "FAILED";
  evaluation?: DetailedEvaluation | null;
}

export interface EvaluationCategory {
  score?: number | null;
  overview: string;
  strengths: string[];
  improvements: string[];
}

export interface DetailedEvaluation {
  overall_score?: number | null;
  recommendation: string;
  summary: string;
  communication: EvaluationCategory;
  technical: EvaluationCategory;
  problem_solving: EvaluationCategory;
  technical_submission: EvaluationCategory;
  background: EvaluationCategory;
  strengths: string[];
  areas_for_improvement: string[];
  detailed_overview: string;
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
  /** Job.instructions, surfaced for the pre-session intro screen. */
  candidate_instructions?: string | null;
  /** Ordered core-section-type list (VERBAL/CODING/MCQ) from the session's
   *  InterviewDefinition, order_index order. Used to compute the waiting
   *  room's "next section" label client-side — the live realtime state only
   *  reports the currently-active section (null during WAITING_ROOM itself). */
  sections?: string[];
  /** CandidateProfile.full_name, resolved server-side from
   *  session.candidate_profile_id. Always present on the response (the
   *  backend's InterviewSessionResponse.candidate_name field is
   *  Optional[str] = None, not omitted), so it's a real string or null —
   *  never actually absent — but kept optional here to match this file's
   *  existing style for the same-shaped candidate_instructions field above. */
  candidate_name?: string | null;
}

export interface InterviewResultResponse {
  session_id: string;
  status: InterviewStatus;
  completed_at?: string;
  final_result: FinalResult;
}
