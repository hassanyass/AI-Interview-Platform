import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { adminClient, type EvaluationDetail } from "../../api/adminClient";
import { ArrowLeft, User, Mail, Calendar, Settings2, Loader2, Save } from "lucide-react";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/Card";
import { useTranslation } from "react-i18next";

export default function CandidateResultPage() {
  const { t } = useTranslation();
  const { jobId, sessionId } = useParams<{ jobId: string; sessionId: string }>();
  const [result, setResult] = useState<EvaluationDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  // Override State
  const [isOverrideMode, setIsOverrideMode] = useState(false);
  const [overrideValue, setOverrideValue] = useState<"computed" | "true" | "false">("computed");
  const [overrideReason, setOverrideReason] = useState("");
  const [isSavingOverride, setIsSavingOverride] = useState(false);

  const fetchResult = async () => {
    if (!sessionId) return;
    setIsLoading(true);
    setError("");
    try {
      const data = await adminClient.getCandidateResult(sessionId);
      setResult(data);
      if (data.override_suggested !== undefined && data.override_suggested !== null) {
        setOverrideValue(data.override_suggested ? "true" : "false");
        setOverrideReason(data.override_reason || "");
      } else {
        setOverrideValue("computed");
        setOverrideReason("");
      }
    } catch (err: any) {
      setError(err.message || "Failed to load candidate result");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchResult();
  }, [sessionId]);

  const handleSaveOverride = async () => {
    if (!sessionId) return;
    setIsSavingOverride(true);
    try {
      const valueToSave = overrideValue === "computed" ? null : overrideValue === "true";
      await adminClient.setSuggestedOverride(sessionId, valueToSave, overrideValue !== "computed" ? overrideReason : undefined);
      await fetchResult();
      setIsOverrideMode(false);
    } catch (err: any) {
      setError(err.message || "Failed to save override");
    } finally {
      setIsSavingOverride(false);
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="h-8 bg-muted rounded w-1/4"></div>
        <div className="h-48 bg-card rounded-lg border border-border"></div>
        <div className="h-96 bg-card rounded-lg border border-border"></div>
      </div>
    );
  }

  if (error || !result) {
    return (
      <div className="bg-red-500/10 border border-red-500/20 text-red-500 p-4 rounded-md flex flex-col gap-4 items-start">
        <p>{error || "An unexpected error occurred."}</p>
        <Button 
          variant="outline"
          onClick={fetchResult}
          className="bg-white/50 text-red-600 border-red-200 hover:bg-white"
        >
          Retry
        </Button>
      </div>
    );
  }

  const computedSuggested = result.recommendation === "Hire" || result.recommendation === "Strong Hire";
  const finalSuggested = result.override_suggested !== undefined && result.override_suggested !== null 
    ? result.override_suggested 
    : computedSuggested;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link to={`/admin/jobs/${jobId}/results`}>
          <Button variant="outline" className="p-2 h-10 w-10">
            <ArrowLeft className="h-5 w-5" />
          </Button>
        </Link>
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Candidate Result</h1>
          <p className="text-muted-foreground mt-1">{result.job_title || "Unknown Job"}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Info & Final Decision */}
        <div className="space-y-6">
          <Card className="border-border shadow-sm">
            <CardHeader className="bg-muted/50 border-b border-border py-4">
              <CardTitle className="text-lg">Candidate Details</CardTitle>
            </CardHeader>
            <CardContent className="p-6 space-y-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-muted rounded-full text-muted-foreground">
                  <User className="h-5 w-5" />
                </div>
                <div>
                  <p className="text-sm font-medium text-foreground">{result.candidate_name || "Unknown Candidate"}</p>
                  <p className="text-xs text-muted-foreground">Name</p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <div className="p-2 bg-muted rounded-full text-muted-foreground">
                  <Mail className="h-5 w-5" />
                </div>
                <div>
                  <p className="text-sm font-medium text-foreground">{result.candidate_email || "No email provided"}</p>
                  <p className="text-xs text-muted-foreground">Email</p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <div className="p-2 bg-muted rounded-full text-muted-foreground">
                  <Calendar className="h-5 w-5" />
                </div>
                <div>
                  <p className="text-sm font-medium text-foreground">
                    {result.completed_at ? new Date(result.completed_at).toLocaleString() : "Pending"}
                  </p>
                  <p className="text-xs text-muted-foreground">Completed At</p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="border-border shadow-sm">
            <CardHeader className="bg-muted/50 border-b border-border py-4 flex flex-row items-center justify-between">
              <CardTitle className="text-lg">Outcome & Override</CardTitle>
              {!isOverrideMode && (
                <Button variant="ghost" size="sm" onClick={() => setIsOverrideMode(true)}>
                  <Settings2 className="h-4 w-4 mr-2" /> Edit Override
                </Button>
              )}
            </CardHeader>
            <CardContent className="p-6">
              {isOverrideMode ? (
                <div className="space-y-4">
                  <div className="space-y-2">
                    <label className="text-sm font-medium">Suggested Next Step</label>
                    <select 
                      className="flex h-10 w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                      value={overrideValue}
                      onChange={(e) => setOverrideValue(e.target.value as any)}
                    >
                      <option value="computed">Use AI Computed Result ({computedSuggested ? "Yes" : "No"})</option>
                      <option value="true">Force Override: Yes</option>
                      <option value="false">Force Override: No</option>
                    </select>
                  </div>
                  
                  {overrideValue !== "computed" && (
                    <div className="space-y-2">
                      <label className="text-sm font-medium">Override Reason (Required)</label>
                      <textarea
                        className="flex min-h-[80px] w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                        placeholder="Why are you overriding the AI's suggestion?"
                        value={overrideReason}
                        onChange={(e) => setOverrideReason(e.target.value)}
                      />
                    </div>
                  )}

                  <div className="flex items-center gap-2 pt-2">
                    <Button 
                      onClick={handleSaveOverride} 
                      disabled={isSavingOverride || (overrideValue !== "computed" && !overrideReason.trim())}
                      className="w-full"
                    >
                      {isSavingOverride ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Save className="h-4 w-4 mr-2" />}
                      Save Changes
                    </Button>
                    <Button variant="outline" onClick={() => {
                      setIsOverrideMode(false);
                      setOverrideValue(result.override_suggested !== undefined && result.override_suggested !== null ? (result.override_suggested ? "true" : "false") : "computed");
                      setOverrideReason(result.override_reason || "");
                    }}>
                      Cancel
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="space-y-6">
                  <div className="flex flex-col items-center justify-center py-4 text-center">
                    <p className="text-sm text-muted-foreground mb-2">Final Suggestion</p>
                    <Badge variant={finalSuggested ? "success" : "secondary"} className="text-lg py-1 px-4">
                      {finalSuggested ? "Proceed to Next Step" : "Do Not Proceed"}
                    </Badge>
                    
                    {result.override_suggested !== undefined && result.override_suggested !== null && (
                      <div className="mt-4 p-3 bg-blue-500/10 border border-blue-500/20 rounded-md text-left w-full">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-xs px-1.5 py-0.5 rounded-sm bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400 font-medium tracking-wide">
                            MANUAL OVERRIDE
                          </span>
                        </div>
                        <p className="text-sm text-foreground mt-2 font-medium">Reason:</p>
                        <p className="text-sm text-muted-foreground mt-1">{result.override_reason}</p>
                      </div>
                    )}
                  </div>
                  
                  <div className="pt-4 border-t border-border grid grid-cols-2 gap-4 text-center">
                    <div>
                      <p className="text-xs text-muted-foreground">AI Score</p>
                      <p className="text-xl font-bold text-foreground mt-1">{result.overall_score || 0}/5</p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground">AI Recommendation</p>
                      <div className="mt-1">
                        <Badge variant={result.recommendation === "Hire" ? "success" : result.recommendation === "Strong Hire" ? "success" : "secondary"}>
                          {result.recommendation || "N/A"}
                        </Badge>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Right Column: AI Analysis & Breakdown */}
        <div className="lg:col-span-2 space-y-6">
          <Card className="border-border shadow-sm">
            <CardHeader className="bg-muted/50 border-b border-border py-4">
              <CardTitle className="text-lg">AI Summary</CardTitle>
            </CardHeader>
            <CardContent className="p-6">
              <p className="text-foreground leading-relaxed">{result.summary || "No summary available."}</p>
              
              {result.detailed_overview && (
                <div className="mt-4 pt-4 border-t border-border">
                  <h4 className="text-sm font-semibold mb-2">Detailed Overview</h4>
                  <p className="text-sm text-muted-foreground leading-relaxed">{result.detailed_overview}</p>
                </div>
              )}
            </CardContent>
          </Card>

          <h3 className="text-xl font-bold tracking-tight pt-4">Criteria Breakdown</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {result.scores.map((score, idx) => (
              <Card key={idx} className="border-border shadow-sm">
                <CardContent className="p-5">
                  <div className="flex items-center justify-between mb-3">
                    <h4 className="font-semibold text-foreground">{score.criterion_label || score.criterion_key}</h4>
                    {score.score !== undefined && (
                      <Badge variant="outline" className="text-sm font-bold bg-muted/50">
                        {score.score}/5
                      </Badge>
                    )}
                  </div>
                  <p className="text-sm text-muted-foreground mb-4 line-clamp-3">{score.overview}</p>
                  
                  {score.strengths.length > 0 && (
                    <div className="mb-3">
                      <p className="text-xs font-semibold text-green-600 dark:text-green-400 uppercase tracking-wider mb-1">Strengths</p>
                      <ul className="list-disc list-inside text-sm text-foreground space-y-1">
                        {score.strengths.map((s, i) => <li key={i} className="line-clamp-1">{s}</li>)}
                      </ul>
                    </div>
                  )}
                  
                  {score.improvements.length > 0 && (
                    <div>
                      <p className="text-xs font-semibold text-amber-600 dark:text-amber-400 uppercase tracking-wider mb-1">Areas for Improvement</p>
                      <ul className="list-disc list-inside text-sm text-foreground space-y-1">
                        {score.improvements.map((s, i) => <li key={i} className="line-clamp-1">{s}</li>)}
                      </ul>
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
            {result.scores.length === 0 && (
              <div className="col-span-full p-8 text-center text-muted-foreground border rounded-lg border-dashed">
                No scores available.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
