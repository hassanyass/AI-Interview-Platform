import { useState } from "react";
import { AdminShell } from "../admin/AdminLayout";
import CandidateResultPage from "../admin/CandidateResultPage";
import type { EvaluationDetail } from "../../api/adminClient";

/**
 * DEV-ONLY visual harness for the candidate result page (registered in
 * App.tsx only under import.meta.env.DEV), added in responsive plan R3-B.
 *
 * Unlike /dev/results-preview, which renders extracted components, this one
 * renders the **real, unmodified `CandidateResultPage`** — all 828 lines of
 * it, including its loading state — by stubbing `window.fetch` for the one
 * endpoint it calls. That was the point: the page is a single large
 * component, and extracting a presentational shell out of it purely to make
 * a preview possible would have been a risky refactor of a page nobody can
 * exercise without a login. A scoped stub in a dev-only file has no such
 * cost and, better, cannot drift from the real page at all.
 *
 * `fetchApi` asks Supabase for a session first; with none it simply sends
 * no Authorization header, so no sign-in is needed. The route is registered
 * as /dev/candidate-result-preview/:jobId/:sessionId (with a redirect from
 * the bare path) because the page reads both from useParams and skips its
 * fetch entirely when sessionId is undefined.
 *
 * Only `GET …/result` is stubbed. Regenerate Evaluation and Save Override
 * go through the real client (and will fail) — the harness never clicks
 * them, and leaving them unstubbed keeps this file from quietly becoming a
 * second implementation of the backend.
 */

const LONG_LABEL = "Structured problem decomposition under ambiguous requirements";

const FIXTURE: EvaluationDetail = {
  session_id: "sess-preview",
  status: "DISCONNECTED", // exercises the "Incomplete session" banner
  completed_at: "2026-09-27T14:32:00Z",
  candidate_name: "Aisha Abdul-Rahman Al-Maktoum",
  candidate_email: "aisha.abdulrahman.almaktoum@averylongcorporatedomainname.example.com",
  job_title: "Senior Machine Learning Engineer, Data Platform & Applied Research",
  overall_score: 4,
  weighted_score: 3.6,
  recommendation: "Hire",
  evidence_sufficiency: 0.82,
  summary: "Strong applied reasoning and a clear sense of trade-offs, with thinner evidence on production ownership.",
  detailed_overview:
    "The candidate moved quickly from an ambiguous prompt to a workable decomposition, and was explicit about what they would measure before committing to an approach.\n\nEvidence on operating systems in production was thinner: the examples given were largely from pre-launch work.",
  // A placeholder evaluation so the Regenerate button renders and can be
  // measured as a touch target.
  is_placeholder: true,
  is_mock_data: false,
  recording_url: undefined, // the "no recording available" branch
  override_suggested: true,
  override_reason: "Panel agreed the take-home compensates for the thin production evidence.",
  scores: [
    {
      criterion_key: "problem_solving",
      criterion_label: LONG_LABEL, // long enough to force the truncate/wrap decision
      score: 4,
      weight: 3,
      overview: "Decomposed the problem before reaching for a model.",
      strengths: ["Named the failure mode before the happy path", "Asked what the metric actually rewards"],
      improvements: ["Did not state a rollback plan"],
    },
    {
      criterion_key: "production_ownership",
      criterion_label: "Production ownership",
      score: 2,
      weight: 2,
      overview: "Examples were mostly pre-launch.",
      strengths: [],
      improvements: ["No on-call or incident examples", "Monitoring described only in general terms"],
    },
    {
      criterion_key: "communication",
      criterion_label: "Communication",
      // No score at all -- the "No evidence" branch.
      weight: 1,
      strengths: [],
      improvements: [],
    },
  ],
  integrity_events: [
    { event_type: "FULLSCREEN_EXITED", phase: "VERBAL", metadata: {}, video_offset_seconds: 92 },
    { event_type: "MULTIPLE_FACES_DETECTED", phase: "VERBAL", metadata: {}, video_offset_seconds: 418 },
    { event_type: "TAB_HIDDEN", metadata: {} }, // no offset -- renders "—"
  ],
  question_records: [
    {
      question_id: "q-bg-1",
      title: "Walk me through the recommendation system on your CV",
      text: "Your CV mentions a recommender serving 2M users. What was yours specifically?",
      competency: "Background",
      order_index: 0,
      outcome: "COMPLETED",
      subsection: "BACKGROUND",
      hints_used: 0,
      followups_used: 1,
      clarifications_used: 0,
    },
    {
      question_id: "q-1",
      title: "Designing an evaluation set when labels are expensive",
      text: "How would you decide what to label first?",
      competency: "Problem solving",
      order_index: 1,
      outcome: "COMPLETED",
      hints_used: 2,
      followups_used: 3,
      clarifications_used: 1,
    },
    {
      question_id: "q-2",
      // No title -- exercises the "Question {{index}}" fallback.
      competency: "Production ownership",
      order_index: 2,
      outcome: "TIME_EXPIRED",
      hints_used: 1,
      followups_used: 0,
      clarifications_used: 0,
    },
    {
      question_id: "q-3",
      title: "Skipped question",
      order_index: 3,
      outcome: "SKIPPED",
      hints_used: 0,
      followups_used: 0,
      clarifications_used: 0,
    },
  ],
  technical_submission: {
    language: "Python",
    code: "def rank(candidates, scores):\n    # deliberately wide line so the <pre> gets something to scroll: ------------------------------\n    return sorted(candidates, key=lambda c: scores.get(c.id, 0.0), reverse=True)\n",
  },
  transcript: [
    { speaker: "agent", text: "Thanks for joining. Could you start by telling me about the recommender on your CV?" },
    { speaker: "candidate", text: "Sure — I owned the candidate-generation half of it for about eighteen months." },
    { speaker: "agent", text: "What would you measure before changing the ranking model?" },
  ],
};

