# Responsive design — phased plan (2026-09-17)

Goal: the platform works on phones, tablets and desktops at any width, in
both LTR and RTL, without leaving half-fixed surfaces behind. This document
is the *overall* plan. Each phase below is executed as its own task under
the same discipline as `.claude/skills/transition-phase/SKILL.md`
(Explore → Plan → wait for approval → Execute → Verify), one phase per
approval, one commit per phase step. Nothing in this document is code.

Status (2026-09-28): **R0, R1, R2-A, R2-B committed (`c2dff10`). R3 split
A/B and both done — verify records §12 and §13 — pushed and CI green at
`4caaabc`.**

Outstanding, in the order they were planned:
- ~~R2-C — `JobCreatePage`~~ **done**, verify record §15.
- ~~R4 — candidate entry~~ **done**, verify record §14.
- **R5, R6** — blocked on decisions **D1–D5** (§5), which are product
  policy and must be asked, not defaulted.
- **R7 — RTL × responsive sweep**, which also inherits the question §7
  records: every control the harness flags at 1024 is exactly 40px, which
  is R2-A's stated convention but sits under §1.2's 44px for a width the
  matrix calls touch. One decision for the whole admin, not per page.

---

## 0. What was examined

Every file under `frontend/src` (63 files, 12,484 lines) was read in full,
plus `index.html`, `tailwind.config.js`, `index.css`, `App.css`,
`vitest.config.ts`, `.claude/launch.json`. Four routes that render without a
backend were also rendered live at 375×812 (phone) to confirm the reading:
`/login`, `/dev/verbal-preview`, `/dev/sections-preview`,
`/dev/start-preview`. The admin shell and results pages need a Supabase
session and were audited from code only; the findings there are structural
(fixed widths, no breakpoint classes) and do not depend on data.

Tooling facts that shape the plan:
- Tailwind v4 (`@import "tailwindcss"` + `@config`), default breakpoints
  only: `sm` 640, `md` 768, `lg` 1024, `xl` 1280. No custom screens.
- `animate-in / fade-in / slide-in-*` classes used in ~10 places are **not
  emitted** (no animation plugin for v4 — already noted in `index.css`).
  They are harmless no-ops; not a responsive issue, but they will show up in
  every diff and must not be "fixed" as a drive-by.
- `vitest` runs in a plain Node environment (one test, `lib/api.test.ts`).
  There is no DOM/visual test harness. `puppeteer` is already a
  devDependency (used by the ad-hoc `frontend/test_5c.cjs`).
- `App.css` is Vite-template leftover and is imported nowhere. Left alone
  (scope discipline); flagged here only.

---

## 1. Ground rules for every phase (the "no leftovers" guardrails)

These are what stop this becoming the usual half-done responsive pass.

1. **Fixed target matrix.** Every phase is verified at *all* of these, not
   "on my laptop":

   | Name | Width × height | Orientation | Notes |
   |---|---|---|---|
   | phone-s | 360 × 740 | portrait | smallest supported Android |
   | phone | 375 × 812 | portrait | iPhone-class |
   | phone-land | 812 × 375 | landscape | short viewport — the hard case for the interview |
   | tablet | 768 × 1024 | portrait | iPad-class |
   | tablet-land | 1024 × 768 | landscape | `lg` boundary exactly |
   | laptop | 1280 × 800 | — | `xl` |
   | desktop | 1440+ | — | existing design target |

   Each in **LTR and RTL** (the LanguageToggle flips `dir` at runtime, so
   every breakpoint has two layouts).

2. **Definition of done per surface** (checked, not assumed):
   - no horizontal page scroll (`document.documentElement.scrollWidth <=
     innerWidth`) at every matrix entry;
   - every action reachable on desktop is reachable on phone (nothing is
     `hidden` below `sm` without a replacement);
   - interactive targets ≥ 44 × 44 CSS px on touch widths (buttons,
     icon-buttons, table row actions);
   - text never truncates *information* (truncate is fine for titles with a
     `title=`/tooltip, never for scores, statuses, emails in a list);
   - no fixed pixel widths on containers below `lg` unless they are ≤ 320px
     and inside a flex/grid that can wrap;
   - vertical layouts use `100dvh`/`min-h-dvh`, not `100vh`/`h-screen`, on
     anything that must fit a phone viewport (mobile browser chrome and the
     on-screen keyboard change `vh`);
   - safe-area insets (`env(safe-area-inset-*)`) respected on fixed/sticky
     bars in the interview.
3. **Scope discipline.** A phase touches only the files it lists. Anything
   adjacent found on the way is added to §7 (parking lot), not fixed inline.
4. **Frozen contracts untouched.** `InterviewerCharacter.tsx` (and its CSS)
   is reusable as-is — it is not in scope of any phase. `BlobCharacter.tsx`
   is a different file (the verbal view uses it) and *is* in scope, but only
   its container/size selection, not its animation code. `agent/` and
   `/internal/*` are not involved at all.
5. **Test-file discipline.** No existing test file is deleted, moved or
   overwritten (`frontend/test_5c.cjs`, `src/lib/api.test.ts`, the root
   `test_phase*.py`).
6. **Verification is evidence, not a sentence.** Each phase ends with the
   screenshot matrix from the harness in Phase R0 attached to the PR/commit
   and the checklist in §6 ticked per surface.
7. **Naming.** No new entity names; the existing `Job`, `InterviewDefinition`,
   `InterviewSection`, `InterviewQuestion`, `CandidateInterviewSession`
   vocabulary is unchanged. New UI primitives get plain component names
   (`Drawer`, `ResponsiveTable`, …) — no renaming of existing components.

---

## 2. Inventory — every surface, what breaks, severity

Severity: **P0** = feature unusable/unreachable on that device; **P1** =
broken layout (overflow, clipped, unreadable); **P2** = works but poor
(cramped, tiny targets, wasted space).

### 2.1 Shell & shared

| Surface | File | Finding | Sev |
|---|---|---|---|
| Admin shell | `routes/admin/AdminLayout.tsx` | `<aside className="w-64">` + `h-screen` + `<main>` with `p-8` and a `h-24 px-8` header. No breakpoint classes at all. On 375px the content column is ~55px wide. On tablet-portrait it is 512px with 64px of padding. | **P0** phone, P1 tablet |
| Language toggle | `components/ui/LanguageToggle.tsx` | Text label always shown ("العربية"/"English") — fine, but it competes for header space in the interview header on phone. | P2 |
| `AppShell` | `components/layout/AppShell.tsx` | Has a `md:hidden` mobile nav already but is only used by `AdminResultView.tsx`, which is not routed from `App.tsx`. Dead path — leave it. | — |
| `Container` | `components/layout/Container.tsx` | Unused. Leave it. | — |
| Buttons | `components/ui/Button.tsx`, `IconButton.tsx` | `size="sm"` is `h-8` (32px) — below the 44px touch target; many icon-only buttons in editors are `p-1.5` on a 16px icon (~28px). | P2 (P1 where it is the only way to delete/edit) |
| Modals | `ConfirmDeleteModal.tsx`, `PublishSetupModal.tsx` | `fixed inset-0 … p-4` + `max-w-md/lg` — OK on phone. `PublishSetupModal` uses a `sm:grid-cols-2` card pair — OK. Footer buttons don't stack on 360px (`flex justify-end gap-3`), `min-w-[140px]` confirm — tight but fits. | P2 |
| Global | `index.html` | `viewport` meta present. No `viewport-fit=cover` (needed for safe-area insets on notched phones in fullscreen). | P2 |

