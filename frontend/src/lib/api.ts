import { supabase } from "./supabase";
import { getGuestToken } from "./guestSession";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
export const API_BASE_URL = API_BASE;

interface ApiOptions extends RequestInit {
  data?: unknown;
  // The InterviewSession id this request is for, when the caller knows it
  // (services/api/interviews.ts's three candidate-facing calls always do —
  // it's already their own `id` param). When the stored guest token was
  // minted for exactly this session id, it wins unconditionally, even if a
  // Supabase session also happens to be active in this browser/tab — see
  // guestSession.ts's module docstring and docs/post-rebrand-issues.md's
  // Issue 3c for why an ambient "whichever credential exists" guess isn't
  // safe on a route that legitimately serves two different identities
  // (Flow B guests and Flow A Supabase-authenticated candidates).
  guestSessionId?: string;
}

export async function fetchApi<T>(endpoint: string, options: ApiOptions = {}): Promise<T> {
  const { data, headers: customHeaders, guestSessionId, ...rest } = options;

  const { data: sessionData } = await supabase.auth.getSession();
  const supabaseToken = sessionData?.session?.access_token || null;
  const matchedGuestToken = guestSessionId ? getGuestToken(guestSessionId) : null;

  if (supabaseToken && getGuestToken()) {
    // Not corrective — this doesn't change which token gets used, just
    // surfaces the ambiguity loudly instead of letting it manifest only as
    // a confusing 403 later. See docs/post-rebrand-issues.md's Issue 3c:
    // auto-clearing either credential here has its own real footguns
    // (racing a guest's own subsequent page loads, or silently signing out
    // an unrelated admin), so this is deliberately just a warning.
    console.warn(
      "[fetchApi] Both a Supabase session and a guest credential are present in this browser. " +
      "Session-scoped calls resolve this correctly via guestSessionId; unscoped calls fall back " +
      "to the Supabase session per the existing precedence order."
    );
  }

  // Session-matched guest token wins unconditionally — a match is proof
  // this token was minted for exactly this request's session, not a
  // guess. Otherwise, fall back to the existing ambient order: Supabase
  // session, then an unscoped guest token (unchanged behavior for admin
  // calls and any caller that doesn't pass guestSessionId).
  const token = matchedGuestToken || supabaseToken || getGuestToken();

  const headers = new Headers(customHeaders);
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  if (data && !(data instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...rest,
    headers,
    body: data instanceof FormData ? data : data ? JSON.stringify(data) : undefined,
  });

  if (!response.ok) {
    let errorDetail = "An error occurred";
    try {
      const errorData = await response.json();
      if (errorData.detail) {
        if (typeof errorData.detail === "string") {
          errorDetail = errorData.detail;
        } else if (Array.isArray(errorData.detail)) {
          errorDetail = errorData.detail.map((e: any) => e.msg).join(", ");
        } else {
          errorDetail = JSON.stringify(errorData.detail);
        }
      }
    } catch {
      // Ignored
    }
    throw new Error(errorDetail);
  }

  // Handle 204 No Content
  if (response.status === 204) {
    return {} as T;
  }

  return response.json();
}
