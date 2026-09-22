/**
 * Frontend configuration — the one place `import.meta.env.VITE_*` is read.
 *
 * docs/production-hardening-plan.md H1-D. Required values have NO fallback:
 * a missing API base or Supabase key used to produce a working-looking app
 * whose every call failed (api.ts fell back to localhost:8000) or a blank
 * page (createClient("") throws at module load). `loadConfig` never throws;
 * it reports `problems`, and main.tsx renders a configuration-error screen
 * instead of the app when there are any. Everything else has the default the
 * code used before it was lifted.
 *
 * Keys are documented in frontend/.env.example and typed in vite-env.d.ts.
 */

export interface FrontendConfig {
  apiBaseUrl: string;
  supabaseUrl: string;
  supabasePublishableKey: string;
  /** Seconds between face-detection samples during a live interview. */
  faceDetectionIntervalSeconds: number;
  /** Consecutive head-down samples before HEAD_DOWN_SUSPECTED fires. */
  headDownConfirmThreshold: number;
  /** Pitch (degrees) beyond which a sample counts as head-down. */
  headDownPitchThresholdDegrees: number;
  /**
   * Log every decomposed head-pose angle to the console. On in dev builds,
   * off in production builds, unless VITE_HEAD_POSE_DEBUG says otherwise
   * (docs/CURRENT_DECISIONS.md, head-pose calibration, decision 2026-09-21).
   */
  headPoseDebug: boolean;
}

export interface LoadedConfig {
  values: FrontendConfig;
  /** Human-readable problems, one per missing/invalid required variable. Empty = OK. */
  problems: string[];
}

type Env = Record<string, string | boolean | undefined>;

const REQUIRED = ["VITE_API_BASE_URL", "VITE_SUPABASE_URL", "VITE_SUPABASE_PUBLISHABLE_KEY"] as const;

function str(env: Env, key: string): string {
  const v = env[key];
  return typeof v === "string" ? v.trim() : "";
}

/** `Number(x) || fallback` — the semantics the inline reads always had. */
function numberOr(env: Env, key: string, fallback: number): number {
  return Number(str(env, key)) || fallback;
}

function boolOr(env: Env, key: string, fallback: boolean): boolean {
  const v = str(env, key).toLowerCase();
  if (v === "true" || v === "1") return true;
  if (v === "false" || v === "0") return false;
  return fallback;
}

export function loadConfig(env: Env): LoadedConfig {
  const problems: string[] = [];
  for (const key of REQUIRED) {
    if (!str(env, key)) problems.push(`${key} is not set`);
  }
  const apiBaseUrl = str(env, "VITE_API_BASE_URL").replace(/\/+$/, "");
  if (apiBaseUrl && !/^https?:\/\//.test(apiBaseUrl)) {
    problems.push(`VITE_API_BASE_URL must be an absolute http(s) URL (got "${apiBaseUrl}")`);
  }

  return {
    values: {
      apiBaseUrl,
      supabaseUrl: str(env, "VITE_SUPABASE_URL"),
      supabasePublishableKey: str(env, "VITE_SUPABASE_PUBLISHABLE_KEY"),
      faceDetectionIntervalSeconds: numberOr(env, "VITE_FACE_DETECTION_INTERVAL_SECONDS", 4),
      headDownConfirmThreshold: numberOr(env, "VITE_HEAD_DOWN_CONFIRM_THRESHOLD", 3),
      headDownPitchThresholdDegrees: numberOr(env, "VITE_HEAD_DOWN_PITCH_THRESHOLD_DEGREES", 25),
      headPoseDebug: boolOr(env, "VITE_HEAD_POSE_DEBUG", env.DEV === true),
    },
    problems,
  };
}

const loaded = loadConfig(import.meta.env as unknown as Env);

export const config: FrontendConfig = loaded.values;
export const configProblems: readonly string[] = loaded.problems;