### 2.2 Admin — job management

| Surface | File | Finding | Sev |
|---|---|---|---|
| Jobs list | `JobsListPage.tsx` | Header row `flex items-center justify-between` (title + "Create" button) — wraps badly < 400px. Each job card is `flex items-center justify-between` with a 3-button action group (`Results`, `Manage`, delete) that never wraps; meta row `gap-4` with 3 items. Overflows at phone widths. | P1 |
| Job create | `JobCreatePage.tsx` | `grid grid-cols-3` for seniority/location/language with **no** `sm:` prefix → three ~90px inputs on a phone. Duration input `w-48` fixed. Cancel/Create footer OK. | P1 |
| Job detail | `JobDetailPage.tsx` | Header: back button + title + meta on the left, **up to 5 action buttons** on the right (`Publish`/`Pause`/`Resume`/`Unpublish`, `View Results`, `Delete`), all `shrink-0` in a `flex` with no wrap. Overflows < ~900px — already cramped on tablet-portrait. | **P1** (P0 on phone: buttons pushed off-screen) |
| Sections editor | `SectionsEditor.tsx` | Mostly good — `SetupRow` uses `sm:grid-cols-[220px_1fr]`, inputs `w-24`, flex-wrap on controls. Verified live at 366px: no overflow. Card header row: expand button + reorder/delete icon cluster (`p-1.5` targets). | P2 (targets) |
| Question editor | `QuestionEditor.tsx` | Generate row is `flex-wrap` — OK. Question card: text column + a 3-icon action cluster (`ms-2 shrink-0`, 28px targets). Long `q.text` OK. MCQ option rows `flex` with `flex-1` input — OK. | P2 |
| Criteria editor | `CriteriaEditor.tsx` | Header `flex items-center justify-between` with a long description paragraph + `Save Criteria` button `size="sm"` — description squeezes the button; no wrap. Grid is `md:grid-cols-2` — OK. Range sliders OK. | P1 (header) |
| Candidate access | `CandidateAccess.tsx` | Header row (title+desc vs "Test interview" button) no wrap. Access-mode cards `sm:grid-cols-2` OK. Public link row already `flex-col sm:flex-row` — good. **Invitations `<table>`** (3 cols, `px-6 py-4`, email `max-w-[200px] truncate`) inside `lg:col-span-2` — at phone width the table has no `overflow-x-auto` wrapper; date column `text-right` is not RTL-aware (`text-end` needed). | P1 |
| Invitation composer | `InvitationComposer.tsx` | Chip input `min-w-[160px]` — OK. Send button row OK. `pl-3 pr-1.5` physical (not logical) padding on chips → wrong in RTL. | P2 |
| Publish modal | `PublishSetupModal.tsx` | Selection check `absolute top-4 right-4` (physical) → wrong corner in RTL. Same in `CandidateAccess`. | P2 (RTL) |

### 2.3 Admin — results

| Surface | File | Finding | Sev |
|---|---|---|---|
| Job results | `JobResultsPage.tsx` | Stat row is `grid-cols-1 lg:grid-cols-[2fr_1fr_1fr]` — OK. The facts card is `grid-cols-3 divide-x` — three numbers in 375px works. **Candidates table: 7 columns**, `px-6 py-4` cells, wrapped in `overflow-x-auto` so it scrolls sideways — usable but the *action* column (View Result / delete) is off-screen on phone; HR must scroll every row. `text-right` on the action header (physical). | P1 |
| Candidate result | `CandidateResultPage.tsx` | Two-zone layout is already `flex-col lg:flex-row`, rail `w-full lg:w-[300px] lg:sticky` — the big structure is responsive. Remaining: header (`Back` + title + `Refresh`) no wrap; criteria rows use `w-40 sm:w-48 shrink-0` label + bar + `w-10` score → label truncates to ~40% of a phone row; `<pre>` for code is `overflow-auto` (OK); `<video max-h-[440px]>` fine; nested `grid sm:grid-cols-2` fine. Left-rail quick-nav (anchors) makes sense only when the rail is sticky (≥ lg); on phone it sits above the content as a long block before any evidence. | P1 (criteria rows), P2 (rail nav on phone) |

### 2.4 Candidate entry (public)

| Surface | File | Finding | Sev |
|---|---|---|---|
| Login | `pages/Auth.tsx` | `max-w-md`, `px-4`, 40px inputs — verified at 375px: no overflow. | OK (targets P2) |
| Invite | `pages/InvitePage.tsx` | Header 64px, `max-w-lg` column, `text-3xl sm:text-4xl` — good. `h-screen` on the invalid-token state (use `min-h-dvh`). | P2 |
| Apply | `pages/ApplyPage.tsx` | Same structure as Invite — good. | P2 |
| CV upload | `features/candidate-entry/CvUploadStep.tsx` | Dropzone is a `<label>` wrapping the file input → tap works on touch (drag is desktop-only, fine). Two-button row already `flex-col sm:flex-row`. | OK |
| Session CV gate | `pages/InterviewSession.tsx` (cvMissing branch) | `min-h-screen` centred card — fine; use `dvh`. | P2 |

### 2.5 Interview — pre-flight

