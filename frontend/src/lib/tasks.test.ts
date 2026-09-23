/**
 * H2-F: runTask starts the work, polls until the backend's task row is
 * terminal, and turns a FAILED task into the ApiError the pages already
 * know how to display.
 */
import { describe, expect, it, vi } from "vitest";

vi.mock("./supabase", () => ({
  supabase: { auth: { getSession: async () => ({ data: { session: null } }) } },
}));
vi.mock("./guestSession", () => ({ getGuestToken: () => null }));
vi.mock("../config", () => ({
  config: { apiBaseUrl: "http://api.test", apiTimeoutMs: 50 },
  configProblems: [],
}));

const { runTask } = await import("./tasks");
const { ApiError, isApiError } = await import("./api");

const accepted = { task_id: "t-1", kind: "generate_questions", status: "QUEUED" };

function task(status: string, extra: Record<string, unknown> = {}) {
  return {
    id: "t-1", kind: "generate_questions", status, result: null, error: null,
    error_code: null, attempts: 1, created_at: "now", started_at: null, finished_at: null,
    ...extra,
  } as any;
}

describe("runTask", () => {
  it("polls until the task succeeds and returns it with its result", async () => {
    const start = vi.fn(async () => accepted);
    const poll = vi.fn()
      .mockResolvedValueOnce(task("QUEUED"))
      .mockResolvedValueOnce(task("RUNNING"))
      .mockResolvedValueOnce(task("SUCCEEDED", { result: { count: 2 } }));

    const finished = await runTask(start, poll, { intervalMs: 1 });

    expect(start).toHaveBeenCalledOnce();
    expect(poll).toHaveBeenCalledTimes(3);
    expect(poll).toHaveBeenCalledWith("t-1");
    expect(finished.result).toEqual({ count: 2 });
  });

  it("reports progress on every poll so the caller can show 'still working'", async () => {
    const seen: string[] = [];
    await runTask(
      async () => accepted,
      vi.fn().mockResolvedValueOnce(task("RUNNING")).mockResolvedValueOnce(task("SUCCEEDED")),
      { intervalMs: 1, onProgress: (t) => seen.push(t.status) }
    );
    expect(seen).toEqual(["RUNNING", "SUCCEEDED"]);
  });

  it("turns a FAILED task into an ApiError carrying the handler's message and code", async () => {
    const err = await runTask(
      async () => accepted,
      vi.fn().mockResolvedValue(task("FAILED", { error: "Groq is down", error_code: "llm_generation_failed" })),
      { intervalMs: 1 }
    ).then(() => { throw new Error("expected rejection"); }, (e) => e as InstanceType<typeof ApiError>);

    expect(isApiError(err)).toBe(true);
    expect(err.message).toBe("Groq is down");
    expect(err.code).toBe("llm_generation_failed");
  });

  it("gives up waiting after the timeout without claiming the work failed", async () => {
    const err = await runTask(
      async () => accepted,
      vi.fn().mockResolvedValue(task("RUNNING")),
      { intervalMs: 1, timeoutMs: 5 }
    ).then(() => { throw new Error("expected rejection"); }, (e) => e as InstanceType<typeof ApiError>);

    expect(err.code).toBe("task_poll_timeout");
    expect(err.message).toMatch(/taking longer/i);
  });

  it("does not poll at all when starting the task fails", async () => {
    const poll = vi.fn();
    await expect(
      runTask(async () => { throw new ApiError("Job is PUBLISHED", { status: 409 }); }, poll, { intervalMs: 1 })
    ).rejects.toThrow("Job is PUBLISHED");
    expect(poll).not.toHaveBeenCalled();
  });
});
