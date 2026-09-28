/**
 * Polling for the backend's durable task queue (H2-F).
 *
 * The four AI endpoints answer 202 with a task id instead of holding the
 * connection open for a Groq call: inline, a generation slower than
 * `config.apiTimeoutMs` (30s) aborted in the browser while the backend
 * carried on and committed the result, so the admin was told it failed
 * when it had not.
 *
 * `runTask` starts the work and resolves with the finished task, or throws
 * an ApiError carrying the handler's own message and code -- the same text
 * the inline version returned as a 4xx/5xx body, so existing
 * `err.message` handling in the pages keeps working unchanged.
 */
import { ApiError } from "./api";

export interface TaskAccepted {
  task_id: string;
  kind: string;
  status: string;
}

export interface Task<TResult = Record<string, unknown>> {
  id: string;
  kind: string;
  status: "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED";
  result: TResult | null;
  error: string | null;
  error_code: string | null;
  attempts: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface RunTaskOptions {
  /** Gap between polls. */
  intervalMs?: number;
  /** Give up after this long. The backend keeps working; only the UI stops waiting. */
  timeoutMs?: number;
  /** Called on each poll, for a "still working" state. */
  onProgress?: (task: Task) => void;
  signal?: AbortSignal;
}

const DEFAULT_INTERVAL_MS = 1_500;
/** Generous on purpose: the point of the queue is that slow is not failure.
 *  Covers the Groq adapter's 30s timeout x 3 attempts plus scheduling. */
const DEFAULT_TIMEOUT_MS = 180_000;

const sleep = (ms: number, signal?: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        reject(new ApiError("Cancelled", { status: 0, code: "aborted" }));
      },
      { once: true }
    );
  });

export async function runTask<TResult = Record<string, unknown>>(
  start: () => Promise<TaskAccepted>,
  poll: (taskId: string) => Promise<Task<TResult>>,
  options: RunTaskOptions = {}
): Promise<Task<TResult>> {
  const { intervalMs = DEFAULT_INTERVAL_MS, timeoutMs = DEFAULT_TIMEOUT_MS, onProgress, signal } = options;

  const accepted = await start();
  const deadline = Date.now() + timeoutMs;

  for (;;) {
    await sleep(intervalMs, signal);
    const task = await poll(accepted.task_id);
    onProgress?.(task as Task);

    if (task.status === "SUCCEEDED") return task;
    if (task.status === "FAILED") {
      throw new ApiError(task.error || "The task failed", {
        status: 502,
        code: task.error_code || "task_failed",
        detail: task.error,
      });
    }
    if (Date.now() >= deadline) {
      // Still QUEUED/RUNNING. The work is not lost -- it finishes and the
      // row keeps the result; this only stops the spinner.
      throw new ApiError("This is taking longer than expected. Reload the page in a moment to see the result.", {
        status: 0,
        code: "task_poll_timeout",
      });
    }
  }
}
