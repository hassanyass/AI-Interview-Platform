import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { adminClient, type JobResultsResponse } from "../../api/adminClient";
import { ArrowLeft, ShieldAlert, RefreshCw } from "lucide-react";
import { Button } from "../../components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/Card";
import { AiCoreIcon } from "../../components/ui/AiCoreIcon";
import ConfirmDeleteModal from "./ConfirmDeleteModal";
import { CandidatesTable } from "./JobResultsTable";

/**
 * Design pass (2026-09-03, e& brand-alignment audit): the previous stat
 * row gave five equally-weighted tiles a different color/icon each --
 * exactly what the e& guide's Section 7 names as the thing to avoid
 * ("10 cards / 10 colors / 10 icons... instead, create stronger
 * hierarchy"). Total/Completed/In Progress are plain FACTS (a count,
 * nothing more) -- grouped into one quiet strip, no icons, no per-item
 * color. Suggested and Flagged are the two real SIGNALS on this page (one
 * AI-derived, one an integrity alert) -- each gets its own card and is
 * the only place color still does real work: the AI-core motif (Section
 * 12) for the AI judgment, e& Red for the one thing that genuinely
 * warrants a second look.
 *
 * Responsive plan R3-A (docs/responsive-design-plan.md §3): the header no
 * longer forces Back + title + Refresh onto one line, the candidates table
 * moved to `JobResultsTable.tsx` (ResponsiveTable -- see that file for why
 * the action column was the problem), and every string on this page is an
 * i18n key so the page is legible in the RTL half of the matrix.
 */

/**
 * The page header, exported so /dev/results-preview renders the REAL one
 * rather than a static copy of it (AdminPreview.tsx keeps copies of the
 * R1/R2 headers and they can drift; this cannot).
 *
 * R3-A: one row at `sm` and up -- the desktop anatomy is unchanged -- and
 * below it the identity stacks over the Refresh button instead of squeezing
 * a truncated title between two buttons at 375px.
 */
export function JobResultsHeader({
  jobId,
  jobTitle,
  isRefreshing,
  onRefresh,
}: {
  jobId: string | undefined;
  jobTitle: string;
  isRefreshing: boolean;
  onRefresh: () => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex min-w-0 flex-col items-start gap-3 sm:flex-row sm:items-center sm:gap-4">
        <Link to={`/admin/jobs/${jobId}`} className="inline-flex sm:shrink-0">
          <Button variant="outline" size="sm" className="h-11 shrink-0 gap-1.5 lg:h-10">
            {/* e& guide Section 16 (RTL requirements): "Mirrored
                directional icons" -- confirmed via a real RTL render
                that a static ArrowLeft points the wrong way once the
                page flows right-to-left; "back" should point toward
                where the reader came from, which is the right in RTL. */}
            <ArrowLeft className="h-4 w-4 rtl:rotate-180" /> {t("jobResults.backToJob")}
          </Button>
        </Link>
        <div className="min-w-0">
          {/* Wraps on phone, truncates with a tooltip from `sm` -- a job
              title is a title, so truncation is allowed, but only where
              the full value is still reachable. */}
          <h1 className="text-2xl font-bold tracking-tight sm:truncate sm:text-3xl" title={jobTitle}>
            {t("jobResults.title", { job: jobTitle })}
          </h1>
          <p className="text-muted-foreground mt-1">{t("jobResults.desc")}</p>
        </div>
      </div>
      <Button
        variant="outline"
        size="sm"
        className="h-11 w-full shrink-0 gap-1.5 sm:w-auto lg:h-10"
        onClick={onRefresh}
        disabled={isRefreshing}
      >
        <RefreshCw className={`h-4 w-4 ${isRefreshing ? "animate-spin" : ""}`} />
        {isRefreshing ? t("jobResults.refreshing") : t("jobResults.refresh")}
      </Button>
    </div>
  );
}

