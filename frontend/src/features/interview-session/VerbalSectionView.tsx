import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Code2, Mic, Send, Volume2, MessageSquare } from "lucide-react";
import { type InterviewerCharacterState } from "./InterviewerCharacter";
import BlobCharacter from "./BlobCharacter";
import type { RemoteAudioTrack } from "livekit-client";
import type { ActiveQuestion, AllowedControl, StateUpdatePayload } from "../../types/realtime";

/**
 * VerbalSectionView — the pre-existing shared layout, extracted verbatim
 * (structure/classNames/behavior unchanged) so it now only renders for
 * VERBAL sections and legacy pre-Phase-9 single-question sessions.
 * CODING/MCQ ordered-flow sections are intercepted at the InterviewWorkspace
 * level before reaching this component — see CodingSectionView/
 * McqSectionView. The internal MCQ branch this file used to also handle
 * was removed as dead code: sections_progress.current_section_type "MCQ"
 * never routes here anymore, so it could never execute.
 */

interface VerbalSectionViewProps {
  question: ActiveQuestion | null | undefined;
  isCompleted: boolean;
  isAgentSpeaking: boolean;
  isMicrophoneEnabled: boolean;
  isTechnical: boolean;
  hasEditor: boolean;
  characterState: InterviewerCharacterState;
  agentAudioTrack: RemoteAudioTrack | undefined;
  code: string;
  setCode: (code: string) => void;
  selectedLanguage: string;
  setSelectedLanguage: (language: string) => void;
  hasConfigStarterCode: boolean;
  codingConfigConstraints?: string;
  codeStatus: string | null;
  onCodeSubmit: () => void;
  currentSectionType: string | null | undefined;
  ReportLoadingState: React.ComponentType;
  allowedControls: AllowedControl[];
  onToggleMicrophone: () => void;
  onSendControl: (control: string) => void;
  backendState: StateUpdatePayload | null;
  hasNextSection: boolean;
  visibleTranscripts: Array<{ id: string; speaker: string; text: string }>;
  transcriptRef: React.RefObject<HTMLDivElement>;
}

