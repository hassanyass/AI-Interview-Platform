import { fetchApi } from "../lib/api";

export interface Job {
  id: string;
  title: string;
  description?: string;
  seniority?: string;
  location?: string;
  instructions?: string;
  required_skills?: string[];
  preferred_skills?: string[];
  responsibilities?: string[];
  status: string;
  language?: string;
  created_at?: string;
  updated_at?: string;
  definition?: {
    id: string;
    job_id: string;
    duration_minutes: number;
    is_public: boolean;
    public_access_token?: string;
  };
}

export type JobCreate = Omit<Job, "id" | "status" | "created_at" | "updated_at" | "definition">;

export interface Question {
  id: string;
  section_id: string;
  order_index: number;
  title: string;
  competency?: string;
  text: string;
  eval_criteria?: any;
  // 9G: type-specific payload — CodingConfig/MCQConfig shape (backend
  // schemas/admin.py), null/undefined for VERBAL questions.
  config?: any;
  created_at: string;
}

export interface Section {
  id: string;
  definition_id: string;
  section_type: string;
  order_index: number;
  config?: any;
  created_at: string;
  questions?: Question[];
}

export interface Invitation {
  id: string;
  application_id: string;
  candidate_email: string;
  status: string;
  token: string;
  expires_at?: string;
  created_at: string;
}

export interface PublicRegisterResponse {
  access_token: string;
  session: {
    id: string;
    job_id: string;
    definition_id: string;
    status: string;
    created_at: string;
  };
  livekit_token: string;
  livekit_url: string;
}

export interface JobDetail extends Omit<Job, 'definition'> {
  definition?: {
    id: string;
    job_id: string;
    duration_minutes: number;
    is_public: boolean;
    public_access_token?: string;
    sections: Section[];
  };
}

export interface AssessmentCriterion {
  key: string;
  label: string;
  kind: string;
  enabled: boolean;
  guidance_text?: string;
  source: string;
  /** Scoring-mechanism upgrade: 1-10, default 5 (equal weighting). */
  weight: number;
}

/** Payload shape for PUT /jobs/{id}/criteria -- one entry per criterion the
 * editor is saving. A key not present in this list is treated as disabled. */
export interface CriterionWeightSetting {
  key: string;
  enabled: boolean;
  weight: number;
}

export interface CriterionScore {
  criterion_key: string;
  criterion_label?: string;
  kind?: string;
  score?: number;
  overview?: string;
  strengths: string[];
  improvements: string[];
  evidence_reference?: string;
  /** The weight this criterion carried when weighted_score was computed. */
  weight?: number;
}

export interface TranscriptMessage {
  speaker: "agent" | "candidate";
  text: string;
}

export interface QuestionRecordDetail {
  question_id: string;
  title?: string;
  text?: string;
  competency?: string;
  order_index?: number;
  outcome: string;
  hints_used: number;
  followups_used: number;
  clarifications_used: number;
}

export interface EvaluationDetail {
  session_id: string;
  status: string;
  completed_at?: string;
  candidate_name?: string;
  candidate_email?: string;
  job_title?: string;
  transcript: TranscriptMessage[];
  question_records: QuestionRecordDetail[];
  technical_submission: { code?: string; language?: string } & Record<string, unknown>;
  overall_score?: number;
  recommendation?: string;
  evidence_sufficiency?: number;
  summary?: string;
  detailed_overview?: string;
  scores: CriterionScore[];
  /** Scoring-mechanism upgrade: code-computed weighted aggregate of
   *  `scores`, deliberately separate from overall_score (the LLM's own
   *  independent holistic judgment). undefined/null when no enabled
   *  criterion had a scoreable result to average. */
  weighted_score?: number;
  /** Evaluation regeneration (2026-09-03): true when this is still the
   *  generic placeholder (_ensure_evaluation_placeholder) -- the session
   *  never got a real AI evaluation (crashed, lost its lease, or ended
   *  via a path that never talks to the agent, e.g. TERMINATED). Drives
   *  the "Regenerate Evaluation" button. */
  is_placeholder: boolean;
  override_suggested?: boolean;
  override_reason?: string;
  /** Short-lived presigned R2 GET URL, computed fresh on every fetch —
   *  never cache/store this beyond the current page load. undefined/null
   *  if no recording exists for this session (R2 not configured when the
   *  interview ran, camera denied, or Egress never started/failed). */
  recording_url?: string;
  /** Aggregation/dashboard pass: every flagged moment for this session
   *  (PR-B fullscreen/tab/focus events + PR-D face-presence events).
   *  Empty is a legitimate, common state, not an error. */
  integrity_events: IntegrityEvent[];
}

