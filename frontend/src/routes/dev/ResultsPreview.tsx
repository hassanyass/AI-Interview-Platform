import { useState } from "react";
import { useTranslation } from "react-i18next";
import { AdminShell } from "../admin/AdminLayout";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/Card";
import { AiCoreIcon } from "../../components/ui/AiCoreIcon";
import { ShieldAlert } from "lucide-react";
import { JobResultsHeader } from "../admin/JobResultsPage";
import { CandidatesTable } from "../admin/JobResultsTable";
import type { JobCandidateRow } from "../../api/adminClient";

/**
 * DEV-ONLY visual harness for the admin RESULTS page (registered in App.tsx
 * only under import.meta.env.DEV), added in responsive plan R3-A because
 * neither results page is reachable by scripts/responsive-shots.cjs: both
 * need a signed-in admin AND a job with completed interviews, so R2-B had to
 * leave its equivalents to a manual pass. This route renders the REAL
 * `JobResultsHeader` and `CandidatesTable` against fixtures, makes no API
 * calls, and needs no session -- so the harness can prove the R3-A
 * acceptance checklist at all seven viewports in LTR and RTL.
 *
 * The rows deliberately cover the shapes that break layouts rather than a
 * tidy happy path: a name and an email long enough to force the truncate/
 * wrap decisions, a row with no email at all, an unfinished interview (no
 * score, "Pending" instead of a link), a flagged row, a manual override,
 * and a score with no evidence figure.
 */
const MOCK_CANDIDATES: JobCandidateRow[] = [
  {
    session_id: "sess-1",
    candidate_name: "Aisha Abdul-Rahman Al-Maktoum",
    candidate_email: "aisha.abdulrahman.almaktoum@averylongcorporatedomainname.example.com",
    status: "COMPLETED",
    overall_score: 4,
    weighted_score: 4.6,
    recommendation: "Hire",
    evidence_sufficiency: 0.92,
    suggested: true,
    flagged_for_review: false,
  },
  {
    session_id: "sess-2",
    candidate_name: "Tom Okafor",
    candidate_email: "tom@example.com",
    status: "COMPLETED",
    overall_score: 2,
    weighted_score: 1.4,
    recommendation: "No Hire",
    evidence_sufficiency: 0.44,
    suggested: false,
    override_suggested: true,
    flagged_for_review: true,
  },
  {
    session_id: "sess-3",
    // No name and no email: both cells fall back to their placeholders.
    status: "IN_PROGRESS",
    suggested: false,
    flagged_for_review: false,
  },
  {
    session_id: "sess-4",
    candidate_name: "Li Wei",
    candidate_email: "li.wei@example.com",
    status: "TERMINATED",
    overall_score: 3,
    // No weighted score: the ranking falls back to the holistic 3.
    recommendation: "Consider",
    // No evidence figure -- the cell must show "-" not "NaN%".
    suggested: false,
    flagged_for_review: true,
  },
  {
    session_id: "sess-5",
    candidate_name: "Fatima Noor",
    candidate_email: "fatima.noor@example.com",
    status: "DISCONNECTED",
    suggested: false,
    flagged_for_review: false,
  },
];

export default function ResultsPreview() {
  const { t } = useTranslation();
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [rows, setRows] = useState(MOCK_CANDIDATES);

  return (
    <AdminShell onSignOut={() => {}}>
      <div
        data-responsive-ignore
        className="border-b bg-amber-50 px-4 py-1.5 text-xs text-amber-800 -mx-4 -mt-4 mb-6 sm:-mx-6 sm:-mt-6 lg:-mx-8 lg:-mt-8"
      >
        <strong>DEV PREVIEW</strong> — job results with mock data (no saves, no API). Rows: {rows.length}
      </div>

      <div className="space-y-6">
        <JobResultsHeader
          jobId="job-preview"
          jobTitle="Senior Machine Learning Engineer, Data Platform & Applied Research"
          isRefreshing={isRefreshing}
          onRefresh={() => {
            setIsRefreshing(true);
            setTimeout(() => setIsRefreshing(false), 600);
          }}
        />

        {/* Same stat row as the page (facts strip + the two signal cards). */}
        <div className="grid grid-cols-1 lg:grid-cols-[2fr_1fr_1fr] gap-4">
          <Card className="border-border shadow-sm">
            <CardContent className="p-4 sm:p-6 grid grid-cols-3 divide-x divide-border rtl:divide-x-reverse">
              <div className="text-center px-1 sm:px-2">
                <h4 className="text-2xl font-bold text-foreground tabular-nums">128</h4>
                <p className="text-xs font-medium text-muted-foreground mt-1">{t("jobResults.totalCandidates")}</p>
              </div>
              <div className="text-center px-1 sm:px-2">
                <h4 className="text-2xl font-bold text-foreground tabular-nums">96</h4>
                <p className="text-xs font-medium text-muted-foreground mt-1">{t("jobResults.completed")}</p>
              </div>
              <div className="text-center px-1 sm:px-2">
                <h4 className="text-2xl font-bold text-foreground tabular-nums">12</h4>
                <p className="text-xs font-medium text-muted-foreground mt-1">{t("jobResults.inProgress")}</p>
              </div>
            </CardContent>
          </Card>

          <Card className="border-border shadow-sm bg-secondary/5">
            <CardContent className="p-6 flex items-center gap-3">
              <AiCoreIcon className="h-6 w-6" />
              <div className="min-w-0">
                <p className="text-xs font-medium text-muted-foreground">{t("jobResults.suggestedForNextStep")}</p>
                <h4 className="text-2xl font-bold text-secondary tabular-nums">31</h4>
              </div>
            </CardContent>
          </Card>

          <Card className="border-border shadow-sm">
            <CardContent className="p-6 flex items-center gap-3">
              <ShieldAlert className="h-6 w-6 shrink-0 text-primary" />
              <div className="min-w-0">
                <p className="text-xs font-medium text-muted-foreground">{t("jobResults.flaggedForReview")}</p>
                <h4 className="text-2xl font-bold text-primary tabular-nums">4</h4>
              </div>
            </CardContent>
          </Card>
        </div>

        <Card className="border-border shadow-sm">
          <CardHeader className="bg-muted/50 border-b border-border">
            <CardTitle className="text-lg">{t("jobResults.candidates")}</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {/* The real component. Delete removes the row locally so the
                action is exercisable at phone widths without a backend. */}
            <CandidatesTable
              jobId="job-preview"
              candidates={rows}
              onRequestDelete={({ sessionId }) => setRows((r) => r.filter((c) => c.session_id !== sessionId))}
            />
          </CardContent>
        </Card>

        {/* The empty state, which the page shows instead of the table. */}
        <Card className="border-border shadow-sm">
          <CardHeader className="bg-muted/50 border-b border-border">
            <CardTitle className="text-lg">{t("jobResults.candidates")} — empty state</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <CandidatesTable jobId="job-preview" candidates={[]} onRequestDelete={() => {}} />
          </CardContent>
        </Card>
      </div>
    </AdminShell>
  );
}
