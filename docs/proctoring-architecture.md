# Proctoring & Integrity Feature — Fullscreen Enforcement, Recording, Cheating Signals, Dashboard Redesign

Not a numbered Transition Phase — reference this doc directly. Builds on
top of Phase 8's now-working evaluation pipeline and the existing
LiveKit-based voice infrastructure.

## Read this before anything else: the consent/framing decision

Recording a candidate and flagging them as a potential cheater carries
real legal and ethical exposure if built carelessly:
- Recording without clear, affirmative disclosure/consent is a legal
  problem in many jurisdictions, not just a nice-to-have.
- Commercial proctoring tools have well-documented bias problems — false
  flags disproportionately hit people with disabilities, poor connections,
  darker skin tones (face-detection bias), or unconventional setups. A
  system that labels someone "cheated" based on a flaky signal is a
  fairness and reputational risk for a real company's hiring process.

**Non-negotiable defaults for this feature, unless explicitly overridden
by the user:**
1. Candidates see a clear, plain-language consent screen before any
   recording/monitoring starts, explaining exactly what's captured (video,
   fullscreen-exit events, focus-loss events) and that HR will review it.
   No recording starts without explicit consent.
2. The system NEVER outputs a hard "cheated" verdict. It surfaces a
   **flagged-for-review** status with the underlying evidence (which
   signals fired, when, snapshots if applicable) — HR makes the actual
   judgment, exactly like Phase 8's manual-override pattern for scoring.
3. All of this applies equally to the public-link (guest) and personalized
   (OTP) flows — no path bypasses consent.

## Confirmed technical approach (researched, not guessed)
- **Recording**: LiveKit Egress (already-integrated infrastructure) —
  composite room recording to storage. Free tier (LiveKit Cloud "Build")
  includes meaningful included egress — confirm current exact quota before
  building, quotas change.
- **Fullscreen/focus detection**: native browser Fullscreen API +
  `visibilitychange`/`blur` events. Free, client-side, no library needed.
- **Cheating signals**: `@timadey/proctor` (or equivalent lightweight,
  actively-maintained client-side library found at build time — verify
  it's still current/maintained before adopting) — face presence/absence,
  multiple-face detection, gaze/head-pose, suspicious-object detection,
  all client-side, no server ML cost.

## Sub-phases

### PR-A — Consent & disclosure (build FIRST, blocks everything else)
- New consent screen, shown before the intro screen's "Start Session"
  (or combined with it) — plain-language explanation, explicit
  checkbox/affirmative action required, not implied by continuing.
- Backend: record consent (timestamp, what was disclosed) tied to the
  session — this is itself evidence the company may need later.
- No technical proctoring work happens before this exists and is verified
  working.

### PR-B — Fullscreen enforcement + tab/focus detection
- Require fullscreen to start the interview (Fullscreen API).
- On exit: start a 5-second grace timer (visible countdown, not silent) —
  if the candidate returns to fullscreen within 5s, no flag; if not, log a
  `FULLSCREEN_EXITED` event (reuse the existing `InterviewEvent` table/
  mechanism already in the schema — this is exactly what it's for).
- Separately log `TAB_HIDDEN`/`WINDOW_BLURRED` via `visibilitychange`/
  `blur` — distinct event types, since "briefly alt-tabbed" and "left
  fullscreen for 5+ seconds" are different severities.
- These events feed PR-D's aggregate flag, not a standalone verdict.

### PR-C — Full audio+video recording via LiveKit Egress
- **Full continuous audio+video recording, not audio-only or periodic
  snapshots.** Storage is Cloudflare R2 (S3-compatible, chosen for its
  much higher per-file limits and zero egress fees — HR will repeatedly
  watch/re-watch recordings). See CURRENT_DECISIONS.md's "Proctoring
  storage & video-recording scope" entry for the full reasoning and the
  storage provider this replaced.
- **Camera capture is in PR-C's scope**, not deferred to PR-D — Room
  Composite Egress only records tracks actually published to the room,
  and the candidate's camera was never turned on anywhere in the existing
  code (`LiveKitRoom video={false}`, hardcoded). PR-C adds the real
  candidate-facing camera request/publish/indicator; PR-D's face/gaze
  detection reuses that same already-published stream rather than
  requesting camera permission a second time.
- Camera-permission denial degrades gracefully (interview proceeds
  audio-only) — this is deliberately different from PR-B's fullscreen
  gate, which hard-blocks. See CURRENT_DECISIONS.md for why the two are
  treated differently.
- Start room composite recording when the interview session begins
  (post-consent), stop on completion/termination.
- Store the recording reference (egress ID + storage path) on the
  session record.
- Confirm actual current LiveKit Cloud free-tier egress quota/pricing
  before assuming cost is negligible — verify, don't assume research from
  months ago is still accurate.

### PR-D — Client-side cheating-signal detection
- Integrate the chosen library (verify it's current/maintained at build
  time) for face-presence/multiple-face/gaze signals, running client-side
  during the interview, reusing the camera stream PR-C already turns on
  (no second permission request).
- Combine with PR-B's fullscreen/focus events into ONE aggregate
  `IntegritySummary` per session — a list of specific flagged moments
  (timestamp, signal type, confidence if available), NOT a single
  cheated/not-cheated boolean. Each flagged moment's timestamp is
  relative to the session start, so it lines up directly with PR-C's
  recording timeline — see PR-F.
- Explicit design requirement: this must degrade gracefully if the
  candidate denies camera permission or the library fails to load — the
  interview must still proceed (voice-only proctoring signals like
  fullscreen/focus still apply), never block someone from completing a
  legitimate interview due to a proctoring-library failure.

### PR-E — Backend schema
- New fields/table(s): consent record (PR-A), recording reference (PR-C),
  integrity events (PR-B/D) — likely extending the existing
  `InterviewEvent` mechanism rather than inventing a parallel one, confirm
  during exploration.
- Additive-only, same migration discipline as every other schema change
  this project has made.

### PR-F — HR Dashboard redesign (incorporating this + Phase 8)
This is the "senior UX/UI, full redesign" ask — treat as a real design
project, not a bolt-on to the existing Phase 8F pages:
- Per-candidate view gains: video playback (the full PR-C recording), an
  integrity timeline (flagged moments plotted against the interview
  timeline, not just a list) where **clicking a flagged moment jumps the
  video player directly to that timestamp** — the moments and the
  recording share the same session-relative clock by construction (see
  PR-D), so this is a direct seek, not a fuzzy match — and a clear,
  human-reviewable summary, never a bare "CHEATED" badge.
- Per-job aggregate view gains: count of flagged-for-review candidates
  alongside Phase 8's existing suggested/completed counts.
- This is the moment to also address the visual quality concerns raised
  about Phase 8's current dashboard (generic, under-designed) — redesign
  holistically, not patch incrementally. Audit against the e& guide's
  Section 21 Do/Don't table explicitly, same discipline as the earlier
  CODING/MCQ consolidation pass, before building.

### PR-G — Integration verification (deferred to manual testing, per standing instruction)

## Non-negotiables
- No automated testing / no live-flow-driving beyond what's needed to
  verify each piece in isolation, per this project's current standing
  instruction — confirm this still applies when you start, in case it's
  changed.
- `controller.py`/`/internal/*` frozen unless a sub-phase explicitly
  justifies and gets sign-off, same as always.
- PR-A must be confirmed complete and live-verified before PR-B onward
  starts — this ordering is not optional given the legal/ethical stakes.
