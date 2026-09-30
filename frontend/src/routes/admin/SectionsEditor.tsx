import { useState, useEffect } from "react";
import ConfirmDeleteModal from "./ConfirmDeleteModal";
import { adminClient, type JobDetail } from "../../api/adminClient";
import { Plus, Trash2, ArrowUp, ArrowDown, Code2, MessageSquare, ListTodo, Loader2, ChevronDown, ChevronUp, Clock, FileText } from "lucide-react";
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

// Verbal Background subsection (docs/verbal-background-subsection-plan.md
// §2/§10): HR's three per-section settings, stored in the same
// InterviewSection.config as time_budget_minutes and validated server-side
// by SectionConfig (background budget <= half the section budget). VERBAL
// sections only. Every change is saved immediately through the same
// updateSection({config}) path the time budget uses, merging over the
// current config so the two never clobber each other.
const BACKGROUND_COUNT_MIN = 1;
const BACKGROUND_COUNT_MAX = 6; // keep in step with backend BACKGROUND_QUESTION_COUNT_MAX
const BACKGROUND_COUNT_DEFAULT = 3;
const BACKGROUND_MINUTES_DEFAULT = 5;

// Section setup panel (docs/interview-start-ux-plan.md, step 1): every
// section type gets the same anatomy -- a summary strip, then titled rows
// (label + hint on the left, controls on the right): Timing, Background
// conversation (VERBAL only), Questions. One input width, one status
// style, one place to read the whole section.
const SETUP_INPUT = "w-24 rounded-md border border-input bg-background px-3 py-2 text-base tabular-nums focus:outline-none focus:ring-2 focus:ring-primary/50 disabled:opacity-60 sm:py-1.5 sm:text-sm";

function SetupRow({ icon, title, hint, status, children }: {
  icon: React.ReactNode; title: string; hint?: string;
  status?: "idle" | "saving" | "saved" | "error" | undefined; children: React.ReactNode;
}) {
  const { t } = useTranslation();
  return (
    <div className="grid gap-3 rounded-lg border border-border bg-background p-4 sm:grid-cols-[220px_minmax(0,1fr)] sm:gap-6">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">{icon}</span>
        <div className="min-w-0">
          <p className="text-sm font-semibold text-foreground">{title}</p>
          {hint && <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{hint}</p>}
        </div>
      </div>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          {children}
          {status === "saving" && (
            <span className="inline-flex items-center gap-1 text-xs text-muted-foreground"><Loader2 className="h-3 w-3 animate-spin" />{t('sectionsEditor.savingBudget')}</span>
          )}
          {status === "saved" && <span className="text-xs font-medium text-green-600">{t('sectionsEditor.timeBudgetSaved')}</span>}
          {status === "error" && <span className="text-xs font-medium text-destructive">{t('sectionsEditor.saveFailed')}</span>}
        </div>
      </div>
    </div>
  );
}

/** One line that reads the whole section, and whether it can publish. */
function useSectionSummary(section: NonNullable<JobDetail["definition"]>["sections"][number]) {
  const { t } = useTranslation();
  const cfg = section.config ?? {};
  const total: number | null = cfg.time_budget_minutes ?? null;
  const questions = section.questions?.length ?? 0;
  const typeLabel = t(`sectionsEditor.${section.section_type.toLowerCase()}`);
  const bgOn = section.section_type === "VERBAL" && cfg.include_background === true;
  const bgMin = cfg.background_time_budget_minutes ?? BACKGROUND_MINUTES_DEFAULT;
  const bgCount = cfg.background_question_count ?? BACKGROUND_COUNT_DEFAULT;
  const problems: string[] = [];
  if (total == null) problems.push(t('sectionsEditor.summaryNoBudget'));
  if (questions === 0) problems.push(t('sectionsEditor.summaryNoQuestions'));
  const questionsLabel = section.section_type === "VERBAL"
    ? t('sectionsEditor.summaryDiscussionQuestions', { count: questions })
    : t('sectionsEditor.summaryQuestions', { count: questions });
  // The card header already names the type; the line reads the numbers.
  let text: string;
  if (total == null) {
    text = t('sectionsEditor.summaryNoBudgetLine', { questions: questionsLabel });
  } else if (bgOn) {
    text = t('sectionsEditor.summaryWithBackground', { total, background: bgMin, bgCount, discussion: Math.max(0, total - bgMin), questions: questionsLabel });
  } else {
    text = t('sectionsEditor.summaryPlain', { total, questions: questionsLabel });
  }
  return { text, ok: problems.length === 0, problems, typeLabel };
}