| Surface | File | Finding | Sev |
|---|---|---|---|
| Intro | `features/interview-session/IntroScreen.tsx` | Grid `sm:grid-cols-[1fr_auto]` with the rules panel `sm:w-64` — at 640–767px the instructions column gets ~330px; OK. Consent/CTA row `flex-col sm:flex-row` — good. Start button `min-w-[220px] w-full sm:w-auto` — good. Sticky header OK. | P2 |
| Device check | `DevicePreview.tsx` | Camera tile `aspect-video sm:aspect-auto sm:w-72 sm:min-h-[220px]` — on phones front cameras are portrait; `object-cover` in a 16:9 box crops the face heavily. Status pill `bottom-3 left-3` physical (RTL). "preview is live on the right" copy is wrong on phone (it is *above*) and in RTL. | P1 (phone camera crop), P2 (copy) |
| Fullscreen gate | `IntroScreen` → `lib/fullscreen.ts`, `WaitingRoomScreen.tsx` | `document.documentElement.requestFullscreen` **is not available on iPhone/iPad Safari** (only `<video>` elements can go fullscreen there). The PR-B proctoring design (fullscreen required to start; 10s grace → termination on exit) therefore cannot run on iOS at all, and on Android Chrome the fullscreen exits whenever the keyboard/notification shade appears. This is a **product decision, not a CSS fix** — see §5. | **P0 on iOS — DECISION REQUIRED** |
| Start sequence | `InterviewWorkspace.tsx` `StartSequenceView` | Verified at 375px: fine. `min-h-screen` → `dvh`. | OK |
| Waiting room | `WaitingRoomScreen.tsx` | `text-4xl sm:text-5xl` heading, `px-10 py-4` CTA — fits. `min-h-[60vh]` inside a `100dvh` grid — OK. | OK |

### 2.6 Interview — live workspace (highest risk)

| Surface | File | Finding | Sev |
|---|---|---|---|
| Workspace header | `InterviewWorkspace.tsx` L669–756 | **`End Session` and `Fullscreen/Exit Fullscreen` buttons are `hidden sm:flex`** → on any phone (<640px) the candidate has *no way to end the session* and *no way to re-enter fullscreen* from the header. The camera on/off indicator and the live-connection status are also `hidden sm:flex`. The timer and LanguageToggle remain. | **P0** |
| Controller bar | `InterviewController.tsx` | Bar is `flex-col sm:flex-row`: on phone it stacks *three rows* (Repeat/Hint, Mic, Skip/Skip background/End Section) under the `sticky bottom-0` wrapper — eats ~200px of a 812px viewport, ~50% of a landscape phone. `SecondaryButton` labels are `hidden sm:inline` → icon-only, no accessible label (`title` only), 40px targets. The `absolute -top-12` error toast overlaps the content above. | **P1** (P0 in landscape) |
| Verbal view | `VerbalSectionView.tsx` | Verified at 375px: stepper wraps, blob centred, caption OK. Transcript toggle turns the main column into a *second* column only at `lg` (`lg:col-span-2`) — below `lg` the transcript `<aside min-h-[280px]>` renders *below* the interviewer in the same scroll, pushing the caption off-screen; the outer `<main>` only `lg:overflow-hidden`, so the page scrolls inside a `100dvh` box — acceptable but needs the header/controller to stay fixed (they do). Legacy technical-with-editor branch: `lg:grid-cols-[…]` split, textarea `min-h-[360px]` on top of a `max-h-[45vh]` problem pane — on a phone in landscape nothing fits. | P1 (transcript on phone), P2 |
| Coding view | `CodingSectionView.tsx` | Split `lg:grid-cols-[0.9fr_1.1fr]` → stacked below `lg`: problem pane (`flex-1 overflow-y-auto`, no max-height when stacked) then editor `min-h-[360px]`. On tablet-portrait the problem pane takes what it needs and the editor is pushed below the fold; on a phone the user scrolls between problem and editor and the soft keyboard covers half the editor. Language `<select>` is 12px text. | P1 phone/tablet-portrait |
| MCQ view | `McqSectionView.tsx` | `max-w-2xl` card, option buttons full-width `py-2.5` (~42px) — fine. Submit row `flex justify-between` with hint text — wraps OK. | OK (targets P2) |
| Self-view PiP | `SelfViewVideo.tsx` | Fixed px sizes `160×112` / `320×256`, default bottom-right with `BOTTOM_MARGIN_PX=110` computed for the *desktop* controller height; on phone the controller is ~200px tall, so the PiP sits **on top of the Skip/End Section buttons**. Expanded 320px is 85% of a phone width. Drag is `touch-none` (good) but the expand toggle is 24px. | P1 |
| Fullscreen grace overlay | `FullscreenGraceOverlay.tsx` | `absolute inset-0` inside the main wrapper, `max-w-sm w-full p-8` — fits phone. | OK |
| TTS retry overlay | `TtsRetryOverlay.tsx` | `max-w-sm mx-4` — OK. | OK |
| End dialogs | `EndInterviewDialog.tsx`, `EndSectionEarlyDialog.tsx` | `min-h-screen` on the backdrop grid (use `dvh`); buttons `flex-col-reverse sm:flex-row` — good. | P2 |
| Ended / Terminated | `SessionEndedScreen.tsx`, `FullscreenTerminatedScreen.tsx` | `min-h-screen` → `dvh`; logo `hidden sm:flex` (acceptable, the role title remains). | P2 |
| Face monitor | `useFaceDetectionMonitor.ts`, `headPose.ts` | Thresholds were tuned on desktop webcams (CURRENT_DECISIONS.md, head-pose section). A phone held in hand moves constantly; false `NO_FACE`/look-away flags likely. Not a layout issue — flagged in §5 as a decision, not touched by this plan. | decision |

---

## 3. Phases

Each phase = one approval, its own Explore→Plan→Execute→Verify, one or more
small commits. Order is chosen so that (a) the harness exists before any fix,
(b) the P0s land early, (c) the riskiest surface (live interview) is done
once the shared primitives are proven on lower-risk pages.

### R0 — Harness & shared primitives (no visual change to the product)

**Why first:** without a repeatable way to *see* every surface at every
matrix entry, every later phase will be verified by eye on one screen and
leave things behind.

Deliverables:
1. `frontend/scripts/responsive-shots.cjs` — puppeteer script (already a
   devDependency) that opens a list of routes at every §1 matrix entry, in
   LTR and RTL (`localStorage['preferred-lang']`), and writes
   `frontend/.responsive/<route>__<viewport>__<dir>.png` plus a JSON report
   of `scrollWidth > innerWidth` and any interactive element under 44px on
   touch widths. Routes it can reach without a backend today: `/login`,
   `/dev/*`. It reads `RESPONSIVE_ROUTES` env to add authenticated routes
   when a dev login is available. `.responsive/` is git-ignored.
2. Two more DEV-only harness routes, same pattern as the existing
   `routes/dev/*` (registered under `import.meta.env.DEV` only):
   - `/dev/admin-preview` — renders `AdminLayout` chrome around a mock
     `JobsListPage`/`JobDetailPage` header so the shell can be viewed
     without Supabase;
   - `/dev/workspace-preview` — renders the *real* `InterviewWorkspace`
     header + `InterviewController` + one section view with mock state
     (the existing `VerbalPreview` copies the header instead of rendering
     it, which is exactly why the `hidden sm:flex` P0 was never seen).
