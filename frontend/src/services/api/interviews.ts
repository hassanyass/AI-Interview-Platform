import { fetchApi } from "../../lib/api";
import type { ConsentResponse, InterviewResultResponse, InterviewSessionResponse } from "../../types/api";

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

/** PR-A: records the candidate's recording/monitoring consent, tied to
 *  their session. Called from the intro screen's Start Session handler
 *  before the LiveKit token request — see InterviewSession.tsx's
 *  handleStart. Idempotent server-side, so a retry after a partial
 *  failure is always safe. */
export async function recordConsent(
  id: string,
  disclosure: { disclosure_language: string; disclosure_text: string }
): Promise<ConsentResponse> {
  return fetchApi<ConsentResponse>(`/api/v1/interviews/${id}/consent`, {
    method: "POST",
    data: disclosure,
    guestSessionId: id,
  });
}

/** Originally just the intro screen's "End interview" action (a candidate
 *  leaving before Start Session, when no LiveKit/agent session exists yet
 *  to send END_INTERVIEW over). Session-finalization-contract fix
 *  (2026-09-01): also used as the REST fallback for a LIVE session when
 *  the data-channel END_INTERVIEW round trip to the agent stalls or is
 *  never acknowledged (see InterviewWorkspace.tsx's handleConfirmEnd/
 *  fullscreen-grace-expiry) — the backend now force-disconnects the
 *  LiveKit room and guarantees an Evaluation row for either case. */
export async function terminateInterview(id: string): Promise<InterviewSessionResponse> {
  return fetchApi<InterviewSessionResponse>(`/api/v1/interviews/${id}/terminate`, {
    method: "POST",
    guestSessionId: id,
  });
}
