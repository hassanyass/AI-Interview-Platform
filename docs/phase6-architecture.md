# Transition Phase 6 — Invitation System
## Architecture, Flow, and Sub-Phase Execution Plan

This document is authoritative for Phase 6's structure and flow. Reference it
directly in every Phase 6 prompt.

## ⚠️ Known limitation this phase does NOT resolve
After Phase 6, a candidate can be invited (both paths) and a
`CandidateInterviewSession` gets created — but when that candidate actually
joins the LiveKit room, the interview will still run on the OLD dynamic
question-generation path, because `agent/agent/interview/controller.py` and
`/internal/load` are not rewired to serve HR-approved questions until
**Phase 7**. Do not treat Phase 6 as delivering the full "candidate gets the
HR-approved questions" experience — it only delivers correct invitation,
identity, and session-creation plumbing. Say this explicitly in any Phase 6
completion report so it isn't mistaken for a finished feature.

## 0. Mandatory verification before Sub-phase 6A
We do not have a reviewed execution walkthrough confirming Phase 2 actually
built the public-link field on `InterviewDefinition` (the approved design
was a flag/token directly on the model, NOT inside `InterviewInvitation`).
**Do not assume this exists.** First step of 6A must be:
> Open the real, current `InterviewDefinition` model and report whether a
> public-access field (e.g. `is_public`, `public_access_token`) already
> exists. If it does not, add it now as part of 6A (nullable/default-false
> boolean + nullable unique token string), via an additive migration, before
> building anything else in this phase.
Similarly, verify the real current shape of `InterviewInvitation` (does it
have `status`, `token`, `otp_code_hash`, `otp_expires_at`,
`otp_attempt_count`, `expires_at` as actually implemented — not just as
planned) before building Sub-phase 6A/6B against it.

## 1. Two distinct flows — do not conflate them

### Flow A — Personalized invitation (email + OTP)
```
Admin: POST /admin/definitions/{id}/invitations {candidate_email}
   -> creates InterviewInvitation (status=INVITED, token=<random>)
   -> NotificationService.send_invitation_email(email, link) [see section 2]

Candidate opens https://.../invite/:token
   -> GET /invitations/{token}  (public) -> validate not expired/revoked,
      return job/definition context (title, instructions, duration) for
      display. Mark status INVITED -> OPENED.
   -> Candidate enters email (frontend calls supabase.auth.signInWithOtp
      directly — no backend call needed for sending the OTP itself, per
      Phase 3's finding that Supabase handles this natively)
   -> Candidate enters 6-digit code (frontend calls
      supabase.auth.verifyOtp directly, receives a Supabase session/JWT)
   -> Frontend calls POST /invitations/{token}/redeem with the Supabase JWT
      -> Backend: validate JWT via existing get_current_candidate_profile_id
         logic (reuse, don't reimplement)
      -> Confirm the JWT's email matches invitation.candidate_email exactly
         (reject if not — this is a security boundary, not optional)
      -> Resolve/create CandidateProfile (reuse Phase 3's dedup-by-email
         logic — do not write a second implementation of this)
      -> Mark invitation status OPENED -> VERIFIED
      -> Create CandidateInterviewSession (job_id, definition_id,
         application_id set; candidate_profile_id set)
         [Note: the real column is `application_id`, not `invitation_id` —
         InterviewSession has no direct FK to InterviewInvitation. The
         actual path to the invitation is
         InterviewSession.application_id -> JobApplication ->
         JobApplication.invitations. Confirmed against the real model,
         Transition Phase 6 planning session.]
      -> Mark invitation status VERIFIED -> STARTED
      -> Return session info + LiveKit token (reuse existing token-issuing
         logic from livekit.py, do not duplicate it)
```

