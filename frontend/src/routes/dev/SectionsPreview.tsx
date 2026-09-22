import SectionsEditor from "../admin/SectionsEditor";
import type { JobDetail } from "../../api/adminClient";

/**
 * DEV-ONLY visual harness for the section setup panel (registered in
 * App.tsx only under import.meta.env.DEV). Renders SectionsEditor with a
 * mock definition -- a VERBAL section with the background on, a CODING
 * section still missing its budget, an MCQ section with nothing yet -- so
 * the collapsed summaries and the expanded panel can be reviewed without
 * an admin sign-in. Saves hit the real API and will simply fail here.
 */
export default function SectionsPreview() {
  const q = (id: string, title: string, text: string, order_index: number, competency?: string) => ({
    id, section_id: "s", order_index, title, text, competency, eval_criteria: null, config: null, created_at: "",
  });
  const definition = {
    id: "def-preview", job_id: "job-preview", duration_minutes: 30, is_public: false, public_access_token: null, created_at: "",
    sections: [
      { id: "verbal", definition_id: "def-preview", section_type: "VERBAL", order_index: 0, created_at: "",
        config: { time_budget_minutes: 20, include_background: true, background_question_count: 3, background_time_budget_minutes: 5 },
        questions: [q("v1", "Ownership", "Tell me about a system you owned end to end and what you would change about it.", 0, "ownership"),
                    q("v2", "Conflict", "Describe a technical disagreement with a colleague and how it was resolved.", 1, "conflict")] },
      { id: "coding", definition_id: "def-preview", section_type: "CODING", order_index: 1, created_at: "", config: null,
        questions: [q("c1", "Rate limiter", "Implement a sliding-window rate limiter.", 0)] },
      { id: "mcq", definition_id: "def-preview", section_type: "MCQ", order_index: 2, created_at: "", config: { time_budget_minutes: 10 }, questions: [] },
    ],
  } as unknown as NonNullable<JobDetail["definition"]>;

  return (
    <div className="min-h-screen bg-background text-foreground">
      <div data-responsive-ignore className="border-b bg-amber-50 px-4 py-1.5 text-xs text-amber-800"><strong>DEV PREVIEW</strong> — section setup panel with mock data (saves will fail).</div>
      <div className="mx-auto max-w-4xl p-6">
        <SectionsEditor jobId="job-preview" definition={definition} onRefresh={async () => {}} status="DRAFT" />
      </div>
    </div>
  );
}
