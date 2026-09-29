import { AdminShell } from "../admin/AdminLayout";
import JobCreatePage from "../admin/JobCreatePage";

/**
 * DEV-ONLY visual harness for the job-create form (registered in App.tsx
 * only under import.meta.env.DEV), added in responsive plan R2-C.
 *
 * The simplest of the preview routes by far: `JobCreatePage` makes no API
 * call on mount — it only calls `createJob` on submit — so unlike
 * /dev/candidate-result-preview there is nothing to stub and no fixture to
 * invent. Rendering the real page inside the real shell is the whole file.
 *
 * Submitting it WILL attempt a real create against whatever backend the
 * environment points at, so the harness only ever renders and measures it.
 */
export default function JobCreatePreview() {
  return (
    <AdminShell onSignOut={() => {}}>
      <div
        data-responsive-ignore
        className="border-b bg-amber-50 px-4 py-1.5 text-xs text-amber-800 -mx-4 -mt-4 mb-6 sm:-mx-6 sm:-mt-6 lg:-mx-8 lg:-mt-8"
      >
        <strong>DEV PREVIEW</strong> — the real JobCreatePage. Do not submit: it would create a job for real.
      </div>
      <JobCreatePage />
    </AdminShell>
  );
}
