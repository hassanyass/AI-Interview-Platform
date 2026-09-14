# Himma Rebrand & Legacy Cutover
## Phased Plan

Not a numbered Transition Phase — reference this doc directly. Combines
Phase 10's original cutover scope (remove legacy candidate self-serve) with
the full visual rebrand, since they're now sequenced together per the
user's decision: don't redesign what's about to be deleted.

**Ground truth for design decisions:** `docs/e_and_visual_identity_prototype_report.md`
(the e& brand guide) is authoritative for all color/type/spacing/tone
decisions. Do not deviate from it without flagging why.

**Ground truth for what exists today:** `docs/API_REFERENCE.md` should exist
and be current before RB-A starts. If it doesn't exist or is stale (check
its date/last-updated marker against recent phase work), regenerate it
first — it's the map of what's legacy vs. current, and this whole plan
depends on that map being accurate.

## Explicit policy amendment (read before touching anything)
`InterviewerCharacter.tsx` was frozen/protected since Phase 5. **This is now
explicitly lifted** — the user has confirmed they want the avatar/AI visual
identity redesigned as part of this rebrand, per the e& guide's Section 12
("AI Visual Language" — no robot heads, glowing brains, circuit boards;
communicate AI through conversation/signals/motion/minimal geometry
instead). Redesign the visual/SVG presentation; do NOT touch whatever
underlying logic drives lip-sync/state-sync with the voice pipeline unless
a sub-phase explicitly scopes that — separate the visual skin from the
sync mechanism if they're currently coupled, flag if that's not cleanly
possible.

**Still frozen, no exceptions:** `agent/agent/interview/controller.py`,
`/internal/*`, `agent/agent/interview/voice_adapter.py` (just hardened in
the real-time voice pass — do not touch), and anything in `agent/agent/`
generally beyond what's needed for the avatar's visual layer specifically.
This is a frontend/branding effort. If any sub-phase seems to need a
backend or agent-logic change, stop and flag it — that's出 of scope by
default.

## Standing rules for this whole effort
1. **Classify every existing page/component before touching it**: DELETE
   (legacy candidate self-serve — login/signup, old dashboard,
   create-interview flow), REDESIGN (functional B2B surfaces — admin panel,
   invite/apply pages), RESTYLE-CHROME-ONLY (the live interview page — new
   visual treatment around it, zero changes to anything touching LiveKit/
   audio/voice_adapter.py), or FLAG (anything ambiguous). Do this
   classification as RB-A's first deliverable, reviewed before any deletion
   or redesign starts.
2. **"Admin as the only real login" still means what it meant when this was
   first scoped**: guest and OTP-invited candidates are NOT accounts and
   are NOT being removed — they access via `/invite/:token` and
   `/apply/:token` only, never a login page. Only the legacy self-serve
   candidate account flow (signup, password login, `/dashboard`,
   `create_interview`) is being deleted.
3. **Live browser review at the end of every sub-phase.** Open the app in
   the browser and show the actual result before moving to the next
   sub-phase — this is a design/visual effort, screenshots and running code
   are the only real verification, not a description of what was built.
4. **Uniqueness bar**: avoid anything that reads as generic AI-website
   template — the e& guide's Section 21 (Do/Don't table) and Section 12 (AI
   visual language) are the concrete guardrails against this, not vague
   taste. If a design choice doesn't map to something in the guide, name
   which principle it's extending and why.
5. **RTL is a first-class requirement, not a later pass** — per the guide's
   Section 16. Scope this explicitly in whichever sub-phase touches each
   page, don't defer it to "later" across the board or it never happens.
6. **Naming scope**: rebrand USER-FACING strings/branding to "Himma"
   (هِمّة) everywhere. Do NOT rename internal file paths, package names,
   directory structure, or code identifiers (still `path2hire`/`backend`/
   `agent` internally) unless explicitly asked — that's a much bigger,
   riskier change with no user-facing benefit. Flag if this distinction
   becomes unclear anywhere (e.g. an email template's "from" name, page
   `<title>` tags, README).
7. **Error messaging is in scope, not an afterthought** — per the user's
   explicit ask for "error friendly messages." Any redesigned page's error/
   empty/loading states get the same design attention as its happy path,
   not a bare "Error: 500" left over from the functional-only Phase 5/6 UI.

## Sub-phases

### RB-A — Inventory & legacy removal
1. Confirm/regenerate `docs/API_REFERENCE.md` if stale.
2. Full page/component inventory per standing rule 1, presented as a table
   for review before deleting anything.
3. Delete: legacy `Auth.tsx` candidate signup/login UI (admin login stays
   — redesigned in RB-F, not deleted), old candidate `Dashboard.tsx`,
   `NewInterview.tsx`, any component only reachable from the deleted
   candidate self-serve flow. Cross-check against the backend: does this
   also mean the legacy `POST /interviews` (`create_interview`) endpoint
   and its `CURRENT_DECISIONS.md`-flagged no-FK gap can finally be removed
   too, or does removing only the frontend leave dead backend surface? Flag
   for a decision, don't silently leave orphaned backend code.
4. Confirm this incidentally fixes the long-flagged "admin lands on
   `/dashboard` first" UX bug, since legacy `/dashboard` won't exist to
   land on anymore — verify explicitly, don't assume.
5. Live browser check: confirm the app still runs, admin login still works,
   invite/apply flows still work, nothing broke from the deletions.

### RB-B — Design system foundation
Design tokens (CSS vars per the e& guide's Section 19), font loading
(Inter/IBM Plex Sans Arabic or the guide's recommended stack), base
component restyle (buttons, cards, inputs, form fields) — the atomic layer
every later sub-phase builds on. Live browser check: a simple page (e.g.
the admin login, post-RB-F, or a component storybook/test page if one
exists) showing the new tokens applied.

### RB-C — Himma rebrand pass
User-facing name change throughout (per standing rule 6's scope
boundary), logo/wordmark treatment per the guide's Section 17 lockup
guidance (e& relationship preserved, not a fully separate identity),
favicon/meta tags, email template sender name (ties to the still-unresolved
P1 email provider decision — cosmetic naming can proceed regardless of
which provider eventually gets picked).

### RB-D — Admin panel redesign
Job list, job creation, section/question editor, publish flow — apply
RB-B's system to Phase 5's already-functional pages. Redesign, not rebuild
— the underlying logic/API calls are proven, only chrome changes. Include
error-friendly messaging pass per standing rule 7 (e.g. the 409
publish-blocked states, validation errors).

### RB-E — Candidate-facing pages redesign
`/invite/:token`, `/apply/:token` landing pages (Phase 6D), and the
interview page's chrome (RESTYLE-CHROME-ONLY per standing rule 1 — the
LiveKit/audio integration underneath is untouched). This is where the new
AI avatar (per the policy amendment above) actually appears.

### RB-F — Auth redesign (admin-only)
Redesign the admin login page per the new system. No candidate-facing
login exists anymore after RB-A.

### RB-G — RTL / Arabic pass
Explicit, dedicated verification across every redesigned page from RB-B
through RB-F: full RTL layout, mirrored directional icons, correct Arabic
typography/line-height, language switch. Do this as its own reviewed
sub-phase even if individual pages tried to build it in as they went — a
dedicated pass catches what individual page-level attempts miss.

### RB-H — Final review pass
Full click-through, both languages, admin + both candidate entry paths,
confirming nothing from Phase 5/6/7/9's actual functionality regressed
under the new design. This is the "does it still work, not just look
different" check.
