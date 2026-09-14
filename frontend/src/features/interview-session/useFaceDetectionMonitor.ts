import { useEffect, useRef } from "react";
import { decomposeHeadPose } from "./headPose";

/**
 * PR-D + Part 2 (docs/proctoring-architecture.md /
 * docs/CURRENT_DECISIONS.md's "Proctoring Part 2 — head-pose detection
 * scope"): client-side face-presence AND head-pose monitoring — the
 * third integrity signal source, alongside PR-B's fullscreen/tab events
 * and PR-C's recording.
 *
 * Library choice, PR-D pass (2026-09-02, real-evidence check, not carried
 * over from the original doc): `@timadey/proctor` was the doc's
 * originally-named candidate, but a fresh check of the npm registry + its
 * GitHub repo found it's a 2-star, 4-commit, single-maintainer wrapper
 * around `@mediapipe/tasks-vision` with no functional value beyond that
 * wrapping -- 316 downloads/month, no real production validation.
 * Depending on `@mediapipe/tasks-vision` directly (Google's own,
 * nightly-published, industry-standard library) removes that bus-factor
 * risk for zero loss of capability.
 *
 * Detector choice, Part 2 pass (2026-09-02): PR-D originally used
 * `FaceDetector` (face count only, lighter). Part 2 needs head-pose,
 * which requires `FaceLandmarker`'s `outputFacialTransformationMatrixes`
 * -- so this pass REPLACES FaceDetector with FaceLandmarker rather than
 * running both models in the same tab (FaceLandmarker also reports face
 * count via `faceLandmarks.length`, so nothing is lost). `numFaces: 2`
 * (not the default 1) -- MULTIPLE_FACES_DETECTED only needs to know
 * "more than one," not an exact headcount; capping at 2 keeps the
 * landmarker's per-tick cost down versus tracking many faces.
 *
 * WASM + the model are self-hosted under frontend/public/mediapipe/
 * (blaze_face_short_range.tflite from the PR-D pass is now unused dead
 * weight -- left in place rather than deleted in this pass since removing
 * committed binary assets isn't this task's scope) rather than pulled
 * from a CDN at runtime -- consistent with this project's existing
 * preference to self-host dependencies (the @fontsource fonts) rather
 * than depend on a third party being reachable during a live candidate
 * interview. face_landmarker.task confirmed via direct download+`file`
 * check: a genuine ~3.6MB zip-format task bundle (HTTP 200 from
 * storage.googleapis.com/mediapipe-models/face_landmarker/...), not an
 * error page saved with the wrong extension.
 *
 * Camera sharing (verified against the actual installed livekit-client
 * types, not assumed): NO second getUserMedia call -- unchanged from
 * PR-D, see InterviewWorkspace.tsx's cameraTrackRefs.
 *
 * Frequency: unchanged from PR-D, one detection every
 * FACE_DETECTION_INTERVAL_SECONDS (default 4s, env-configurable).
 *
 * Debounce: NO_FACE_DETECTED/MULTIPLE_FACES_DETECTED keep PR-D's
 * CONFIRM_THRESHOLD (2 consecutive samples). HEAD_DOWN_SUSPECTED uses its
 * own, longer HEAD_DOWN_CONFIRM_THRESHOLD (default 3 samples, ~12s at the
 * default interval) -- deliberately longer than face-absence's window
 * per docs/CURRENT_DECISIONS.md: a glance down (notes, keyboard, second
 * monitor) is far more common and benign than disappearing entirely, so
 * it needs a longer sustained window before it's worth a reviewer's
 * attention. All three are edge-triggered (fire once per incident, reset
 * on a single good sample) -- same "log the event, not a heartbeat" shape
 * as PR-B's FULLSCREEN_EXITED.
 *
 * HEAD_DOWN_SUSPECTED threshold status -- NOT YET CALIBRATED against a
 * real capture (see headPose.ts's docstring for the full reasoning): this
 * sandbox's Browser pane blocks camera access, so the pitch-angle sign
 * and which axis truly isolates "nodding down" can only be confirmed via
 * a real live test. Until that happens, DEBUG_LOG_HEAD_POSE below prints
 * every decomposed angle to the console on every tick a single face is
 * detected, and the trigger condition uses `Math.abs(pitchDegrees)` (both
 * directions) rather than assuming the sign -- deliberately conservative
 * instrumentation, not a finished, silently-trusted threshold.
 *
 * Graceful degradation (explicit, not an afterthought):
 * - No camera track (permission denied, or camera-off) -> this hook
 *   simply never starts. No error, no retry, voice-only PR-B signals are
 *   entirely unaffected.
 * - FaceLandmarker fails to initialize (WASM/model fetch failure,
 *   unsupported browser) -> caught, logged, hook no-ops for the rest of
 *   the session. Never blocks or degrades the interview itself.
 */

