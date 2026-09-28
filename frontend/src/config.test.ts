/**
 * H1-D: src/config.ts — required VITE_* values have no fallbacks and are
 * reported as problems; tunables keep the `Number(x) || default` semantics
 * the inline reads had; head-pose debug is on in dev, off in prod, and
 * VITE_HEAD_POSE_DEBUG overrides either way (docs/CURRENT_DECISIONS.md).
 */
import { describe, expect, it } from "vitest";

import { loadConfig, mergeEnv } from "./config";

const COMPLETE = {
  VITE_API_BASE_URL: "http://127.0.0.1:8001",
  VITE_SUPABASE_URL: "https://p.supabase.co",
  VITE_SUPABASE_PUBLISHABLE_KEY: "sb_publishable_x",
};

describe("loadConfig", () => {
  it("accepts a complete environment with no problems and the old defaults", () => {
    const { values, problems } = loadConfig({ ...COMPLETE, DEV: false });
    expect(problems).toEqual([]);
    expect(values.apiBaseUrl).toBe("http://127.0.0.1:8001");
    expect(values.apiTimeoutMs).toBe(30_000);
    expect(values.faceDetectionIntervalSeconds).toBe(4);
    expect(values.headDownConfirmThreshold).toBe(3);
    expect(values.headDownPitchThresholdDegrees).toBe(25);
  });

  it("names every missing required variable instead of falling back", () => {
    const { values, problems } = loadConfig({});
    expect(problems).toEqual([
      "VITE_API_BASE_URL is not set",
      "VITE_SUPABASE_URL is not set",
      "VITE_SUPABASE_PUBLISHABLE_KEY is not set",
    ]);
    expect(values.apiBaseUrl).toBe(""); // never "http://localhost:8000"
  });

  it("treats blank strings as missing and rejects a relative API base", () => {
    expect(loadConfig({ ...COMPLETE, VITE_SUPABASE_URL: "   " }).problems).toEqual(["VITE_SUPABASE_URL is not set"]);
    expect(loadConfig({ ...COMPLETE, VITE_API_BASE_URL: "127.0.0.1:8001" }).problems[0]).toMatch(/absolute http\(s\) URL/);
  });

  it("strips a trailing slash from the API base so endpoints concatenate cleanly", () => {
    expect(loadConfig({ ...COMPLETE, VITE_API_BASE_URL: "https://api.example.com/" }).values.apiBaseUrl).toBe(
      "https://api.example.com",
    );
  });

  it("keeps Number(x) || default semantics for the proctoring tunables", () => {
    const env = {
      ...COMPLETE,
      VITE_FACE_DETECTION_INTERVAL_SECONDS: "abc",
      VITE_HEAD_DOWN_CONFIRM_THRESHOLD: "0",
      VITE_HEAD_DOWN_PITCH_THRESHOLD_DEGREES: "30",
    };
    const { values } = loadConfig(env);
    expect(values.faceDetectionIntervalSeconds).toBe(4); // NaN -> default
    expect(values.headDownConfirmThreshold).toBe(3); // 0 is falsy -> default, as before
    expect(values.headDownPitchThresholdDegrees).toBe(30);
  });

  it("head-pose debug: on in dev builds, off in production builds, env overrides both", () => {
    expect(loadConfig({ ...COMPLETE, DEV: true }).values.headPoseDebug).toBe(true);
    expect(loadConfig({ ...COMPLETE, DEV: false }).values.headPoseDebug).toBe(false);
    expect(loadConfig({ ...COMPLETE, DEV: false, VITE_HEAD_POSE_DEBUG: "true" }).values.headPoseDebug).toBe(true);
    expect(loadConfig({ ...COMPLETE, DEV: true, VITE_HEAD_POSE_DEBUG: "false" }).values.headPoseDebug).toBe(false);
    expect(loadConfig({ ...COMPLETE, DEV: true, VITE_HEAD_POSE_DEBUG: "maybe" }).values.headPoseDebug).toBe(true);
  });
});

describe("mergeEnv (H6-A: runtime config overlay)", () => {
  it("returns the build-time env untouched when the container injected nothing", () => {
    const build = { ...COMPLETE, DEV: false };
    expect(mergeEnv(build, undefined)).toBe(build);
  });

  it("lets the container's values win over the ones baked into the bundle", () => {
    // The production image is built with deliberate placeholders; using
    // them would point the app at runtime.invalid.
    const merged = mergeEnv(
      { ...COMPLETE, VITE_API_BASE_URL: "http://runtime.invalid" },
      { VITE_API_BASE_URL: "https://api.hire.example.com" }
    );
    expect(merged.VITE_API_BASE_URL).toBe("https://api.hire.example.com");
  });

  it("ignores empty injected values instead of blanking a real one", () => {
    const merged = mergeEnv({ ...COMPLETE }, { VITE_API_BASE_URL: "", VITE_SUPABASE_URL: "   " });
    expect(merged.VITE_API_BASE_URL).toBe(COMPLETE.VITE_API_BASE_URL);
    expect(merged.VITE_SUPABASE_URL).toBe(COMPLETE.VITE_SUPABASE_URL);
  });

  it("carries injected values through to a loaded config", () => {
    const { values, problems } = loadConfig(
      mergeEnv({ DEV: false }, { ...COMPLETE } as Record<string, string>)
    );
    expect(problems).toEqual([]);
    expect(values.apiBaseUrl).toBe(COMPLETE.VITE_API_BASE_URL.replace(/\/+$/, ""));
  });
});