3. Shared primitives (new files only, nothing existing refactored yet):
   - `components/ui/Drawer.tsx` — off-canvas panel (used by R1 sidebar);
   - `components/ui/ResponsiveTable.tsx` — renders `<table>` ≥ `md` and a
     card list below, driven by a column config (used by R2/R3);
   - `lib/useMediaQuery.ts` — for the *few* places where CSS cannot decide
     (SelfView size/position, controller layout);
   - `index.css`: add `--safe-*` custom properties from
     `env(safe-area-inset-*)`, a `.touch-target` utility (min 44px), and
     `viewport-fit=cover` in `index.html`.
4. `docs/responsive-checklist.md` — the §6 checklist as a copy-paste
   template for each phase's verify step.

Files touched: new files above, `index.html`, `index.css`, `App.tsx` (dev
routes only), `.gitignore`. Verify: script runs, produces the matrix for
`/login` + `/dev/*`; `npm run typecheck`, `npm run lint`, `npm test` green.

R0 as built deviates from the above in one way, by design: two pure JSX
moves (`AdminLayout` → role gate + exported `AdminShell`; the workspace
`<header>` → `WorkspaceHeader.tsx`) so the two new previews render the
real chrome instead of copies. No behaviour or class changed.

### R1 — Admin shell (P0)

`AdminLayout.tsx`: sidebar becomes a `Drawer` below `lg` (hamburger in a
compact header, `LanguageToggle` kept), persistent `w-64` at `lg+`.
Content padding `p-4 sm:p-6 lg:p-8`; header `h-16 lg:h-24`. Root switches
from `h-screen` to `h-dvh`. Keep the decorative SVG as-is.
Verify at full matrix via `/dev/admin-preview` + real login. Depends on R0.

### R2 — Admin job management pages (P1 cluster)

`JobsListPage`, `JobCreatePage`, `JobDetailPage`, `CriteriaEditor`,
`CandidateAccess`, `InvitationComposer`, `PublishSetupModal`,
`ConfirmDeleteModal`, `SectionsEditor` (targets only), `QuestionEditor`
(targets only).
- Header action bars → `flex-wrap` with a consistent pattern: primary
  action stays visible, secondary/destructive actions collapse into an
  overflow menu below `md` (one new `components/ui/ActionMenu.tsx`).
- `grid-cols-3` → `sm:grid-cols-3`; `w-48` → `w-full sm:w-48`.
- Invitations table → `ResponsiveTable`.
- All physical `left/right/pl/pr/text-right` in these files → logical
  (`start/end/ps/pe/text-end`), since RTL is part of the matrix.
- Icon-only actions get `min-h-11 min-w-11` on touch widths and an
  `aria-label` (they currently have only `title`).
Depends on R0, R1.

### R3 — Admin results pages (P1 cluster)

`JobResultsPage` (7-col table → `ResponsiveTable` with the action column
pinned/first on cards), `CandidateResultPage` (header wrap, criteria row
becomes two-line below `sm`: label on line 1, bar+score on line 2; rail
quick-nav collapses to a horizontal chip row below `lg`). No data or API
changes. Depends on R0, R1.

**Split on 2026-09-28** (both pages turned out to have zero i18n — 27 and
~75 hard-coded English strings, which R2-A and R2-B would have converted):

- **R3-A — `JobResultsPage`** (done, §12): the table, the header, the page's
  i18n, and `/dev/results-preview` so the harness can reach it at all.
- **R3-B — `CandidateResultPage`** (done, §13): header wrap, the two-line
  criteria row, its strings, and the rail quick-nav, which the user decided
  is **hidden below `lg`** rather than becoming a chip row — on a phone the
  whole report is one scroll, and scrolling is the replacement that keeps
  it off the "hidden without a replacement" list.

### R4 — Candidate entry (small, mostly `dvh`/targets)

`Auth`, `InvitePage`, `ApplyPage`, `CvUploadStep`, `InterviewSession`
(cvMissing/loading/error branches only): `h-screen/min-h-screen` → `dvh`,
inputs `h-11` on touch, button targets. Depends on R0.

### R5 — Interview pre-flight (needs §5 decision D1 first)

`IntroScreen`, `DevicePreview`, `WaitingRoomScreen`, `StartSequenceView`:
portrait camera tile on phones (`aspect-[3/4]` below `sm`, keep 16:9
above), logical positioning, copy that doesn't say "on the right", `dvh`.
If D1 = "phones unsupported for the live interview", this phase *also* adds
the capability gate on `IntroScreen`: detect missing
`documentElement.requestFullscreen` (and optionally narrow width) and show
a clear "open this on a laptop/desktop" screen instead of a Start button
that can never work. Depends on R0, D1.

### R6 — Live interview workspace (P0/P1 cluster; needs D1, D2)

`InterviewWorkspace` header, `InterviewController`, `SelfViewVideo`,
`VerbalSectionView`, `CodingSectionView`, `McqSectionView`, the two end
dialogs, `SessionEndedScreen`, `FullscreenTerminatedScreen`,
`TtsRetryOverlay`, `FullscreenGraceOverlay`.
- Header: nothing action-bearing is hidden below `sm`; End Session and
  Fullscreen move into a compact overflow (`ActionMenu`) on phone; status
  indicators become icon-only rather than removed.
- Controller: single row at every width — mic in the centre, two icon
  buttons each side, `aria-label` on each, labels shown from `md`; bar
  height fixed so the PiP margin can be computed from it; error toast moves
  *inside* the bar rather than `absolute -top-12`.
- Self-view: size and default position from `useMediaQuery`
  (`120×90`/`240×180` below `sm`), margin computed from the actual
  controller height (`ResizeObserver`), never over the controls.
- Verbal: transcript on `< lg` becomes a bottom sheet (reuses `Drawer`)
  instead of a stacked column, so the interviewer/caption stay in view.
- Coding: below `lg` a two-tab layout (Problem / Code) instead of stacked
  panes, so the editor always gets the full viewport; `min-h` derived from
  `dvh` minus header/controller; `<select>` 14px. Whether phones get the
  coding section at all is D2.
- `min-h-screen` → `dvh` everywhere in this folder; safe-area padding on
  the sticky controller.
- `BlobCharacter`: only pass `size="small"` below `sm` (prop already
  exists), no changes to its drawing code. `InterviewerCharacter.tsx`
  untouched.
Depends on R0, R5, D1, D2. This is the only phase that must be
live-tested end-to-end with a real agent on at least one real phone and
one real tablet, not just the harness.

### R7 — RTL × responsive sweep, regression, docs

Run the full harness in both directions on every route (with a dev login),
fix anything that is a *responsive* regression (not new features), update
`docs/PROJECT_STATUS.md`, and add the harness to `docs/technical/testing-strategy.md`.
Optionally (ask first) codify the per-phase workflow as a
`.claude/skills/responsive-phase/SKILL.md` mirroring `transition-phase`.

---

## 4. Per-phase template (what each phase's own plan must contain)