export default function JobResultsPage() {
  const { t } = useTranslation();
  const { id } = useParams<{ id: string }>();
  const [results, setResults] = useState<JobResultsResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState("");
  // Candidate deletion (2026-09-14): which session the confirm modal is
  // currently asking about; null = closed. Scoped to the SESSION (this
  // job's result row), not the person -- see the backend endpoint's
  // docstring for why the CandidateProfile is deliberately left intact.
  const [pendingDelete, setPendingDelete] = useState<{ sessionId: string; name: string } | null>(null);

  const fetchResults = async (isManualRefresh = false) => {
    if (!id) return;
    if (isManualRefresh) setIsRefreshing(true);
    else setIsLoading(true);
    setError("");
    try {
      const data = await adminClient.getJobResults(id);
      setResults(data);
    } catch (err: any) {
      setError(err.message || t("jobResults.failedToLoad"));
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    fetchResults();
  }, [id]);

  const handleConfirmDelete = async () => {
    if (!pendingDelete) return;
    try {
      await adminClient.deleteInterviewSession(pendingDelete.sessionId);
      setPendingDelete(null);
      await fetchResults(true);
    } catch (err: any) {
      setPendingDelete(null);
      setError(err.message || t("jobResults.failedToDelete"));
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="h-8 bg-muted rounded w-1/4"></div>
        <div className="grid grid-cols-1 lg:grid-cols-[2fr_1fr_1fr] gap-4">
          <div className="h-24 bg-card rounded-lg"></div>
          <div className="h-24 bg-card rounded-lg"></div>
          <div className="h-24 bg-card rounded-lg"></div>
        </div>
        <div className="h-64 bg-card border border-border rounded-lg"></div>
      </div>
    );
  }

  if (error || !results) {
    return (
      <div className="bg-destructive/10 border border-destructive/20 text-destructive p-4 rounded-md flex flex-col gap-4 items-start">
        <p>{error || t("jobResults.unexpectedError")}</p>
        <Button
          variant="outline"
          onClick={() => fetchResults()}
          className="h-11 bg-white/50 text-destructive border-destructive/20 hover:bg-white lg:h-10"
        >
          {t("jobResults.retry")}
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <JobResultsHeader
        jobId={id}
        jobTitle={results.job_title}
        isRefreshing={isRefreshing}
        onRefresh={() => fetchResults(true)}
      />

      {/* Aggregate stats -- see the module docstring above for the
          hierarchy reasoning (facts grouped and quiet; the two real
          signals separated and the only color left on this row). */}
      <div className="grid grid-cols-1 lg:grid-cols-[2fr_1fr_1fr] gap-4">
        <Card className="border-border shadow-sm">
          <CardContent className="p-4 sm:p-6 grid grid-cols-3 divide-x divide-border rtl:divide-x-reverse">
            <div className="text-center px-1 sm:px-2">
              <h4 className="text-2xl font-bold text-foreground tabular-nums">{results.total_candidates}</h4>
              <p className="text-xs font-medium text-muted-foreground mt-1">{t("jobResults.totalCandidates")}</p>
            </div>
            <div className="text-center px-1 sm:px-2">
              <h4 className="text-2xl font-bold text-foreground tabular-nums">{results.completed_count}</h4>
              <p className="text-xs font-medium text-muted-foreground mt-1">{t("jobResults.completed")}</p>
            </div>
            <div className="text-center px-1 sm:px-2">
              <h4 className="text-2xl font-bold text-foreground tabular-nums">{results.in_progress_count}</h4>
              <p className="text-xs font-medium text-muted-foreground mt-1">{t("jobResults.inProgress")}</p>
            </div>
          </CardContent>
        </Card>

        <Card className="border-border shadow-sm bg-secondary/5">
          <CardContent className="p-6 flex items-center gap-3">
            <AiCoreIcon className="h-6 w-6" />
            <div className="min-w-0">
              <p className="text-xs font-medium text-muted-foreground">{t("jobResults.suggestedForNextStep")}</p>
              <h4 className="text-2xl font-bold text-secondary tabular-nums">{results.suggested_count}</h4>
            </div>
          </CardContent>
        </Card>

        <Card className="border-border shadow-sm">
          <CardContent className="p-6 flex items-center gap-3">
            <ShieldAlert className="h-6 w-6 shrink-0 text-primary" />
            <div className="min-w-0">
              <p className="text-xs font-medium text-muted-foreground">{t("jobResults.flaggedForReview")}</p>
              <h4 className="text-2xl font-bold text-primary tabular-nums">{results.flagged_count}</h4>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Candidate List */}
      <Card className="border-border shadow-sm">
        <CardHeader className="bg-muted/50 border-b border-border">
          <CardTitle className="text-lg">{t("jobResults.candidates")}</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <CandidatesTable jobId={id} candidates={results.candidates} onRequestDelete={setPendingDelete} />
        </CardContent>
      </Card>

      <ConfirmDeleteModal
        isOpen={pendingDelete !== null}
        onClose={() => setPendingDelete(null)}
        onConfirm={handleConfirmDelete}
        title={t("jobResults.deleteModal.title")}
        description={t("jobResults.deleteModal.description", {
          name: pendingDelete?.name ?? t("jobResults.thisCandidate"),
        })}
        confirmLabel={t("jobResults.deleteModal.confirm")}
      />
    </div>
  );
}
