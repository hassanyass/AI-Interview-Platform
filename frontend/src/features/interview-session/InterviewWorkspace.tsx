import { useEffect, useMemo, useRef, useState } from "react";
import { useLocalParticipant, useRoomContext, useTracks } from "@livekit/components-react";
import { Track, type RemoteAudioTrack } from "livekit-client";
import { Loader2, Timer, LogOut } from "lucide-react";
import { InterviewRealtimeService } from "../../services/livekit/InterviewRealtimeService";
import { useInterviewStore } from "../../stores/InterviewContext";
import type { InterviewSessionResponse } from "../../types/api";
import { LanguageToggle } from "../../components/ui/LanguageToggle";
import { useTranslation } from "react-i18next";
import { WaitingRoomScreen } from "./WaitingRoomScreen";
import { VerbalSectionView } from "./VerbalSectionView";
import { CodingSectionView } from "./CodingSectionView";
import { McqSectionView } from "./McqSectionView";
import { SessionEndedScreen } from "./SessionEndedScreen";
import { TtsRetryOverlay } from "./TtsRetryOverlay";
import { InterviewController } from "./InterviewController";
import { EndInterviewDialog } from "./EndInterviewDialog";

const AgentConnectingScreen = () => {
  const { t } = useTranslation();
  const [progress, setProgress] = useState(15);
  const [status, setStatus] = useState(t('workspace.connecting'));

  useEffect(() => {
    const timer1 = setTimeout(() => { setProgress(45); setStatus(t('workspace.initializing')); }, 800);
    const timer2 = setTimeout(() => { setProgress(80); setStatus(t('workspace.preparing')); }, 2200);
    return () => { clearTimeout(timer1); clearTimeout(timer2); };
  }, []);

  return (
    <div className="min-h-screen w-full flex flex-col bg-background text-foreground">
      {/* Skeleton Header matching the actual workspace header */}
      <header className="border-b bg-card">
        <div className="mx-auto flex min-h-16 max-w-[1440px] items-center justify-between gap-4 px-4 py-3 sm:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex items-center gap-2 font-bold text-xl tracking-tight text-primary">
              <span dir="ltr" className="inline-block">e&</span> <span className="text-muted-foreground font-normal">|</span> هِمّة
            </div>
            <div className="min-w-0 ms-4 ps-4 border-s">
              <p className="truncate text-sm font-semibold text-foreground">{t('workspace.session')}</p>
              <p className="text-xs text-muted-foreground">{t('workspace.connectingShort')}</p>
            </div>
          </div>
        </div>
      </header>

      {/* Main Centered Progress Card */}
      <main className="flex-1 flex items-center justify-center p-4">
        <div className="w-full max-w-sm rounded-xl border bg-card p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-foreground mb-1">{t('workspace.starting')}</h2>
          <p className="text-sm text-muted-foreground mb-6">{status}</p>

          <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-primary transition-all duration-700 ease-out"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      </main>
    </div>
  );
};

const ReportLoadingState = () => {
  const { t } = useTranslation();
  const [progress, setProgress] = useState(15);
  const [status, setStatus] = useState(t('workspace.finalizing'));

  useEffect(() => {
    const timer1 = setTimeout(() => { setProgress(45); setStatus(t('workspace.reviewing')); }, 1500);
    const timer2 = setTimeout(() => { setProgress(85); setStatus(t('workspace.retrieving')); }, 3500);
    return () => { clearTimeout(timer1); clearTimeout(timer2); };
  }, []);

  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-4 px-5 text-center bg-muted/30 min-h-[300px]">
      <div className="flex flex-col items-center gap-3 w-full max-w-xs">
        <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10 text-primary mb-2">
          <Loader2 className="h-6 w-6 animate-spin" />
        </span>
        <h2 className="text-xl font-semibold text-foreground">{t('workspace.complete')}</h2>
        <p className="text-sm text-muted-foreground mb-3">{status}</p>

        <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
          <div
            className="h-full rounded-full bg-primary transition-all duration-1000 ease-out"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>
    </div>
  );
};

interface InterviewWorkspaceProps { session: InterviewSessionResponse; onCompleted?: () => void; }