```
## Rn — <name>
Explore: quoted current contents of every file to be touched (re-read live).
Plan:    files touched; new components; classes/patterns replaced;
         Frozen Contracts Confirmation (InterviewerCharacter.tsx, agent/, /internal/* — not touched);
         decisions from §5 this phase relies on (by ID).
Execute: after approval only. One commit per logical step.
Verify:  harness matrix (all 7 viewports × LTR/RTL) attached;
         §6 checklist ticked per surface;
         npm run typecheck && npm run lint && npm test output pasted;
         for R6: real-device notes (device, browser, what was exercised).
Left over: anything discovered and NOT fixed, appended to §7.
```

---

## 5. Decisions required from you before R5/R6 (not decided here)

These are product decisions; per AGENTS.md §5 I am not picking defaults.

- **D1 — Is the live interview supported on phones?**
  Facts: iOS Safari cannot fullscreen the document, so PR-B's "fullscreen
  required, 10s grace, terminate" is impossible on iPhone/iPad; on Android
  Chrome fullscreen drops on every keyboard/notification, so a candidate
  would be terminated for typing a coding answer. Options: (a) phones
  unsupported for the *live* interview — entry pages/CV upload work on
  phone, the intro screen gates with a clear message; tablets/laptops
  supported; (b) supported, with fullscreen enforcement relaxed on devices
  that cannot do it (this changes the proctoring contract — needs its own
  decision in `CURRENT_DECISIONS.md` and likely an `InterviewEvent`
  variant, backend involved); (c) supported for VERBAL/MCQ only. The layout
  work in R6 is the same for (b)/(c); (a) makes R6 tablet-first.
- **D2 — Coding section on touch devices.** A `<textarea>` code editor
  with a soft keyboard is a poor experience; decide whether phones (and
  tablets without keyboards) may take CODING sections or get a "use a
  computer" gate for that section type.
- **D3 — Minimum supported width.** Proposed: 360px (§1 matrix). Below
  that, no guarantees.
- **D4 — Admin on phone: full parity or read-mostly?** Authoring
  (sections/questions editors) works but is cramped on phone; decide whether
  phone admin is "review results + pause/resume" (lets R2 collapse editors
  behind a "best on a larger screen" note) or full parity (R2 as written).
- **D5 — Face-monitor thresholds on handheld devices** (only if D1 ≠ a):
  the head-pose numbers in `CURRENT_DECISIONS.md` were confirmed on desktop
  webcams; on a handheld phone they will over-flag. Out of this plan's scope
  either way; listed so it is not silently inherited.

---

## 6. Acceptance checklist (copied into every phase's Verify)

Per surface, per matrix entry, LTR and RTL:
- [ ] no horizontal scroll (`scrollWidth <= innerWidth`)
- [ ] every desktop action reachable (nothing `hidden` without replacement)
- [ ] touch targets ≥ 44px on ≤ `md`
- [ ] no clipped/overlapping text; no truncated *data* (only titles, with tooltip)
- [ ] fixed/sticky bars don't cover content or each other; safe-area respected
- [ ] `dvh` not `vh` for full-height layouts
- [ ] logical properties only (`ps/pe/ms/me/start/end/text-start/text-end`)
- [ ] focus order and `aria-label` present on icon-only controls
- [ ] harness screenshots attached; typecheck/lint/test green

---

## 7. Parking lot (found during the audit, deliberately NOT in scope)

- `document.documentElement.dir` is set only inside `LanguageToggle`'s
  effect, so a hard load of a page without the toggle (`/login`, every
  admin page) with `preferred-lang=ar` renders Arabic text in an LTR
  layout. `i18n.ts` should set `dir` at init. (Found while building the
  harness, which sets `dir` itself to compensate.)
- Hard-coded English in the live workspace chrome: "Fullscreen"/"Exit
  Fullscreen"/"End Session" (`WorkspaceHeader`), "Repeat"/"Hint"/"Skip"/
  "End Section"/"Listening"/"Muted" and the tooltips (`InterviewController`)
  — visible in every RTL harness shot. i18n, not layout.
- R6 input from the harness: at 812×375 (phone landscape) header + stepper
  + controller leave ~60px for the interviewer. Recorded here so R6's plan
  starts from the measurement, not a guess.

- `frontend/src/App.css` is Vite-template CSS, imported nowhere.
- `AppShell.tsx`, `Container.tsx`, `AdminResultView.tsx` are unreferenced
  by the router.
- `animate-in / fade-in / slide-in-*` utilities are no-ops under Tailwind
  v4 here (already documented in `index.css`).
- `CandidateAccess.handleTestDrive` opens `/interview/${id}` (singular);
  the route is `/interviews/:id`. Looks like a real bug, unrelated to
  responsiveness.
- `QuestionEditor`/`SectionsEditor` use `window.confirm` for deletes while
  the rest of the admin uses `ConfirmDeleteModal`.
- ~~`JobResultsPage` / `CandidateResultPage` are the only two places with
  `rtl:rotate-180` on `ArrowLeft`~~ — R2-C fixed `JobCreatePage`.
  **`JobDetailPage` is the last one still unmirrored.**
- (R2-C) `JobCreatePage`'s error banner uses raw `bg-red-500/10` /
  `text-red-500` rather than the `destructive` tokens, so it ignores
  theming. Left alone for the same reason as `JobResultsPage`'s
  `bg-white/50`: colour, not layout.
- (R3-A) `JobResultsPage`'s error branch uses a hard-coded `bg-white/50`
  instead of a token, so it ignores theming. Left alone: colour, not layout.
- (R4) **`App.tsx`'s root wrapper is `min-h-screen`** — `100vh`, on the one
  element that wraps every route. R4 converted the five candidate-entry
  surfaces to `dvh`, but they sit inside this. On mobile `100vh` exceeds the
  visible viewport while the browser chrome is showing, so the root stays
  taller than the screen regardless of what its children use. One class to
  change; left alone only because `App.tsx` is not in R4's file list and §3
  says adjacent finds are recorded, not fixed inline. Worth doing before R5,
  which is all full-height layout.
- (R4) `Auth`, `InvitePage` and `ApplyPage` carry `peer-disabled:` modifiers
  on their `<label>`s, implying a `peer` pattern that was never wired (the
  inputs have no `peer` class). Harmless dead styling; R4 wired real
  `htmlFor`/`id` instead rather than adopting the peer approach.
- (R3-B, user decision) `CandidateResultPage` renders `completed_at` with
  `toLocaleString()`, which follows the **browser** locale, not the app
  language — so the date stays English/Gregorian in Arabic. Deliberately not
  fixed here: doing it properly means choosing a calendar and digit set for
  Arabic (Gregorian vs Hijri, Arabic-Indic vs Western numerals), which is a
  product decision that would apply to every date in the app, not one page.
