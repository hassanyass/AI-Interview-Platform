import { useTranslation } from "react-i18next";
import { Code2, Mic, Send, Timer, Volume2 } from "lucide-react";
import { InterviewController } from "./InterviewController";
import type { ActiveQuestion, AllowedControl, StateUpdatePayload } from "../../types/realtime";

/**
 * CodingSectionView — LeetCode/CoderPad-style split view for an ordered
 * CODING core question. No avatar (matches how real coding-assessment
 * platforms separate "conversational screening" chrome from the technical
 * workspace) — the agent still speaks (TTS) throughout, surfaced only via
 * the compact speaking/listening status pill in the header, not an
 * illustrated character. No transcript panel — real coding/quiz platforms
 * don't show a running conversation log in the workspace itself; still
 * fully recorded server-side regardless.
 *
 * Rebrand consolidation pass (2026-08-26, per e& visual identity report
 * Section 7/21 audit): one header card (title/badge/status/timer/controls)
 * + one work-area card, not five stacked boxes. Same rounded-xl/shadow-sm
 * scale as every other card in this view; pills are rounded-full.
 */

interface CodingSectionViewProps {
  question: ActiveQuestion;
  isAgentSpeaking: boolean;
  isMicrophoneEnabled: boolean;
  code: string;
  setCode: (code: string) => void;
  selectedLanguage: string;
  setSelectedLanguage: (language: string) => void;
  hasConfigStarterCode: boolean;
  codingConfigConstraints?: string;
  codeStatus: string | null;
  onCodeSubmit: () => void;
  allowedControls: AllowedControl[];
  isCompleted: boolean;
  onToggleMicrophone: () => void;
  onSendControl: (control: string) => void;
  backendState: StateUpdatePayload | null;
  hasNextSection: boolean;
  formattedTime: string;
}

export function CodingSectionView({
  question,
  isAgentSpeaking,
  isMicrophoneEnabled,
  code,
  setCode,
  selectedLanguage,
  setSelectedLanguage,
  hasConfigStarterCode,
  codingConfigConstraints,
  codeStatus,
  onCodeSubmit,
  allowedControls,
  isCompleted,
  onToggleMicrophone,
  onSendControl,
  backendState,
  hasNextSection,
  formattedTime,
}: CodingSectionViewProps) {
  const { t } = useTranslation();

  return (
    <section className="col-span-full flex min-h-0 min-w-0 flex-1 flex-col gap-3 lg:overflow-hidden">
      {/* Consolidated header — one card, not four floating pieces. Title is
          the dominant element; badge + status are small supporting
          metadata beneath it, not equal-weight siblings. */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border bg-card px-4 py-3 shadow-sm">
        <div className="min-w-0">
          <h1 className="truncate text-lg font-bold text-foreground">{question.title}</h1>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-xs font-semibold text-primary">
              <Code2 className="h-3 w-3" />
              {t('workspace.sectionTypes.CODING')}
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
          <InterviewController
            variant="compact"
            isCompleted={isCompleted}
            allowedControls={allowedControls}
            isMicrophoneEnabled={isMicrophoneEnabled}
            onToggleMicrophone={onToggleMicrophone}
            onSendControl={onSendControl}
            backendState={backendState}
            hasNextSection={hasNextSection}
          />
        </div>
      </div>

      {/* Split pane — problem left, editor right. Takes the remaining
          height (no fixed sidebar competing with it now). */}
      <div className="grid min-h-0 flex-1 gap-3 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <article className="flex min-h-0 min-w-0 flex-col overflow-hidden rounded-xl border bg-card shadow-sm">
          <div className="shrink-0 border-b px-5 py-4"><div className="flex flex-wrap items-center gap-2 text-xs"><span className="rounded-md bg-primary/10 px-2 py-1 font-semibold capitalize text-primary">{question.difficulty}</span>{question.competency && <span className="rounded-md bg-muted px-2 py-1 text-muted-foreground">{question.competency}</span>}{question.time_budget_minutes ? <span className="text-muted-foreground">{question.time_budget_minutes} {t('workspace.min')}</span> : null}</div></div>
          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-6">
            <div className="space-y-3">
              <h2 className="text-base font-semibold text-foreground">{t('workspace.problemStatement')}</h2>
              <p className="whitespace-pre-line text-[15px] leading-7 text-muted-foreground">{question.problem_statement}</p>
            </div>
            {codingConfigConstraints ? (
              <div className="mt-6">
                <p className="mb-2 text-sm font-semibold text-foreground">{t('workspace.constraints')}</p>
                <p className="text-sm text-muted-foreground">{codingConfigConstraints}</p>
              </div>
            ) : question.constraints.length > 0 && (
              <div className="mt-6">
                <p className="mb-2 text-sm font-semibold text-foreground">{t('workspace.constraints')}</p>
                <ul className="grid gap-1.5 text-sm text-muted-foreground">
                  {question.constraints.map((constraint) => <li key={constraint} className="flex gap-2"><span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />{constraint}</li>)}
                </ul>
              </div>
            )}
          </div>
        </article>

        <section className="flex min-h-[360px] min-w-0 flex-col overflow-hidden border border-secondary rounded-xl bg-secondary text-secondary-foreground shadow-sm" aria-label={t('workspace.codeAnswer')}>
          <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-white/10 px-4 py-3">
            <div className="flex items-center gap-2 text-sm font-medium"><Code2 className="h-4 w-4 text-primary/70" />{t('workspace.codeAnswer')}</div>
            <div className="flex items-center gap-2 text-xs text-white/50">
              <span>{t('workspace.language')}</span>
              <select
                value={selectedLanguage}
                onChange={(event) => { setSelectedLanguage(event.target.value); if (!hasConfigStarterCode && question.starter_code[event.target.value]) setCode(question.starter_code[event.target.value]); }}
                className="rounded-md border border-white/10 bg-white/5 px-2 py-1.5 text-xs text-slate-200 outline-none"
              >
                <option className="bg-slate-800" value="">{t('workspace.select')}</option>
                {(question.supported_languages.length ? question.supported_languages : Object.keys(question.starter_code)).map((language) => <option className="bg-slate-800" key={language} value={language}>{language}</option>)}
              </select>
            </div>
          </div>
          <textarea
            value={code}
            onChange={(event) => setCode(event.target.value)}
            spellCheck={false}
            aria-label={t('workspace.codeAnswer')}
            className="min-h-0 w-full flex-1 resize-none overflow-auto bg-transparent p-4 font-mono text-sm leading-6 text-slate-100 outline-none placeholder:text-white/30"
            placeholder={t('workspace.writeSolution')}
          />
          <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-t border-white/10 px-4 py-3">
            <span className="text-xs text-white/45">{t('workspace.submitOnceReady')}</span>
            <button type="button" onClick={onCodeSubmit} className="inline-flex items-center gap-2 rounded-md bg-primary px-3 py-2 text-xs font-semibold text-primary-foreground transition hover:bg-primary/90">
              <Send className="h-3.5 w-3.5" />
              {t('workspace.submitAnswer')}
            </button>
            {codeStatus && <span className="sr-only" role="status">{codeStatus}</span>}
          </div>
        </section>
      </div>
    </section>
  );
}
