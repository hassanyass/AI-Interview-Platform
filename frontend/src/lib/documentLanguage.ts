/**
 * Owns `<html lang>` and `<html dir>`.
 *
 * R7 found that nothing did. `LanguageToggle` — a presentational button —
 * set both in a `useEffect`, so:
 *
 * - pages that render the toggle set direction only *after* mount, flashing
 *   LTR on every load; and
 * - pages that do not render it (`/login`, and `InterviewSession`'s
 *   loading / error / cvMissing branches) **never set it at all**. Verified
 *   live: with `preferred-lang=ar`, `/login` rendered Arabic text with an
 *   empty `dir`, `lang="en"` and a computed direction of `ltr`.
 *
 * That made every `ps-`/`pe-`/`text-start`/`rtl:` class written across
 * R1–R6 inert on those pages. It went unseen for the whole track because
 * `scripts/responsive-shots.cjs` sets `dir` itself before shooting, so the
 * harness was compensating for the bug it should have caught.
 *
 * Direction is a property of the language, so it belongs beside the i18n
 * setup and is applied at init — before first paint — and again on every
 * `languageChanged`. The toggle now only changes the language.
 */

export const RTL_LANGUAGES = new Set(["ar", "fa", "he", "ur"]);

export function directionFor(language: string): "rtl" | "ltr" {
  // `ar-AE` and `ar` must agree, so compare on the base subtag.
  return RTL_LANGUAGES.has(language.split("-")[0].toLowerCase()) ? "rtl" : "ltr";
}

/** Applies both attributes. Safe to call before React mounts. */
export function applyDocumentLanguage(language: string): void {
  if (typeof document === "undefined") return;
  document.documentElement.lang = language;
  document.documentElement.dir = directionFor(language);
}