### Flow B — Public link (guest, no verification)
```
Admin: PATCH /admin/definitions/{id} {is_public: true}
  -> RESOLVED in Sub-phase 6A: public_access_token is generated lazily
     inside this existing endpoint, the moment is_public flips false->true
     and no token exists yet. Not tied to Job publish — is_public and
     PUBLISHED are independent (this flow requires both, but a job can be
     published without being public).

Candidate opens https://.../apply/:public_access_token
   -> GET /apply/{token} (public) -> validate definition is_public=true AND
      job status=PUBLISHED, return job/definition context for display
   -> Candidate submits name + email (+ CV upload, reusing existing Resume
      upload/text-extraction logic per the audit — do not rewrite it)
   -> POST /apply/{token}/register
      -> Resolve/create CandidateProfile by email — call
         get_or_create_candidate_profile (backend/backend/services/
         candidate_profile_service.py), the same shared function Flow A
         uses, not a parallel copy.
      -> Resolve/create JobApplication by (job_id, candidate_profile_id) —
         call get_or_create_job_application (backend/backend/services/
         job_application_service.py), the SAME shared function 6A built
         and Flow A also calls. RESOLVED in Transition Phase 6 planning:
         both flows create/reuse a JobApplication, for applicant-listing
         consistency — it is not invitation-only.
      -> Mint guest JWT (reuse Phase 3's existing /public/register logic —
         if that endpoint already does this, call into the same underlying
         service function rather than duplicating the JWT-minting code)
      -> Create CandidateInterviewSession (job_id, definition_id,
         application_id all set — there is still no InterviewInvitation
         row for this path, since there was never an invitation, but
         application_id is NOT null here the way it was mis-described
         before)
      -> Return guest JWT + session info + LiveKit token
```

**Do not let the agent merge these into one endpoint or one status enum.**
They have different identity models (guest vs. Supabase-verified) and
different data (one has an `InterviewInvitation` row, one doesn't).

## 2. Email provider — build the seam, not the provider
P1 (which provider) is still unresolved. Build:
```
backend/backend/services/notifications/base.py       [NEW] — NotificationService interface: send_invitation_email(to: str, link: str, context: dict) -> None
backend/backend/services/notifications/console.py    [NEW] — default impl: logs the email content/link to console/dev log instead of sending
```
Wire the admin invitation-creation endpoint to call this interface. This
means Phase 6 is fully functional and testable end-to-end without picking a
real provider — swapping in Resend/SendGrid/etc. later (P1's eventual
answer) only requires a new implementation of this interface, not touching
call sites. Do not hardcode any specific provider's SDK in this phase.

## 3. Off-limits for this entire phase
- `agent/agent/interview/controller.py`, `/internal/*` — frozen until Phase 7.
- The existing LiveKit token-issuing logic in `livekit.py` — call it, don't
  rewrite it.
- Phase 3's dedup-by-email / JWT-minting logic — reuse the actual functions,
  don't reimplement equivalent logic in a new file.

## 4. Sub-phases (execute and verify each before starting the next)

### 6A — Schema verification + Invitation CRUD (Admin side)
- Do the section-0 verification first.
- `POST /admin/definitions/{id}/invitations`, `GET .../invitations` (list
  with status), notification interface + console implementation.
- **Stop condition:** creating an invitation produces a real row with a
  unique token; the console notification implementation logs a sensible
  invite link.

### 6B — Personalized redemption flow (backend)
- `GET /invitations/{token}`, `POST /invitations/{token}/redeem` exactly as
  in Flow A above.
- **Stop condition:** a test using a mocked Supabase JWT (matching
  Phase 3's existing OTP-mock test pattern — reuse that mocking approach)
  successfully redeems, creates the session, and correctly REJECTS a JWT
  whose email doesn't match the invitation.

### 6C — Public link flow (backend)
- `GET /apply/{token}`, `POST /apply/{token}/register` exactly as in Flow B
  above, explicitly reusing Phase 3's guest-JWT and dedup logic (grep for
  and call the existing function/service, do not copy its logic into a new
  file).
- **Stop condition:** registering twice with the same email resolves to the
  same `CandidateProfile` (same dedup guarantee as Phase 3), each producing
  its own new `CandidateInterviewSession`.

### 6D — Frontend: public routes
- `/invite/:token` and `/apply/:public_access_token` pages: landing display,
  OTP entry (personalized) or name/email/CV form (public), wired to 6B/6C.
- **Stop condition:** both flows work end-to-end through the UI against the
  real backend, ending in a valid LiveKit token being returned (do not need
  to actually join a room to complete this phase — that's existing,
  untouched functionality).

## 5. What "done" looks like for Phase 6
A candidate can be invited by email+OTP or self-register via a public link,
in both cases correctly deduped by email against any existing profile, and
in both cases a real `CandidateInterviewSession` is created with a valid
LiveKit token — with the explicit caveat from the top of this document that
the interview content itself still runs on the legacy dynamic-generation
path until Phase 7.