- (R3-A) **40px at exactly 1024 is now a track-wide decision, not a page
  one.** Every control the harness still flags at `tablet-land` is exactly
  40px: the sidebar's Jobs/Settings/Sign Out, `LanguageToggle`, and any
  `Button` at `lg`. That is R2-A's stated convention ("buttons are 40px
  from lg by design"), but 1024 is in §1's matrix as a *touch* width where
  §1.2 asks for 44. R7 should settle it one way for the whole admin —
  raise the shell to 44 at `lg`, or narrow what counts as a touch width —
  rather than each phase deciding for its own page.

---

## 8. R0 — verify record (2026-09-17)

Built: `scripts/responsive-shots.cjs` (+ `npm run responsive`),
`/dev/admin-preview`, `/dev/workspace-preview`, `Drawer`, `ResponsiveTable`,
`useMediaQuery`, safe-area vars + `touch-target` utility, `viewport-fit=cover`,
`docs/responsive-checklist.md`, `frontend/.responsive/` git-ignored.

Harness, full matrix (6 routes × 7 viewports × LTR/RTL = 84 shots):
`overflow: 0  errors: 0`. It reproduces the audit: `/dev/workspace-preview`
reports `hiddenControls` = Fullscreen + End Session at phone widths;
`/dev/admin-preview` reports `innerScroll` (the `w-64` sidebar's hidden
overflow) and "Create new job" past the viewport. `npm run typecheck`
clean; `npx oxlint src` adds no warnings in R0 files; `npm test` 3/3.

Commit note: the working tree carried unrelated uncommitted edits before
R0 started (section-view prop cleanup, `CriteriaEditor`/`JobResultsPage`/
`QuestionEditor` fixes, `test_phase*.py`). `HEAD` alone does not typecheck
and `WorkspacePreview` uses the cleaned-up section-view props, so R0 is
staged on top of that work, not committed separately.

## 9. R1 — verify record (2026-09-17)

Changed: `routes/admin/AdminLayout.tsx` (`AdminShell`): sidebar markup is
one `SidebarPanel`, rendered in a persistent `hidden lg:flex w-64` aside
and, below `lg`, inside R0's `Drawer side="start"` opened from a 44×44
menu button in a compact `h-16` header (wordmark + `LanguageToggle`);
header `h-24` and `p-8` well kept at `lg+`, `p-4 sm:p-6` below; root
`h-screen` → `h-dvh`. Drawer closes on route change, ESC, overlay; focus
returns to the menu button. Two i18n keys added (`adminLayout.openMenu`,
`adminLayout.menu`).

Checked live (`/dev/admin-preview`): 375 LTR and RTL (drawer from the
logical start edge — right in RTL — no code branch), 1024 (sidebar
persistent, header 96) vs 1023 (drawer mode, header 64, button 44×44).
Harness on the route, 14 shots: `overflow: 0, errors: 0`; the remaining
`innerScroll` is the page content (job-card action group at phone; the
job-detail action bar, 916px in a 768px well, at tablet) — R2's scope.
`npm run typecheck` clean; oxlint clean on the touched files; `npm test` 3/3.

## 10. R2-A — verify record (2026-09-17, from manual feedback)

Feedback (user, phone-width browser): login OK; admin nav OK; jobs list
"label/time/name noisy"; job page "Delete off screen, Publish too far up".
Decision: Unpublish + Delete in an overflow menu at every width.

Changed: new `routes/admin/JobSummary.tsx` (`JobStatusBadge`, `JobMetaRow`,
`JobCard`, `JobHeader`) used by `JobsListPage` and `JobDetailPage`; new
`components/ui/ActionMenu.tsx`. One identity anatomy on both pages: title
wraps freely; status pill first on a wrapping meta row with `nowrap` chips
(no more "30 / min"). List card stacks actions under the identity below
`md` (Results/Manage share the width, 44px; delete icon-only with
`aria-label`). Job page: identity block + a `role="toolbar"` action bar —
primary (Publish/Pause/Resume) + View results + ⋯ (Unpublish, Delete) —
pinned to the viewport bottom below `lg` (page gets `pb-24`), static
beside the identity at `lg+`. Hard-coded English labels replaced with
i18n keys (`jobDetail.*`, `jobsList.results/deleteJob`, `jobStatus.*`).
`/dev/admin-preview` now renders the real `JobCard`/`JobHeader`.

Checked: harness `/dev/admin-preview` 14 shots — `overflow: 0`, no inner
scrollers left; menu opens upward from the pinned bar (real
pointerdown/up/click sequence), closes on outside tap and ESC; 1280 shows
the bar static beside the identity. Leftover for R7: `LanguageToggle` is
40px tall on touch widths (shared component); buttons are 40px from `lg`
(1024) by design.

## 11. R2-B — verify record (2026-09-17)

Scope confirmed by the user incl. Criteria i18n. Changed: `CandidateAccess`
(stacked block header, 44px Test-interview button, invitations `<table>`
→ `ResponsiveTable`, `end-4` check marks, labelled open-in-new-tab);
`InvitationComposer` (chip `ps/pe`); `CriteriaEditor` (stacked header, 44px
save, every string moved to `criteriaEditor.*` EN+AR); `SectionsEditor`
(stacked header; card row is two lines — title/expand + 44px labelled
↑↓🗑 cluster, summary on its own line; 40px/16px inputs on phone);
`QuestionEditor` (no side-rail indent below `sm`; all inputs 40px/16px on
phone; ○/✕/✎/↻/🗑 are 44px with `aria-label`; form buttons 44px on phone);
`PublishSetupModal`/`ConfirmDeleteModal` (stacked 44px footer, labelled
close, `end-4`). New key `questionEditor.generateCount`,
`candidateAccess.openInNewTab`.

Checked: `/dev/sections-preview` at 375 with the MCQ manual-add form open —
zero sub-44px controls left (inputs are 42px, inside 44px rows); harness
28 shots (`sections-preview` + `admin-preview`): `overflow: 0, errors: 0`,
no inner scrollers. `Criteria` and `Candidate Access` need a signed-in
job — left to the manual pass. typecheck clean; oxlint: only the
pre-existing `err2` warning; tests 3/3. All three services confirmed up.

## 12. R3-A — verify record (2026-09-28)

Scope confirmed by the user: split R3 into A/B, add a dev preview route,
and (for R3-B) hide the rail quick-nav below `lg`.

