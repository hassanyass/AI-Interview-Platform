# People Hub ↔ Himma Integration — Data Flow (Approach 1: Isolated)

Status: **design spec, not yet built**. Everything in `data-flow-diagram.md` and `architecture-overview.md` describes what exists today; everything in this file is new, additive, and unbuilt — proposed to slot on top of the existing system without changing any existing table, model, or endpoint. Where a decision hasn't actually been made yet, it's flagged explicitly in §10 rather than assumed — confirm those before anyone designs pixels or writes code against this.

Approach recap: People Hub is HR's system of record. It sends one signed request to create a requisition; Himma runs the entire interview lifecycle in isolation; People Hub receives back one thing — a ranked shortlist. HR never logs into Himma. No other path into Himma exists.

---

## 1. New entity

| Entity | Type | Role |
|---|---|---|
| **People Hub** | External system | HR's existing hosted platform. Sole external caller. Never receives candidate PII beyond what it already has (name/email it sent); never receives raw transcripts or recordings — only the scored shortlist. |

All other entities (HR admin, Candidate, Supabase Auth, LiveKit Cloud, Groq, Azure Speech, Cloudflare R2) are unchanged from `data-flow-diagram.md` §1 — **HR admin never appears in this file's data flows**, by design of Approach 1.

---

## 2. New data store

One new table, fully additive — no foreign key touches an existing table's primary key in a way that requires altering it, and every existing table (`jobs`, `interview_definitions`, etc.) is used as-is.

### `requisition_links`
| Column | Type | Notes |
|---|---|---|
| `id` | UUID, PK | |
| `job_id` | UUID, FK → `jobs.id`, `ON DELETE CASCADE` | The Himma job this requisition produced |
| `external_requisition_id` | String, unique | People Hub's own id for this requisition — the correlation key for every future call about this job |
| `source_system` | String | `"PEOPLE_HUB"` (future-proofs for a second HRIS later) |
| `callback_url` | String | Where Himma POSTs the finished shortlist |
| `webhook_secret` | String, encrypted at rest | HMAC key Himma signs outbound webhooks with; People Hub verifies |
| `requested_top_x` | Integer | How many ranked candidates People Hub wants back |
| `candidate_source_mode` | String | `"PUBLIC_LINK"` \| `"PROVIDED_LIST"` — see §10, open decision 1 |
| `submission_deadline` | Timestamp, nullable | When Himma stops accepting new candidates and computes the shortlist regardless of volume |
| `status` | String | `"GENERATING"` → `"OPEN"` → `"SHORTLISTED"` → `"DELIVERED"` \| `"FAILED"` |
| `delivery_attempts` | Integer, default 0 | Webhook retry counter — see §8 |
| `created_at` / `updated_at` | Timestamp | |

Nothing else changes. `jobs`, `interview_definitions`, `interview_sections`, `interview_questions`, `job_applications`, `interview_invitations`, `interview_sessions`, `evaluations`, `scores` are all read/written exactly as documented in `data-flow-diagram.md` §2 — this integration only adds a new *front door* and a new *back door*, not a new interview pipeline.

---

## 3. New process: P0 — Integration Gateway (`backend/backend/api/endpoints/integrations.py`, proposed)

The only code that is genuinely new. Everything downstream of it (P2.2 Job & Content Authoring, P2.3 Candidate Acquisition, P2.4 Live Session Support, P2.5 Results & Evaluation, P3 Agent) is reused exactly as-is — P0 just calls into them the same way the admin UI already does.

- **Inputs**
  - `job requisition payload` (see §4) — from People Hub, signed
  - `requisition status poll` (`GET .../requisitions/{external_requisition_id}`) — from People Hub, signed
