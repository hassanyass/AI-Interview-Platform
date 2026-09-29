#!/usr/bin/env node
/**
 * Responsive harness (docs/responsive-design-plan.md, R0).
 *
 * Opens each route at every viewport in the plan's §1 matrix, in LTR and
 * RTL, and writes:
 *   frontend/.responsive/<route>__<viewport>__<dir>.png
 *   frontend/.responsive/report.json   (one entry per shot, see below)
 * and prints a summary table. Findings per shot:
 *   - overflow:  document.scrollWidth > window.innerWidth (horizontal scroll)
 *   - overflowers: up to 8 elements whose right edge passes the viewport
 *   - smallTargets: interactive elements under 44x44 CSS px on touch widths
 *   - hiddenControls: buttons/links present in the DOM but not rendered
 *     (display:none) -- the `hidden sm:flex` pattern the plan is hunting
 *   - innerScrollers: nested containers that scroll horizontally (a table
 *     in overflow-x-auto, or the admin <main> hiding a too-wide page) --
 *     not always a defect, but always worth a look
 * Anything inside an element with `data-responsive-ignore` (the DEV
 * PREVIEW strips) is skipped.
 *
 * Usage (dev server must be running on BASE_URL, default 127.0.0.1:5174):
 *   node scripts/responsive-shots.cjs
 *   node scripts/responsive-shots.cjs --strict            # exit 1 on any overflow
 *   node scripts/responsive-shots.cjs --routes=login,dev/admin-preview
 *     (leading slash optional -- Git Bash on Windows rewrites "/dev/..."
 *      into a Windows path before node sees it, so omit it there)
 *   node scripts/responsive-shots.cjs --viewports=phone,tablet --dirs=ltr
 * Env: BASE_URL, RESPONSIVE_ROUTES (comma list appended to the defaults),
 *      RESPONSIVE_OUT (output dir).
 *
 * Only routes that render without a backend are listed by default. Add
 * authenticated routes through RESPONSIVE_ROUTES once a dev login exists.
 * RTL is applied the way LanguageToggle does it (preferred-lang in
 * localStorage + `dir` on <html>), set before the page's own scripts run.
 */
const path = require("node:path");
const fs = require("node:fs");
const puppeteer = require("puppeteer");

const BASE_URL = process.env.BASE_URL || "http://127.0.0.1:5174";
const OUT_DIR = process.env.RESPONSIVE_OUT || path.join(__dirname, "..", ".responsive");

// docs/responsive-design-plan.md §1 -- keep in step with the doc.
const VIEWPORTS = {
  "phone-s":     { width: 360,  height: 740, touch: true },
  "phone":       { width: 375,  height: 812, touch: true },
  "phone-land":  { width: 812,  height: 375, touch: true },
  "tablet":      { width: 768,  height: 1024, touch: true },
  "tablet-land": { width: 1024, height: 768, touch: true },
  "laptop":      { width: 1280, height: 800, touch: false },
  "desktop":     { width: 1440, height: 900, touch: false },
};

const DEFAULT_ROUTES = [
  "/login",
  "/dev/verbal-preview",
  "/dev/sections-preview",
  "/dev/start-preview",
  "/dev/unsupported-preview",
  "/dev/admin-preview",
  "/dev/results-preview",
  "/dev/job-create-preview",
  "/dev/candidate-result-preview/job-preview/sess-preview",
  "/dev/workspace-preview",
];

const MIN_TARGET_PX = 44;

function parseArgs(argv) {
  const args = { strict: false, routes: null, viewports: null, dirs: null };
  for (const a of argv) {
    if (a === "--strict") args.strict = true;
    else if (a.startsWith("--routes=")) args.routes = a.slice(9).split(",").filter(Boolean);
    else if (a.startsWith("--viewports=")) args.viewports = a.slice(12).split(",").filter(Boolean);
    else if (a.startsWith("--dirs=")) args.dirs = a.slice(7).split(",").filter(Boolean);
  }
  return args;
}