Changed: new `routes/admin/JobResultsTable.tsx` (`CandidatesTable` — the
seven columns lifted out of the page so the page and the harness render the
same component, the `JobSummary.tsx` precedent from R2-A);
`JobResultsPage.tsx` (header exported as `JobResultsHeader`, stacks below
`sm`, `title=` on the truncating `h1`, every string moved to
`jobResults.*`); new `routes/dev/ResultsPreview.tsx` + its route in
`App.tsx` + `/dev/results-preview` in the harness's `DEFAULT_ROUTES`;
`components/ui/ResponsiveTable.tsx` gains an optional `breakpoint`
(`md` default | `lg` | `xl`); `locales/en.json` + `ar.json` gain
`jobResults` (37 keys each, key parity asserted, existing namespaces
byte-identical); two tests appended to `ResponsiveTable.test.tsx`.

**Three defects the harness found that reading the code did not.** All
three were measured, not guessed:

1. `a "View Result" 101x17` — a bare `<a>` around a button collapses to the
   text's own 17px box, so the LINK, which is what a finger and a screen
   reader target, was under 44px even though the button inside was not.
   `inline-flex` on the `Link`.
2. `innerScroll: 779/718` at **768** — `ResponsiveTable`'s hard-coded `md`
   was too early for seven columns: the table went back to scrolling
   sideways inside its own well, putting the action column off-screen,
   which is the exact bug the component exists to prevent.
3. `innerScroll: 771/702` at **1024** — and `lg` was no better, because at
   `lg` the admin sidebar stops being a drawer and takes a persistent
   256px back. Hence `breakpoint="xl"`: cards until 1280. The right
   breakpoint depends on the column count *and* on what else holds the
   width at that size; it is a measurement, not a default.

Checked: harness on `/dev/results-preview`, 14 shots — `overflow: 0,
errors: 0, innerScroll: 0`. Full `DEFAULT_ROUTES` run afterwards, **98
shots across 7 routes: `overflow: 0, errors: 0`, and zero inner scrollers
anywhere** — the `ResponsiveTable` change defaults to `md`, so Candidate
Access (R2-B) is untouched. Live at 375 LTR and RTL: header stacks, the
job title wraps instead of truncating, the stat strip mirrors, cards carry
`View Result` + delete at the end of every card, and `Hire`/`No Hire` now
read توظيف / عدم التوظيف (display only — `recommendationTone()` still
switches on the raw value, so the colour logic is untouched). RTL
`scrollWidth === innerWidth === 375`, `scrollX 0`, measured in the page
rather than judged from a screenshot.

`npm run typecheck` clean; oxlint: **zero warnings in the new and changed
files** (`JobResultsPage`'s `exhaustive-deps` is pre-existing — the same
`useEffect(..., [id])` is in `HEAD`, and `JobDetailPage`/`JobsListPage`
carry it too); `npm test` **40/40** (was 38).

Not verified here: the real page behind a login. The preview renders the
real components against fixtures — long name, long email, no email, no
score, no evidence figure, an override, a flagged row, and an unfinished
interview — but fixtures are not a signed-in job, and the delete path is
local-only in the preview. The live check belongs to the owner's manual
pass along with the H2-E/H2-F items.

Still open, unchanged by this phase: `LanguageToggle` at 40px on touch
widths (R2-A leftover, R7), and the 1024/40px question now recorded in §7
as a track-wide decision for R7.

## 13. R3-B — verify record (2026-09-28)

Scope confirmed by the user: its own dev preview route, fix the override
form's unlabelled controls, park the date-locale question.

Changed: `CandidateResultPage.tsx` — **61 asserted replacements**, every one
anchored so a partial application was impossible. Header stacks below `sm`
with an `inline-flex` Link (the R3-A anchor-collapse finding, present here
too); the candidate **name** and the **email** now wrap instead of
truncating, because both are data; the criteria row is two lines below `sm`
(label, then bar + score) and its boxes are `<span>`s, since a `<button>`
may only contain phrasing content and the old markup nested a `<div>`; the
rail quick-nav is `hidden lg:flex`; the override `select`/`textarea` gained
`id`/`htmlFor` (they had **no accessible name at all**) and 16px text on
phone so iOS does not zoom on focus; Save/Cancel/Regenerate are 44px below
`lg`; `mr-2` became `me-2` so the spinner's spacing flips with direction.

