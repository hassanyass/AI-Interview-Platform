// @vitest-environment jsdom
/**
 * R7: direction used to be set by `LanguageToggle`'s effect, so it existed
 * only on pages that rendered that button — `/login` served Arabic text in
 * a left-to-right layout and never corrected itself. These tests pin the
 * rule and the attributes, because the screenshot harness cannot catch a
 * regression here: it sets `dir` itself before shooting, which is exactly
 * how the original bug survived the whole track.
 */
import { afterEach, describe, expect, it } from "vitest";

import { applyDocumentLanguage, directionFor } from "./documentLanguage";

afterEach(() => {
  document.documentElement.removeAttribute("dir");
  document.documentElement.removeAttribute("lang");
});

describe("directionFor", () => {
  it("returns rtl for Arabic", () => {
    expect(directionFor("ar")).toBe("rtl");
  });

  it("returns ltr for English", () => {
    expect(directionFor("en")).toBe("ltr");
  });

  it("agrees between a base tag and a regional one", () => {
    // i18next may hand back `ar-AE` where the stored preference is `ar`.
    expect(directionFor("ar-AE")).toBe("rtl");
    expect(directionFor("en-GB")).toBe("ltr");
  });

  it("ignores case", () => {
    expect(directionFor("AR")).toBe("rtl");
  });

  it("treats an unknown language as ltr rather than guessing", () => {
    expect(directionFor("xx")).toBe("ltr");
  });
});

describe("applyDocumentLanguage", () => {
  it("sets both lang and dir", () => {
    applyDocumentLanguage("ar");
    expect(document.documentElement.lang).toBe("ar");
    expect(document.documentElement.dir).toBe("rtl");
  });

  it("flips back when the language changes", () => {
    applyDocumentLanguage("ar");
    applyDocumentLanguage("en");
    expect(document.documentElement.lang).toBe("en");
    expect(document.documentElement.dir).toBe("ltr");
  });

  it("sets dir explicitly for ltr instead of leaving it empty", () => {
    // An empty `dir` inherits, which is what made the original bug look
    // fine in English and wrong only in Arabic.
    applyDocumentLanguage("en");
    expect(document.documentElement.dir).toBe("ltr");
  });
});
