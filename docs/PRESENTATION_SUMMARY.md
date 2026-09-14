# Himma — Presentation Summary

Prepared for a live demo audience. Every claim below is grounded in this project's own `docs/CURRENT_DECISIONS.md` / `docs/PROJECT_STATUS.md` entries, this session's own direct hands-on verification of the running app, or is explicitly flagged as unverified — nothing here is presented as "working" without a real basis for that claim.

---

## 1. What Himma is, and who it's for

**Himma (هِمّة)** is an AI-driven interview and career-assessment platform, built as **e& Himma — an AI Interview & Career Experience** (per `docs/e_and_visual_identity_prototype_report.md`, the project's e& brand-identity guide): recognizably connected to the e& group brand, with its own product personality.

It's **B2B / HR-facing**, not a consumer job board. The people who use it:
- **HR / Admin users** — create a Job, define its interview structure (sections, questions, assessment criteria), publish it, invite or share access with candidates, and review AI-generated, HR-configurable scored results afterward.
- **Candidates** — reach a specific interview two ways: a public share link, or a personalized email invitation — never a general sign-up/login. They complete a real-time, voice-driven AI interview and, depending on the job's configured sections, may also solve a coding problem or answer multiple-choice questions.

The core architectural principle, unchanged since the project's Phase 0 foundation: **"The LLM is the interviewer intelligence; the application controls the interview"** — the backend/state machine own the lifecycle, timing, and guardrails; the LLM owns natural conversation, reasoning, and follow-ups within those bounds.

---

## 2. Feature walkthrough (for a live demo)

Each item states its real, current verification status — not what was planned, what was intended, or what "should" work.

### Admin: Job & interview authoring
**Verified end-to-end**, per `docs/PROJECT_STATUS.md` Phases 4–5 and re-confirmed by this session's own direct work in `CriteriaEditor.tsx`/`JobResultsPage.tsx`. An HR admin creates a Job (title, seniority, required/preferred skills, responsibilities, candidate instructions), adds Sections (Verbal, Coding, MCQ — each type once per interview, admin-reorderable), and generates questions with AI (Groq), which are individually HR-editable and regenerable. Publishing is live and unblocked — a `409` publish-blocking stopgap that existed during Phase 9 was **deliberately removed** on 2026-08-26 after explicit user sign-off, confirmed via a real publish through the actual admin UI.

### Candidate access: public link & personalized OTP
**Verified end-to-end**, Phase 6 (6A–6D). Two independent paths, both live-tested against the real backend and browser, no mocking:
- **Public link**: candidate provides name + contact info directly, no password, no account.
- **Personalized invitation**: candidate enters their email, confirms via a one-time code (Supabase's native email OTP), then proceeds — invitation status (invited/opened/verified/started/completed) is visible to the admin.
- One caveat worth knowing before a live demo: the personalized flow's magic-link redirect was *mechanically* verified (the outgoing request was confirmed to carry the right redirect URL) but a full behavioral, end-to-end confirmation was still pending as of the last status update — worth a quick real test with a real inbox before demoing this specific path live.

### The live voice interview — Verbal, Coding, MCQ
**Verified end-to-end for all three section types**, each with its own dedicated, purpose-built UI (not one generic layout reused three ways):
- **Verbal**: the original shared interview layout — AI avatar, transcript, voice-driven Q&A with up to 2 AI follow-ups per question.
- **Coding**: a LeetCode/CoderPad-style split pane — problem statement left, a real code editor right, no avatar, a collapsible transcript, and a live "request a hint" mechanism that gives graduated hints without revealing the answer. No follow-ups after submission — it's live problem-solving during solving, not a submit-and-grade box.
- **MCQ**: a centered quiz card, no avatar, options with radio/checkbox selection depending on single/multi-select — binary right/wrong grading, no follow-up interaction by design.
- All three were live-verified end-to-end on 2026-08-26 per `docs/PROJECT_STATUS.md`: real sessions, real submissions, real agent acknowledgment, correct advancement through the interview.

### Waiting room between sections
**Verified end-to-end**, live-tested 2026-08-26 against a real published multi-section job. Time between sections is free/unclocked — the interview timer pauses entirely — with an auto-proceed timeout if a candidate goes AFK, and correct "what's next" messaging (which section just finished, which is coming up).

### HR-defined assessment criteria with weighted scoring
**Verified end-to-end**, shipped 2026-09-01. Two scores are shown, deliberately distinct and separately labeled: the LLM's own **holistic** judgment (`overall_score`, unchanged from the original design), and a **new, genuinely code-computed weighted score** — HR sets a 1–10 weight per enabled assessment criterion, and the system averages only the criteria that had enough evidence to score, re-normalizing weights among those rather than treating missing ones as zero. Proven correct with real computed math, not just code review.

### Results dashboard
**Verified end-to-end**, fully redesigned 2026-09-01 (a genuine visual redesign, not a token/color pass — the first attempt was explicitly rejected and rebuilt). Per-candidate view: identity, both scores, AI recommendation, an HR override control, a grouped criteria breakdown, the interview recording, and a full record (question-by-question detail, technical submission, full transcript). Per-job view: aggregate stats (completed/in-progress/suggested-for-next-step counts) and a sortable candidate table.

### Proctoring — fullscreen/tab monitoring, video recording, face/gaze detection
Three independent signal sources, all real, all logging into one shared `interview_events` mechanism — with **one signal genuinely not yet trustworthy for a live demo claim** (see below):
- **Fullscreen & tab/focus monitoring**: **verified working in production.** Requires fullscreen to start; a 5-second visible grace period on exit before logging a real flagged event; separate, distinctly-typed events for tab-hidden vs. window-blurred.
- **Video recording**: **verified working in production.** Full continuous audio+video via LiveKit Egress to Cloudflare R2, with a short-lived signed playback URL generated fresh per view.
- **Face-presence detection** (face disappeared / a second face appeared): **built and verified this session** (2026-09-02) — a real, found-and-fixed bug (a missing `.play()` call that silently broke multi-face detection) is a good concrete example to have on hand if asked "how do we know this works," since it shows the feature was actually tested against real detection behavior, not just written and assumed correct.
- **Head-pose detection** ("looking down at a phone" while the face stays visible): **built, wired end-to-end, but NOT yet calibrated** — this is a real, current limitation, not a hypothetical one. The detection math itself is verified correct (tested against hand-built synthetic data), but which direction of head tilt actually means "down" in the real camera feed has not been confirmed against a live capture as of this writing. **Do not claim this specific signal reliably catches phone use in a live demo** — it may or may not fire correctly today.
- **Aggregation & dashboard display**: **verified end-to-end** (2026-09-02) — any fired integrity event (from any of the three sources above) marks a session "flagged for review," visible as a per-job stat tile and a per-candidate "Integrity Timeline" that seeks the recording to the exact flagged moment when clicked.

### Himma visual identity & RTL support
**Partially verified, not fully audited this session.** This session directly observed the live admin login screen carrying real Himma/e& branding ("e& | هِمّة — Sign in to Admin Dashboard"), and `frontend/src/locales/ar.json` exists with real Arabic translations alongside `en.json`. However, `docs/PROJECT_STATUS.md` — the project's own single source of truth for phase completion — **does not record a completion status for the rebrand plan's sub-phases** (`docs/rebrand-architecture.md`'s RB-A through RB-H: legacy cleanup, design tokens, the Himma naming pass, admin/candidate page redesigns, and a dedicated RTL verification pass). **Recommendation: personally click through both languages on the actual pages you intend to demo before the presentation**, rather than presenting RTL/rebrand completeness as a settled fact — this is a real gap in the record, not a confirmed pass.

---

## 3. Technology stack, by layer

### Frontend
- **React + Vite + TypeScript** — the admin dashboard and candidate-facing pages, a single-page app.
- **LiveKit client SDK (`@livekit/components-react`)** — the browser-side half of the real-time voice/video connection to the interview room; also publishes the candidate's camera track, shared (not re-requested) by the proctoring features below.
- **`@mediapipe/tasks-vision` (`FaceLandmarker`)** — runs client-side, in the candidate's own browser, on the shared camera track: face-count (presence/multiple-face) and head-pose detection for proctoring, self-hosted (not CDN-loaded) so the interview doesn't depend on a third party being reachable mid-session.
- **Supabase JS client** — candidate/HR authentication (OTP email codes, admin session tokens).

### Backend
- **FastAPI (Python)** — the REST API: job/section/question CRUD, publish workflow, invitation management, results/evaluation endpoints, LiveKit token minting, and the `/internal/*` contract the agent worker calls back into.
- **SQLAlchemy (async) + Alembic** — the ORM and migration system against the real database below; every schema change this project has made has been additive-only (new tables/nullable columns), never a destructive rewrite.
- **Supabase (Postgres + Auth)** — the actual database (a real remote Supabase Postgres instance, confirmed not a local dev DB) and the identity provider behind both admin login and candidate OTP.
- **Cloudflare R2 (via `boto3`, S3-compatible)** — stores the full interview video/audio recordings that LiveKit Egress produces; the backend only ever hands out short-lived signed URLs for playback, never proxies the video itself.

### Agent / voice layer
- **`livekit-agents` (Python)** — the actual interviewer: a persistent worker process that registers with LiveKit Cloud and joins each interview room as a real-time participant.
- **LiveKit Cloud (WebRTC + Egress)** — the real-time audio/video transport between candidate and agent, and the recording pipeline (Egress) that produces the video files stored in R2.
- **Groq** — the LLM doing the interview reasoning/conversation (with a resilient multi-API-key rotation pool for its speech models to survive Groq's free-tier per-key daily quota), and also generating AI-drafted interview questions on the admin side.
- **Azure Speech** — the current text-to-speech provider used for the interviewer's actual spoken voice (English/Arabic voices), reachable as an alternate provider alongside Groq's own TTS depending on configuration.

---

## 4. Known limitations / what's next — say this before someone finds it live

Honest, not defensive. A presenter should know all of these going in:

- **Head-pose ("phone use") detection is built but not calibrated** (see §2) — don't promise it reliably catches a candidate glancing at a phone in this demo; the disappearance/multiple-face signals are the ones proven to work.
- **The real-time voice pipeline's own hardening work has automated tests passing (120/120) but explicitly has NOT had a live, spoken, human-verified confirmation** as of the last status update (`docs/PROJECT_STATUS.md`'s RT-A/RT-B0/B1/B2 entry) — the fixes for audio "clashing," premature cutoff, and intermittent delay are code-complete and unit-tested, but "does it actually sound right to a real ear in a real conversation" is explicitly called out as not yet done. Worth a real practice run of the voice interview before presenting it live, not just trusting the test suite.
- **Rebrand/RTL completion isn't recorded** in `PROJECT_STATUS.md` (see §2's visual identity note) — verify the specific pages you'll demo, in both languages, beforehand.
- **Deferred, not broken, by explicit design decisions** (`docs/CURRENT_DECISIONS.md`'s "Still unresolved" list) — a presenter should not promise these exist: invitation expiration policy, whether candidates can retake an interview, editing an already-published interview, multiple admin users/permissions, and real email delivery (the invitation/notification layer is provider-agnostic and functional, but currently backed by a console-log stub, not a real email provider — P1 is explicitly deferred).
- **The legacy `create_interview` endpoint** still creates sessions with no `job_id`/`definition_id`/`application_id` — flagged for a future cutover phase, not user-visible, but worth knowing it exists if a question about data-model cleanliness comes up.
- **This is a prototype, not a hardened production deployment.** No public deployment currently exists — `docs/deployment-readiness.md` and `docs/deployment-guide.md` cover what's needed to actually host this for outside test users, and that work is still in progress as of this writing (the Supabase database credential was mid-rotation at the time this document was written — confirm that's fully complete before any demo that touches the real database, live or local).
