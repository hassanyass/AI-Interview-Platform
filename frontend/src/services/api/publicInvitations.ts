import { fetchApi } from "../../lib/api";

export interface InvitationPublicContext {
  job_title: string;
  job_description?: string;
  seniority?: string;
  candidate_instructions?: string;
  duration_minutes: number;
  invitation_status: string;
  candidate_email: string;
}

export interface RedeemedSessionInfo {
  id: string;
  job_id?: string;
  definition_id?: string;
  status: string;
  created_at?: string;
}

export interface RedeemResponse {
  session: RedeemedSessionInfo;
  livekit_token: string;
  livekit_url: string;
}

export async function getInvitationContext(token: string): Promise<InvitationPublicContext> {
  return fetchApi<InvitationPublicContext>(`/api/v1/invitations/${token}`);
}

export async function redeemInvitation(token: string): Promise<RedeemResponse> {
  return fetchApi<RedeemResponse>(`/api/v1/invitations/${token}/redeem`, {
    method: "POST",
  });
}
