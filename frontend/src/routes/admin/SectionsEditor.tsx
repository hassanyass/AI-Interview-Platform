import { useState, useEffect } from "react";
import { adminClient, type JobDetail } from "../../api/adminClient";
import { Plus, Trash2, ArrowUp, ArrowDown, Code2, MessageSquare, ListTodo, Loader2, ChevronDown, ChevronUp, Clock } from "lucide-react";
import QuestionEditor from "./QuestionEditor";
import { Card, CardContent } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { useTranslation } from "react-i18next";

interface SectionsEditorProps {
  jobId: string;
  definition: NonNullable<JobDetail['definition']>;
  onRefresh: () => Promise<void>;
  status: string;
}

// 9G: CODING/MCQ section creation + question authoring enabled here.
// 2026-08-26: publish_job's backend 409 stopgap (admin.py) is now also
// lifted, for both types, per explicit user go-ahead — Part 1's
// controller.py/main.py bridging fix, the 9H candidate submission UI, and
// this authoring UI are all built and live-verified end-to-end (see
// docs/CURRENT_DECISIONS.md / docs/phase9-architecture.md's 9H section).
// A published CODING/MCQ job now works for real, not just under a
// temporary bypass.
const SECTION_TYPES = [
  { value: "VERBAL", label: "Verbal", icon: MessageSquare, comingSoon: false },
  { value: "CODING", label: "Coding", icon: Code2, comingSoon: false },
  { value: "MCQ", label: "Multiple Choice", icon: ListTodo, comingSoon: false },
];