/**
 * Installs the stub once and never removes it, deliberately.
 *
 * The first attempt restored `window.fetch` in an effect cleanup, and under
 * StrictMode that breaks: React mounts, runs effects, runs cleanups, then
 * runs effects again — and child effects run BEFORE parent effects, so the
 * page re-fetched against the restored real `fetch` (observed: a live
 * request to :8001, ERR_CONNECTION_REFUSED, and a permanent skeleton). A
 * parent effect cannot win that race, so there is nothing to restore.
 *
 * Safe because the match is pinned to this fixture's own session id: a real
 * candidate result, which can never be `sess-preview`, is never intercepted.
 */
let installed = false;

function installStub(): true {
  if (installed) return true;
  installed = true;
  const original = window.fetch;
  window.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    if (url.includes(`/admin/interviews/${FIXTURE.session_id}/result`)) {
      return new Response(JSON.stringify(FIXTURE), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    return original(input as RequestInfo, init);
  }) as typeof window.fetch;
  return true;
}

export default function CandidateResultPreview() {
  // Installed during the first render, not in an effect: the page's own
  // fetch runs in ITS effect, which fires after this component renders, so
  // by then the stub is already in place.
  useState(installStub);

  return (
    <AdminShell onSignOut={() => {}}>
      <div
        data-responsive-ignore
        className="border-b bg-amber-50 px-4 py-1.5 text-xs text-amber-800 -mx-4 -mt-4 mb-6 sm:-mx-6 sm:-mt-6 lg:-mx-8 lg:-mt-8"
      >
        <strong>DEV PREVIEW</strong> — the real CandidateResultPage over a stubbed GET (no backend, no saves).
      </div>

      {/* Rendered directly: the dev route carries :jobId/:sessionId itself,
          so the page's own useParams resolves from the app router. A nested
          MemoryRouter was the first attempt and React Router v7 rejects it
          outright -- "You cannot render a <Router> inside another <Router>". */}
      <CandidateResultPage />
    </AdminShell>
  );
}
