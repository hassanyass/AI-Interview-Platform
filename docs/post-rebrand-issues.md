# Post-Rebrand Issues — Triage

Found during live testing after the Himma rebrand/cutover. Triaged by type
so each gets the right process, not a uniform "just fix it."

## P0 — Urgent regression (was working, now broken)

### Issue 3c — Guest candidates cannot join their interview
Repro (exact, as reported): open a real public-apply link
(`http://localhost:5173/apply/<token>`), enter name + email, submit ->
lands on the interview page -> **"Connection Error: Not authorized to
access this interview session."**

This exact flow (Phase 6C/6D) was live-verified working end-to-end with
real network evidence before the rebrand started: `POST /register -> 200`,
`GET /interviews/{id} -> 200`, `POST /livekit/token -> 200`. Something
between then and now broke it. Treat as a regression, not a fresh bug —
find what changed, don't just patch the symptom.

Suspects to check, in order:
1. `GuestOrAuthRoute` (Phase 6D, scoped only to `/interviews/:id` and its
   `/result` variant) — still present, still applied, still correctly
   distinct from `ProtectedRoute`?
2. `lib/api.ts`'s `fetchApi` guest-token fallback logic — still checking
   for a guest session when no Supabase session exists?
3. `AuthContext.tsx`'s `guestToken` state — still intact after RB-A/RB-F's
   Auth.tsx changes (Auth.tsx was repurposed to admin-only login — did
   that repurposing touch anything guest-session-related it shouldn't
   have)?
4. Backend: `get_current_candidate_profile_id`'s guest-token resolution,
   and the session-ownership check on whatever endpoint is returning
   "not authorized" — is it actually the `/interviews/{id}` fetch, the
   LiveKit token endpoint, or something else? Get the REAL failing
   endpoint from the network tab, don't assume.

## Not a bug — working as designed, flag only

### Issue 2 — Coding/MCQ sections show "coming soon"
This is the intentional Phase 7/9F stopgap (`publish_job`'s CODING/MCQ
block + `SectionsEditor.tsx`'s `comingSoon` flag), correctly still active
because 9G (HR question-authoring UI) and 9H (candidate submission UI)
were deliberately deferred and never built. Do NOT remove this guard as
part of addressing this list — that would silently reopen exactly the
broken-candidate-experience risk it exists to prevent. If Coding/MCQ
support is wanted now, that's resuming Phase 9 (9G/9H), a real scoped
effort — flag it as a decision for later, not a quick fix here.

## Needs a product decision before implementation

### Issue 1 — Cannot delete/pause/end a published job
Partially by design: `DELETE /admin/jobs/{id}` was deliberately restricted
to DRAFT-only back in Phase 4 (prevents orphaning sessions/invitations tied
to a published job). But there's a real gap: `CLOSED` exists in the DB
schema but was explicitly deferred — "explicit API handling for
transitioning to CLOSED is deliberately deferred" (Phase 4 decision). No
"pause" concept exists anywhere in the schema at all.

Before building anything: decide, explicitly —
- Is "pause" a distinct state from "closed," or does closing a job
  (stop accepting new candidates, existing in-flight sessions unaffected)
  cover what "pause" means here? A new PAUSED status is a real schema
  change; reusing CLOSED for both is not.
- What does deletion mean for a CLOSED job — is it now allowed (since
  presumably no new sessions can be created against it), or still blocked
  because historical sessions/results still reference it?

### Issue 3a/3b — Public vs. personalized access UI is confusing / can't add public after creating invitations
Per the original product spec, public access and personalized invitations
were designed as INDEPENDENT, coexisting modes on one InterviewDefinition
— not mutually exclusive. The backend (`is_public` flag + separate
`InterviewInvitation` rows) was built this way. This is very likely a UI
gap (no clear toggle to enable public access after/alongside creating
invitations) around a backend capability that may already work — verify
that before assuming new backend work is needed.

## New feature, not scoped before

### Issue 4 — No "Test Interview" option for admins
Admins currently have no way to preview/test-drive an interview without
going through a real candidate flow. Needs design: does this create a
special, non-persisted (or clearly-marked-test) session tied to the
admin's own identity, bypassing invitation/application entirely? Scope
this as its own small design-then-build task, not a quick patch.

## P0 — Live interview does not follow the HR-approved flow (new, most urgent)

### Issue 6 — VERBAL-only job produced a legacy "technical problem" instead of the ordered core-question walk
Repro: created a fresh job with ONLY a VERBAL section (no CODING), published,
tested via the real public-apply link. Expected: the interview should have
asked the HR-authored VERBAL questions via CORE_QUESTION_PROMPT, then gone
straight to CLOSING once exhausted (per Phase 7's design — this is
deterministic at the controller level, not LLM-dependent). Actual: the
interview produced a dynamically-generated TECHNICAL problem — behavior
that should only be reachable when `_active_core_section()` returns `None`,
i.e. `context.sections` was empty for this session.

Do NOT assume the Phase 7/9 logic itself is broken — 7F/9I's mock-LLM tests
specifically proved this routing works, but only against in-memory state,
never through the real DB -> /load -> main.py pipeline end to end, live.
This needs fresh reproduction and real data tracing, same standard as
every other issue on this list, before concluding anything.

## P1 — Candidate-facing feedback exposure (clear policy, needs a dependency check)

### Issue 7 — Candidates should not see their own evaluation/feedback
Currently, completing an interview shows the candidate a full results/
feedback page (inherited from the original B2C product design, where this
was intentional). In the B2B model, candidates should see only a polite
completion message ("Thank you, your interview is complete") — full
evaluation belongs to HR/admin only.

**Dependency to check before restricting access**: does ANY admin-facing
way to view a candidate's result currently exist? Phase 8 (results
normalization + HR comparison views) was explicitly deferred — if nothing
admin-facing exists at all today, blocking candidate access would leave HR
with zero visibility into results, which is worse than the current state.
At minimum, a bare-bones admin endpoint to fetch a candidate's result
(not full Phase 8) may need to ship alongside this fix, not after it.

Scope both layers, not just the visible one: (a) frontend — replace the
candidate-facing FinalResult.tsx experience with a thank-you screen, (b)
backend — should GET /interviews/{id}/result actually reject a candidate
token now, or does it stay reachable via direct API call with only the UI
hidden? Recommend blocking at the API layer too, matching this project's
established pattern of not relying on UI-only enforcement for anything
access-control-related.

## Deferred, noted for later — not part of this phase
User wants to discuss adding a "follow-up section" concept to the
interview UI/style at some point after this phase closes. Not scoped, not
designed, not started — just recorded here so it isn't lost.

## Deferred, confirmed
### Issue 5 — Results/evaluation logical gaps
Already correctly identified by the user as Phase 8 (results
normalization) territory. Stays deferred beyond the minimal admin-view
dependency Issue 7 may require. No further action here.
