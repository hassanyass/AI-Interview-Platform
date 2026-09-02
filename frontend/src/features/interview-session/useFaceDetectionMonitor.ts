import { useEffect, useRef } from "react";

/**
 * PR-D (docs/proctoring-architecture.md): client-side face-presence
 * monitoring — the third and final integrity signal source, alongside
 * PR-B's fullscreen/tab events and PR-C's recording.
 *
 * Library choice (2026-09-02, real-evidence check, not carried over from
 * the original doc): `@timadey/proctor` was the doc's originally-named
 * candidate, but a fresh check of the npm registry + its GitHub repo found
 * it's a 2-star, 4-commit, single-maintainer wrapper around
 * `@mediapipe/tasks-vision` with no functional value beyond that wrapping
 * -- 316 downloads/month, no real production validation. Depending on
 * `@mediapipe/tasks-vision` directly (Google's own, nightly-published,
 * industry-standard library) removes that bus-factor risk for zero loss
 * of capability. Using `FaceDetector` specifically, not the heavier
 * `FaceLandmarker` -- this pass only needs face COUNT (present/absent/
 * multiple), not the 478-point mesh gaze/head-pose would need. Gaze/
 * head-pose is deliberately deferred to its own later addition (see the
 * plan this was built from) -- reliable gaze estimation needs the heavier
 * landmarker and is known to degrade at typical home-webcam resolution/
 * lighting, exactly the kind of flaky signal the architecture doc's own
 * fairness non-negotiable warns against shipping.
 *
 * WASM + the BlazeFace short-range model are self-hosted under
 * frontend/public/mediapipe/ (copied from the installed package + fetched
 * from Google's model storage once) rather than pulled from a CDN at
 * runtime -- consistent with this project's existing preference to
 * self-host dependencies (the @fontsource fonts) rather than depend on a
 * third party being reachable during a live candidate interview.
 *
 * Camera sharing (verified against the actual installed livekit-client
 * types, not assumed): NO second getUserMedia call. The camera
 * MediaStreamTrack this hook receives is the exact same one
 * @livekit/components-react already published for the room (via
 * room.localParticipant.getTrackPublication(Track.Source.Camera)?.track
 * ?.mediaStreamTrack in InterviewWorkspace.tsx) -- confirmed Track.
 * mediaStreamTrack and Participant.getTrackPublication both exist in
 * node_modules/livekit-client's real type definitions before this was
 * built on that assumption.
 *
 * Frequency: one detection every FACE_DETECTION_INTERVAL_SECONDS (default
 * 4s, env-configurable -- matching this project's established pattern for
 * timing constants, e.g. the agent's WAITING_ROOM_TIMEOUT_SECONDS). A
 * lightweight face-count model run 30x/second would compete with LiveKit's
 * own WebRTC encode/decode in the same tab; face-absence/multi-face are
 * sustained multi-second conditions, not single-frame events, so a few-
 * second sampling interval loses nothing meaningful while cutting CPU cost
 * by roughly two orders of magnitude versus continuous analysis.
 *
 * Debounce: a condition must be observed on CONFIRM_THRESHOLD (2)
 * consecutive samples before an event fires -- a single dropped/blurred
 * frame must never become a false flag, per the architecture doc's own
 * fairness requirement. Edge-triggered: fires once when a condition is
 * newly confirmed, not once per interval for the whole duration of one
 * incident (same "log the event, not a heartbeat" shape as PR-B's
 * FULLSCREEN_EXITED, which also has no "restored" companion event).
 *
 * Graceful degradation (explicit, not an afterthought):
 * - No camera track (permission denied, or camera-off) -> this hook
 *   simply never starts. No error, no retry, voice-only PR-B signals are
 *   entirely unaffected.
 * - FaceDetector fails to initialize (WASM/model fetch failure,
 *   unsupported browser) -> caught, logged, hook no-ops for the rest of
 *   the session. Never blocks or degrades the interview itself.
 */

const FACE_DETECTION_INTERVAL_SECONDS = Number(import.meta.env.VITE_FACE_DETECTION_INTERVAL_SECONDS) || 4;
const CONFIRM_THRESHOLD = 2;

const WASM_BASE_PATH = "/mediapipe/wasm";
const MODEL_ASSET_PATH = "/mediapipe/models/blaze_face_short_range.tflite";

export type FaceDetectionEvent = "NO_FACE_DETECTED" | "MULTIPLE_FACES_DETECTED";

// Module-level singleton: the WASM runtime + model only ever need to load
// once per browser tab, not once per hook mount (a resume/reconnect, or a
// remount from an unrelated re-render higher up, must not re-download or
// re-initialize this).
let detectorPromise: Promise<import("@mediapipe/tasks-vision").FaceDetector> | null = null;

