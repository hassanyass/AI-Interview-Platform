import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { ArrowLeft, CheckCircle2, Clock, RotateCw, SkipForward } from "lucide-react";
import { getInterviewResult } from "../../services/api/interviews";
import type { InterviewResultResponse } from "../../types/api";
import { AppShell } from "../../components/layout/AppShell";
import { Button } from "../../components/ui/Button";

export default function FinalResult() {
  const { id } = useParams();
  const [result, setResult] = useState<InterviewResultResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function fetchResult() {
      if (!id) return;
      try {
        const data = await getInterviewResult(id);
        setResult(data);
      } catch (err: any) {
        setError(err.message || "Failed to load result.");
      } finally {
        setLoading(false);
      }
    }
    fetchResult();
  }, [id]);

  if (loading) {
    return (
      <AppShell>
        <div className="flex justify-center py-20 text-muted-foreground animate-pulse">
          Retrieving assessment report...
        </div>
      </AppShell>
    );
  }

  if (error || !result) {
    return (
      <AppShell>
        <div className="max-w-2xl mx-auto py-12">
          <div className="rounded-xl border border-destructive/20 bg-destructive/5 p-8 text-center space-y-4">
            <h2 className="text-lg font-medium text-destructive">Result Unavailable</h2>
            <p className="text-muted-foreground">{error}</p>
            <div className="pt-4">
              <Link to="/dashboard">
                <Button variant="outline">Return to Dashboard</Button>
              </Link>
            </div>
          </div>
        </div>
      </AppShell>
    );
  }

  const { final_result } = result;
  const interviewDate = "Recent Assessment";

  return (
    <AppShell>
      <div className="max-w-3xl mx-auto py-8">
        <Link to="/dashboard" className="text-sm font-medium text-muted-foreground hover:text-foreground inline-flex items-center mb-10 transition-colors">
          <ArrowLeft className="mr-2 h-4 w-4" /> Back to Dashboard
        </Link>

        {/* Header section */}
        <div className="space-y-4 mb-12">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-50 text-emerald-700 text-sm font-medium mb-2 border border-emerald-200">
            <CheckCircle2 className="h-4 w-4" /> Interview Completed
          </div>
          <h1 className="text-3xl font-semibold tracking-tight text-foreground">
            {final_result.role || "Backend Engineer"}
          </h1>
          <div className="flex items-center gap-3 text-muted-foreground text-lg">
            <span className="capitalize">{final_result.level || "Mid-Level"}</span>
            <span className="h-1 w-1 rounded-full bg-border" />
            <span>{interviewDate}</span>
          </div>
        </div>

        {/* Summary section */}
        <div className="space-y-4 mb-12">
          <h2 className="text-lg font-medium tracking-tight text-foreground">Interview Overview</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="rounded-xl border border-border bg-card p-5">
              <div className="text-sm font-medium text-muted-foreground mb-1">Questions</div>
              <div className="text-3xl font-medium">{final_result.total_questions}</div>
            </div>
            <div className="rounded-xl border border-border bg-card p-5">
              <div className="text-sm font-medium text-muted-foreground mb-1">Completed</div>
              <div className="text-3xl font-medium text-emerald-600">{final_result.completed}</div>
            </div>
            <div className="rounded-xl border border-border bg-card p-5">
              <div className="text-sm font-medium text-muted-foreground mb-1">Skipped</div>
              <div className="text-3xl font-medium text-muted-foreground">{final_result.skipped}</div>
            </div>
            <div className="rounded-xl border border-border bg-card p-5">
              <div className="text-sm font-medium text-muted-foreground mb-1">Changed</div>
              <div className="text-3xl font-medium text-muted-foreground">{final_result.changed}</div>
            </div>
          </div>
        </div>

        {/* Timeline section */}
        <div className="space-y-4">
          <h2 className="text-lg font-medium tracking-tight text-foreground">Assessment Log</h2>
          <div className="rounded-xl border border-border bg-card">
            {final_result.question_records.length === 0 ? (
              <div className="p-8 text-center text-muted-foreground">
                No questions were attempted during this session.
              </div>
            ) : (
              <div className="divide-y divide-border">
                {final_result.question_records.map((record, index) => {
                  let Icon = Clock;
                  let colorClass = "text-muted-foreground";
                  
                  if (record.outcome === "COMPLETED") {
                    Icon = CheckCircle2;
                    colorClass = "text-emerald-600";
                  } else if (record.outcome === "SKIPPED") {
                    Icon = SkipForward;
                  } else if (record.outcome === "CHANGED") {
                    Icon = RotateCw;
                  }

                  return (
                    <div key={record.question_id || index} className="p-6 flex sm:items-center flex-col sm:flex-row gap-4 justify-between hover:bg-muted/30 transition-colors">
                      <div className="flex items-start sm:items-center gap-4">
                        <div className="flex-shrink-0 h-10 w-10 rounded-full bg-muted flex items-center justify-center text-sm font-medium text-muted-foreground">
                          {String(index + 1).padStart(2, '0')}
                        </div>
                        <div>
                          <div className="font-medium text-foreground">
                            {/* Assuming title is available, else generic fallback */}
                            Question {index + 1}
                          </div>
                          <div className="text-sm text-muted-foreground mt-0.5">
                            Technical Assessment
                          </div>
                        </div>
                      </div>
                      
                      <div className={`flex items-center gap-2 text-sm font-medium ${colorClass} capitalize bg-background px-3 py-1.5 rounded-lg border border-border sm:border-transparent`}>
                        <Icon className="h-4 w-4" />
                        {record.outcome.toLowerCase()}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
