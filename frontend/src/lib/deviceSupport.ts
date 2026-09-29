import { canFullscreenDocument } from "./fullscreen";

/**
 * Is this device allowed to take the LIVE interview?
 *
 * Product decision D1 (docs/CURRENT_DECISIONS.md, "Device support for the
 * live interview", 2026-09-29): **phones are not supported.** Candidate
 * entry — invite, apply, OTP, CV upload — stays fully supported on a phone;
 * only the interview itself is gated, and it is gated *before* the Start
 * button rather than failing at a fullscreen request that cannot succeed.
 *
 * Two independent reasons, which is why one test is not enough:
 *
 * 1. **iOS Safari cannot fullscreen the document at all.** PR-B's
 *    "fullscreen required, 10s grace, then terminate" can never run there.
 *    `canFullscreenDocument()` catches this.
 * 2. **Android Chrome on a phone CAN fullscreen** — and then drops it every
 *    time the keyboard or the notification shade appears, which would
 *    terminate a candidate for typing. A capability probe waves this case
 *    straight through, so it needs a size test as well.
 *
 * The size test uses the **shorter** viewport edge deliberately: a phone
 * held in landscape is ~812px wide, so a width-only rule would let it
 * through. It is paired with a coarse-pointer test so that someone working
 * in a narrow window on a laptop is not gated for no reason.
 */

/** The shorter edge of the smallest supported device, an iPad in portrait
 *  (768×1024). Anything narrower than this on a touch device is a phone. */
export const TABLET_MIN_EDGE_PX = 768;

export interface DeviceProbe {
  /** Can the browser fullscreen the document (any vendor prefix)? */
  canFullscreen: boolean;
  /** Coarse pointer = finger. Excludes laptops with small windows. */
  coarsePointer: boolean;
  /** min(width, height), so rotating a phone does not change the answer. */
  shortestViewportEdgePx: number;
}

/** Reads the current environment. Split from the decision below so the
 *  policy can be tested without a browser. */
export function probeDevice(): DeviceProbe {
  const width = typeof window === "undefined" ? 0 : window.innerWidth;
  const height = typeof window === "undefined" ? 0 : window.innerHeight;
  return {
    canFullscreen: canFullscreenDocument(),
    // No matchMedia (jsdom, very old browsers) is treated as a fine
    // pointer: the capability test above still stands on its own, and
    // guessing "touch" would gate desktops that simply cannot answer.
    coarsePointer:
      typeof window !== "undefined" &&
      typeof window.matchMedia === "function" &&
      window.matchMedia("(pointer: coarse)").matches,
    shortestViewportEdgePx: Math.min(width, height),
  };
}

/** The policy. Pure, so every case below is covered by a real test. */
export function isLiveInterviewSupported(probe: DeviceProbe): boolean {
  if (!probe.canFullscreen) return false;
  if (probe.coarsePointer && probe.shortestViewportEdgePx < TABLET_MIN_EDGE_PX) return false;
  return true;
}