export function VerbalSectionView({
  question,
  isCompleted,
  isAgentSpeaking,
  isMicrophoneEnabled,
  isTechnical,
  hasEditor,
  characterState,
  agentAudioTrack,
  code,
  setCode,
  selectedLanguage,
  setSelectedLanguage,
  hasConfigStarterCode,
  codingConfigConstraints,
  codeStatus,
  onCodeSubmit,
  currentSectionType,
  ReportLoadingState,
  allowedControls,
  onToggleMicrophone,
  onSendControl,
  backendState,
  hasNextSection,
  visibleTranscripts,
  transcriptRef,
}: VerbalSectionViewProps) {
  const { t } = useTranslation();
  // Hidden by default: keeps the blob avatar centered in a single full-width
  // column instead of permanently reserving a 340px side panel most of the
  // interview doesn't need — the transcript is one click away, not gone.
  const [showTranscript, setShowTranscript] = useState(false);

  return (
    <>
      <div className="col-span-full flex flex-wrap items-center justify-between gap-2 rounded-xl border bg-card px-4 py-2.5 shadow-sm">
        <div className="min-w-0">
          <h1 className="truncate text-lg font-bold text-foreground">{question?.title || t('workspace.preparingInterview')}</h1>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-xs font-semibold text-primary">
              {isTechnical ? <Code2 className="h-3 w-3" /> : <MessageSquare className="h-3 w-3" />}
              {isTechnical ? t('workspace.technicalAssessment') : t('workspace.interview')}
            </span>
            <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${isAgentSpeaking ? "bg-primary/10 text-primary" : "bg-success/10 text-success"}`} role="status" aria-live="polite">
              {isAgentSpeaking ? <Volume2 className="h-3 w-3" /> : <Mic className="h-3 w-3" />}
              {isAgentSpeaking ? t('workspace.interviewerSpeaking') : t('workspace.listening')}
            </span>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setShowTranscript((prev) => !prev)}
          aria-pressed={showTranscript}
          className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition ${
            showTranscript ? "border-primary/30 bg-primary/10 text-primary" : "border-border text-muted-foreground hover:bg-muted"
          }`}
        >
          <MessageSquare className="h-3.5 w-3.5" />
          {showTranscript ? t('workspace.hideTranscript') : t('workspace.showTranscript')}
        </button>
      </div>

      <section className={`flex min-w-0 flex-1 flex-col gap-4 lg:min-h-0 lg:overflow-hidden ${showTranscript ? "" : "lg:col-span-2"}`}>
        {isTechnical && question && hasEditor ? <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
          <article className="flex min-h-0 min-w-0 flex-col overflow-hidden rounded-xl border bg-card shadow-sm">
            <div className="shrink-0 flex items-center min-h-[68px] border-b px-5 py-4 sm:px-7"><div className="flex flex-wrap items-center gap-2 text-xs"><span className="rounded-md bg-primary/10 px-2 py-1 font-semibold capitalize text-primary">{question.difficulty}</span><span className="rounded-md bg-muted px-2 py-1 text-muted-foreground">{question.competency}</span>{question.time_budget_minutes && <span className="text-muted-foreground">{question.time_budget_minutes} {t('workspace.min')}</span>}</div></div>
            <div className="min-h-0 max-h-[45vh] flex-1 overflow-y-auto px-5 py-6 sm:px-7 lg:max-h-none"><div className="space-y-3"><h2 className="text-base font-semibold text-foreground sm:text-lg">{t('workspace.problemStatement')}</h2><p className="whitespace-pre-line text-[15px] leading-7 text-muted-foreground">{question.problem_statement}</p></div>{question.examples.length > 0 && <div className="mt-6 grid gap-3">{question.examples.map((example, index) => <div key={index} className="rounded-lg border bg-muted/30 p-3 text-xs"><p className="mb-2 font-semibold text-foreground">{t('workspace.example', { num: index + 1 })}</p><pre className="overflow-auto whitespace-pre-wrap leading-5 text-muted-foreground">{JSON.stringify(example, null, 2)}</pre></div>)}</div>}{codingConfigConstraints ? <div className="mt-6"><p className="mb-2 text-sm font-semibold text-foreground">{t('workspace.constraints')}</p><p className="text-sm text-muted-foreground">{codingConfigConstraints}</p></div> : question.constraints.length > 0 && <div className="mt-6"><p className="mb-2 text-sm font-semibold text-foreground">{t('workspace.constraints')}</p><ul className="grid gap-1.5 text-sm text-muted-foreground">{question.constraints.map((constraint) => <li key={constraint} className="flex gap-2"><span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />{constraint}</li>)}</ul></div>}</div>
          </article>
          <section className="flex min-h-[360px] min-w-0 flex-col overflow-hidden border border-secondary rounded-xl bg-secondary text-secondary-foreground shadow-sm" aria-label={t('workspace.codeAnswer')}><div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-white/10 px-4 py-3"><div className="flex items-center gap-2 text-sm font-medium"><Code2 className="h-4 w-4 text-primary/70" />{t('workspace.codeAnswer')}</div><div className="flex items-center gap-2 text-xs text-white/50"><span>{t('workspace.language')}</span><select value={selectedLanguage} onChange={(event) => { setSelectedLanguage(event.target.value); if (!hasConfigStarterCode && question.starter_code[event.target.value]) setCode(question.starter_code[event.target.value]); }} className="rounded-md border border-white/10 bg-white/5 px-2 py-1.5 text-xs text-slate-200 outline-none"><option className="bg-slate-800" value="">{t('workspace.select')}</option>{(question.supported_languages.length ? question.supported_languages : Object.keys(question.starter_code)).map((language) => <option className="bg-slate-800" key={language} value={language}>{language}</option>)}</select></div></div><textarea value={code} onChange={(event) => setCode(event.target.value)} spellCheck={false} aria-label={t('workspace.codeAnswer')} className="min-h-0 w-full flex-1 resize-none overflow-auto bg-transparent p-4 font-mono text-sm leading-6 text-slate-100 outline-none placeholder:text-white/30" placeholder={t('workspace.writeSolution')} /><div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-t border-white/10 px-4 py-3"><span className="text-xs text-white/45">{t('workspace.submitOnceReady')}</span><button type="button" onClick={onCodeSubmit} className="inline-flex items-center gap-2 rounded-md bg-primary px-3 py-2 text-xs font-semibold text-primary-foreground transition hover:bg-primary/90"><Send className="h-3.5 w-3.5" />{t('workspace.submitAnswer')}</button>{codeStatus && <span className="sr-only" role="status">{codeStatus}</span>}</div></section>
        </div> : <article className="flex flex-col min-h-0 flex-1 overflow-hidden rounded-xl border bg-card shadow-sm"><div className="shrink-0 flex items-center min-h-[68px] border-b px-5 py-4 sm:px-7 z-10 bg-white"><div className="flex flex-wrap items-center gap-2 text-xs"><span className="rounded-md bg-primary/10 px-2 py-1 font-semibold capitalize text-primary">{question?.difficulty || currentSectionType || t('workspace.backgroundDiscussion')}</span>{question?.competency && <span className="rounded-md bg-muted px-2 py-1 text-muted-foreground">{question.competency}</span>}{question?.time_budget_minutes && <span className="text-muted-foreground">{question.time_budget_minutes} {t('workspace.min')}</span>}</div></div>{isCompleted ? <ReportLoadingState /> : question ? <div className="flex-1 overflow-y-auto space-y-6 px-5 py-6 sm:px-7"><div className="space-y-3"><h2 className="text-base font-semibold text-foreground sm:text-lg">{t('workspace.problemStatement')}</h2><p className="whitespace-pre-line text-[15px] leading-7 text-muted-foreground">{question.problem_statement}</p></div></div> : <div className="flex-1 relative flex items-center justify-center overflow-hidden bg-background"><BlobCharacter state={characterState} size="medium" audioTrack={agentAudioTrack} /></div>}</article>}
      </section>

      {showTranscript && (
        <aside className="flex min-h-0 flex-1 flex-col gap-4 lg:overflow-hidden"><section className="flex min-h-[280px] flex-1 flex-col overflow-hidden rounded-xl border bg-card shadow-sm"><div className="flex min-h-[68px] items-center justify-between border-b px-5 py-4"><div><p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">{t('workspace.liveTranscript')}</p><p className="mt-1 text-xs text-muted-foreground">{t('workspace.finalizedTurns')}</p></div><span className="rounded bg-muted px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{t('workspace.live')}</span></div><div ref={transcriptRef} className="flex-1 space-y-4 overflow-y-auto p-5">{visibleTranscripts.length ? visibleTranscripts.map((message) => <div key={message.id} className="border-s-2 border-border ps-3"><p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">{message.speaker === "agent" ? t('workspace.interviewer') : t('workspace.you')}</p><p className={`mt-1 text-sm leading-6 ${message.speaker === "agent" ? "text-foreground" : "text-muted-foreground"}`}>{message.text}</p></div>) : <p className="text-sm leading-6 text-muted-foreground">{t('workspace.conversationWillAppear')}</p>}</div></section></aside>
      )}
    </>
  );
}
