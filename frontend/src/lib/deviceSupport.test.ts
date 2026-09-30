/**
 * R5: the gate that implements product decision D1 — phones are not
 * supported for the live interview (docs/CURRENT_DECISIONS.md).
 *
 * This is tested rather than eyeballed because the interesting cases are
 * devices nobody has to hand: an iPhone that cannot fullscreen at all, and
 * an Android phone that *can* and would therefore sail past a capability
 * check before being terminated the first time its keyboard appeared. The
 * screenshot harness cannot produce either.
 */
import { describe, expect, it } from "vitest";

import {
  TABLET_MIN_EDGE_PX,
  isCodingSupported,
  isLiveInterviewSupported,
  type DeviceProbe,
} from "./deviceSupport";

const probe = (over: Partial<DeviceProbe> = {}): DeviceProbe => ({
  canFullscreen: true,
  coarsePointer: false,
  shortestViewportEdgePx: 1024,
  ...over,
});

describe("isLiveInterviewSupported", () => {
  it("allows a laptop", () => {
    expect(isLiveInterviewSupported(probe({ shortestViewportEdgePx: 800 }))).toBe(true);
  });

  it("allows a narrow laptop window, because the pointer is fine", () => {
    // 600px wide but mouse-driven: not a phone, must not be gated.
    expect(isLiveInterviewSupported(probe({ shortestViewportEdgePx: 600 }))).toBe(true);
  });

  it("blocks anything that cannot fullscreen the document (iOS Safari)", () => {
    expect(isLiveInterviewSupported(probe({ canFullscreen: false }))).toBe(false);
  });

  it("blocks an iPhone even though it is otherwise a normal browser", () => {
    // iOS Safari: no document fullscreen, coarse pointer, 375x812.
    expect(
      isLiveInterviewSupported({ canFullscreen: false, coarsePointer: true, shortestViewportEdgePx: 375 })
    ).toBe(false);
  });

  it("blocks an Android phone, which CAN fullscreen and would otherwise pass", () => {
    // The case a capability-only check gets wrong: fullscreen is supported
    // and then lost to the keyboard, terminating the candidate mid-answer.
    expect(
      isLiveInterviewSupported({ canFullscreen: true, coarsePointer: true, shortestViewportEdgePx: 375 })
    ).toBe(false);
  });

  it("blocks a phone held in landscape too", () => {
    // 812x375 — a width-only rule would read 812 and let this through.
    // The shorter edge is still 375.
    expect(
      isLiveInterviewSupported({ canFullscreen: true, coarsePointer: true, shortestViewportEdgePx: 375 })
    ).toBe(false);
  });

  it("allows an iPad in either orientation", () => {
    // 768x1024 and 1024x768 both have a shorter edge of exactly 768.
    expect(
      isLiveInterviewSupported({ canFullscreen: true, coarsePointer: true, shortestViewportEdgePx: 768 })
    ).toBe(true);
  });

  it("puts the boundary exactly at the tablet edge", () => {
    const touch = (edge: number) =>
      isLiveInterviewSupported({ canFullscreen: true, coarsePointer: true, shortestViewportEdgePx: edge });
    expect(touch(TABLET_MIN_EDGE_PX - 1)).toBe(false);
    expect(touch(TABLET_MIN_EDGE_PX)).toBe(true);
  });

  it("gates on capability even on a large touch screen", () => {
    // A big kiosk-style touch display that still cannot fullscreen: the
    // proctoring contract cannot run, so size does not rescue it.
    expect(
      isLiveInterviewSupported({ canFullscreen: false, coarsePointer: true, shortestViewportEdgePx: 1200 })
    ).toBe(false);
  });
});

/**
 * D2 is a different question from D1 and must not collapse into it: a
 * tablet is a *supported device* that takes verbal and MCQ sections
 * normally, and is blocked from coding alone.
 */
describe("isCodingSupported", () => {
  it("allows a laptop", () => {
    expect(isCodingSupported(probe())).toBe(true);
  });

  it("blocks a tablet, which passes the interview gate but has no keyboard", () => {
    const tablet: DeviceProbe = { canFullscreen: true, coarsePointer: true, shortestViewportEdgePx: 768 };
    // The pair that matters: supported for the interview, not for coding.
    expect(isLiveInterviewSupported(tablet)).toBe(true);
    expect(isCodingSupported(tablet)).toBe(false);
  });

  it("blocks a large touch screen too — it is the pointer, not the size", () => {
    expect(
      isCodingSupported({ canFullscreen: true, coarsePointer: true, shortestViewportEdgePx: 1400 })
    ).toBe(false);
  });

  it("allows a narrow laptop window, where size would say otherwise", () => {
    expect(
      isCodingSupported({ canFullscreen: true, coarsePointer: false, shortestViewportEdgePx: 500 })
    ).toBe(true);
  });
});
