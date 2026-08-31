import { useState, useEffect } from "react";
import { adminClient, type AssessmentCriterion } from "../../api/adminClient";
import { Card, CardContent } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { Loader2, CheckSquare, Square, Save } from "lucide-react";
import { useTranslation } from "react-i18next";

interface CriteriaEditorProps {
  jobId: string;
  status: string;
  onRefresh?: () => Promise<void>;
}

export default function CriteriaEditor({ jobId, status, onRefresh }: CriteriaEditorProps) {
  const { t } = useTranslation();
  const [criteria, setCriteria] = useState<AssessmentCriterion[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState("");
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [localEnabledKeys, setLocalEnabledKeys] = useState<Set<string>>(new Set());

  const fetchCriteria = async () => {
    setIsLoading(true);
    setError("");
    try {
      const data = await adminClient.getJobCriteria(jobId);
      setCriteria(data);
      setLocalEnabledKeys(new Set(data.filter(c => c.enabled).map(c => c.key)));
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
    setLocalEnabledKeys(prev => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  const handleSave = async () => {
    if (status !== "DRAFT") return;
    setIsSaving(true);
    setError("");
    setSaveSuccess(false);
    try {
      const updated = await adminClient.updateJobCriteria(jobId, Array.from(localEnabledKeys));
      setCriteria(updated);
      setLocalEnabledKeys(new Set(updated.filter(c => c.enabled).map(c => c.key)));
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

  const behavioralCriteria = criteria.filter(c => c.kind === "behavioral");
  const otherCriteria = criteria.filter(c => c.kind !== "behavioral");
  const isDraft = status === "DRAFT";

  // Check if current local state differs from server state
  const serverEnabledKeys = new Set(criteria.filter(c => c.enabled).map(c => c.key));
  const hasChanges = 
    localEnabledKeys.size !== serverEnabledKeys.size || 
    Array.from(localEnabledKeys).some(k => !serverEnabledKeys.has(k));

  return (
    <Card className="border-border shadow-sm mt-6">
      <div className="bg-muted/50 p-4 border-b border-border flex items-center justify-between">
        <div className="flex flex-col">
          <h3 className="font-semibold text-lg text-foreground">Assessment Criteria</h3>
          <p className="text-sm text-muted-foreground mt-1">
            Configure the behavioral dimensions the AI will evaluate.
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
              const isEnabled = localEnabledKeys.has(criterion.key);
              return (
                <div 
                  key={criterion.key}
                  className={`border rounded-lg p-4 transition-colors ${
                    isDraft ? 'cursor-pointer hover:border-primary/50' : 'opacity-80'
                  } ${isEnabled ? 'border-primary/50 bg-primary/5' : 'border-border bg-card'}`}
                  onClick={() => handleToggle(criterion.key)}
                >
                  <div className="flex items-start gap-3">
                    <div className="mt-0.5 text-primary shrink-0">
                      {isEnabled ? (
                        <CheckSquare className="h-5 w-5" />
                      ) : (
                        <Square className="h-5 w-5 text-muted-foreground" />
                      )}
                    </div>
                    <div>
                      <h4 className="font-medium text-foreground">{criterion.label}</h4>
                      {criterion.guidance_text && (
                        <p className="text-sm text-muted-foreground mt-1 line-clamp-2">
                          {criterion.guidance_text}
                        </p>
                      )}
                    </div>
                  </div>
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
