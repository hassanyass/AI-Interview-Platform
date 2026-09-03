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