export default function SectionsEditor({ definition, onRefresh, status }: SectionsEditorProps) {
  const { t } = useTranslation();
  const [isAdding, setIsAdding] = useState(false);
  const [selectedType, setSelectedType] = useState("");
  const [loadingAction, setLoadingAction] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [expandedSectionId, setExpandedSectionId] = useState<string | null>(null);

  // Per-section time budget: sectionId -> { draftMinutes, saveStatus }
  const [timeBudgets, setTimeBudgets] = useState<Record<string, { draft: string; status: "idle" | "saving" | "saved" | "error" }>>();

  const sections = [...definition.sections].sort((a, b) => a.order_index - b.order_index);
  const existingTypes = new Set(sections.map((s) => s.section_type));
  const availableTypes = SECTION_TYPES.filter((t) => !existingTypes.has(t.value));
  // Only these can actually be selected/submitted — comingSoon types still
  // render in the dropdown (disabled, labeled) so HR can see what's on the
  // way, but never become the live selectedType.
  const selectableTypes = availableTypes.filter((t) => !t.comingSoon);

  // Keep selectedType in sync with selectableTypes so the dropdown's visible
  // selection and the value actually submitted can never diverge. Without
  // this, selectedType could stay pointed at a type that's no longer
  // available (e.g. right after it was just added, or on first mount when
  // the default SECTION_TYPES[0] is already taken) while the <select>
  // silently falls back to displaying its first real option — submitting
  // whatever selectedType still holds, not what's on screen. Excluding
  // comingSoon types here too means selectedType can never silently land on
  // CODING/MCQ even though they're still visible in the list.
  useEffect(() => {
    if (!selectableTypes.some((t) => t.value === selectedType)) {
      setSelectedType(selectableTypes[0]?.value ?? "");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAdding, selectableTypes.map((t) => t.value).join(",")]);

  // Sync draft time budgets from server definition (on load or refresh)
  useEffect(() => {
    const initial: Record<string, { draft: string; status: "idle" | "saving" | "saved" | "error" }> = {};
    for (const section of definition.sections) {
      const existing = (timeBudgets ?? {})[section.id];
      initial[section.id] = existing ?? {
        draft: section.config?.time_budget_minutes != null ? String(section.config.time_budget_minutes) : "",
        status: "idle",
      };
    }
    setTimeBudgets(initial);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [definition.sections.map((s) => s.id + (s.config?.time_budget_minutes ?? "")).join(",")]);

  const handleTimeBudgetChange = (sectionId: string, value: string) => {
    setTimeBudgets((prev) => ({
      ...(prev ?? {}),
      [sectionId]: { draft: value, status: "idle" },
    }));
  };

  const handleTimeBudgetSave = async (sectionId: string) => {
    const entry = (timeBudgets ?? {})[sectionId];
    if (!entry) return;
    const parsed = entry.draft.trim() === "" ? null : parseInt(entry.draft, 10);
    if (parsed !== null && (isNaN(parsed) || parsed < 1 || parsed > 300)) return;

    setTimeBudgets((prev) => ({
      ...(prev ?? {}),
      [sectionId]: { ...(prev ?? {})[sectionId], status: "saving" },
    }));
    try {
      const section = sections.find((s) => s.id === sectionId);
      const currentConfig = section?.config ?? {};
      await adminClient.updateSection(sectionId, {
        config: { ...currentConfig, time_budget_minutes: parsed },
      });
      setTimeBudgets((prev) => ({
        ...(prev ?? {}),
        [sectionId]: { ...(prev ?? {})[sectionId], status: "saved" },
      }));
      setTimeout(() => {
        setTimeBudgets((prev) => ({
          ...(prev ?? {}),
          [sectionId]: { ...(prev ?? {})[sectionId], status: "idle" },
        }));
      }, 2000);
      await onRefresh();
    } catch {
      setTimeBudgets((prev) => ({
        ...(prev ?? {}),
        [sectionId]: { ...(prev ?? {})[sectionId], status: "error" },
      }));
      setTimeout(() => {
        setTimeBudgets((prev) => ({
          ...(prev ?? {}),
          [sectionId]: { ...(prev ?? {})[sectionId], status: "idle" },
        }));
      }, 3000);
    }
  };

  const isDraft = status === "DRAFT";

  const handleAddSection = async () => {
    if (!selectedType || !selectableTypes.some((t) => t.value === selectedType)) return;
    setLoadingAction("add");
    setError("");
    try {
      const nextOrder = sections.length > 0 ? sections[sections.length - 1].order_index + 1 : 0;
      await adminClient.createSection({
        definition_id: definition.id,
        section_type: selectedType,
        order_index: nextOrder,
      });
      await onRefresh();
      setIsAdding(false);
      // selectedType resyncs automatically via the useEffect above once
      // availableTypes updates from the refreshed definition.
    } catch (err: any) {
      if (err.message?.includes("409")) {
        setError(t('sectionsEditor.alreadyExists'));
      } else {
        setError(err.message || t('sectionsEditor.failedToAdd'));
      }
    } finally {
      setLoadingAction(null);
    }
  };

  const handleDelete = async (sectionId: string) => {
    if (!confirm(t('sectionsEditor.deleteConfirm'))) return;
    setLoadingAction(`delete-${sectionId}`);
    setError("");
    try {
      await adminClient.deleteSection(sectionId);
      await onRefresh();
    } catch (err: any) {
      setError(err.message || t('sectionsEditor.failedToDelete'));
    } finally {
      setLoadingAction(null);
    }
  };

  const handleSwap = async (indexA: number, indexB: number) => {
    const sectionA = sections[indexA];
    const sectionB = sections[indexB];
    if (!sectionA || !sectionB) return;

    setLoadingAction(`swap-${sectionA.id}`);
    setError("");
    
    // We do sequential PATCH requests.
    try {
      // 1st request
      await adminClient.updateSection(sectionA.id, { order_index: sectionB.order_index });
      
      try {
        // 2nd request
        await adminClient.updateSection(sectionB.id, { order_index: sectionA.order_index });
        await onRefresh();
      } catch (err2: any) {
        // Minimum acceptable behavior: on ANY failure in the swap, immediately refetch 
        // the real job state from the backend and re-render from that, plus show an inline error.
        setError(t('sectionsEditor.failedToReorderFull'));
        await onRefresh();
      }
    } catch (err: any) {
      setError(err.message || t('sectionsEditor.failedToReorder'));
    } finally {
      setLoadingAction(null);
    }
  };

  return (
    <div className="space-y-4 mt-8">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">{t('sectionsEditor.title')}</h2>
        {isDraft && (
          <Button
            variant="secondary"
            onClick={() => setIsAdding(true)}
            disabled={availableTypes.length === 0 || isAdding || loadingAction !== null}
            className="inline-flex items-center gap-2"
          >
            <Plus className="h-4 w-4" />
            <span>{t('sectionsEditor.addSection')}</span>
          </Button>
        )}
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 text-red-500 p-3 rounded-md text-sm">
          {error}
        </div>
      )}

      {isAdding && (
        <Card>
          <CardContent className="p-4 flex flex-col sm:flex-row sm:items-end space-y-4 sm:space-y-0 sm:gap-4">
            <div className="flex-1 space-y-1">
              <label className="text-sm font-medium">{t('sectionsEditor.sectionType')}</label>
              <select
                value={selectedType}
                onChange={(e) => setSelectedType(e.target.value)}
                className="w-full bg-background border border-input rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
              >
                {availableTypes.map((type) => (
                  <option
                    key={type.value}
                    value={type.value}
                    disabled={type.comingSoon}
                    title={type.comingSoon ? t('sectionsEditor.comingSoonHover') : undefined}
                  >
                    {t(`sectionsEditor.${type.value.toLowerCase()}`)}{type.comingSoon ? t('sectionsEditor.comingSoon') : ""}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex items-center gap-2">
              <Button
                onClick={handleAddSection}
                disabled={loadingAction === "add" || !selectableTypes.some((t) => t.value === selectedType)}
                className="flex items-center gap-2"
              >
                {loadingAction === "add" && <Loader2 className="h-4 w-4 animate-spin" />}
                <span>{t('sectionsEditor.add')}</span>
              </Button>
              <Button
                variant="outline"
                onClick={() => setIsAdding(false)}
                disabled={loadingAction === "add"}
              >
                {t('sectionsEditor.cancel')}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {sections.length === 0 ? (
        <Card className="text-center py-8 border-dashed">
          <CardContent className="pt-6">
            <p className="text-muted-foreground text-sm">{t('sectionsEditor.noSections')}</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {sections.map((section, index) => {
            const typeConfig = SECTION_TYPES.find((t) => t.value === section.section_type) || SECTION_TYPES[0];
            const Icon = typeConfig.icon;
            
            const isExpanded = expandedSectionId === section.id;
            const questionCount = section.questions?.length ?? 0;

            return (
              <Card
                key={section.id}
                className="hover:border-primary/30 transition-colors"
              >
                <CardContent className="p-4 m-0">
                  <div className="flex items-center justify-between">
                    <button
                      onClick={() => setExpandedSectionId(isExpanded ? null : section.id)}
                      className="flex items-center gap-4 text-start flex-1 min-w-0"
                    >
                      <div className="bg-primary/10 p-2 rounded-md text-primary shrink-0">
                        <Icon className="h-5 w-5" />
                      </div>
                      <div>
                        <h3 className="font-semibold text-foreground">{t(`sectionsEditor.${typeConfig.value.toLowerCase()}`)}</h3>
                        <p className="text-xs text-muted-foreground">
                          {t('sectionsEditor.order')}: {section.order_index} &middot; {questionCount} {t('sectionsEditor.questions')}
                        </p>
                      </div>
                      {isExpanded ? (
                        <ChevronUp className="h-4 w-4 text-muted-foreground ms-2" />
                      ) : (
                        <ChevronDown className="h-4 w-4 text-muted-foreground ms-2" />
                      )}
                    </button>

                    {isDraft && (
                      <div className="flex items-center gap-1 shrink-0">
                        <button
                          onClick={() => handleSwap(index, index - 1)}
                          disabled={index === 0 || loadingAction !== null}
                          className="p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground rounded-md disabled:opacity-30 disabled:hover:bg-transparent"
                          title={t('sectionsEditor.moveUp')}
                        >
                          <ArrowUp className="h-4 w-4" />
                        </button>
                        <button
                          onClick={() => handleSwap(index, index + 1)}
                          disabled={index === sections.length - 1 || loadingAction !== null}
                          className="p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground rounded-md disabled:opacity-30 disabled:hover:bg-transparent"
                          title={t('sectionsEditor.moveDown')}
                        >
                          <ArrowDown className="h-4 w-4" />
                        </button>
                        <div className="w-px h-6 bg-border mx-2"></div>
                        <button
                          onClick={() => handleDelete(section.id)}
                          disabled={loadingAction !== null}
                          className="p-1.5 text-red-500 hover:bg-red-500/10 rounded-md transition-colors disabled:opacity-30"
                          title={t('sectionsEditor.deleteSection')}
                        >
                          {loadingAction === `delete-${section.id}` ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <Trash2 className="h-4 w-4" />
                          )}
                        </button>
                      </div>
                    )}
                  </div>

                  {isExpanded && (
                    <div className="pt-4 mt-4 border-t border-border space-y-5">
                      {/* Time budget input — DRAFT only, saved on blur */}
                      {isDraft && (
                        <div className="flex items-center gap-3">
                          <Clock className="h-4 w-4 shrink-0 text-muted-foreground" />
                          <label htmlFor={`time-budget-${section.id}`} className="text-sm font-medium text-foreground whitespace-nowrap">
                            {t('sectionsEditor.timeBudget')}
                          </label>
                          <input
                            id={`time-budget-${section.id}`}
                            type="number"
                            min={1}
                            max={300}
                            placeholder={t('sectionsEditor.timeBudgetPlaceholder')}
                            value={(timeBudgets ?? {})[section.id]?.draft ?? ""}
                            onChange={(e) => handleTimeBudgetChange(section.id, e.target.value)}
                            onBlur={() => handleTimeBudgetSave(section.id)}
                            disabled={loadingAction !== null || (timeBudgets ?? {})[section.id]?.status === "saving"}
                            className="w-24 rounded-md border border-input bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 disabled:opacity-60"
                          />
                          {(timeBudgets ?? {})[section.id]?.status === "saving" && (
                            <span className="text-xs text-muted-foreground flex items-center gap-1">
                              <Loader2 className="h-3 w-3 animate-spin" />
                              {t('sectionsEditor.savingBudget')}
                            </span>
                          )}
                          {(timeBudgets ?? {})[section.id]?.status === "saved" && (
                            <span className="text-xs text-green-600 font-medium">{t('sectionsEditor.timeBudgetSaved')}</span>
                          )}
                          {(timeBudgets ?? {})[section.id]?.status === "error" && (
                            <span className="text-xs text-destructive font-medium">{t('sectionsEditor.timeBudgetFailed')}</span>
                          )}
                        </div>
                      )}

                      <QuestionEditor
                        sectionId={section.id}
                        sectionType={section.section_type}
                        questions={section.questions ?? []}
                        onRefresh={onRefresh}
                        status={status}
                      />
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
