/**
 * H2-E: fetchApi throws ApiError with the backend's structured fields
 * (status, code, request_id) while `message` stays the human-readable
 * detail every page shows; network failures and timeouts are ApiErrors too.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./supabase", () => ({
  supabase: { auth: { getSession: async () => ({ data: { session: null } }) } },
}));
vi.mock("./guestSession", () => ({ getGuestToken: () => null }));
vi.mock("../config", () => ({
  config: { apiBaseUrl: "http://api.test", apiTimeoutMs: 50 },
  configProblems: [],
}));

const { fetchApi, ApiError, isApiError } = await import("./api");

const fail = (p: Promise<unknown>) => p.then(() => { throw new Error("expected rejection"); }, (e: unknown) => e as InstanceType<typeof ApiError>);

function jsonResponse(status: number, body: unknown, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });
}

describe("fetchApi errors", () => {
  const originalFetch = globalThis.fetch;
  beforeEach(() => {
    vi.useRealTimers();
  });
  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("carries status, code, detail and request id from a problem body; message is the detail", async () => {
    globalThis.fetch = vi.fn(async () =>
      jsonResponse(409, { type: "about:blank", title: "Conflict", status: 409, detail: "CV_REQUIRED: upload your CV first", code: "cv_required", request_id: "req-1" }),
    ) as any;
    const err = await fail(fetchApi("/x"));
    expect(isApiError(err)).toBe(true);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.message).toBe("CV_REQUIRED: upload your CV first");
    expect(err.status).toBe(409);
    expect(err.code).toBe("cv_required");
    expect(err.requestId).toBe("req-1");
  });

  it("joins a validation-error list the way it always did", async () => {
    globalThis.fetch = vi.fn(async () => jsonResponse(422, { detail: [{ msg: "a" }, { msg: "b" }] })) as any;
    const err = await fail(fetchApi("/x"));
    expect(err.message).toBe("a, b");
    expect(err.status).toBe(422);
  });

  it("falls back to the status text when the body is not JSON, and reads the request id header", async () => {
    globalThis.fetch = vi.fn(async () => new Response("<html>bad gateway</html>", { status: 502, statusText: "Bad Gateway", headers: { "x-request-id": "hdr-9" } })) as any;
    const err = await fail(fetchApi("/x"));
    expect(err.status).toBe(502);
    expect(err.message).toBe("Bad Gateway");
    expect(err.requestId).toBe("hdr-9");
  });

  it("a network failure is an ApiError with status 0 and code network", async () => {
    globalThis.fetch = vi.fn(async () => { throw new TypeError("Failed to fetch"); }) as any;
    const err = await fail(fetchApi("/x"));
    expect(err.status).toBe(0);
    expect(err.code).toBe("network");
  });

  it("aborts a request that exceeds the timeout and reports code timeout", async () => {
    let seenSignal: AbortSignal | undefined;
    globalThis.fetch = vi.fn((_url: string, init: RequestInit) => {
      seenSignal = init.signal as AbortSignal;
      return new Promise((_resolve, reject) => {
        seenSignal!.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
      });
    }) as any;
    const err = await fail(fetchApi("/slow"));       // config timeout = 50ms
    expect(err.code).toBe("timeout");
    expect(err.status).toBe(0);
    expect(seenSignal?.aborted).toBe(true);
  });

  it("honours a per-call timeoutMs", async () => {
    globalThis.fetch = vi.fn((_url: string, init: RequestInit) =>
      new Promise((_r, reject) => (init.signal as AbortSignal).addEventListener("abort", () => reject(new DOMException("x", "AbortError")))),
    ) as any;
    const started = Date.now();
    const err = await fail(fetchApi("/slow", { timeoutMs: 120 }));
    expect(err.code).toBe("timeout");
    expect(Date.now() - started).toBeGreaterThanOrEqual(100);
  });
});
