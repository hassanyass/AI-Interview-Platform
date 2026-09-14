import { useState, useEffect } from "react";
import { adminClient, type AssessmentCriterion, type CriterionWeightSetting } from "../../api/adminClient";
import { Card, CardContent } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { Loader2, CheckSquare, Square, Save } from "lucide-react";
import { useTranslation } from "react-i18next";

interface CriteriaEditorProps {
  jobId: string;
  status: string;
  onRefresh?: () => Promise<void>;
}

/** Local per-criterion editable state: enabled + weight together, since the
 * scoring-mechanism upgrade needs both to travel through the same save. */
interface CriterionState {
  enabled: boolean;
  weight: number;
}

function stateMapFrom(data: AssessmentCriterion[]): Record<string, CriterionState> {
  const map: Record<string, CriterionState> = {};
  for (const c of data) {
    map[c.key] = { enabled: c.enabled, weight: c.weight };
  }
  return map;
}

export default function CriteriaEditor({ jobId, status, onRefresh }: CriteriaEditorProps) {
  const { t } = useTranslation();
  const [criteria, setCriteria] = useState<AssessmentCriterion[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState("");
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [localState, setLocalState] = useState<Record<string, CriterionState>>({});

  // Computed up front (not after the isLoading early-return below) so
  // handleSave's closure never reads a binding declared later in this
  // function -- works fine as originally written too (TS/React don't
  // actually invoke handleSave until well after this render completes),
  // but this ordering is the safer one to refactor around later.
  const behavioralCriteria = criteria.filter(c => c.kind === "behavioral");
  const otherCriteria = criteria.filter(c => c.kind !== "behavioral");
  const isDraft = status === "DRAFT";

  const fetchCriteria = async () => {
    setIsLoading(true);
    setError("");
    try {
      const data = await adminClient.getJobCriteria(jobId);
      setCriteria(data);
      setLocalState(stateMapFrom(data));
    } catch (err: any) {
      setError(err.message || "Failed to load criteria");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchCriteria();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  const handleToggle = (key: string) => {
    if (status !== "DRAFT") return;
    setSaveSuccess(false);
    setLocalState(prev => ({
      ...prev,
      [key]: { ...prev[key], enabled: !prev[key]?.enabled },
    }));
  };

  const handleWeightChange = (key: string, weight: number) => {
    if (status !== "DRAFT") return;
    setSaveSuccess(false);
    setLocalState(prev => ({
      ...prev,
      [key]: { ...prev[key], weight },
    }));
  };

  const handleSave = async () => {
    if (status !== "DRAFT") return;
    setIsSaving(true);
    setError("");
    setSaveSuccess(false);
    try {
      // Only behavioral criteria go through this save -- "otherCriteria"
      // (kind !== "behavioral") are auto-managed and never toggled here,
      // matching update_job_criteria's own behavioral-only scope.
      const settings: CriterionWeightSetting[] = behavioralCriteria.map(c => ({
        key: c.key,
        enabled: localState[c.key]?.enabled ?? false,
        weight: localState[c.key]?.weight ?? 5,
      }));
      const updated = await adminClient.updateJobCriteria(jobId, settings);
      setCriteria(updated);
      setLocalState(stateMapFrom(updated));
      setSaveSuccess(true);
      if (onRefresh) {
        await onRefresh();
      }
    } catch (err: any) {
      setError(err.message || "Failed to save criteria");
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return (
      <Card className="border-border shadow-sm">
        <div className="bg-muted/50 p-4 border-b border-border flex items-center justify-between">
          <h3 className="font-semibold flex items-center gap-2">Assessment Criteria</h3>
        </div>
        <CardContent className="p-6">
          <div className="flex items-center justify-center p-4">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        </CardContent>
      </Card>
    );
  }

  // Check if current local state differs from server state (enabled OR weight).
  const hasChanges = behavioralCriteria.some(c => {
    const local = localState[c.key];
    return !local || local.enabled !== c.enabled || local.weight !== c.weight;
  });

  return (
    <Card className="border-border shadow-sm mt-6">
      <div className="bg-muted/50 p-4 border-b border-border flex items-center justify-between">
        <div className="flex flex-col">
          <h3 className="font-semibold text-lg text-foreground">Assessment Criteria</h3>
          <p className="text-sm text-muted-foreground mt-1">
            Configure the behavioral dimensions the AI will evaluate, and how much each counts toward the criteria-weighted score.
          </p>
        </div>
        {isDraft && (
          <Button
            onClick={handleSave}
            disabled={isSaving || !hasChanges}
            size="sm"
            className="flex items-center gap-2"
          >
            {isSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            Save Criteria
          </Button>
        )}
      </div>

      <CardContent className="p-0">
        {error && (
          <div className="p-4 bg-red-500/10 border-b border-red-500/20 text-red-500 text-sm">
            {error}
          </div>
        )}

        {saveSuccess && !hasChanges && (
          <div className="p-3 bg-green-500/10 border-b border-green-500/20 text-green-600 text-sm flex items-center justify-center">
            Criteria saved successfully.
          </div>
        )}

        <div className="p-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {behavioralCriteria.map(criterion => {
              const local = localState[criterion.key] ?? { enabled: criterion.enabled, weight: criterion.weight };
              const isEnabled = local.enabled;
              return (
                <div
                  key={criterion.key}
                  className={`border rounded-lg p-4 transition-colors ${
                    isDraft ? 'hover:border-primary/50' : 'opacity-80'
                  } ${isEnabled ? 'border-primary/50 bg-primary/5' : 'border-border bg-card'}`}
                >
                  <div
                    className={`flex items-start gap-3 ${isDraft ? 'cursor-pointer' : ''}`}
                    onClick={() => handleToggle(criterion.key)}
                  >
                    <div className="mt-0.5 text-primary shrink-0">
                      {isEnabled ? (
                        <CheckSquare className="h-5 w-5" />
                      ) : (
                        <Square className="h-5 w-5 text-muted-foreground" />
                      )}
                    </div>
                    <div className="min-w-0">
                      <h4 className="font-medium text-foreground">{criterion.label}</h4>
                      {criterion.guidance_text && (
                        <p className="text-sm text-muted-foreground mt-1 line-clamp-2">
                          {criterion.guidance_text}
                        </p>
                      )}
                    </div>
                  </div>

                  {/* Scoring-mechanism upgrade: weight only shown/meaningful
                      once a criterion is enabled -- moot when off. Integer
                      steps only (matches the DB's INTEGER column), and the
                      actual number is always shown, not left to be inferred
                      from the slider's fill level. */}
                  {isEnabled && (
                    <div
                      className="mt-3 pt-3 border-t border-border/60 flex items-center gap-3"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <label htmlFor={`weight-${criterion.key}`} className="text-xs font-medium text-muted-foreground shrink-0">
                        Weight
                      </label>
                      <input
                        id={`weight-${criterion.key}`}
                        type="range"
                        min={1}
                        max={10}
                        step={1}
                        value={local.weight}
                        disabled={!isDraft}
                        onChange={(e) => handleWeightChange(criterion.key, parseInt(e.target.value, 10))}
                        className="flex-1 accent-primary disabled:opacity-50"
                      />
                      <span className="text-sm font-semibold text-foreground tabular-nums w-6 text-end shrink-0">
                        {local.weight}
                      </span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {behavioralCriteria.length === 0 && (
            <div className="text-center p-8 text-muted-foreground border rounded-lg border-dashed">
              No behavioral criteria found.
            </div>
          )}

          {otherCriteria.length > 0 && (
            <div className="mt-8">
              <h4 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3">
                Content-Specific Criteria (Auto-managed)
              </h4>
              <div className="flex flex-wrap gap-2">
                {otherCriteria.map(c => (
                  <div key={c.key} className="px-3 py-1.5 bg-muted rounded-md text-sm text-muted-foreground border border-border">
                    {c.label}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