const PHASE_LABELS: Record<string, string> = {
  CREATED: "preparation", BRIEFING: "intro", WELCOME: "intro", BACKGROUND: "background",
  WAITING_ROOM: "waitingRoom",
  TECHNICAL_INTRO: "technical", TECHNICAL: "technical", CODING: "technical",
  CLOSING: "closing", COMPLETED: "completed", TERMINATED: "ended",
};

function formatTime(seconds = 0) {
  return `${Math.floor(seconds / 60).toString().padStart(2, "0")}:${Math.max(0, seconds % 60).toString().padStart(2, "0")}`;
}

export function InterviewWorkspace({ session, onCompleted }: InterviewWorkspaceProps) {
  const { t } = useTranslation();
  const room = useRoomContext();
  const { isMicrophoneEnabled } = useLocalParticipant();
  // The agent's live mic track, handed straight to BlobCharacter (see its
  // audioTrack prop) so IT can sample the waveform inside its own animation
  // loop. useTracks only re-renders on track/room events, not per-frame —
  // deliberately NOT using useTrackVolume here, since that returns a
  // React-state number that would re-render this whole tree every frame.
  const micTrackRefs = useTracks([Track.Source.Microphone], { onlySubscribed: true });
  const agentAudioTrack = micTrackRefs.find(
    (ref) => !ref.participant.isLocal && "publication" in ref,
  )?.publication?.track as RemoteAudioTrack | undefined;
  const { state, updateState, isAgentSpeaking, setIsAgentSpeaking, transcriptMessages, updateTranscript, ttsStatus, updateTtsStatus } = useInterviewStore();
  const [realtimeService, setRealtimeService] = useState<InterviewRealtimeService | null>(null);
  const [characterState, setCharacterState] = useState<'idle' | 'listening' | 'thinking' | 'speaking' | 'hidden'>('idle');
  const [code, setCode] = useState("");
  const [codeStatus, setCodeStatus] = useState<string | null>(null);
  const [selectedLanguage, setSelectedLanguage] = useState("");
  // 9H: MCQ answer selection — array to uniformly support both single- and
  // multi-select (is_multi_select just changes whether a second toggle adds
  // to or replaces the selection).
  const [selectedOptionIds, setSelectedOptionIds] = useState<string[]>([]);
  const [mcqSubmitted, setMcqSubmitted] = useState(false);
  const [displaySeconds, setDisplaySeconds] = useState(0);
  const [isEndDialogOpen, setIsEndDialogOpen] = useState(false);
  const [isEndingSession, setIsEndingSession] = useState(false);
  const timerDeadlineRef = useRef<number | null>(null);
  const transcriptRef = useRef<HTMLDivElement>(null);
  const question = state?.current_question;
  const isCompleted = state?.phase === "COMPLETED" || state?.phase === "TERMINATED" || state?.phase === "CLOSING" || session.status === "COMPLETED" || session.status === "TERMINATED";
  // Rebrand pass (2026-08-26): Phase 9's ordered CODING/MCQ questions run
  // under phase BACKGROUND (see _active_core_section()'s docstring in
  // controller.py), not the legacy TECHNICAL_INTRO/TECHNICAL/CODING phases
  // — sections_progress.current_section_type is the real signal for which
  // is active. These two flags now drive which dedicated section view
  // renders (CodingSectionView/McqSectionView/VerbalSectionView) instead of
  // one shared layout with an internal ternary.
  const isOrderedCoding = state?.sections_progress?.current_section_type === "CODING";
  const isOrderedMcq = state?.sections_progress?.current_section_type === "MCQ";
  const isTechnical = ["TECHNICAL_INTRO", "TECHNICAL", "CODING"].includes(state?.phase || "") || isOrderedCoding;
  const hasEditor = Boolean(question?.coding_required);
  // Part 1: for an ordered-flow CODING question, the legacy Dict[str,str]
  // starter_code/List[str] constraints fields are deliberately left empty —
  // config.starter_code (string)/config.constraints (string) are the real
  // CodingConfig-shaped source of truth. Legacy/single-question sessions
  // still populate the typed fields directly, so fall back to those.
  const codingConfig = question?.config;
  const hasConfigStarterCode = typeof codingConfig?.starter_code === "string" && codingConfig.starter_code.length > 0;
  const codingConfigConstraints = typeof codingConfig?.constraints === "string" && codingConfig.constraints ? codingConfig.constraints : undefined;
  const mcqOptions = isOrderedMcq ? codingConfig?.options ?? [] : [];
  const mcqIsMultiSelect = Boolean(codingConfig?.is_multi_select);
  const phaseKey = state?.phase ? PHASE_LABELS[state.phase] : "connectingShort";
  const phaseLabel = phaseKey ? t(`workspace.phase.${phaseKey}`) : state?.phase || t('workspace.connectingShort');
  const visibleTranscripts = useMemo(() => transcriptMessages.slice(-8), [transcriptMessages]);

  // WR-D: section progress for header label + hasNextSection for End Section Early dialog
  const sectionsProgress = state?.sections_progress;
  const hasNextSection = sectionsProgress
    ? sectionsProgress.completed < sectionsProgress.total - 1
    : true;

  // Waiting-room "what's next" info. The live realtime state only reports
  // the CURRENTLY active section (sections_progress.current_section_type is
  // None while phase === WAITING_ROOM itself — _active_core_section() on
  // the backend is phase-gated to BACKGROUND only). session.sections is the
  // static, definition-level ordered section-type list fetched once by
  // InterviewSession.tsx, so it's used here instead: sectionsProgress
  // .completed is a 0-based count of finished sections, which is also the
  // 0-based index of both the section that just finished (completed - 1)
  // and the one coming up next (completed) in that same ordered list.
  const orderedSectionTypes = session.sections || [];
  const completedSectionType =
    sectionsProgress && sectionsProgress.completed > 0
      ? orderedSectionTypes[sectionsProgress.completed - 1] ?? null
      : null;
  const nextSectionType =
    sectionsProgress ? orderedSectionTypes[sectionsProgress.completed] ?? null : null;
  const sectionProgressLabel =
    state?.phase === "BACKGROUND" && sectionsProgress && sectionsProgress.total > 0
      ? t("workspace.sectionProgress", {
          current: sectionsProgress.current_index ?? sectionsProgress.completed + 1,
          total: sectionsProgress.total,
          type: sectionsProgress.current_section_type
            ? t(`workspace.sectionTypes.${sectionsProgress.current_section_type}`, { defaultValue: sectionsProgress.current_section_type })
            : "",
        })
      : null;


  useEffect(() => {
    // Rebrand pass: MCQ now routes to its own no-avatar view (McqSectionView)
    // just like CODING already did — this flag stays correct defensively
    // (e.g. characterState shouldn't carry a stale 'speaking' value into a
    // later VERBAL section) even though neither new view ever reads it.
    if (isTechnical || isOrderedMcq || isCompleted) {
      setCharacterState('hidden');
      return;
    }

    if (isAgentSpeaking) {
      setCharacterState('speaking');
    } else if (isMicrophoneEnabled && room?.localParticipant?.isSpeaking) {
      setCharacterState('listening');
    } else {
      setCharacterState(prev => prev === 'listening' || prev === 'thinking' ? 'thinking' : 'idle');
    }
  }, [isTechnical, isOrderedMcq, isCompleted, isAgentSpeaking, isMicrophoneEnabled, room?.localParticipant?.isSpeaking]);

  // State updates are event-driven, so keep the visible clock running locally
  // between authoritative agent updates. The backend remains the source of
  // truth whenever a new state packet arrives.
  useEffect(() => {
    // WAITING_ROOM: backend sends time_remaining_seconds: null — do not set a
    // countdown deadline (the clock is paused and must not tick down).
    if (state?.time_remaining_seconds == null) {
      timerDeadlineRef.current = null;
      setDisplaySeconds(0);
      return;
    }
    if (isCompleted) {
      timerDeadlineRef.current = null;
      setDisplaySeconds(Math.max(0, state.time_remaining_seconds));
      return;
    }
    timerDeadlineRef.current = Date.now() + Math.max(0, state.time_remaining_seconds) * 1000;
    setDisplaySeconds(Math.max(0, state.time_remaining_seconds));
  }, [state?.time_remaining_seconds, isCompleted]);

  useEffect(() => {
    if (isCompleted || timerDeadlineRef.current == null) return;
    const tick = () => {
      const deadline = timerDeadlineRef.current;
      if (deadline == null) return;
      setDisplaySeconds(Math.max(0, Math.ceil((deadline - Date.now()) / 1000)));
    };
    tick();
    const interval = window.setInterval(tick, 250);
    return () => window.clearInterval(interval);
  }, [isCompleted, state?.time_remaining_seconds]);

  useEffect(() => {
    const transcript = transcriptRef.current;
    if (transcript) transcript.scrollTop = transcript.scrollHeight;
  }, [visibleTranscripts.length]);

  useEffect(() => {
    if (!room) return;
    const service = new InterviewRealtimeService(room, updateState, updateTranscript, updateTtsStatus);
    setRealtimeService(service);
    const onSpeakersChanged = (speakers: Array<{ identity: string }>) => setIsAgentSpeaking(speakers.some((speaker) => speaker.identity !== room.localParticipant.identity));
    room.on("activeSpeakersChanged", onSpeakersChanged);
    return () => { room.off("activeSpeakersChanged", onSpeakersChanged); service.cleanup(); };
  }, [room, updateState, updateTranscript, updateTtsStatus, setIsAgentSpeaking]);

  useEffect(() => {
    const languages = question?.supported_languages || Object.keys(question?.starter_code || {});
    setSelectedLanguage(languages[0] || "");
    // Part 1: ordered-flow CODING carries ONE starter_code string in
    // config, shared across every supported language (CodingConfig has no
    // per-language mapping) — legacy/single-question sessions still carry
    // a real Dict[str,str], one snippet per language.
    if (typeof question?.config?.starter_code === "string" && question.config.starter_code.length > 0) {
      setCode(question.config.starter_code);
    } else if (question?.starter_code && Object.keys(question.starter_code).length > 0) {
      setCode(question.starter_code[languages[0]] || Object.values(question.starter_code)[0]);
    } else {
      setCode("");
    }
    setCodeStatus(null);
  }, [question?.id, question?.starter_code, question?.supported_languages, question?.config]);

  // 9H: reset MCQ selection whenever the active question changes.
  useEffect(() => {
    setSelectedOptionIds([]);
    setMcqSubmitted(false);
  }, [question?.id]);

  useEffect(() => {
    if (!isCompleted || !session.id) return;
    onCompleted?.();
  }, [isCompleted, session.id, onCompleted]);

  // Audit fix (2026-08-27): client-side Web Speech API fallback. Fires only
  // on ttsStatus.status === "gave_up" — the point voice_adapter.py has
  // definitively failed to speak this turn server-side (TTS provider outage,
  // exhausted quota, etc.), not on every "retrying" tick. Free, unlimited,
  // built into every mainstream browser — the interview keeps a voice even
  // when the server-side provider is completely down. Lower voice quality
  // than the real provider, which is the acceptable tradeoff for "never
  // fully silent" over "perfect voice or nothing."
  useEffect(() => {
    if (ttsStatus?.status !== "gave_up" || !ttsStatus.text) return;
    if (typeof window === "undefined" || !("speechSynthesis" in window)) {
      console.warn("[TTS-FALLBACK] Web Speech API unavailable in this browser; turn stays silent.");
      return;
    }
    // Cancel any still-pending fallback utterance before queuing a new one —
    // mirrors the server-side barge-in/interruption behavior rather than
    // letting stale turns queue up and speak out of order.
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(ttsStatus.text);
    utterance.lang = ttsStatus.language === "ar" ? "ar-SA" : "en-US";
    window.speechSynthesis.speak(utterance);
  }, [ttsStatus]);

  const handleControl = (control: string) => { if (!isCompleted) realtimeService?.sendControlIntent(control as never); };
  const handleCodeSubmit = () => {
    setCodeStatus(t('workspace.answerSubmitted'));
    realtimeService?.sendControlIntent("SUBMIT_CODE", { code, language: selectedLanguage });
  };

  const handleConfirmEnd = () => {
    setIsEndingSession(true);
    setIsEndDialogOpen(false);
    handleControl("END_INTERVIEW");
  };

  // 9H: MCQ selection + submission. Matches controller.py's SUBMIT_MCQ_ANSWER
  // handler exactly — payload key is selected_option_ids (a list even for
  // single-select), grading is a strict set-equality check server-side.
  const toggleMcqOption = (optionId: string) => {
    if (mcqSubmitted) return;
    setSelectedOptionIds((prev) => {
      if (mcqIsMultiSelect) {
        return prev.includes(optionId) ? prev.filter((id) => id !== optionId) : [...prev, optionId];
      }
      return [optionId];
    });
  };
  const handleMcqSubmit = () => {
    if (selectedOptionIds.length === 0) return;
    setMcqSubmitted(true);
    realtimeService?.sendControlIntent("SUBMIT_MCQ_ANSWER", { selected_option_ids: selectedOptionIds });
  };

  if (isCompleted) {
    return <SessionEndedScreen session={session} />;
  }

  if (!state?.phase) {
    return <AgentConnectingScreen />;
  }

  return (
    <div className="h-[100dvh] flex flex-col w-full bg-background text-foreground overflow-hidden">
      <header className="border-b bg-white">
        <div className="mx-auto flex min-h-16 max-w-[1440px] items-center justify-between gap-4 px-4 py-3 sm:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex items-center gap-2 font-bold text-xl tracking-tight text-primary hidden sm:flex">
              <span dir="ltr" className="inline-block">e&</span> <span className="text-muted-foreground font-normal">|</span> هِمّة
            </div>
            <div className="min-w-0 sm:ms-4 sm:ps-4 sm:border-s">
              <p className="truncate text-sm font-semibold text-foreground">{session.role || t('workspace.session')}</p>
              <p className="text-xs text-muted-foreground">
                {sectionProgressLabel ? sectionProgressLabel : phaseLabel}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-4 text-xs text-muted-foreground sm:gap-6">
            <LanguageToggle />
            <span className="hidden items-center gap-2 sm:flex">
              <span className={`h-2 w-2 rounded-full ${isCompleted ? "bg-muted-foreground" : state?.phase === "WAITING_ROOM" ? "bg-blue-400" : "bg-success"}`} />
              {isCompleted ? t('workspace.sessionEnded') : state?.phase === "WAITING_ROOM" ? t('workspace.phase.waitingRoom') : t('workspace.liveConnection')}
            </span>
            {/* Show timer always except during WAITING_ROOM (clock is paused). */}
            {state?.phase !== "WAITING_ROOM" && (
              <span className="flex items-center gap-1.5 rounded-md border bg-muted/30 px-2.5 py-1.5 font-semibold tabular-nums text-foreground">
                <Timer className="h-3.5 w-3.5 text-muted-foreground" />
                {formatTime(displaySeconds)}
              </span>
            )}
            
            <button
              onClick={() => setIsEndDialogOpen(true)}
              disabled={isCompleted || isEndingSession}
              className="hidden sm:flex items-center gap-1.5 rounded-md bg-destructive/10 px-3 py-1.5 text-xs font-semibold text-destructive transition hover:bg-destructive hover:text-destructive-foreground disabled:opacity-50"
            >
              {isEndingSession ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <LogOut className="h-3.5 w-3.5" />}
              End Session
            </button>
          </div>
        </div>
      </header>

      {/* Audit fix (2026-08-27): relative wrapper around main + the sticky
          controller bar, purely so TtsRetryOverlay (an absolute inset-0
          child) can blur just the live interview content below the header
          — the header itself (logo, phase label, timer, End Session) is a
          SIBLING above this wrapper, outside its bounding box, so it stays
          fully visible and clickable through the overlay with no z-index/
          height math needed. */}
      <div className="relative flex flex-1 min-h-0 flex-col">
      <main className={`mx-auto grid w-full flex-1 min-h-0 max-w-[1440px] grid-cols-1 p-3 sm:p-4 lg:overflow-hidden ${state?.phase === "WAITING_ROOM" ? "place-items-center" : "gap-4 lg:grid-cols-[minmax(0,1fr)_340px] lg:gap-6"}`}>

        {/* WAITING_ROOM: full-width, replaces the normal two-column layout */}
        {state?.phase === "WAITING_ROOM" ? (
          <WaitingRoomScreen
            completedSectionIndex={sectionsProgress?.completed ?? 1}
            totalSections={sectionsProgress?.total ?? 1}
            completedSectionType={completedSectionType}
            nextSectionType={nextSectionType}
            onContinue={() => handleControl("PROCEED_TO_NEXT_SECTION")}
          />
        ) : isOrderedCoding ? (
          question ? (
            <CodingSectionView
              question={question}
              isAgentSpeaking={isAgentSpeaking}
              isMicrophoneEnabled={isMicrophoneEnabled}
              code={code}
              setCode={setCode}
              selectedLanguage={selectedLanguage}
              setSelectedLanguage={setSelectedLanguage}
              hasConfigStarterCode={hasConfigStarterCode}
              codingConfigConstraints={codingConfigConstraints}
              codeStatus={codeStatus}
              onCodeSubmit={handleCodeSubmit}
              allowedControls={state?.allowed_controls || []}
              isCompleted={isCompleted}
              onToggleMicrophone={() => room.localParticipant.setMicrophoneEnabled(!isMicrophoneEnabled)}
              onSendControl={handleControl}
              backendState={state}
              hasNextSection={hasNextSection}
              formattedTime={formatTime(displaySeconds)}
            />
          ) : (
            <div className="col-span-full flex flex-1 items-center justify-center rounded-xl border bg-card"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
          )
        ) : isOrderedMcq ? (
          question ? (
            <McqSectionView
              question={question}
              isAgentSpeaking={isAgentSpeaking}
              isMicrophoneEnabled={isMicrophoneEnabled}
              mcqOptions={mcqOptions}
              selectedOptionIds={selectedOptionIds}
              onToggleOption={toggleMcqOption}
              mcqIsMultiSelect={mcqIsMultiSelect}
              mcqSubmitted={mcqSubmitted}
              onMcqSubmit={handleMcqSubmit}
              allowedControls={state?.allowed_controls || []}
              isCompleted={isCompleted}
              onToggleMicrophone={() => room.localParticipant.setMicrophoneEnabled(!isMicrophoneEnabled)}
              onSendControl={handleControl}
              backendState={state}
              hasNextSection={hasNextSection}
              formattedTime={formatTime(displaySeconds)}
            />
          ) : (
            <div className="col-span-full flex flex-1 items-center justify-center rounded-xl border bg-card"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
          )
        ) : (
          <VerbalSectionView
            question={question}
            isCompleted={isCompleted}
            isAgentSpeaking={isAgentSpeaking}
            isMicrophoneEnabled={isMicrophoneEnabled}
            isTechnical={isTechnical}
            hasEditor={hasEditor}
            characterState={characterState}
            agentAudioTrack={agentAudioTrack}
            code={code}
            setCode={setCode}
            selectedLanguage={selectedLanguage}
            setSelectedLanguage={setSelectedLanguage}
            hasConfigStarterCode={hasConfigStarterCode}
            codingConfigConstraints={codingConfigConstraints}
            codeStatus={codeStatus}
            onCodeSubmit={handleCodeSubmit}
            currentSectionType={state?.sections_progress?.current_section_type}
            ReportLoadingState={ReportLoadingState}
            allowedControls={state?.allowed_controls || []}
            onToggleMicrophone={() => room.localParticipant.setMicrophoneEnabled(!isMicrophoneEnabled)}
            onSendControl={handleControl}
            backendState={state}
            hasNextSection={hasNextSection}
            visibleTranscripts={visibleTranscripts}
            transcriptRef={transcriptRef}
          />
        )}
      </main>

      {/* Global Unified Controller */}
      {state?.phase !== "WAITING_ROOM" && (
        <div className="sticky bottom-0 z-20 w-full border-t bg-background/95 px-4 py-3 backdrop-blur sm:py-4">
          <div className="mx-auto max-w-[1440px]">
            <InterviewController
              isCompleted={isCompleted}
              allowedControls={state?.allowed_controls || []}
              isMicrophoneEnabled={isMicrophoneEnabled}
              onToggleMicrophone={() => room?.localParticipant?.setMicrophoneEnabled(!isMicrophoneEnabled)}
              onSendControl={handleControl}
              backendState={state}
              hasNextSection={hasNextSection}
            />
          </div>
        </div>
      )}

      <TtsRetryOverlay ttsStatus={ttsStatus} />
      </div>

      <EndInterviewDialog
        isOpen={isEndDialogOpen}
        onCancel={() => setIsEndDialogOpen(false)}
        onConfirm={handleConfirmEnd}
      />
    </div>
  );
}
