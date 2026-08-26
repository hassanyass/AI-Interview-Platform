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
};
