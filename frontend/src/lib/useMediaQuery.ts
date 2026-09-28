import { useCallback, useSyncExternalStore } from "react";

/**
 * Responsive plan R0 (docs/responsive-design-plan.md §3): the one JS-side
 * breakpoint helper. CSS (`sm:` / `md:` / `lg:` classes) decides layout
 * wherever it can; this exists only for the handful of places where a
 * component needs the answer as a value -- the self-view's pixel size and
 * default position, the controller bar's layout choice, a bottom-sheet vs
 * side-panel switch. Keep it that way: if a layout can be expressed with
 * Tailwind classes, do not reach for this hook.
 *
 * Mirrors Tailwind v4's default screens (tailwind.config.js adds none).
 */
export const BREAKPOINTS = { sm: 640, md: 768, lg: 1024, xl: 1280 } as const;
export type Breakpoint = keyof typeof BREAKPOINTS;

function subscribe(query: string, onChange: () => void): () => void {
  if (typeof window === "undefined" || !window.matchMedia) return () => {};
  const mql = window.matchMedia(query);
  mql.addEventListener("change", onChange);
  return () => mql.removeEventListener("change", onChange);
}

/** True while `query` matches; re-renders on change. False before mount / without matchMedia. */
export function useMediaQuery(query: string): boolean {
  const subscribeToQuery = useCallback((onChange: () => void) => subscribe(query, onChange), [query]);
  const getSnapshot = useCallback(
    () => (typeof window !== "undefined" && window.matchMedia ? window.matchMedia(query).matches : false),
    [query],
  );
  return useSyncExternalStore(subscribeToQuery, getSnapshot, () => false);
}

/** True at and above the named Tailwind breakpoint (same semantics as the `md:` prefix). */
export function useBreakpoint(name: Breakpoint): boolean {
  return useMediaQuery(`(min-width: ${BREAKPOINTS[name]}px)`);
}

/** Coarse pointer = touch device (phone/tablet); used for touch-target sizing decisions. */
export function useIsTouch(): boolean {
  return useMediaQuery("(pointer: coarse)");
}
