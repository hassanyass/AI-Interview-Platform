import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { ArrowLeft, CheckCircle2, Clock, RotateCw, SkipForward } from "lucide-react";
import { getInterviewResult, getInterviewSession } from "../../services/api/interviews";
import type { InterviewResultResponse, InterviewStatus } from "../../types/api";
import { AppShell } from "../../components/layout/AppShell";
import { Button } from "../../components/ui/Button";

export default function FinalResult() {
  const { id } = useParams();
  const [result, setResult] = useState<InterviewResultResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [processing, setProcessing] = useState(false);
  const [interviewStatus, setInterviewStatus] = useState<InterviewStatus | null>(null);

  useEffect(() => {
    async function fetchResult() {
      if (!id) return;
      const maxAttempts = 12;
      for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
        try {
          const data = await getInterviewResult(id);
          if (data.final_result) {
            setResult(data);
            setProcessing(false);
            setLoading(false);
            return;
          }
        } catch (err: any) {
          try {
            const session = await getInterviewSession(id);
            setInterviewStatus(session.status);
            if (session.status === "FAILED") {
              setError("The interview evaluation failed. Please contact support.");
              setLoading(false);
              return;
            }
            if (session.status === "IN_PROGRESS" || session.status === "DISCONNECTED" || err.message?.includes("still being persisted")) {
              setProcessing(true);
            } else if (attempt === maxAttempts - 1) {
              setError(err.message || "Failed to load result.");
              setLoading(false);
              return;
            }
          } catch {
            if (attempt === maxAttempts - 1) {
              setError(err.message || "Failed to load result.");
              setLoading(false);
              return;
            }
          }
        }
        await new Promise((resolve) => setTimeout(resolve, 2000));
      }
      setProcessing(true);
      setLoading(false);
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

  if (processing && !result && !error) {
    return (
      <AppShell>
        <div className="max-w-2xl mx-auto py-12">
          <div className="rounded-xl border border-border bg-card p-8 text-center space-y-4">
            <h2 className="text-lg font-medium">{interviewStatus === "IN_PROGRESS" ? "Interview still active" : "Evaluation in progress"}</h2>
            <p className="text-muted-foreground">{interviewStatus === "IN_PROGRESS" ? "The interview has not reached its completion state yet." : "Your interview is complete. The assessment report is still being finalized."}</p>
            <Link to="/dashboard"><Button variant="outline">Return to Dashboard</Button></Link>
          </div>
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
  const evaluation = final_result.evaluation;
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

        {final_result.evaluation_status === "FAILED" && (
          <div className="mb-8 rounded-xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-800">
            The interview was completed, but the detailed evaluation could not be generated. The transcript and submission below remain available.
          </div>
        )}

        {evaluation && (
          <div className="space-y-8 mb-12">
            <div className="rounded-xl border border-border bg-card p-6 space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 className="text-lg font-medium tracking-tight text-foreground">Overall Assessment</h2>
                <span className="rounded-md bg-emerald-50 px-3 py-1 text-sm font-semibold text-emerald-700">{evaluation.recommendation}</span>
              </div>
              {evaluation.overall_score != null && <p className="text-3xl font-semibold">{evaluation.overall_score}<span className="text-base font-normal text-muted-foreground"> / 5</span></p>}
              <p className="text-sm leading-7 text-muted-foreground">{evaluation.summary}</p>
              {evaluation.detailed_overview && <p className="whitespace-pre-line text-sm leading-7 text-muted-foreground">{evaluation.detailed_overview}</p>}
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              {([
                ["Communication", evaluation.communication],
                ["Technical understanding", evaluation.technical],
                ["Problem solving", evaluation.problem_solving],
                ["Technical submission", evaluation.technical_submission],
                ["Background", evaluation.background],
              ] as const).map(([label, category]) => (
                <section key={label} className="rounded-xl border border-border bg-card p-5 space-y-3">
                  <div className="flex items-center justify-between gap-3"><h3 className="font-medium">{label}</h3>{category.score != null && <span className="text-sm font-semibold text-primary">{category.score}/5</span>}</div>
                  <p className="text-sm leading-6 text-muted-foreground">{category.overview}</p>
                  {category.strengths.length > 0 && <div><p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Strengths</p><ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted-foreground">{category.strengths.map((item) => <li key={item}>{item}</li>)}</ul></div>}
                  {category.improvements.length > 0 && <div><p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Improve</p><ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted-foreground">{category.improvements.map((item) => <li key={item}>{item}</li>)}</ul></div>}
                </section>
              ))}
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <section className="rounded-xl border border-border bg-card p-5"><h3 className="font-medium">Strengths</h3>{evaluation.strengths.length ? <ul className="mt-3 list-disc space-y-2 pl-5 text-sm text-muted-foreground">{evaluation.strengths.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="mt-3 text-sm text-muted-foreground">No specific strengths were recorded.</p>}</section>
              <section className="rounded-xl border border-border bg-card p-5"><h3 className="font-medium">Areas for improvement</h3>{evaluation.areas_for_improvement.length ? <ul className="mt-3 list-disc space-y-2 pl-5 text-sm text-muted-foreground">{evaluation.areas_for_improvement.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="mt-3 text-sm text-muted-foreground">No specific improvement areas were recorded.</p>}</section>
            </div>
          </div>
        )}

        {final_result.technical_submission?.code && (
          <section className="space-y-4 mb-12"><h2 className="text-lg font-medium tracking-tight text-foreground">Technical Submission</h2><pre className="max-h-96 overflow-auto rounded-xl border border-border bg-[#20252b] p-5 text-sm leading-6 text-white">{final_result.technical_submission.code}</pre></section>
        )}

        {final_result.transcript && final_result.transcript.length > 0 && (
          <section className="space-y-4 mb-12"><h2 className="text-lg font-medium tracking-tight text-foreground">Interview Transcript</h2><div className="rounded-xl border border-border bg-card divide-y divide-border">{final_result.transcript.map((message, index) => <div key={`${message.speaker}-${index}`} className="p-5"><p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{message.speaker === "agent" ? "Interviewer" : "Candidate"}</p><p className="mt-2 whitespace-pre-line text-sm leading-7">{message.text}</p></div>)}</div></section>
        )}

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
