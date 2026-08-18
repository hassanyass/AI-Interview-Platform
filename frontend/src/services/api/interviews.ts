import { fetchApi } from "../../lib/api";
import type { InterviewResultResponse, InterviewSessionResponse } from "../../types/api";

export async function getInterviewSession(id: string): Promise<InterviewSessionResponse> {
  return fetchApi<InterviewSessionResponse>(`/api/v1/interviews/${id}`);
}

export async function getLiveKitToken(id: string): Promise<{ token: string; url: string }> {
  return fetchApi<{ token: string; url: string }>(`/api/v1/livekit/token`, {
    method: "POST",
    data: { session_id: id },
  });
}

export async function getInterviewResult(id: string): Promise<InterviewResultResponse> {
  return fetchApi<InterviewResultResponse>(`/api/v1/interviews/${id}/result`);
}