- **Outputs**
  - `requisition accepted` ack (Himma's internal `job_id`, initial `status`) — to People Hub, synchronous response
  - `ranked shortlist webhook` (see §7) — to People Hub, asynchronous, signed
  - `requisition status` (poll response, mirrors webhook payload) — to People Hub
- **Reads**: D5 `jobs`, D18 `evaluations`, D19 `scores`, plus the new `requisition_links` table
- **Writes**: `requisition_links` (create on intake, update `status`/`delivery_attempts` throughout); delegates the actual `jobs`/`interview_definitions`/`interview_sections`/`interview_questions` writes to P2.2's existing code path — **P0 does not duplicate that logic, it calls it**
- **Security boundary**: this is the *only* unauthenticated-by-user-JWT entry point that accepts data from outside Himma's own frontend/agent. See §9.

---

## 4. Inbound contract — job requisition

`POST /api/v1/integrations/people-hub/requisitions`

| Field | Maps to | Notes |
|---|---|---|
| `external_requisition_id` | `requisition_links.external_requisition_id` | Required, unique per People Hub tenant |
| `callback_url` | `requisition_links.callback_url` | Required |
| `job_title` | `jobs.title` | Required |
| `job_description` | `jobs.description` | |
| `seniority` | `jobs.seniority` | |
| `location` | `jobs.location` | |
| `required_skills` | `jobs.required_skills` | Array of strings |
| `preferred_skills` | `jobs.preferred_skills` | Array of strings |
| `responsibilities` | `jobs.responsibilities` | Array of strings |
| `language` | `jobs.language` | `"en"` \| `"ar"` |
| `sections_requested` | drives P2.2's section-generation loop | Array of `"VERBAL"` \| `"CODING"` \| `"MCQ"`, e.g. `["VERBAL", "MCQ"]` |
| `duration_minutes` | `interview_definitions.duration_minutes` | |
| `requested_top_x` | `requisition_links.requested_top_x` | Required, integer |
| `submission_deadline` | `requisition_links.submission_deadline` | Optional ISO-8601 timestamp |
| `candidates` | see §10, open decision 1 | Optional array of `{name, email}` — only used if `candidate_source_mode = "PROVIDED_LIST"` |

**Synchronous response** (People Hub gets this immediately, before questions are even generated):
```
{ "job_id": "<Himma UUID>", "external_requisition_id": "...", "status": "GENERATING" }
```

**What happens internally, in order** (all reused, existing code):
1. P0 creates `requisition_links` row, `status = GENERATING`.
2. P0 calls P2.2's job-creation path → writes D5, D6 (`status = DRAFT` momentarily).
3. For each requested section type, P0 calls `question_generator.generate_questions` (the exact Groq call the admin UI's "Generate Questions" button uses) → writes D7, D8.
4. P0 sets a default `time_budget_minutes` per section (needed for publish — see `data-flow-diagram.md`'s P2.2 publish-validation rule) and flips `jobs.status → PUBLISHED`.
5. `requisition_links.status → OPEN`.
6. If `candidate_source_mode = "PROVIDED_LIST"`: P0 calls P2.3's invitation-creation path once per candidate (writes D10, D11) — each candidate gets a real Flow-B invite email/OTP, unchanged from today's invitation flow.
7. If `candidate_source_mode = "PUBLIC_LINK"`: nothing further needed — `interview_definitions.is_public` is already true from step 2, so the job's public apply link is live immediately.

---

## 5. Candidate flow (unchanged)

Candidates never touch People Hub or the gateway. They apply/interview through Himma exactly as documented in `data-flow-diagram.md` §4 (P2.3 → P2.4 → P3), whether they arrived via a provided-list invitation or the public link. This is the core property of Approach 1: **the gateway has no participant in the actual interview.**

---

## 6. Shortlist computation (new logic, small)

Triggered by whichever comes first:
- `submission_deadline` passing (a scheduled check), or
- the count of `COMPLETED` sessions for this job reaching some threshold worth flagging — see §10, open decision 2.

Query (conceptually): D12 `interview_sessions` where `job_id = <this job>` and `status = 'COMPLETED'`, joined to D18 `evaluations` where `is_placeholder = false`, ordered by `weighted_score DESC NULLS LAST, overall_score DESC`, limited to `requested_top_x`.

Each shortlist entry carries: `candidate_name`, `candidate_email`, `overall_score`, `weighted_score`, `recommendation`, `summary` (D18 field) — **not** the full transcript, not the recording, not per-criterion `scores` detail. People Hub gets a decision-ready summary, not raw interview evidence — a deliberate scope boundary given Approach 1's "isolated" premise (see §10, open decision 3 if this should be richer).

---

## 7. Outbound contract — shortlist delivery

`POST <callback_url>` (People Hub's own endpoint), headers include `X-Himma-Signature: <HMAC-SHA256 of body, using requisition_links.webhook_secret>`.

```
{
  "external_requisition_id": "...",
  "job_id": "<Himma UUID>",
  "status": "SHORTLISTED",
  "generated_at": "<ISO-8601>",
  "candidates": [
    { "rank": 1, "candidate_name": "...", "candidate_email": "...",
      "overall_score": 87, "weighted_score": 84.2,
      "recommendation": "Hire", "summary": "..." },
    ...
  ]
}
```

**Polling fallback** (same payload shape): `GET /api/v1/integrations/people-hub/requisitions/{external_requisition_id}` — People Hub can call this any time regardless of webhook delivery, so a missed/failed webhook is never a dead end.

---

## 8. Delivery reliability

- Webhook POST retried with backoff on any non-2xx response, up to a defined attempt ceiling (`requisition_links.delivery_attempts`) — see §10, open decision 4 for the exact policy.
- `requisition_links.status → DELIVERED` only after a 2xx response; stays `SHORTLISTED` (deliverable, not yet acknowledged) otherwise, so the poll endpoint always has something correct to return even if every webhook attempt failed.

---

## 9. Security model (answers "prevent any external integration outside safe gateways")

- **Inbound**: every request to `/api/v1/integrations/people-hub/*` must carry a signed request (HMAC over the body + timestamp, shared secret provisioned out-of-band per People Hub tenant) and a timestamp within a small tolerance window (replay protection). No session cookie, no user JWT — this is a service-to-service credential, structurally identical to how the agent worker already authenticates to `/internal/*` today (`AGENT_API_SECRET`), just a second, independent secret.
- **Outbound**: every webhook is signed the same way, with People Hub verifying `X-Himma-Signature` before trusting the payload.
- **No other path exists.** Himma's admin dashboard, `/api/v1/admin/*`, is completely unreachable by People Hub or by this integration's code path — P0 calls the *same internal Python functions* P2.2/P2.3 use, not the HTTP admin endpoints, so there's no admin-JWT requirement to route around.
- **Rate limiting / allowlisting**: recommend an IP allowlist for People Hub's known egress ranges at the gateway/proxy level, on top of the signature check — belt and suspenders, not a replacement for it.

---

## 10. Open decisions — confirm before implementation

1. **Candidate sourcing mode**: does People Hub always provide the candidate list (`PROVIDED_LIST`), or does Himma's public apply link handle sourcing independently (`PUBLIC_LINK`), or must both be supported? This changes whether `job_applications`/`interview_invitations` get created by P0 at intake time or lazily by a candidate's own action.
2. **Shortlist trigger**: purely deadline-based, or also triggered early once N candidates complete (whichever comes first)? Affects whether "top X" can ever be delivered with fewer than X real completions.
3. **Shortlist payload richness**: is the summary-only payload in §6 sufficient, or does People Hub need the full transcript/per-criterion breakdown too? (If yes, that's a materially bigger data-sharing decision, not just a bigger JSON body — worth its own sign-off.)
4. **Webhook retry policy**: exact backoff schedule and max-attempts ceiling before a requisition is marked `FAILED` and requires manual attention.
5. **Multi-tenancy**: is `webhook_secret` provisioned per People Hub *tenant* or is there only ever one People Hub instance calling in? Affects whether `source_system` alone is enough correlation or a tenant id is also needed.