export interface IntegrityEvent {
  event_type: "FULLSCREEN_EXITED" | "TAB_HIDDEN" | "WINDOW_BLURRED" | "NO_FACE_DETECTED" | "MULTIPLE_FACES_DETECTED" | "HEAD_DOWN_SUSPECTED";
  phase?: string;
  metadata: Record<string, unknown>;
  /** Approximate seconds into the recording -- see backend's
   *  _get_integrity_events docstring for why this isn't frame-exact. */
  video_offset_seconds?: number;
}

export interface JobCandidateRow {
  session_id: string;
  candidate_name?: string;
  candidate_email?: string;
  status: string;
  completed_at?: string;
  overall_score?: number;
  recommendation?: string;
  evidence_sufficiency?: number;
  suggested: boolean;
  override_suggested?: boolean;
  /** Option A (confirmed): any integrity event at all, no threshold. */
  flagged_for_review: boolean;
}

export interface JobResultsResponse {
  job_id: string;
  job_title: string;
  total_candidates: number;
  completed_count: number;
  in_progress_count: number;
  suggested_count: number;
  flagged_count: number;
  candidates: JobCandidateRow[];
}

export const adminClient = {
  ping: async (): Promise<{ status: string; admin_id: string }> => {
    return fetchApi<{ status: string; admin_id: string }>("/api/v1/admin/ping");
  },
  
  getJobs: async (): Promise<Job[]> => {
    return fetchApi<Job[]>("/api/v1/admin/jobs");
  },

  createJob: async (data: JobCreate): Promise<Job> => {
    return fetchApi<Job>("/api/v1/admin/jobs", {
      method: "POST",
      data,
    });
  },

  publishJob: async (jobId: string): Promise<Job> => {
    return fetchApi<Job>(`/api/v1/admin/jobs/${jobId}/publish`, {
      method: "POST",
    });
  },

  updateJobStatus: async (jobId: string, status: string): Promise<Job> => {
    return fetchApi<Job>(`/api/v1/admin/jobs/${jobId}/status`, {
      method: "PATCH",
      data: { status },
    });
  },

  deleteJob: async (jobId: string): Promise<void> => {
    return fetchApi<void>(`/api/v1/admin/jobs/${jobId}`, {
      method: "DELETE",
    });
  },

  updateDefinition: async (definitionId: string, data: { duration_minutes?: number; is_public?: boolean }): Promise<Job> => {
    return fetchApi<Job>(`/api/v1/admin/definitions/${definitionId}`, {
      method: "PATCH",
      data,
    });
  },

  getJob: async (jobId: string): Promise<JobDetail> => {
    return fetchApi<JobDetail>(`/api/v1/admin/jobs/${jobId}`);
  },

  createSection: async (data: { definition_id: string; section_type: string; order_index: number; config?: any }): Promise<Section> => {
    return fetchApi<Section>("/api/v1/admin/sections", {
      method: "POST",
      data,
    });
  },

  updateSection: async (sectionId: string, data: { order_index?: number; config?: any }): Promise<Section> => {
    return fetchApi<Section>(`/api/v1/admin/sections/${sectionId}`, {
      method: "PATCH",
      data,
    });
  },

  deleteSection: async (sectionId: string): Promise<void> => {
    return fetchApi<void>(`/api/v1/admin/sections/${sectionId}`, {
      method: "DELETE",
    });
  },

  generateQuestions: async (sectionId: string, numQuestions: number = 5): Promise<Question[]> => {
    return fetchApi<Question[]>(`/api/v1/admin/sections/${sectionId}/generate-questions`, {
      method: "POST",
      data: { num_questions: numQuestions },
    });
  },

  createQuestion: async (
    sectionId: string,
    data: { title: string; competency?: string; text: string; eval_criteria?: any; config?: any }
  ): Promise<Question> => {
    return fetchApi<Question>(`/api/v1/admin/sections/${sectionId}/questions`, {
      method: "POST",
      data,
    });
  },

  updateQuestion: async (
    questionId: string,
    data: { title?: string; competency?: string; text?: string; eval_criteria?: any; config?: any }
  ): Promise<Question> => {
    return fetchApi<Question>(`/api/v1/admin/questions/${questionId}`, {
      method: "PATCH",
      data,
    });
  },

  deleteQuestion: async (questionId: string): Promise<void> => {
    return fetchApi<void>(`/api/v1/admin/questions/${questionId}`, {
      method: "DELETE",
    });
  },

  regenerateQuestion: async (questionId: string): Promise<Question> => {
    return fetchApi<Question>(`/api/v1/admin/questions/${questionId}/regenerate`, {
      method: "POST",
    });
  },

  createInvitation: async (definitionId: string, candidateEmail: string): Promise<Invitation> => {
    return fetchApi<Invitation>(`/api/v1/admin/definitions/${definitionId}/invitations`, {
      method: "POST",
      data: { candidate_email: candidateEmail },
    });
  },

  listInvitations: async (definitionId: string): Promise<Invitation[]> => {
    return fetchApi<Invitation[]>(`/api/v1/admin/definitions/${definitionId}/invitations`);
  },

  createTestDrive: async (definitionId: string): Promise<PublicRegisterResponse> => {
    return fetchApi<PublicRegisterResponse>(`/api/v1/admin/definitions/${definitionId}/test-drive`, {
      method: "POST",
    });
  },

  getJobCriteria: async (jobId: string): Promise<AssessmentCriterion[]> => {
    return fetchApi<AssessmentCriterion[]>(`/api/v1/admin/jobs/${jobId}/criteria`);
  },

  updateJobCriteria: async (jobId: string, settings: CriterionWeightSetting[]): Promise<AssessmentCriterion[]> => {
    return fetchApi<AssessmentCriterion[]>(`/api/v1/admin/jobs/${jobId}/criteria`, {
      method: "PUT",
      data: { criteria: settings },
    });
  },

  getJobResults: async (jobId: string): Promise<JobResultsResponse> => {
    return fetchApi<JobResultsResponse>(`/api/v1/admin/jobs/${jobId}/results`);
  },

  getCandidateResult: async (sessionId: string): Promise<EvaluationDetail> => {
    return fetchApi<EvaluationDetail>(`/api/v1/admin/interviews/${sessionId}/result`);
  },

  /** Evaluation regeneration (2026-09-03): HR-triggered, on-demand --
   *  generates a real evaluation from whatever transcript/question_records
   *  exist (live DB sources, not the legacy final_result snapshot), for a
   *  session currently showing the generic placeholder. Can take a real
   *  several-second Groq call; the caller should show a loading state. */
  regenerateEvaluation: async (sessionId: string): Promise<EvaluationDetail> => {
    return fetchApi<EvaluationDetail>(`/api/v1/admin/interviews/${sessionId}/regenerate-evaluation`, {
      method: "POST",
    });
  },

  setSuggestedOverride: async (sessionId: string, overrideSuggested: boolean | null, reason?: string): Promise<any> => {
    return fetchApi<any>(`/api/v1/admin/interviews/${sessionId}/suggested-override`, {
      method: "PATCH",
      data: { override_suggested: overrideSuggested, reason: reason },
    });
  },
};
