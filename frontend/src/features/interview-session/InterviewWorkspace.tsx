import { useEffect, useMemo, useRef, useState } from "react";
import { useLocalParticipant, useRoomContext, useTracks } from "@livekit/components-react";
import { Track, type RemoteAudioTrack } from "livekit-client";
import { Loader2, Timer, LogOut, Video, VideoOff, Maximize2, Minimize2 } from "lucide-react";
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
import { FullscreenGraceOverlay } from "./FullscreenGraceOverlay";
import { InterviewController } from "./InterviewController";
import { EndInterviewDialog } from "./EndInterviewDialog";
import { isFullscreenActive, requestFullscreen } from "../../lib/fullscreen";
import { terminateInterview } from "../../services/api/interviews";
import { useFaceDetectionMonitor } from "./useFaceDetectionMonitor";

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

interface InterviewWorkspaceProps {
  session: InterviewSessionResponse;
  onCompleted?: () => void;
  /** PR-B: called when the 10s fullscreen grace expires and the session is
   *  auto-terminated so the parent can swap to the FullscreenTerminatedScreen
   *  rather than showing the normal "thank you" completion screen. */
  onFullscreenTerminated?: () => void;
}

const PHASE_LABELS: Record<string, string> = {
  CREATED: "preparation", BRIEFING: "intro", WELCOME: "intro", BACKGROUND: "background",
  WAITING_ROOM: "waitingRoom",
  TECHNICAL_INTRO: "technical", TECHNICAL: "technical", CODING: "technical",
  CLOSING: "closing", COMPLETED: "completed", TERMINATED: "ended",
};

function formatTime(seconds = 0) {
  return `${Math.floor(seconds / 60).toString().padStart(2, "0")}:${Math.max(0, seconds % 60).toString().padStart(2, "0")}`;
}

