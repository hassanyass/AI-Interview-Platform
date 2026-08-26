import { fetchApi } from "../../lib/api";
import type { RedeemedSessionInfo } from "./publicInvitations";

export interface PublicApplyContext {
  job_title: string;
  job_description?: string;
  seniority?: string;
  candidate_instructions?: string;
  duration_minutes: number;
}

export interface PublicRegisterResponse {
  access_token: string;
  token_type: string;
  session: RedeemedSessionInfo;
  livekit_token: string;
  livekit_url: string;
}

export async function getApplyContext(token: string): Promise<PublicApplyContext> {
  return fetchApi<PublicApplyContext>(`/api/v1/apply/${token}`);
}

export async function registerApplicant(
  token: string,
  data: { name: string; email: string }
): Promise<PublicRegisterResponse> {
  return fetchApi<PublicRegisterResponse>(`/api/v1/apply/${token}/register`, {
    method: "POST",
    data,
  });
}
