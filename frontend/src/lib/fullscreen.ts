/**
 * PR-B (docs/proctoring-architecture.md): shared Fullscreen API helper,
 * used by both fullscreen gates — IntroScreen's Start Session and
 * WaitingRoomScreen's Continue — so the cross-browser prefix handling and
 * failure behavior live in exactly one place.
 *
 * Deliberately swallows every failure into a plain `false` rather than
 * throwing: a rejected/unsupported requestFullscreen() is an expected,
 * common outcome (denied, unsupported browser, not called within a fresh
 * user gesture), not an exceptional one — callers just show their own
 * inline "fullscreen is required" error and let the candidate retry.
 */
export async function requestFullscreen(): Promise<boolean> {
  try {
    const el = document.documentElement as HTMLElement & {
      webkitRequestFullscreen?: () => Promise<void> | void;
      mozRequestFullScreen?: () => Promise<void> | void;
      msRequestFullscreen?: () => Promise<void> | void;
    };
    const request =
      el.requestFullscreen?.bind(el) ||
      el.webkitRequestFullscreen?.bind(el) ||
      el.mozRequestFullScreen?.bind(el) ||
      el.msRequestFullscreen?.bind(el);
    if (!request) return false;
    await request();
    return true;
  } catch {
    return false;
  }
}

/**
 * Can this browser fullscreen the DOCUMENT at all? Asked before anything is
 * attempted, unlike `requestFullscreen()` above, which only reports failure
 * after the candidate has already pressed Start.
 *
 * The case this exists for: iOS Safari on iPhone exposes no document-level
 * fullscreen at all — only `<video>` elements can go fullscreen — so PR-B's
 * "fullscreen required, 10s grace, then terminate" can never succeed there.
 * `lib/deviceSupport.ts` turns this into the policy decision; this function
 * only reports the capability, next to the prefix list it shares with
 * `requestFullscreen()`.
 */
export function canFullscreenDocument(): boolean {
  if (typeof document === "undefined") return false;
  const el = document.documentElement as HTMLElement & {
    webkitRequestFullscreen?: () => Promise<void> | void;
    mozRequestFullScreen?: () => Promise<void> | void;
    msRequestFullscreen?: () => Promise<void> | void;
  };
  return Boolean(
    el.requestFullscreen || el.webkitRequestFullscreen || el.mozRequestFullScreen || el.msRequestFullscreen
  );
}

/** True if the document is currently in fullscreen (any vendor prefix). */
export function isFullscreenActive(): boolean {
  const doc = document as Document & {
    webkitFullscreenElement?: Element | null;
    mozFullScreenElement?: Element | null;
    msFullscreenElement?: Element | null;
  };
  return Boolean(
    doc.fullscreenElement || doc.webkitFullscreenElement || doc.mozFullScreenElement || doc.msFullscreenElement
  );
}