async function getFaceDetector() {
  if (!detectorPromise) {
    detectorPromise = (async () => {
      const { FaceDetector, FilesetResolver } = await import("@mediapipe/tasks-vision");
      const wasmFileset = await FilesetResolver.forVisionTasks(WASM_BASE_PATH);
      return FaceDetector.createFromOptions(wasmFileset, {
        baseOptions: { modelAssetPath: MODEL_ASSET_PATH },
        runningMode: "VIDEO",
      });
    })();
  }
  return detectorPromise;
}

interface UseFaceDetectionMonitorArgs {
  /** Same gate PR-B's fullscreen monitoring already uses (!isCompleted &&
   *  phase !== "WAITING_ROOM") -- no proctoring signal fires during the
   *  free/unclocked waiting room, reusing an already-approved product
   *  decision rather than inventing new gating logic here. */
  active: boolean;
  /** The room's own published camera track (see the module docstring for
   *  exactly where this comes from) -- undefined/null when no camera is
   *  published (permission denied, or the candidate toggled it off). */
  cameraTrack: MediaStreamTrack | null | undefined;
  onFlag: (event: FaceDetectionEvent, payload: { face_count: number; consecutive_samples: number; severity: "medium" | "high" }) => void;
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
    // Sized to a real resolution rather than 1x1 -- a live test against a
    // 1x1 element produced constant WebGL "Framebuffer is incomplete:
    // Attachment has zero size" warnings on every tick (present whether
    // that tick's detection was correct or not, so this specific warning
    // turned out to be unrelated noise, not the cause of the real bug
    // found below -- but there's no reason to keep triggering it either).
    video.style.width = "640px";
    video.style.height = "480px";
    video.muted = true;
    video.playsInline = true;
    video.srcObject = new MediaStream([cameraTrack]);
    document.body.appendChild(video);
    // Real-verification finding (2026-09-02): without an explicit .play()
    // call, a live test correctly detected 0/1 faces (blank/single-face
    // cases) but silently, deterministically failed to ever detect a
    // second face -- readyState reported HAVE_ENOUGH_DATA throughout, but
    // detectForVideo's output never changed once the video stabilized. A
    // muted+playsInline video assigned a live MediaStream autoplays on most
    // browsers without this call, which is exactly why the simpler cases
    // still worked well enough to look correct -- but it's not guaranteed,
    // and this is the standards-correct thing to do regardless of which
    // browser happens to paper over its absence.
    video.play().catch(() => {});

    let consecutiveNoFace = 0;
    let consecutiveMultiple = 0;
    let noFaceFired = false;
    let multipleFacesFired = false;

    const runDetection = async () => {
      if (cancelled || video.readyState < 2) return; // HAVE_CURRENT_DATA
      try {
        const detector = await getFaceDetector();
        if (cancelled) return;
        const result = detector.detectForVideo(video, performance.now());
        const faceCount = result.detections.length;

        if (faceCount === 0) {
          consecutiveNoFace += 1;
          consecutiveMultiple = 0;
          multipleFacesFired = false;
          if (consecutiveNoFace >= CONFIRM_THRESHOLD && !noFaceFired) {
            noFaceFired = true;
            // Aggregation/dashboard pass: severity added for display
            // consistency with PR-B's events. "medium", not "high" --
            // absence alone has real benign explanations (stepped away
            // briefly, connection hiccup); a second face has far fewer,
            // hence higher, below.
            onFlagRef.current("NO_FACE_DETECTED", { face_count: 0, consecutive_samples: consecutiveNoFace, severity: "medium" });
          }
        } else if (faceCount > 1) {
          consecutiveMultiple += 1;
          consecutiveNoFace = 0;
          noFaceFired = false;
          if (consecutiveMultiple >= CONFIRM_THRESHOLD && !multipleFacesFired) {
            multipleFacesFired = true;
            onFlagRef.current("MULTIPLE_FACES_DETECTED", { face_count: faceCount, consecutive_samples: consecutiveMultiple, severity: "high" });
          }
        } else {
          // Exactly one face -- the normal case. Reset both debounce
          // counters and both "already fired" latches immediately (not
          // requiring 2 good samples to reset) so a second, genuinely
          // separate incident later in the interview can still be
          // detected, while one continuous incident still only fires once.
          consecutiveNoFace = 0;
          consecutiveMultiple = 0;
          noFaceFired = false;
          multipleFacesFired = false;
        }
      } catch (e) {
        // Graceful degradation: a detection-loop failure (e.g. the video
        // element's frame isn't decodable this tick) must never throw out
        // of an interval callback and never affects the interview itself.
        console.warn("[PR-D] Face detection tick failed, skipping:", e);
      }
    };

    (async () => {
      try {
        await getFaceDetector();
      } catch (e) {
        // Graceful degradation: WASM/model failed to load (offline,
        // unsupported browser, self-hosted asset missing). Log and never
        // start the interval -- voice-only proctoring signals (PR-B) are
        // completely unaffected, and the interview itself never blocks.
        console.warn("[PR-D] Face detector failed to initialize; face-presence monitoring disabled for this session:", e);
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
