/**
 * Covers Issue 3c (docs/post-rebrand-issues.md): a guest candidate's
 * request must carry the guest token minted for their own interview
 * session, even when a Supabase session (e.g. an admin logged in in the
 * same browser/tab) is concurrently present — fetchApi must not guess
 * ambiently and let the wrong identity win.
 *
 * Node's built-in fetch/Headers (stable since Node 18) are used directly —
 * no jsdom. sessionStorage/localStorage are polyfilled in-memory below
 * since Node doesn't provide them by default; guestSession.ts's real
 * implementation is exercised unmocked.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

class MemoryStorage implements Storage {
  private store = new Map<string, string>();
  get length() { return this.store.size; }
  clear() { this.store.clear(); }
  getItem(key: string) { return this.store.has(key) ? this.store.get(key)! : null; }
  key(index: number) { return Array.from(this.store.keys())[index] ?? null; }
  removeItem(key: string) { this.store.delete(key); }
  setItem(key: string, value: string) { this.store.set(key, String(value)); }
}

(globalThis as any).sessionStorage = new MemoryStorage();
(globalThis as any).localStorage = new MemoryStorage();

const mockGetSession = vi.fn();

// lib/supabase.ts calls createClient() at module-load time against
// import.meta.env values that don't exist in this test run — mock it out
// entirely rather than letting the real client construct.
vi.mock("./supabase", () => ({
  supabase: {
    auth: {
      getSession: () => mockGetSession(),
    },
  },
}));

const { fetchApi } = await import("./api");
const { setGuestToken } = await import("./guestSession");

const SUPABASE_TOKEN = "supabase-admin-token";
const GUEST_TOKEN = "guest-minted-token";
const GUEST_SESSION_ID = "session-guest-owns";
const OTHER_SESSION_ID = "session-someone-else-owns";

function mockSupabaseSession(hasSession: boolean) {
  mockGetSession.mockResolvedValue({
    data: { session: hasSession ? { access_token: SUPABASE_TOKEN } : null },
  });
}

function authHeaderFromLastCall(fetchMock: ReturnType<typeof vi.fn>): string | null {
  const [, init] = fetchMock.mock.calls[0];
  return (init.headers as Headers).get("Authorization");
}

describe("fetchApi guest/Supabase token selection (Issue 3c)", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();
    mockGetSession.mockReset();
    vi.spyOn(console, "warn").mockImplementation(() => {});
    fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({}),
    });
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("uses the guest token when it matches the requested session, even with a concurrent Supabase session", async () => {
    mockSupabaseSession(true); // e.g. an admin logged in in the same browser/tab
    setGuestToken(GUEST_TOKEN, GUEST_SESSION_ID);

    await fetchApi(`/api/v1/interviews/${GUEST_SESSION_ID}`, {
      guestSessionId: GUEST_SESSION_ID,
    });

    expect(authHeaderFromLastCall(fetchMock)).toBe(`Bearer ${GUEST_TOKEN}`);
  });

  it("uses the Supabase session when the guest token belongs to a different session", async () => {
    mockSupabaseSession(true);
    setGuestToken(GUEST_TOKEN, GUEST_SESSION_ID);

    await fetchApi(`/api/v1/interviews/${OTHER_SESSION_ID}`, {
      guestSessionId: OTHER_SESSION_ID,
    });

    expect(authHeaderFromLastCall(fetchMock)).toBe(`Bearer ${SUPABASE_TOKEN}`);
  });

  it("keeps today's ambient precedence unchanged when no guestSessionId is passed", async () => {
    mockSupabaseSession(true);
    setGuestToken(GUEST_TOKEN, GUEST_SESSION_ID);

    await fetchApi("/api/v1/admin/ping");

    expect(authHeaderFromLastCall(fetchMock)).toBe(`Bearer ${SUPABASE_TOKEN}`);
  });
});