export function InterviewWorkspace({ session, onCompleted, onFullscreenTerminated }: InterviewWorkspaceProps) {
  const { t } = useTranslation();
  const room = useRoomContext();
  const { isMicrophoneEnabled, isCameraEnabled } = useLocalParticipant();
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
  // PR-B: visible 10s grace countdown after a fullscreen exit — null means
  // no countdown active. After grace expires, the interview is terminated.
  // isFullscreenBlockedRef survives effect re-runs (realtimeService changes)
  // so clearGrace() in effect cleanup never wipes an in-progress countdown.
  const [fullscreenGraceSeconds, setFullscreenGraceSeconds] = useState<number | null>(null);
  const [isFullscreenBlocked, setIsFullscreenBlocked] = useState(false);
  const isFullscreenBlockedRef = useRef(false);  // survives effect re-runs
  // Track current fullscreen state for the toggle button in the header.
  const [isFullscreenNow, setIsFullscreenNow] = useState(false);
  const timerDeadlineRef = useRef<number | null>(null);
  const fullscreenGraceDeadlineRef = useRef<number | null>(null);
  const fullscreenGraceTimeoutRef = useRef<number | null>(null);
  const fullscreenGraceIntervalRef = useRef<number | null>(null);
  const transcriptRef = useRef<HTMLDivElement>(null);
  // Session-finalization-contract fix (2026-09-01): sendControlIntent's
  // reliable data channel has no application-level ack -- if the agent
  // never replies (crashed, lost its lease, message dropped), isCompleted
  // would never flip and "Ending session..." would spin forever while the
  // room/recording kept running. endFallbackTimeoutRef backs that with a
  // REST fallback (see handleConfirmEnd); isCompletedRef lets that
  // timeout's closure read the latest value instead of a stale one.
  const isCompletedRef = useRef(false);
  const endFallbackTimeoutRef = useRef<number | null>(null);
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

  // PR-B (docs/proctoring-architecture.md): fullscreen-exit / tab-hidden /
  // window-blurred detection, mounted once at this top level so it covers
  // every section view (Verbal/Coding/MCQ) and WaitingRoomScreen uniformly
  // rather than being duplicated per view. Paused during WAITING_ROOM (and
  // once completed) — mirrors the existing clock-pause precedent above
  // (time_remaining_seconds == null there): waiting-room time is explicitly
  // FREE/UNCLOCKED per CURRENT_DECISIONS.md, so a candidate leaving
  // fullscreen on that intentional break should not be flagged.
  const monitoringActive = !isCompleted && state?.phase !== "WAITING_ROOM";
  useEffect(() => {
    const clearGrace = () => {
      // Only wipe the visual countdown — do NOT clear isFullscreenBlocked
      // here, because clearGrace() is called in effect cleanup on every
      // realtimeService re-mount, which would kill an in-progress countdown.
      setFullscreenGraceSeconds(null);
      fullscreenGraceDeadlineRef.current = null;
      if (fullscreenGraceTimeoutRef.current != null) {
        window.clearTimeout(fullscreenGraceTimeoutRef.current);
        fullscreenGraceTimeoutRef.current = null;
      }
      if (fullscreenGraceIntervalRef.current != null) {
        window.clearInterval(fullscreenGraceIntervalRef.current);
        fullscreenGraceIntervalRef.current = null;
      }
    };

    if (!monitoringActive) {
      // Only clear if we weren't already blocked — avoids wiping a
      // persistent block when the phase briefly flickers.
      if (!isFullscreenBlockedRef.current) {
        clearGrace();
      }
      return;
    }

    const onFullscreenChange = () => {
      if (isFullscreenActive()) {
        // Returned to fullscreen — cancel grace and unblock.
        clearGrace();
        isFullscreenBlockedRef.current = false;
        setIsFullscreenBlocked(false);
        return;
      }
      // Already counting down — don't restart.
      if (fullscreenGraceDeadlineRef.current != null) return;
      // Exited fullscreen — start the visible 10s countdown.
      const GRACE_MS = 10000;
      const deadline = Date.now() + GRACE_MS;
      fullscreenGraceDeadlineRef.current = deadline;
      setFullscreenGraceSeconds(10);
      fullscreenGraceIntervalRef.current = window.setInterval(() => {
        const remaining = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
        setFullscreenGraceSeconds(remaining);
      }, 250);
      fullscreenGraceTimeoutRef.current = window.setTimeout(() => {
        realtimeService?.sendIntegrityEvent("FULLSCREEN_EXITED", {
          severity: "high",
          grace_period_seconds: 10,
        });
        clearGrace();
        // Mute the candidate's mic immediately so the agent gets no more
        // audio input and stops speaking / processing.
        room?.localParticipant?.setMicrophoneEnabled(false).catch(() => {});
        // Grace expired — terminate the interview.
        isFullscreenBlockedRef.current = true;
        setIsFullscreenBlocked(true);
        // Send the termination signal to the agent.
        realtimeService?.sendControlIntent("END_INTERVIEW" as never);
        // Session-finalization-contract fix (2026-09-01): onFullscreenTerminated
        // below unmounts <LiveKitRoom>, which disconnects the CANDIDATE's
        // own connection -- it does not disconnect the agent or end the
        // room, so without this the recording/room could keep running
        // indefinitely waiting on an agent that may never process the
        // data-channel message above. This is a policy-driven forced end
        // (not a "wait and see" like handleConfirmEnd), so finalize
        // server-side immediately rather than racing/timing out first.
        if (session.id) terminateInterview(session.id).catch(() => {});
        // Notify the parent so it can swap to FullscreenTerminatedScreen.
        onFullscreenTerminated?.();
      }, GRACE_MS);
    };

    const onVisibilityChange = () => {
      if (document.hidden) {
        realtimeService?.sendIntegrityEvent("TAB_HIDDEN", { severity: "low" });
      }
    };

    const onWindowBlur = () => {
      realtimeService?.sendIntegrityEvent("WINDOW_BLURRED", { severity: "low" });
    };

    // PR-C manual-test finding (2026-09-01): a real fullscreen exit
    // produced no grace overlay at all — this handler was reading the
    // unprefixed document.fullscreenElement directly (fixed above to use
    // isFullscreenActive(), which already correctly checks every vendor
    // prefix — lib/fullscreen.ts's requestFullscreen() already did this
    // for entering, this file just never matched it for reading state
    // back out) and only listening for the unprefixed "fullscreenchange"
    // event. On any browser that fires a prefixed variant instead, this
    // handler never ran at all. Listening for all four is harmless on
    // browsers that only ever fire the unprefixed one.
    const fullscreenChangeEvents = ["fullscreenchange", "webkitfullscreenchange", "mozfullscreenchange", "MSFullscreenChange"];
    fullscreenChangeEvents.forEach((evt) => document.addEventListener(evt, onFullscreenChange));
    document.addEventListener("visibilitychange", onVisibilityChange);
    window.addEventListener("blur", onWindowBlur);
    // Sync the header fullscreen-toggle button state.
    const syncFullscreenState = () => setIsFullscreenNow(isFullscreenActive());
    fullscreenChangeEvents.forEach((evt) => document.addEventListener(evt, syncFullscreenState));
    // Set initial state in case we're already in fullscreen when mounted.
    syncFullscreenState();
    return () => {
      fullscreenChangeEvents.forEach((evt) => document.removeEventListener(evt, onFullscreenChange));
      fullscreenChangeEvents.forEach((evt) => document.removeEventListener(evt, syncFullscreenState));
      document.removeEventListener("visibilitychange", onVisibilityChange);
      window.removeEventListener("blur", onWindowBlur);
      // NOTE: deliberately do NOT call clearGrace() here — that would wipe
      // the countdown every time realtimeService re-mounts. The refs
      // (fullscreenGraceTimeoutRef/IntervalRef) are long-lived and survive
      // the effect re-run, so the timers keep firing correctly.
    };
  }, [monitoringActive, realtimeService]);

  // PR-D (docs/proctoring-architecture.md): face-presence monitoring.
  // cameraTrackRefs mirrors the exact micTrackRefs pattern above, filtered
  // to the LOCAL participant instead of the agent -- this is the same
  // published camera track @livekit/components-react already created for
  // `video={true}` on <LiveKitRoom> (InterviewSession.tsx), never a second
  // getUserMedia call. undefined whenever no camera is published (denied,
  // or toggled off), which is exactly when useFaceDetectionMonitor must
  // (and does) stay inactive.
  const cameraTrackRefs = useTracks([Track.Source.Camera], { onlySubscribed: false });
  const localCameraTrack = cameraTrackRefs.find((ref) => ref.participant.isLocal)?.publication?.track?.mediaStreamTrack;
  useFaceDetectionMonitor({
    active: monitoringActive,
    cameraTrack: localCameraTrack,
    onFlag: (event, payload) => realtimeService?.sendIntegrityEvent(event, payload),
  });

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
    isCompletedRef.current = isCompleted;
    if (isCompleted && endFallbackTimeoutRef.current) {
      // The graceful path won the race -- the REST fallback below is no
      // longer needed.
      window.clearTimeout(endFallbackTimeoutRef.current);
      endFallbackTimeoutRef.current = null;
    }
    if (!isCompleted || !session.id) return;
    onCompleted?.();
  }, [isCompleted, session.id, onCompleted]);

  useEffect(() => {
    return () => {
      if (endFallbackTimeoutRef.current) window.clearTimeout(endFallbackTimeoutRef.current);
    };
  }, []);

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

  // Session-finalization-contract fix (2026-09-01): how long to wait for
  // the agent's own state_update acknowledging END_INTERVIEW before
  // assuming the round trip failed and forcing it server-side instead.
  // Generous enough to cover a real in-flight LLM turn, short enough that
  // a genuinely stuck session doesn't leave the candidate staring at
  // "Ending session..." for long.
  const END_SESSION_FALLBACK_MS = 6000;

  const handleConfirmEnd = () => {
    setIsEndingSession(true);
    setIsEndDialogOpen(false);
    room?.localParticipant?.setCameraEnabled(false).catch(() => {});
    room?.localParticipant?.setMicrophoneEnabled(false).catch(() => {});
    handleControl("END_INTERVIEW");

    if (endFallbackTimeoutRef.current) window.clearTimeout(endFallbackTimeoutRef.current);
    endFallbackTimeoutRef.current = window.setTimeout(() => {
      endFallbackTimeoutRef.current = null;
      if (isCompletedRef.current || !session.id) return;
      // The agent never acknowledged -- force-finalize server-side so the
      // room/recording actually stop and an Evaluation row is guaranteed,
      // instead of leaving the interview live with the candidate's camera
      // only LOOKING off. terminateInterview is idempotent (no-op if the
      // session already reached a terminal status by the time this fires).
      terminateInterview(session.id)
        .then(() => onCompleted?.())
        .catch(() => {
          // Best-effort: even if the REST call itself fails (network
          // blip), still flip the local UI so the candidate isn't stuck
          // on this screen forever -- the idle-disconnect sweep is the
          // last-resort backstop for the server-side state in that case.
          onCompleted?.();
        });
    }, END_SESSION_FALLBACK_MS);
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
            {/* PR-C: transparency indicator, same principle as PR-B's grace
                banner — the candidate should always be able to see at a
                glance whether their camera is actually on, not just have
                consented to it once at Start. Shown whenever the session
                isn't over; distinguishes "recording" from "camera denied/
                unavailable, proceeding audio-only" (per CURRENT_DECISIONS.md's
                graceful-degradation decision) rather than hiding that gap. */}
            {!isCompleted && (
              <span className="hidden items-center gap-1.5 sm:flex" title={isCameraEnabled ? t('workspace.cameraOn') : t('workspace.cameraOff')}>
                {isCameraEnabled ? (
                  <Video className="h-3.5 w-3.5 text-success" />
                ) : (
                  <VideoOff className="h-3.5 w-3.5 text-muted-foreground" />
                )}
              </span>
            )}
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
                onClick={async () => {
                  if (isFullscreenNow) {
                    await document.exitFullscreen?.();
                  } else {
                    await requestFullscreen();
                  }
                }}
                className="hidden sm:flex items-center gap-1.5 rounded-md border border-border bg-background/60 px-3 py-1.5 text-xs font-semibold text-foreground/80 transition hover:bg-muted"
                title={isFullscreenNow ? "Exit fullscreen" : "Enter fullscreen"}
              >
                {isFullscreenNow
                  ? <><Minimize2 className="h-3.5 w-3.5" />Exit Fullscreen</>
                  : <><Maximize2 className="h-3.5 w-3.5" />Fullscreen</>
                }
              </button>
            
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
              isLocked={isFullscreenBlocked}
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
      <FullscreenGraceOverlay secondsRemaining={fullscreenGraceSeconds} isBlocked={isFullscreenBlocked} />
      </div>

      <EndInterviewDialog
        isOpen={isEndDialogOpen}
        onCancel={() => setIsEndDialogOpen(false)}
        onConfirm={handleConfirmEnd}
      />
    </div>
  );
}