/** Runs in the page. Returns the layout findings for the current viewport. */
function inspectPage(minTarget, isTouch) {
  const innerW = window.innerWidth;
  const scrollW = document.documentElement.scrollWidth;
  const describe = (el) => {
    const cls = (el.getAttribute("class") || "").split(/\s+/).slice(0, 4).join(" ");
    const text = (el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 30);
    return `${el.tagName.toLowerCase()}${cls ? "." + cls.replace(/\s+/g, ".") : ""}${text ? ` "${text}"` : ""}`;
  };
  const ignored = (el) => Boolean(el.closest("[data-responsive-ignore]"));
  const all = Array.from(document.querySelectorAll("body *")).filter((el) => !ignored(el));
  const overflowers = all
    .filter((el) => {
      const r = el.getBoundingClientRect();
      return r.width > 0 && r.right > innerW + 1;
    })
    .slice(0, 8)
    .map(describe);
  const interactive = Array.from(document.querySelectorAll('button, a[href], input, select, textarea, [role="button"]')).filter((el) => !ignored(el));
  const smallTargets = isTouch
    ? interactive
        .filter((el) => {
          const r = el.getBoundingClientRect();
          const visible = r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== "hidden";
          return visible && (r.width < minTarget || r.height < minTarget);
        })
        .map((el) => {
          const r = el.getBoundingClientRect();
          return `${describe(el)} ${Math.round(r.width)}x${Math.round(r.height)}`;
        })
    : [];
  const hiddenControls = interactive
    .filter((el) => getComputedStyle(el).display === "none")
    .map(describe);
  const innerScrollers = all
    .filter((el) => {
      const ox = getComputedStyle(el).overflowX;
      return (ox === "auto" || ox === "scroll") && el.scrollWidth > el.clientWidth + 1;
    })
    .slice(0, 8)
    .map((el) => `${describe(el)} ${el.scrollWidth}/${el.clientWidth}`);
  return { innerW, scrollW, overflow: scrollW > innerW, overflowers, smallTargets, hiddenControls, innerScrollers };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const routes = (args.routes || [...DEFAULT_ROUTES, ...(process.env.RESPONSIVE_ROUTES || "").split(",").filter(Boolean)])
    .map((r) => (r.startsWith("/") ? r : "/" + r));
  const viewportNames = args.viewports || Object.keys(VIEWPORTS);
  const dirs = args.dirs || ["ltr", "rtl"];
  for (const v of viewportNames) if (!VIEWPORTS[v]) throw new Error(`Unknown viewport "${v}". Known: ${Object.keys(VIEWPORTS).join(", ")}`);

  fs.mkdirSync(OUT_DIR, { recursive: true });
  const browser = await puppeteer.launch({ headless: true });
  const report = [];
  try {
    for (const route of routes) {
      for (const dir of dirs) {
        for (const vName of viewportNames) {
          const vp = VIEWPORTS[vName];
          const page = await browser.newPage();
          await page.setViewport({ width: vp.width, height: vp.height, deviceScaleFactor: 1, isMobile: vp.touch, hasTouch: vp.touch });
          await page.evaluateOnNewDocument((lang, direction) => {
            try { localStorage.setItem("preferred-lang", lang); } catch {}
            document.documentElement.lang = lang;
            document.documentElement.dir = direction;
          }, dir === "rtl" ? "ar" : "en", dir);
          const url = BASE_URL + route;
          let error = null;
          try {
            await page.goto(url, { waitUntil: "networkidle0", timeout: 30000 });
            await page.evaluate(() => document.fonts && document.fonts.ready);
            await new Promise((r) => setTimeout(r, 300));
          } catch (e) {
            error = String(e.message || e);
          }
          const slug = route.replace(/^\//, "").replace(/[^a-z0-9]+/gi, "-") || "root";
          const file = `${slug}__${vName}__${dir}.png`;
          let findings = null;
          if (!error) {
            findings = await page.evaluate(inspectPage, MIN_TARGET_PX, vp.touch);
            await page.screenshot({ path: path.join(OUT_DIR, file), fullPage: true });
          }
          report.push({ route, viewport: vName, width: vp.width, height: vp.height, dir, file, error, ...(findings || {}) });
          await page.close();
          const flag = error ? "ERR " : findings.overflow ? "OVER" : "ok  ";
          const small = findings && findings.smallTargets.length ? ` small=${findings.smallTargets.length}` : "";
          const hidden = findings && findings.hiddenControls.length ? ` hidden=${findings.hiddenControls.length}` : "";
          const inner = findings && findings.innerScrollers.length ? ` innerScroll=${findings.innerScrollers.length}` : "";
          console.log(`${flag} ${route.padEnd(24)} ${vName.padEnd(12)} ${dir}  ${error ? error : `${findings.scrollW}/${findings.innerW}${small}${hidden}${inner}`}`);
        }
      }
    }
  } finally {
    await browser.close();
  }

  fs.writeFileSync(path.join(OUT_DIR, "report.json"), JSON.stringify(report, null, 2));
  const overflowing = report.filter((r) => r.overflow);
  const errored = report.filter((r) => r.error);
  console.log(`\n${report.length} shots -> ${OUT_DIR}`);
  console.log(`overflow: ${overflowing.length}   errors: ${errored.length}   small targets (touch widths): ${report.reduce((n, r) => n + (r.smallTargets ? r.smallTargets.length : 0), 0)}`);
  if (args.strict && (overflowing.length || errored.length)) process.exit(1);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
