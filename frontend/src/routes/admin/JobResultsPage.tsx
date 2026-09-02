import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { adminClient, type JobResultsResponse } from "../../api/adminClient";
import { ArrowLeft, Users, CheckCircle, Clock, AlertCircle, ShieldAlert } from "lucide-react";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/Card";
import { useTranslation } from "react-i18next";

export default function JobResultsPage() {
  const { t } = useTranslation();
  const { id } = useParams<{ id: string }>();
  const [results, setResults] = useState<JobResultsResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  const fetchResults = async () => {
    if (!id) return;
    setIsLoading(true);
    setError("");
    try {
      const data = await adminClient.getJobResults(id);
      setResults(data);
    } catch (err: any) {
      setError(err.message || "Failed to load results");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchResults();
  }, [id]);

  if (isLoading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="h-8 bg-muted rounded w-1/4"></div>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="h-24 bg-card rounded-lg"></div>
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
      <div className="bg-red-500/10 border border-red-500/20 text-red-500 p-4 rounded-md flex flex-col gap-4 items-start">
        <p>{error || "An unexpected error occurred."}</p>
        <Button 
          variant="outline"
          onClick={fetchResults}
          className="bg-white/50 text-red-600 border-red-200 hover:bg-white"
        >
          Retry
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link to={`/admin/jobs/${id}`}>
          <Button variant="outline" className="p-2 h-10 w-10">
            <ArrowLeft className="h-5 w-5" />
          </Button>
        </Link>
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{results.job_title} - Results</h1>
          <p className="text-muted-foreground mt-1">Aggregate dashboard and candidate tracking</p>
        </div>
      </div>

      {/* Aggregate Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-4">
        <Card className="border-border shadow-sm">
          <CardContent className="p-6 flex items-center gap-4">
            <div className="p-3 bg-primary/10 text-primary rounded-full">
              <Users className="h-6 w-6" />
            </div>
            <div>
              <p className="text-sm font-medium text-muted-foreground">Total Candidates</p>
              <h4 className="text-2xl font-bold">{results.total_candidates}</h4>
            </div>
          </CardContent>
        </Card>
        
        <Card className="border-border shadow-sm">
          <CardContent className="p-6 flex items-center gap-4">
            <div className="p-3 bg-success/10 text-success rounded-full">
              <CheckCircle className="h-6 w-6" />
            </div>
            <div>
              <p className="text-sm font-medium text-muted-foreground">Completed</p>
              <h4 className="text-2xl font-bold">{results.completed_count}</h4>
            </div>
          </CardContent>
        </Card>

        <Card className="border-border shadow-sm">
          <CardContent className="p-6 flex items-center gap-4">
            <div className="p-3 bg-warning/10 text-warning rounded-full">
              <Clock className="h-6 w-6" />
            </div>
            <div>
              <p className="text-sm font-medium text-muted-foreground">In Progress</p>
              <h4 className="text-2xl font-bold">{results.in_progress_count}</h4>
            </div>
          </CardContent>
        </Card>

        {/* Design audit (2026-09-01): was raw blue-500, unrelated to the e&
            palette entirely. Maroon (--secondary) is exactly what the brand
            guide names it for -- "high-value summary areas" -- which fits
            "candidates worth a second look" far better than an arbitrary
            info-blue that has no other meaning in this system. */}
        <Card className="border-border shadow-sm">
          <CardContent className="p-6 flex items-center gap-4">
            <div className="p-3 bg-secondary/10 text-secondary rounded-full">
              <AlertCircle className="h-6 w-6" />
            </div>
            <div>
              <p className="text-sm font-medium text-muted-foreground">Suggested for Next Step</p>
              <h4 className="text-2xl font-bold">{results.suggested_count}</h4>
            </div>
          </CardContent>
        </Card>

        {/* Aggregation/dashboard pass: Option A (confirmed) -- any
            integrity event at all flags a session, no severity/count
            threshold. Destructive tone, not warning: this is meant to
            stand out from the neutral status tiles above it as something
            that specifically warrants a second look, not just a workflow
            state. */}
        <Card className="border-border shadow-sm">
          <CardContent className="p-6 flex items-center gap-4">
            <div className="p-3 bg-destructive/10 text-destructive rounded-full">
              <ShieldAlert className="h-6 w-6" />
            </div>
            <div>
              <p className="text-sm font-medium text-muted-foreground">Flagged for Review</p>
              <h4 className="text-2xl font-bold">{results.flagged_count}</h4>
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
                  {results.candidates.map((cand) => (
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
                            {/* Design audit (2026-09-01): the "Strong Hire" branch below was
                                dead code -- Recommendation only ever contains "Hire" /
                                "Consider / Mixed" / "No Hire" per CURRENT_DECISIONS.md's
                                explicit enum. "Consider / Mixed" now maps to the (now-
                                corrected, AA-passing) warning tone instead of maroon --
                                maroon signals "premium/high-value" per the brand guide,
                                the wrong read for a mixed/uncertain recommendation. */}
                            <Badge variant={cand.recommendation === "Hire" ? "success" : cand.recommendation === "No Hire" ? "destructive" : "warning"}>
                              {cand.recommendation}
                            </Badge>
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
                            {/* "No" used to render in solid maroon (Badge's "secondary"
                                variant) -- maroon means "high-value" in this system, the
                                opposite of what a "not suggested" pill should signal.
                                "outline" is the correct neutral weight for this. */}
                            <Badge variant={cand.suggested ? "success" : "outline"}>
                              {cand.suggested ? "Yes" : "No"}
                            </Badge>
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
                        {/* Design audit (2026-09-01): this used to gate on
                            status === "COMPLETED" only. The session-finalization-
                            contract fix now guarantees an Evaluation row (real or a
                            clearly-labeled placeholder) for TERMINATED sessions too --
                            this was the highest-severity finding in the audit: a real,
                            viewable result that the UI made unreachable. DISCONNECTED
                            stays "Pending" -- it may still resume, and forcing a link
                            into a not-yet-finalized state isn't accurate. */}
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
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