function SectionSummaryLine({ section }: { section: NonNullable<JobDetail["definition"]>["sections"][number] }) {
  const { text, ok } = useSectionSummary(section);
  return <p className={`text-xs ${ok ? "text-muted-foreground" : "text-amber-700"}`}>{text}</p>;
}

function SectionSummaryStrip({ section }: { section: NonNullable<JobDetail["definition"]>["sections"][number] }) {
  const { t } = useTranslation();
  const { text, ok, problems } = useSectionSummary(section);
  return (
    <div className={`flex flex-wrap items-center justify-between gap-2 rounded-lg px-4 py-2.5 text-sm ${ok ? "bg-muted/50 text-foreground" : "bg-amber-50 text-amber-900 border border-amber-200"}`}>
      <span className="font-medium">{text}</span>
      <span className={`text-xs ${ok ? "text-muted-foreground" : "font-medium"}`}>
        {ok ? t('sectionsEditor.summaryReady') : problems.join(" · ")}
      </span>
    </div>
  );
}

interface BackgroundSettingsProps {
  section: NonNullable<JobDetail["definition"]>["sections"][number];
  disabled: boolean;
  onRefresh: () => Promise<void>;
}

function BackgroundSettings({ section, disabled, onRefresh }: BackgroundSettingsProps) {
  const { t } = useTranslation();
  const config = section.config ?? {};
  const enabled = config.include_background === true;
  const total: number | null = config.time_budget_minutes ?? null;
  const [count, setCount] = useState<string>(String(config.background_question_count ?? BACKGROUND_COUNT_DEFAULT));
  const [minutes, setMinutes] = useState<string>(String(config.background_time_budget_minutes ?? BACKGROUND_MINUTES_DEFAULT));
  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [localError, setLocalError] = useState<string>("");

  // Re-sync drafts when the server config changes (refresh after a save).
  useEffect(() => {
    setCount(String(config.background_question_count ?? BACKGROUND_COUNT_DEFAULT));
    setMinutes(String(config.background_time_budget_minutes ?? BACKGROUND_MINUTES_DEFAULT));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [section.id, config.background_question_count, config.background_time_budget_minutes]);

  const maxMinutes = total != null ? Math.floor(total / 2) : null;

  const save = async (patch: Record<string, unknown>) => {
    setStatus("saving");
    setLocalError("");
    try {
      await adminClient.updateSection(section.id, { config: { ...config, ...patch } });
      setStatus("saved");
      setTimeout(() => setStatus("idle"), 2000);
      await onRefresh();
    } catch {
      setStatus("error");
      setTimeout(() => setStatus("idle"), 3000);
    }
  };

  const handleToggle = (checked: boolean) => {
    void save({
      include_background: checked,
      background_question_count: config.background_question_count ?? BACKGROUND_COUNT_DEFAULT,
      background_time_budget_minutes: config.background_time_budget_minutes ?? BACKGROUND_MINUTES_DEFAULT,
    });
  };

  const commitCount = () => {
    const parsed = parseInt(count, 10);
    if (isNaN(parsed) || parsed < BACKGROUND_COUNT_MIN || parsed > BACKGROUND_COUNT_MAX) {
      setCount(String(config.background_question_count ?? BACKGROUND_COUNT_DEFAULT));
      return;
    }
    if (parsed !== config.background_question_count) void save({ background_question_count: parsed });
  };

  const commitMinutes = () => {
    const parsed = parseInt(minutes, 10);
    if (isNaN(parsed) || parsed < 1) {
      setMinutes(String(config.background_time_budget_minutes ?? BACKGROUND_MINUTES_DEFAULT));
      return;
    }
    // Same rule the backend enforces -- surface it here instead of a bare
    // "failed to save".
    if (maxMinutes != null && parsed > maxMinutes) {
      setLocalError(t("sectionsEditor.backgroundTooLong", { max: maxMinutes }));
      setMinutes(String(config.background_time_budget_minutes ?? BACKGROUND_MINUTES_DEFAULT));
      return;
    }
    if (parsed !== config.background_time_budget_minutes) void save({ background_time_budget_minutes: parsed });
  };


  return (
    <SetupRow
      icon={<FileText className="h-4 w-4" />}
      title={t("sectionsEditor.backgroundTitle")}
      hint={t("sectionsEditor.backgroundHelp")}
      status={status}
    >
      <label className="inline-flex cursor-pointer items-center gap-2 text-sm font-medium text-foreground">
        <input
          type="checkbox"
          role="switch"
          aria-checked={enabled}
          checked={enabled}
          disabled={disabled || status === "saving"}
          onChange={(e) => handleToggle(e.target.checked)}
          className="h-5 w-5 rounded border-input accent-primary sm:h-4 sm:w-4"
        />
        {enabled ? t("sectionsEditor.backgroundOn") : t("sectionsEditor.backgroundOff")}
      </label>
      {enabled && (
        <>
          <label className="inline-flex items-center gap-2 text-sm text-foreground">
            <span className="whitespace-nowrap">{t("sectionsEditor.backgroundCount")}</span>
            <input type="number" min={BACKGROUND_COUNT_MIN} max={BACKGROUND_COUNT_MAX} value={count}
              disabled={disabled || status === "saving"} onChange={(e) => setCount(e.target.value)} onBlur={commitCount} className={SETUP_INPUT} />
          </label>
          <label className="inline-flex items-center gap-2 text-sm text-foreground">
            <span className="whitespace-nowrap">{t("sectionsEditor.backgroundMinutes")}</span>
            <input type="number" min={1} max={maxMinutes ?? undefined} value={minutes}
              disabled={disabled || status === "saving"} onChange={(e) => setMinutes(e.target.value)} onBlur={commitMinutes} className={SETUP_INPUT} />
            <span className="text-xs text-muted-foreground">{t("sectionsEditor.min")}</span>
          </label>
          {localError && <p className="basis-full text-xs text-destructive">{localError}</p>}
          {total == null && <p className="basis-full text-xs text-muted-foreground">{t("sectionsEditor.backgroundSummaryNoBudget")}</p>}
        </>
      )}
    </SetupRow>
  );
}

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
      if (err.status === 409) {
        setError(t('sectionsEditor.alreadyExists'));
      } else {
        setError(err.message || t('sectionsEditor.failedToAdd'));
      }
    } finally {
      setLoadingAction(null);
    }
  };

  const [sectionToDelete, setSectionToDelete] = useState<string | null>(null);

  const handleDelete = async (sectionId: string) => {
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
      {/* R2-B: block header stacks below sm; the action is full-width there. */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h2 className="text-xl font-semibold">{t('sectionsEditor.title')}</h2>
        {isDraft && (
          <Button
            variant="secondary"
            onClick={() => setIsAdding(true)}
            disabled={availableTypes.length === 0 || isAdding || loadingAction !== null}
            className="inline-flex h-11 w-full items-center justify-center gap-2 sm:w-auto sm:shrink-0 lg:h-10"
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
                className="flex h-11 flex-1 items-center justify-center gap-2 sm:h-10 sm:flex-none"
              >
                {loadingAction === "add" && <Loader2 className="h-4 w-4 animate-spin" />}
                <span>{t('sectionsEditor.add')}</span>
              </Button>
              <Button
                variant="outline"
                onClick={() => setIsAdding(false)}
                disabled={loadingAction === "add"}
                className="h-11 flex-1 sm:h-10 sm:flex-none"
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
                  {/* R2-B: two-line row. Line 1 = type + title (the expand
                      target) and the reorder/delete cluster (44px, labelled);
                      line 2 = the summary sentence on its own full-width line,
                      so it no longer wraps in a narrow column beside the arrows. */}
                  <div className="flex items-center justify-between gap-2">
                    <button
                      onClick={() => setExpandedSectionId(isExpanded ? null : section.id)}
                      aria-expanded={isExpanded}
                      className="flex min-h-11 items-center gap-3 text-start flex-1 min-w-0 sm:gap-4"
                    >
                      <div className="bg-primary/10 p-2 rounded-md text-primary shrink-0">
                        <Icon className="h-5 w-5" />
                      </div>
                      <h3 className="min-w-0 font-semibold text-foreground">{t(`sectionsEditor.${typeConfig.value.toLowerCase()}`)}</h3>
                      {isExpanded ? (
                        <ChevronUp className="h-4 w-4 shrink-0 text-muted-foreground" />
                      ) : (
                        <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
                      )}
                    </button>

                    {isDraft && (
                      <div className="flex items-center shrink-0">
                        <button
                          onClick={() => handleSwap(index, index - 1)}
                          disabled={index === 0 || loadingAction !== null}
                          className="touch-target flex items-center justify-center text-muted-foreground hover:bg-muted hover:text-foreground rounded-md disabled:opacity-30 disabled:hover:bg-transparent"
                          title={t('sectionsEditor.moveUp')}
                          aria-label={t('sectionsEditor.moveUp')}
                        >
                          <ArrowUp className="h-4 w-4" />
                        </button>
                        <button
                          onClick={() => handleSwap(index, index + 1)}
                          disabled={index === sections.length - 1 || loadingAction !== null}
                          className="touch-target flex items-center justify-center text-muted-foreground hover:bg-muted hover:text-foreground rounded-md disabled:opacity-30 disabled:hover:bg-transparent"
                          title={t('sectionsEditor.moveDown')}
                          aria-label={t('sectionsEditor.moveDown')}
                        >
                          <ArrowDown className="h-4 w-4" />
                        </button>
                        <div className="w-px h-6 bg-border mx-1 sm:mx-2"></div>
                        <button
                          onClick={() => setSectionToDelete(section.id)}
                          disabled={loadingAction !== null}
                          className="touch-target flex items-center justify-center text-red-500 hover:bg-red-500/10 rounded-md transition-colors disabled:opacity-30"
                          title={t('sectionsEditor.deleteSection')}
                          aria-label={t('sectionsEditor.deleteSection')}
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
                  {!isExpanded && <div className="mt-1 ps-12 sm:ps-[3.75rem]"><SectionSummaryLine section={section} /></div>}

                  {isExpanded && (
                    <div className="mt-4 space-y-3 border-t border-border pt-4">
                      <SectionSummaryStrip section={section} />

                      <SetupRow
                        icon={<Clock className="h-4 w-4" />}
                        title={t('sectionsEditor.timingTitle')}
                        hint={t('sectionsEditor.timingHint')}
                        status={(timeBudgets ?? {})[section.id]?.status}
                      >
                        <label htmlFor={`time-budget-${section.id}`} className="inline-flex items-center gap-2 text-sm text-foreground">
                          <span className="whitespace-nowrap">{t('sectionsEditor.timeBudget')}</span>
                          <input
                            id={`time-budget-${section.id}`}
                            type="number"
                            min={1}
                            max={300}
                            placeholder={t('sectionsEditor.timeBudgetPlaceholder')}
                            value={(timeBudgets ?? {})[section.id]?.draft ?? ""}
                            onChange={(e) => handleTimeBudgetChange(section.id, e.target.value)}
                            onBlur={() => handleTimeBudgetSave(section.id)}
                            disabled={!isDraft || loadingAction !== null || (timeBudgets ?? {})[section.id]?.status === "saving"}
                            className={SETUP_INPUT}
                          />
                          <span className="text-xs text-muted-foreground">{t('sectionsEditor.min')}</span>
                        </label>
                      </SetupRow>

                      {section.section_type === "VERBAL" && (
                        <BackgroundSettings
                          section={section}
                          disabled={!isDraft || loadingAction !== null}
                          onRefresh={onRefresh}
                        />
                      )}

                      <div className="rounded-lg border border-border bg-background p-4">
                        <div className="flex items-start gap-3">
                          <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary"><Icon className="h-4 w-4" /></span>
                          <div className="min-w-0">
                            <p className="text-sm font-semibold text-foreground">
                              {t(`sectionsEditor.questionsTitle.${section.section_type}`)} <span className="font-normal text-muted-foreground">({questionCount})</span>
                            </p>
                            <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{t(`sectionsEditor.questionsHint.${section.section_type}`)}</p>
                          </div>
                        </div>
                        <QuestionEditor
                          sectionId={section.id}
                          sectionType={section.section_type}
                          questions={section.questions ?? []}
                          onRefresh={onRefresh}
                          status={status}
                        />
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
      <ConfirmDeleteModal
        isOpen={sectionToDelete !== null}
        onClose={() => setSectionToDelete(null)}
        onConfirm={async () => {
          const id = sectionToDelete!;
          setSectionToDelete(null);
          await handleDelete(id);
        }}
        title={t('sectionsEditor.delete')}
        description={t('sectionsEditor.deleteConfirm')}
        confirmLabel={t('sectionsEditor.delete')}
      />
    </div>
  );
}
