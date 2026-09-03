import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { adminClient, type JobResultsResponse } from "../../api/adminClient";
import { ArrowLeft, ShieldAlert, RefreshCw } from "lucide-react";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/Card";
import { AiCoreIcon } from "../../components/ui/AiCoreIcon";
import { useTranslation } from "react-i18next";

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
 */

/** Score visualization per the guide's own words ("Use mostly Grey base,
 * Red progress, Maroon for high-level summaries... avoid rainbow
 * dashboards"): Hire is the high-value outcome (maroon), No Hire is the
 * one signal worth flagging (red), Consider/Mixed is genuinely neutral
 * (grey) -- not a three-color success/warning/destructive traffic light. */
function recommendationTone(recommendation: string | undefined): { text: string; dot: string } {
  if (recommendation === "Hire") return { text: "text-secondary", dot: "bg-secondary" };
  if (recommendation === "No Hire") return { text: "text-primary", dot: "bg-primary" };
  return { text: "text-muted-foreground", dot: "bg-muted-foreground" };
}

export default function JobResultsPage() {
  const { t } = useTranslation();
  const { id } = useParams<{ id: string }>();
  const [results, setResults] = useState<JobResultsResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState("");

  const fetchResults = async (isManualRefresh = false) => {
    if (!id) return;
    if (isManualRefresh) setIsRefreshing(true);
    else setIsLoading(true);
    setError("");
    try {
      const data = await adminClient.getJobResults(id);
      setResults(data);
    } catch (err: any) {
      setError(err.message || "Failed to load results");
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    fetchResults();
  }, [id]);

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
        <p>{error || "An unexpected error occurred."}</p>
        <Button
          variant="outline"
          onClick={() => fetchResults()}
          className="bg-white/50 text-destructive border-destructive/20 hover:bg-white"
        >
          Retry
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-4 min-w-0">
          <Link to={`/admin/jobs/${id}`}>
            <Button variant="outline" size="sm" className="shrink-0 gap-1.5">
              {/* e& guide Section 16 (RTL requirements): "Mirrored
                  directional icons" -- confirmed via a real RTL render
                  that a static ArrowLeft points the wrong way once the
                  page flows right-to-left; "back" should point toward
                  where the reader came from, which is the right in RTL. */}
              <ArrowLeft className="h-4 w-4 rtl:rotate-180" /> Back to Job
            </Button>
          </Link>
          <div className="min-w-0">
            <h1 className="text-3xl font-bold tracking-tight truncate">{results.job_title} - Results</h1>
            <p className="text-muted-foreground mt-1">Aggregate dashboard and candidate tracking</p>
          </div>
        </div>
        <Button
          variant="outline"
          size="sm"
          className="shrink-0 gap-1.5"
          onClick={() => fetchResults(true)}
          disabled={isRefreshing}
        >
          <RefreshCw className={`h-4 w-4 ${isRefreshing ? "animate-spin" : ""}`} />
          {isRefreshing ? "Refreshing…" : "Refresh"}
        </Button>
      </div>

      {/* Aggregate stats -- see the module docstring above for the
          hierarchy reasoning (facts grouped and quiet; the two real
          signals separated and the only color left on this row). */}
      <div className="grid grid-cols-1 lg:grid-cols-[2fr_1fr_1fr] gap-4">
        <Card className="border-border shadow-sm">
          <CardContent className="p-6 grid grid-cols-3 divide-x divide-border rtl:divide-x-reverse">
            <div className="text-center px-2">
              <h4 className="text-2xl font-bold text-foreground">{results.total_candidates}</h4>
              <p className="text-xs font-medium text-muted-foreground mt-1">Total Candidates</p>
            </div>
            <div className="text-center px-2">
              <h4 className="text-2xl font-bold text-foreground">{results.completed_count}</h4>
              <p className="text-xs font-medium text-muted-foreground mt-1">Completed</p>
            </div>
            <div className="text-center px-2">
              <h4 className="text-2xl font-bold text-foreground">{results.in_progress_count}</h4>
              <p className="text-xs font-medium text-muted-foreground mt-1">In Progress</p>
            </div>
          </CardContent>
        </Card>

        <Card className="border-border shadow-sm bg-secondary/5">
          <CardContent className="p-6 flex items-center gap-3">
            <AiCoreIcon className="h-6 w-6" />
            <div>
              <p className="text-xs font-medium text-muted-foreground">Suggested for Next Step</p>
              <h4 className="text-2xl font-bold text-secondary">{results.suggested_count}</h4>
            </div>
          </CardContent>
        </Card>

        <Card className="border-border shadow-sm">
          <CardContent className="p-6 flex items-center gap-3">
            <ShieldAlert className="h-6 w-6 shrink-0 text-primary" />
            <div>
              <p className="text-xs font-medium text-muted-foreground">Flagged for Review</p>
              <h4 className="text-2xl font-bold text-primary">{results.flagged_count}</h4>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Candidate List */}
      <Card className="border-border shadow-sm">
        <CardHeader className="bg-muted/50 border-b border-border">
          <CardTitle className="text-lg">Candidates</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {results.candidates.length === 0 ? (
            <div className="p-8 text-center text-muted-foreground">
              No candidates have started this interview yet.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-left">
                <thead className="text-xs text-muted-foreground uppercase bg-muted/20 border-b border-border">
                  <tr>
                    <th className="px-6 py-3">Candidate</th>
                    <th className="px-6 py-3">Status</th>
                    <th className="px-6 py-3">Score</th>
                    <th className="px-6 py-3">Evidence</th>
                    <th className="px-6 py-3">Suggested</th>
                    <th className="px-6 py-3">Integrity</th>
                    <th className="px-6 py-3 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {results.candidates.map((cand) => {
                    const tone = recommendationTone(cand.recommendation);
                    return (
                    <tr key={cand.session_id} className="hover:bg-muted/10 transition-colors">
                      <td className="px-6 py-4">
                        <div className="font-medium text-foreground">
                          {cand.candidate_name || "Unknown"}
                        </div>
                        <div className="text-xs text-muted-foreground mt-0.5">
                          {cand.candidate_email || "No email"}
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <Badge variant={cand.status === "COMPLETED" ? "success" : "warning"}>
                          {cand.status}
                        </Badge>
                      </td>
                      <td className="px-6 py-4">
                        {cand.overall_score !== undefined && cand.overall_score !== null ? (
                          <div className="flex items-center gap-2">
                            <span className="font-medium">{cand.overall_score}/5</span>
                            {/* Score visualization per the e& guide (Section
                                11): grey/red/maroon, not a green/amber/red
                                traffic light -- a dot + label reads calmer
                                than a filled pill for something that's
                                really a status word, not an alert. */}
                            <span className={`inline-flex items-center gap-1.5 text-xs font-semibold ${tone.text}`}>
                              <span className={`h-1.5 w-1.5 rounded-full ${tone.dot}`} />
                              {cand.recommendation}
                            </span>
                          </div>
                        ) : (
                          <span className="text-muted-foreground">-</span>
                        )}
                      </td>
                      <td className="px-6 py-4">
                        {cand.evidence_sufficiency !== undefined && cand.evidence_sufficiency !== null ? (
                          <span>{(cand.evidence_sufficiency * 100).toFixed(0)}%</span>
                        ) : (
                          <span className="text-muted-foreground">-</span>
                        )}
                      </td>
                      <td className="px-6 py-4">
                        {cand.status === "COMPLETED" || cand.status === "TERMINATED" ? (
                          <div className="flex items-center gap-2">
                            {cand.suggested ? (
                              <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-secondary">
                                <AiCoreIcon className="h-3 w-3" /> Yes
                              </span>
                            ) : (
                              <Badge variant="outline">No</Badge>
                            )}
                            {cand.override_suggested !== undefined && cand.override_suggested !== null && (
                              <span className="text-xs px-1.5 py-0.5 rounded-sm bg-primary/10 text-primary font-medium tracking-wide">
                                OVERRIDE
                              </span>
                            )}
                          </div>
                        ) : (
                          <span className="text-muted-foreground">-</span>
                        )}
                      </td>
                      <td className="px-6 py-4">
                        {cand.flagged_for_review ? (
                          <Badge variant="destructive" className="inline-flex items-center gap-1">
                            <ShieldAlert className="h-3 w-3" /> Flagged
                          </Badge>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                      <td className="px-6 py-4 text-right">
                        {cand.status === "COMPLETED" || cand.status === "TERMINATED" ? (
                          <Link to={`/admin/jobs/${id}/results/${cand.session_id}`}>
                            <Button size="sm" variant="outline">
                              View Result
                            </Button>
                          </Link>
                        ) : (
                          <span className="text-muted-foreground text-xs italic">Pending</span>
                        )}
                      </td>
                    </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