const FACE_DETECTION_INTERVAL_SECONDS = Number(import.meta.env.VITE_FACE_DETECTION_INTERVAL_SECONDS) || 4;
const CONFIRM_THRESHOLD = 2;
const HEAD_DOWN_CONFIRM_THRESHOLD = Number(import.meta.env.VITE_HEAD_DOWN_CONFIRM_THRESHOLD) || 3;
const HEAD_DOWN_PITCH_THRESHOLD_DEGREES = Number(import.meta.env.VITE_HEAD_DOWN_PITCH_THRESHOLD_DEGREES) || 25;
// Temporary verification instrumentation (docs/CURRENT_DECISIONS.md's
// Part 2 entry) -- prints every decomposed angle so a real live test can
// confirm axis/sign before the threshold above is trusted. Left on by
// default during calibration; flip via VITE_HEAD_POSE_DEBUG=false once
// confirmed and this comment/flag should be revisited.
const DEBUG_LOG_HEAD_POSE = import.meta.env.VITE_HEAD_POSE_DEBUG !== "false";

const WASM_BASE_PATH = "/mediapipe/wasm";
const MODEL_ASSET_PATH = "/mediapipe/models/face_landmarker.task";

export type FaceDetectionEvent = "NO_FACE_DETECTED" | "MULTIPLE_FACES_DETECTED" | "HEAD_DOWN_SUSPECTED";

// Module-level singleton: the WASM runtime + model only ever need to load
// once per browser tab, not once per hook mount (a resume/reconnect, or a
// remount from an unrelated re-render higher up, must not re-download or
// re-initialize this).
let landmarkerPromise: Promise<import("@mediapipe/tasks-vision").FaceLandmarker> | null = null;

async function getFaceLandmarker() {
  if (!landmarkerPromise) {
    landmarkerPromise = (async () => {
      const { FaceLandmarker, FilesetResolver } = await import("@mediapipe/tasks-vision");
      const wasmFileset = await FilesetResolver.forVisionTasks(WASM_BASE_PATH);
      return FaceLandmarker.createFromOptions(wasmFileset, {
        baseOptions: { modelAssetPath: MODEL_ASSET_PATH },
        runningMode: "VIDEO",
        numFaces: 2,
        outputFacialTransformationMatrixes: true,
        outputFaceBlendshapes: false,
      });
    })();
  }
  return landmarkerPromise;
}

interface UseFaceDetectionMonitorArgs {
  /** Same gate PR-B's fullscreen monitoring already uses (!isCompleted &&
   *  phase !== "WAITING_ROOM") -- no proctoring signal fires during the
   *  free/unclocked waiting room, reusing an already-approved product
   *  decision rather than inventing new gating logic here. Part 2
   *  (2026-09-02): deliberately NOT narrowed further to exclude CODING --
   *  considered and rejected, see docs/CURRENT_DECISIONS.md. */
  active: boolean;
  /** The room's own published camera track (see the module docstring for
   *  exactly where this comes from) -- undefined/null when no camera is
   *  published (permission denied, or the candidate toggled it off). */
  cameraTrack: MediaStreamTrack | null | undefined;
  onFlag: (
    event: FaceDetectionEvent,
    payload: {
      face_count: number;
      consecutive_samples: number;
      severity: "medium" | "high";
      /** Only present on HEAD_DOWN_SUSPECTED -- the decomposed angles
       *  that triggered it, kept for later threshold calibration. */
      pitch_degrees?: number;
      yaw_degrees?: number;
      roll_degrees?: number;
    }
  ) => void;
}

