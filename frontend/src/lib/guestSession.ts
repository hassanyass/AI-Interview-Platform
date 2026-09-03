/**
 * Guest-session token storage — Phase 6, Sub-phase 6D. Session-scoped as of
 * the Issue 3c fix (post-rebrand): see docs/post-rebrand-issues.md.
 *
 * Backs a public-link (Flow B) candidate's guest JWT, minted by
 * POST /apply/{token}/register. sessionStorage (not localStorage): scoped
 * to this tab, cleared when it closes — appropriate for a short-lived
 * (24h), single-flow token, and avoids it lingering indefinitely across
 * browser sessions the way localStorage would.
 *
 * Stored as {token, sessionId} rather than a bare token string — the
 * sessionId is the InterviewSession.id this token was actually minted for
 * (ApplyPage passes it at registration time). This lets lib/api.ts's
 * fetchApi match a request's target session against the token it's
 * carrying, rather than guessing "guest vs. Supabase" from ambient state
 * alone. That ambient guess was Issue 3c's root cause: a leftover Supabase
 * session (e.g. an admin logged in in the same browser/tab) would win
 * fetchApi's old precedence order even for a guest's own interview
 * request, because nothing tied the guest token to the specific session it
 * belonged to.
 *
 * Consumed by lib/api.ts's fetchApi (session-matched first, then as an
 * unscoped fallback), and by AuthContext/GuestOrAuthRoute's coarse
 * "does this tab carry any guest credential at all" check.
 */
const GUEST_TOKEN_KEY = "path2hire_guest_access_token";

interface StoredGuestSession {
  token: string;
  sessionId: string;
}

function readRecord(): StoredGuestSession | null {
  try {
    const raw = sessionStorage.getItem(GUEST_TOKEN_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (
      parsed &&
      typeof parsed === "object" &&
      typeof parsed.token === "string" &&
      typeof parsed.sessionId === "string"
    ) {
      return parsed as StoredGuestSession;
    }
    // Shape mismatch — e.g. a pre-fix flat-string token left over from
    // before this change. Treat as absent rather than crashing; the guest
    // just re-registers if they genuinely need a fresh session.
    return null;
  } catch {
    return null;
  }
}

/**
 * Returns the guest token, optionally scoped to a specific interview
 * session id.
 *
 * - `getGuestToken(sessionId)`: returns the token only if it was minted
 *   for exactly this session id. This is the call fetchApi makes for
 *   session-specific requests (getInterviewSession/getLiveKitToken/
 *   getInterviewResult) — a match is proof of intent, not a guess.
 * - `getGuestToken()`: returns the token regardless of which session it's
 *   for. Used only for the coarse "is there a guest credential in this
 *   tab at all" check (GuestOrAuthRoute's access gate, fetchApi's unscoped
 *   fallback for backward compatibility).
 */
export function getGuestToken(sessionId?: string): string | null {
  const record = readRecord();
  if (!record) return null;
  if (sessionId !== undefined && record.sessionId !== sessionId) return null;
  return record.token;
}

export function setGuestToken(token: string, sessionId: string): void {
  try {
    sessionStorage.setItem(GUEST_TOKEN_KEY, JSON.stringify({ token, sessionId }));
  } catch {
    // sessionStorage unavailable (e.g. private browsing edge cases) —
    // fail silently, the guest just won't be able to reach the
    // authenticated interview page, which will surface as a normal
    // redirect rather than a crash.
  }
}

export function clearGuestToken(): void {
  try {
    sessionStorage.removeItem(GUEST_TOKEN_KEY);
  } catch {
    // no-op
  }
}