New `routes/dev/CandidateResultPreview.tsx` + its route + the harness entry;
`locales/en.json` and `ar.json` gain `candidateResult` (98 EN leaf keys, 110
AR — the difference is Arabic's extra plural forms), with existing
namespaces asserted byte-identical and key parity checked on plural stems.

**The preview renders the real page, not a copy.** `CandidateResultPage` is
one 828-line component, so extracting a presentational shell purely to make
a preview possible would have been a risky refactor of a page nobody can
exercise without a login. Instead the dev file stubs `window.fetch` for the
single GET the page makes. Two things had to be got right, both found by
running it:

1. A nested `MemoryRouter` (so `useParams` would resolve) is rejected
   outright by React Router v7 — *"You cannot render a `<Router>` inside
   another `<Router>`"*. The dev route carries `:jobId/:sessionId` itself
   instead, with a redirect from the bare path.
2. Restoring `window.fetch` in an effect cleanup **silently defeated the
   stub under StrictMode**: React mounts, runs effects, runs cleanups, then
   runs effects again, and child effects run *before* parent effects — so
   the page re-fetched against the restored real `fetch`. Observed as a live
   request to :8001, `ERR_CONNECTION_REFUSED`, and a permanent skeleton. A
   parent effect cannot win that race, so the stub installs once and is
   never removed; it is pinned to the fixture's own `sess-preview` id, which
   a real result can never have.

The four English `+ "s"` plural hacks (`flagged moment`, `hint`,
`follow-up`, `clarification`) are now i18next plurals, following the
convention already in `ar.json` (`sectionsEditor.summaryQuestions` carries
the full CLDR set): English `_one/_other`, Arabic
`_one/_two/_few/_many/_other`.

`OUTCOME_STYLE` and `INTEGRITY_EVENT_META` are module-level, where `t()`
cannot be called, so their 12 English labels left the maps entirely; each
entry's key is now also its translation key, resolved at the call site by
`outcomeKey()` / `integrityKey()`, which reproduce the old
NOT_ATTEMPTED/DEFAULT fallbacks. Icons and tones stayed in the maps.

Checked: harness on the new route, 14 shots — `overflow: 0, errors: 0`.
Full `DEFAULT_ROUTES` afterwards, **112 shots across 8 routes: `overflow:
0, errors: 0`**. The only inner scroller is the `<pre>` code block
(794/341), which §2.3 records as acceptable for code. Live at 375 RTL: the
long criterion label wraps in full instead of being cut at 160px, the bar
and score take their own line, the unscored criterion reads "لا توجد أدلة",
the name wraps to two lines, and the email wraps rather than truncating.

One thing the harness improved: the three quick-nav anchors were 36px, so
hiding them below `lg` left them visible only at a width where they were
still under even the project's own 40px convention. They are now 40px,
matching the sidebar's links, and **every** flagged control at 1024 is now
exactly 40px with no outliers — the same track-wide question R3-A recorded
in §7, unchanged by this phase.

`npm run typecheck` clean; oxlint **16 warnings, identical to the count
before this phase** (`CandidateResultPage`'s `exhaustive-deps` is the same
`useEffect(..., [sessionId])` that is in `HEAD`); `npm test` 40/40.

Not verified here: the real page behind a login. The fixture covers an
incomplete (DISCONNECTED) session, a placeholder evaluation, a manual
override, a missing recording, a long name and email, a long criterion
label, a criterion with no score, a question with no title, four outcomes,
three integrity events including one with no offset, a code submission and
a transcript — but Regenerate Evaluation and Save Override deliberately go
through the real client and are not stubbed, so those two actions remain
part of the owner's manual pass.

## 14. R4 — verify record (2026-09-28)

Scope confirmed by the user: the plan's `dvh`/target work **plus** the two
defects found on examination that sat just outside it — unlabelled form
fields and three untranslated strings.

Changed: `pages/Auth.tsx`, `pages/InvitePage.tsx`, `pages/ApplyPage.tsx`,
`features/candidate-entry/CvUploadStep.tsx`, `pages/InterviewSession.tsx`
(loading / error / ended / cvMissing branches only — the live workspace is
R6's), `locales/en.json` + `ar.json` (+3 `workspace.*` keys each).

- **11 `vh` sites → `dvh`.** Mobile browser chrome and the on-screen
  keyboard both change `vh`, which is what the checklist's rule is about.
- **Touch targets:** six inputs and every submit button to `h-11 lg:h-10`;
  `CvUploadStep`'s four buttons likewise (the inventory called that file
  OK, which was true of its *layout* — the label-wrapped dropzone and the
  `flex-col sm:flex-row` row — but said nothing about target size); and the
  raw `<button>` in the error branch, which was `px-4 py-2` ≈ 36px and is
  the candidate's only recovery action on a failed connection.
- **16px text on phone** (`text-base sm:text-sm`) for all six inputs.
  Below 16px iOS zooms the page the moment a field is focused — the same
  defect fixed in R3-B's override form, and worse here because these are
  the login and the candidate's OTP entry.
- **`id`/`htmlFor` on all six fields.** They had none, and the inputs had
  no `id`, so **the login form's fields had no accessible name at all**.
  (The `peer-disabled:` modifiers on the labels imply a `peer` pattern that
  was never wired either — recorded in §7.)
- **Three strings an earlier i18n pass missed** in `InterviewSession`'s
  loading and error branches: "Preparing Interview Room...", "Connection
  Error", "Try Again". The neighbouring `ended` and `cvMissing` branches
  were already translated, so these rendered English inside an otherwise
  Arabic page, on the candidate's entry path. Now `workspace.preparingRoom`
  / `.connectionError` / `.tryAgain`.

Checked, measured in the page rather than read off a screenshot: `/login`
at 375 reports **zero** sub-44px targets, both inputs 44px at a computed
**16px**, and `labelled: true` for each. Across the matrix `/login` went
from **30 small targets to 6**, and all six are the same three controls at
exactly 1024, each exactly 40px — the `lg` convention, the open track-wide
question in §7, not a regression. Zero at phone and zero at tablet.

Full `DEFAULT_ROUTES` run: **112 shots across 8 routes, `overflow: 0,
errors: 0`**; every other route's numbers unchanged from §13. The only
inner scrollers remain the `<pre>` code block on the candidate-result
preview.

`npm run typecheck` clean; oxlint unchanged; `npm test` 40/40.

Not verified here: `InvitePage` and `ApplyPage` past their first screen,
which need a real token — and with no backend running, `/invite/<bogus>`
stays on the loading branch rather than reaching the invalid-token state.
Both belong to the owner's manual pass. What *was* confirmed live on that
route is that the loading branch now renders `min-h-dvh`.

## 15. R2-C — verify record (2026-09-29)

The phase R2 left behind: `JobCreatePage`, never started, and easy to miss
because the numbering jumps from R2-B to R3. Scope confirmed by the user:
the plan's two findings, plus `id`/`htmlFor` (the one item outside R2's
stated bullets), plus a dev preview route.

Changed: `routes/admin/JobCreatePage.tsx` (18 asserted replacements), new
`routes/dev/JobCreatePreview.tsx` + its route + the harness entry. **No
i18n work** — this page was already fully translated, so unlike R3 and R4
nothing moved into the locale files. The back button's `aria-label` reuses
the existing `jobDetail.backToJobs` rather than adding a duplicate string;
`ApplyPage` already reuses `invite.emailLabel`, so cross-namespace reuse is
established here.

- **`grid grid-cols-3` → `grid gap-4 sm:grid-cols-3`.** Measured after:
  `gridTemplateColumns` at 375 is a single `293.6px` track, where it used
  to be three ~87px ones.
- **Duration `w-48` → `w-full sm:w-48`** — 294px at 375, measured.
- **Ten controls sized.** Every input and the `<select>` were
  padding-sized (`py-2`, no height class) and landed at ~40px; they are
  `h-11 lg:h-10` now. The textareas keep their `rows` heights.
- **Ten `id`/`htmlFor` pairs.** Measured after: `unlabelled: 0` of 10
  controls, where before every one of them was anonymous to a screen
  reader — on the form that creates a job.
- **Back button**: `h-11 w-11 lg:h-10 lg:w-10`, an `aria-label` where it
  had none, `inline-flex` on the `Link` (the collapsing-anchor finding from
  R3-A, present here too), and **`rtl:rotate-180` on the `ArrowLeft`** —
  §7 named this exact file as missing it. Confirmed live: the arrow points
  → in Arabic.
- **Footer**: `flex-wrap` and 44px targets. The inventory called it OK,
  which was true at 375 in English; Arabic labels are longer and it had no
  wrap to fall back on.

**The cheapest preview route yet.** `JobCreatePage` makes no call on mount
— only on submit — so unlike `/dev/candidate-result-preview` there is no
`fetch` to stub and no fixture to invent. The dev file renders the real
page in the real shell and is about 25 lines.

Checked: harness on the new route, 14 shots — `overflow: 0, errors: 0`.
At phone and tablet the only flagged control is the shell's
`LanguageToggle` (90x40, the R2-A leftover for R7); at 1024 all 14 are
exactly 40px, the `lg` convention, no outliers — the same posture as R3
and R4. Live at 375 RTL: the three fields stack one per row and the back
arrow mirrors.

`npm run typecheck` clean; oxlint unchanged; `npm test` 40/40.

Not verified here: submitting the form. The preview renders the real page,
but a submit would create a real job against whatever backend the
environment points at, so the create path stays in the owner's manual pass.
