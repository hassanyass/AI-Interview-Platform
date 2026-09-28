import { supabase } from "./supabase";
import { getGuestToken } from "./guestSession";
import { config } from "../config";

// No fallback: a missing VITE_API_BASE_URL is reported by src/config.ts and
// main.tsx shows the configuration screen instead of the app.
const API_BASE = config.apiBaseUrl;
export const API_BASE_URL = API_BASE;

/**
 * H2-E: every failed request throws an ApiError. `message` is still the
 * human-readable `detail` (what every page shows), and the structured fields
 * the backend sends since H2-A1 are kept: `status`, `code` (a stable machine
 * identifier such as "cv_required"), `requestId` (quote it when reporting).
 * A request that never got an answer has status 0 and code "network" or
 * "timeout".
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;
  readonly detail: unknown;
  readonly requestId?: string;

  constructor(message: string, opts: { status: number; code?: string; detail?: unknown; requestId?: string }) {
    super(message);
    this.name = "ApiError";
    this.status = opts.status;
    this.code = opts.code;
    this.detail = opts.detail ?? message;
    this.requestId = opts.requestId;
  }
}

export function isApiError(err: unknown): err is ApiError {
  return err instanceof ApiError;
}

function detailToMessage(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((e: any) => e?.msg ?? JSON.stringify(e)).join(", ");
  if (detail == null) return "An error occurred";
  return JSON.stringify(detail);
}

interface ApiOptions extends RequestInit {
  data?: unknown;
  /** Per-call timeout; defaults to config.apiTimeoutMs. Long operations (CV upload + parsing) pass a larger value. */
  timeoutMs?: number;
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
  const { data, headers: customHeaders, guestSessionId, timeoutMs, ...rest } = options;

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

  // H2-E: no request waits forever. The caller's own signal (if any) and the
  // timeout both abort the same fetch.
  const controller = new AbortController();
  const limit = timeoutMs ?? config.apiTimeoutMs;
  const timer = setTimeout(() => controller.abort(new DOMException("timeout", "TimeoutError")), limit);
  if (rest.signal) {
    const outer = rest.signal;
    if (outer.aborted) controller.abort(outer.reason);
    else outer.addEventListener("abort", () => controller.abort(outer.reason), { once: true });
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${endpoint}`, {
      ...rest,
      signal: controller.signal,
      headers,
      body: data instanceof FormData ? data : data ? JSON.stringify(data) : undefined,
    });
  } catch {
    clearTimeout(timer);
    const timedOut = controller.signal.aborted && (controller.signal.reason as any)?.name === "TimeoutError";
    throw new ApiError(
      timedOut ? `The request timed out after ${Math.round(limit / 1000)}s.` : "Could not reach the server.",
      { status: 0, code: timedOut ? "timeout" : "network" },
    );
  }
  clearTimeout(timer);

  if (!response.ok) {
    let body: any = null;
    try {
      body = await response.json();
    } catch {
      // not JSON (proxy error page, empty body) -- fall through to the status text
    }
    const detail = body?.detail;
    throw new ApiError(detail != null ? detailToMessage(detail) : (response.statusText || "An error occurred"), {
      status: response.status,
      code: typeof body?.code === "string" ? body.code : undefined,
      detail,
      requestId: body?.request_id ?? response.headers.get("x-request-id") ?? undefined,
    });
  }

  // Handle 204 No Content
  if (response.status === 204) {
    return {} as T;
  }

  return response.json();
}
