import { fetchApi } from "../../lib/api";
import type { InterviewResultResponse, InterviewSessionResponse } from "../../types/api";

// guestSessionId: id is passed through on every call below so a guest's own
// session-scoped token wins over an unrelated concurrent Supabase session
// (Issue 3c) — see lib/api.ts's fetchApi and lib/guestSession.ts. Harmless
// for Flow A (Supabase-authenticated) candidates: their session id will
// never match a stored guest record, so these calls fall through to the
// existing Supabase-session behavior unchanged.

export async function getInterviewSession(id: string): Promise<InterviewSessionResponse> {
  return fetchApi<InterviewSessionResponse>(`/api/v1/interviews/${id}`, { guestSessionId: id });
}

export async function getLiveKitToken(id: string): Promise<{ token: string; url: string }> {
  return fetchApi<{ token: string; url: string }>(`/api/v1/livekit/token`, {
    method: "POST",
    data: { session_id: id },
    guestSessionId: id,
  });
}

export async function getInterviewResult(id: string): Promise<InterviewResultResponse> {
  return fetchApi<InterviewResultResponse>(`/api/v1/interviews/${id}/result`, { guestSessionId: id });
}

/** Used by the intro screen's "End interview" action — a candidate leaving
 *  before Start Session, when no LiveKit/agent session exists yet to send
 *  END_INTERVIEW over. Marks the still-CREATED session TERMINATED. */
export async function terminateInterview(id: string): Promise<InterviewSessionResponse> {
  return fetchApi<InterviewSessionResponse>(`/api/v1/interviews/${id}/terminate`, {
    method: "POST",
    guestSessionId: id,
  });
}
