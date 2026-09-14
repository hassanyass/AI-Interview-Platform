import { useTranslation } from "react-i18next";
import { CheckCircle2, Circle, ListTodo, Mic, Send, Timer, Volume2 } from "lucide-react";
import type { ActiveQuestion, AllowedControl, StateUpdatePayload } from "../../types/realtime";

interface McqOption { id: string; text: string }

/**
 * McqSectionView — quiz-card layout for an ordered MCQ core question. No
 * avatar (same reasoning as CodingSectionView) — the compact speaking/
 * listening pill is the "agent present" signal instead. No transcript
 * panel — real quiz platforms don't show a running conversation log in
 * the workspace itself; still fully recorded server-side regardless.
 *
 * Rebrand consolidation pass (2026-08-26, per e& visual identity report
 * Section 7/21 audit): one header card + one quiz card, not four stacked
 * boxes. Same rounded-xl/shadow-sm scale as CodingSectionView.
 */

interface McqSectionViewProps {
  question: ActiveQuestion;
  isAgentSpeaking: boolean;
  isMicrophoneEnabled: boolean;
  mcqOptions: McqOption[];
  selectedOptionIds: string[];
  onToggleOption: (id: string) => void;
  mcqIsMultiSelect: boolean;
  mcqSubmitted: boolean;
  onMcqSubmit: () => void;
  allowedControls: AllowedControl[];
  isCompleted: boolean;
  onToggleMicrophone: () => void;
  onSendControl: (control: string) => void;
  backendState: StateUpdatePayload | null;
  hasNextSection: boolean;
  formattedTime: string;
}

export function McqSectionView({
  question,
  isAgentSpeaking,
  isMicrophoneEnabled,
  mcqOptions,
  selectedOptionIds,
  onToggleOption,
  mcqIsMultiSelect,
  mcqSubmitted,
  onMcqSubmit,
  allowedControls,
  isCompleted,
  onToggleMicrophone,
  onSendControl,
  backendState,
  hasNextSection,
  formattedTime,
}: McqSectionViewProps) {
  const { t } = useTranslation();

  return (
    <section className="col-span-full flex min-h-0 flex-1 flex-col gap-3 lg:overflow-hidden">
      {/* Consolidated header — one card, not four floating pieces. */}
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border bg-card px-4 py-2.5 shadow-sm">
        <div className="min-w-0">
          <h1 className="truncate text-lg font-bold text-foreground">{question.title}</h1>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-xs font-semibold text-primary">
              <ListTodo className="h-3 w-3" />
              {t('workspace.sectionTypes.MCQ')}
            </span>
            <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${isAgentSpeaking ? "bg-primary/10 text-primary" : "bg-success/10 text-success"}`} role="status" aria-live="polite">
              {isAgentSpeaking ? <Volume2 className="h-3 w-3" /> : <Mic className="h-3 w-3" />}
              {isAgentSpeaking ? t('workspace.speaking') : t('workspace.listening')}
            </span>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-3">
          <span className="flex items-center gap-1.5 rounded-full bg-muted/60 px-3 py-1.5 text-sm font-semibold tabular-nums text-foreground">
            <Timer className="h-3.5 w-3.5 text-muted-foreground" />
            {formattedTime}
          </span>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col items-center overflow-y-auto py-1">
        <div className="w-full max-w-2xl">
          <article className="overflow-hidden rounded-xl border bg-card shadow-sm">
            <div className="h-1.5 w-full bg-gradient-to-r from-primary/60 via-primary to-primary/60" />
            <div className="px-5 py-4 sm:px-8 sm:py-5">
              <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
                <span className="rounded-md bg-primary/10 px-2 py-1 font-semibold capitalize text-primary">{question.difficulty}</span>
                {question.competency && <span className="rounded-md bg-muted px-2 py-1 text-muted-foreground">{question.competency}</span>}
              </div>
              <h1 className="mb-3 text-base font-semibold leading-snug text-foreground sm:text-lg">{question.problem_statement}</h1>

              <div className="space-y-1.5" role={mcqIsMultiSelect ? "group" : "radiogroup"}>
                {mcqOptions.map((option) => {
                  const isSelected = selectedOptionIds.includes(option.id);
                  return (
                    <button
                      key={option.id}
                      type="button"
                      role={mcqIsMultiSelect ? "checkbox" : "radio"}
                      aria-checked={isSelected}
                      onClick={() => onToggleOption(option.id)}
                      disabled={mcqSubmitted}
                      className={`flex w-full items-center gap-2.5 rounded-xl border-2 px-4 py-2.5 text-start text-sm font-medium transition ${isSelected ? "border-primary bg-primary/5 text-foreground" : "border-input hover:border-primary/40 hover:bg-muted/50 text-foreground"} disabled:cursor-not-allowed disabled:opacity-70`}
                    >
                      {isSelected ? <CheckCircle2 className="h-4 w-4 shrink-0 text-primary" /> : <Circle className="h-4 w-4 shrink-0 text-muted-foreground" />}
                      {option.text}
                    </button>
                  );
                })}
              </div>

              <div className="mt-5 flex items-center justify-between gap-2">
                <span className="text-xs text-muted-foreground">{mcqIsMultiSelect ? t('workspace.selectAllApply') : t('workspace.selectOne')}</span>
                <button
                  type="button"
                  onClick={onMcqSubmit}
                  disabled={selectedOptionIds.length === 0 || mcqSubmitted}
                  className="inline-flex items-center gap-2 rounded-lg bg-primary px-6 py-3 text-sm font-semibold text-primary-foreground shadow-sm transition hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <Send className="h-4 w-4" />
                  {mcqSubmitted ? t('workspace.answerSubmitted') : t('workspace.submitAnswer')}
                </button>
              </div>
            </div>
          </article>
        </div>
      </div>
    </section>
  );
}