export function useFaceDetectionMonitor({ active, cameraTrack, onFlag }: UseFaceDetectionMonitorArgs) {
  const onFlagRef = useRef(onFlag);
  onFlagRef.current = onFlag;

  useEffect(() => {
    if (!active || !cameraTrack) return;

    let cancelled = false;
    let intervalId: number | null = null;
    const video = document.createElement("video");
    // Not display:none -- some browsers pause frame decoding on a
    // display:none video element, which would silently starve detection.
    // Positioned off-screen and fully transparent instead so the browser
    // keeps decoding real frames while nothing is visible to the candidate.
    video.style.position = "absolute";
    video.style.opacity = "0";
    video.style.pointerEvents = "none";
    video.style.width = "640px";
    video.style.height = "480px";
    video.muted = true;
    video.playsInline = true;
    video.srcObject = new MediaStream([cameraTrack]);
    document.body.appendChild(video);
    // Real-verification finding from the PR-D pass (2026-09-02): without
    // an explicit .play() call, a live test correctly detected 0/1 faces
    // but silently, deterministically failed to ever detect a second
    // face -- readyState reported HAVE_ENOUGH_DATA throughout, but
    // detectForVideo's output never changed once the video stabilized.
    video.play().catch(() => {});

    let consecutiveNoFace = 0;
    let consecutiveMultiple = 0;
    let consecutiveHeadDown = 0;
    let noFaceFired = false;
    let multipleFacesFired = false;
    let headDownFired = false;

    const runDetection = async () => {
      if (cancelled || video.readyState < 2) return; // HAVE_CURRENT_DATA
      try {
        const landmarker = await getFaceLandmarker();
        if (cancelled) return;
        const result = landmarker.detectForVideo(video, performance.now());
        const faceCount = result.faceLandmarks.length;

        if (faceCount === 0) {
          consecutiveNoFace += 1;
          consecutiveMultiple = 0;
          consecutiveHeadDown = 0;
          multipleFacesFired = false;
          headDownFired = false;
          if (consecutiveNoFace >= CONFIRM_THRESHOLD && !noFaceFired) {
            noFaceFired = true;
            onFlagRef.current("NO_FACE_DETECTED", { face_count: 0, consecutive_samples: consecutiveNoFace, severity: "medium" });
          }
        } else if (faceCount > 1) {
          consecutiveMultiple += 1;
          consecutiveNoFace = 0;
          consecutiveHeadDown = 0;
          noFaceFired = false;
          headDownFired = false;
          if (consecutiveMultiple >= CONFIRM_THRESHOLD && !multipleFacesFired) {
            multipleFacesFired = true;
            // Aggregation/dashboard pass: severity added for display
            // consistency with PR-B's events. "high", not "medium" -- a
            // second face has far fewer benign explanations than absence.
            onFlagRef.current("MULTIPLE_FACES_DETECTED", { face_count: faceCount, consecutive_samples: consecutiveMultiple, severity: "high" });
          }
        } else {
          // Exactly one face -- reset the absence/multi-face counters and
          // latches immediately (not requiring 2 good samples to reset)
          // so a second, genuinely separate incident later in the
          // interview can still be detected, while one continuous
          // incident still only fires once.
          consecutiveNoFace = 0;
          consecutiveMultiple = 0;
          noFaceFired = false;
          multipleFacesFired = false;

          // Part 2: head-pose check, only meaningful with exactly one
          // face (an ambiguous/multi-face frame has no single pose to
          // trust). Fails soft to "no pose data" if the matrix is
          // missing for any reason (e.g. outputFacialTransformationMatrixes
          // rejected by an older WASM build) rather than throwing.
          const matrix = result.facialTransformationMatrixes[0];
          if (matrix) {
            const pose = decomposeHeadPose(matrix);
            if (DEBUG_LOG_HEAD_POSE) {
              // Temporary calibration instrumentation -- see this file's
              // docstring and headPose.ts. Intentionally console.log (not
              // .debug) so it's visible in devtools' default filter level
              // during a live calibration test.
              console.log("[Part2-HeadPose-DEBUG] pitch=%s yaw=%s roll=%s", pose.pitchDegrees.toFixed(1), pose.yawDegrees.toFixed(1), pose.rollDegrees.toFixed(1));
            }
            if (Math.abs(pose.pitchDegrees) > HEAD_DOWN_PITCH_THRESHOLD_DEGREES) {
              consecutiveHeadDown += 1;
              if (consecutiveHeadDown >= HEAD_DOWN_CONFIRM_THRESHOLD && !headDownFired) {
                headDownFired = true;
                onFlagRef.current("HEAD_DOWN_SUSPECTED", {
                  face_count: 1,
                  consecutive_samples: consecutiveHeadDown,
                  severity: "medium",
                  pitch_degrees: pose.pitchDegrees,
                  yaw_degrees: pose.yawDegrees,
                  roll_degrees: pose.rollDegrees,
                });
              }
            } else {
              consecutiveHeadDown = 0;
              headDownFired = false;
            }
          }
        }
      } catch (e) {
        // Graceful degradation: a detection-loop failure (e.g. the video
        // element's frame isn't decodable this tick) must never throw out
        // of an interval callback and never affects the interview itself.
        console.warn("[PR-D/Part 2] Face detection tick failed, skipping:", e);
      }
    };

    (async () => {
      try {
        await getFaceLandmarker();
      } catch (e) {
        // Graceful degradation: WASM/model failed to load (offline,
        // unsupported browser, self-hosted asset missing). Log and never
        // start the interval -- voice-only proctoring signals (PR-B) are
        // completely unaffected, and the interview itself never blocks.
        console.warn("[PR-D/Part 2] Face landmarker failed to initialize; face/head-pose monitoring disabled for this session:", e);
        return;
      }
      if (cancelled) return;
      intervalId = window.setInterval(runDetection, FACE_DETECTION_INTERVAL_SECONDS * 1000);
    })();

    return () => {
      cancelled = true;
      if (intervalId != null) window.clearInterval(intervalId);
      video.pause();
      video.srcObject = null;
      video.remove();
    };
  }, [active, cameraTrack]);
}
