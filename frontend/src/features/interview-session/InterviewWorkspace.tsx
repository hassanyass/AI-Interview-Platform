import { useEffect, useMemo, useRef, useState } from "react";
import { useLocalParticipant, useRoomContext } from "@livekit/components-react";
import { CheckCircle2, Code2, HelpCircle, Mic, MicOff, Send, Timer, Volume2 } from "lucide-react";
import { InterviewRealtimeService } from "../../services/livekit/InterviewRealtimeService";
import { useInterviewStore } from "../../stores/InterviewContext";
import { InterviewController } from "./InterviewController";
import type { InterviewSessionResponse } from "../../types/api";
import InterviewerCharacter, { type InterviewerCharacterState } from "./InterviewerCharacter";

const AgentConnectingScreen = () => {
  const [progress, setProgress] = useState(15);
  const [status, setStatus] = useState("Connecting to server...");

  useEffect(() => {
    const timer1 = setTimeout(() => { setProgress(45); setStatus("Initializing AI interviewer..."); }, 800);
    const timer2 = setTimeout(() => { setProgress(80); setStatus("Preparing workspace..."); }, 2200);
    return () => { clearTimeout(timer1); clearTimeout(timer2); };
  }, []);

  return (
    <div className="min-h-screen w-full flex flex-col bg-[#f6f8fb] text-foreground">
      {/* Skeleton Header matching the actual workspace header */}
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex min-h-16 max-w-[1440px] items-center justify-between gap-4 px-4 py-3 sm:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-slate-950 text-sm font-semibold text-white shadow-sm">P</div>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-slate-950">Interview session</p>
              <p className="text-xs text-slate-500">Connecting...</p>
            </div>
          </div>
        </div>
      </header>

      {/* Main Centered Progress Card */}
      <main className="flex-1 flex items-center justify-center p-4">
        <div className="w-full max-w-sm rounded-xl border border-slate-200 bg-white p-6 shadow-[0_2px_8px_rgba(15,23,42,0.04)]">
          <h2 className="text-lg font-semibold text-slate-950 mb-1">Starting Interview</h2>
          <p className="text-sm text-slate-500 mb-6">{status}</p>
          
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
            <div 
              className="h-full rounded-full bg-sky-500 transition-all duration-700 ease-out" 
              style={{ width: `${progress}%` }} 
            />
          </div>
        </div>
      </main>
    </div>
  );
};

interface InterviewWorkspaceProps { session: InterviewSessionResponse; onCompleted?: () => void; }

const PHASE_LABELS: Record<string, string> = {
  CREATED: "Preparation", BRIEFING: "Introduction", WELCOME: "Introduction", BACKGROUND: "Background",
  TECHNICAL_INTRO: "Technical interview", TECHNICAL: "Technical interview", CODING: "Technical interview",
  CLOSING: "Closing", COMPLETED: "Completed", TERMINATED: "Ended",
};

function formatTime(seconds = 0) {
  return `${Math.floor(seconds / 60).toString().padStart(2, "0")}:${Math.max(0, seconds % 60).toString().padStart(2, "0")}`;
}

export function InterviewWorkspace({ session, onCompleted }: InterviewWorkspaceProps) {
  const room = useRoomContext();
  const { isMicrophoneEnabled } = useLocalParticipant();
  const { state, updateState, isAgentSpeaking, setIsAgentSpeaking, transcriptMessages, updateTranscript } = useInterviewStore();
  const [realtimeService, setRealtimeService] = useState<InterviewRealtimeService | null>(null);
  const [characterState, setCharacterState] = useState<InterviewerCharacterState>('idle');
  const [code, setCode] = useState("");
  const [codeStatus, setCodeStatus] = useState<string | null>(null);
  const [selectedLanguage, setSelectedLanguage] = useState("");
  const [displaySeconds, setDisplaySeconds] = useState(0);
  const timerDeadlineRef = useRef<number | null>(null);
  const transcriptRef = useRef<HTMLDivElement>(null);
  const question = state?.current_question;
  const isCompleted = state?.phase === "COMPLETED" || state?.phase === "TERMINATED";
  const isTechnical = ["TECHNICAL_INTRO", "TECHNICAL", "CODING"].includes(state?.phase || "");
  const hasEditor = Boolean(question?.coding_required);
  const phaseLabel = state?.phase ? (PHASE_LABELS[state.phase] || state.phase) : "Connecting";
  const visibleTranscripts = useMemo(() => transcriptMessages.slice(-8), [transcriptMessages]);

  useEffect(() => {
    if (isTechnical || isCompleted) {
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
  }, [isTechnical, isCompleted, isAgentSpeaking, isMicrophoneEnabled, room?.localParticipant?.isSpeaking]);

  // State updates are event-driven, so keep the visible clock running locally
  // between authoritative agent updates. The backend remains the source of
  // truth whenever a new state packet arrives.
  useEffect(() => {
    if (state?.time_remaining_seconds == null) return;
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
    const service = new InterviewRealtimeService(room, updateState, updateTranscript);
    setRealtimeService(service);
    const onSpeakersChanged = (speakers: Array<{ identity: string }>) => setIsAgentSpeaking(speakers.some((speaker) => speaker.identity !== room.localParticipant.identity));
    room.on("activeSpeakersChanged", onSpeakersChanged);
    return () => { room.off("activeSpeakersChanged", onSpeakersChanged); service.cleanup(); };
  }, [room, updateState, updateTranscript, setIsAgentSpeaking]);

  useEffect(() => {
    const languages = question?.supported_languages || Object.keys(question?.starter_code || {});
    setSelectedLanguage(languages[0] || "");
    if (question?.starter_code && Object.keys(question.starter_code).length > 0) setCode(question.starter_code[languages[0]] || Object.values(question.starter_code)[0]);
    else setCode("");
    setCodeStatus(null);
  }, [question?.id, question?.starter_code, question?.supported_languages]);

  useEffect(() => {
    if (!isCompleted || !session.id) return;
    onCompleted?.();
    const timer = setTimeout(() => { window.location.href = `/interviews/${session.id}/result`; }, 2000);
    return () => clearTimeout(timer);
  }, [isCompleted, session.id, onCompleted]);

  const handleControl = (control: string) => { if (!isCompleted) realtimeService?.sendControlIntent(control as never); };
  const handleCodeSubmit = () => {
    setCodeStatus("Answer submitted.");
    realtimeService?.sendControlIntent("SUBMIT_CODE", { code, language: selectedLanguage });
  };

  if (!state?.phase) {
    return <AgentConnectingScreen />;
  }

  return (
    <div className="min-h-screen w-full bg-[#f6f8fb] text-foreground">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex min-h-16 max-w-[1440px] items-center justify-between gap-4 px-4 py-3 sm:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-slate-950 text-sm font-semibold text-white shadow-sm">P</div>
            <div className="min-w-0"><p className="truncate text-sm font-semibold text-slate-950">{session.role || "Interview session"}</p><p className="text-xs text-slate-500">{phaseLabel}</p></div>
          </div>
          <div className="flex items-center gap-4 text-xs text-slate-500 sm:gap-6"><span className="hidden items-center gap-2 sm:flex"><span className={`h-2 w-2 rounded-full ${isCompleted ? "bg-slate-300" : "bg-emerald-500"}`} />{isCompleted ? "Session ended" : "Live connection"}</span><span className="flex items-center gap-1.5 rounded-md border border-slate-200 bg-slate-50 px-2.5 py-1.5 font-semibold tabular-nums text-slate-700"><Timer className="h-3.5 w-3.5 text-slate-400" />{formatTime(displaySeconds)}</span></div>
        </div>
      </header>

      <main className="mx-auto grid min-h-[calc(100vh-64px)] max-w-[1440px] grid-cols-1 gap-4 p-4 sm:p-6 lg:h-[calc(100vh-64px)] lg:grid-cols-[minmax(0,1fr)_340px] lg:gap-6 lg:overflow-hidden">
        <section className="flex min-w-0 flex-col gap-4 lg:min-h-0 lg:overflow-hidden">
          <div className="flex items-end justify-between gap-4 px-1"><div><p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">{isTechnical ? "Technical assessment" : "Interview"}</p><h1 className="mt-1 text-xl font-semibold tracking-tight text-slate-950 sm:text-2xl">{question?.title || "Preparing your interview"}</h1></div>{question && <span className="shrink-0 rounded-md bg-slate-100 px-2 py-1 text-xs font-medium text-slate-500">Technical problem</span>}</div>

          <div className={`flex items-center gap-3 rounded-lg border px-4 py-3 text-sm ${isAgentSpeaking ? "border-sky-200 bg-sky-50 text-sky-900" : "border-emerald-200 bg-emerald-50 text-emerald-900"}`} role="status" aria-live="polite"><span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md ${isAgentSpeaking ? "bg-sky-100 text-sky-600" : "bg-emerald-100 text-emerald-600"}`}>{isAgentSpeaking ? <Volume2 className="h-4 w-4" /> : <Mic className="h-4 w-4" />}</span><span>{isAgentSpeaking ? "The interviewer is speaking. Listen for the next prompt." : "You have the floor. Take your time and explain your thinking."}</span></div>

          {isTechnical && question && hasEditor ? <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
            <article className="flex min-h-0 min-w-0 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-[0_2px_8px_rgba(15,23,42,0.04)]">
              <div className="shrink-0 border-b border-slate-100 px-5 py-4 sm:px-7"><div className="flex flex-wrap items-center gap-2 text-xs"><span className="rounded-md bg-sky-50 px-2 py-1 font-semibold capitalize text-sky-700">{question.difficulty}</span><span className="rounded-md bg-slate-100 px-2 py-1 text-slate-600">{question.competency}</span>{question.time_budget_minutes && <span className="text-slate-400">{question.time_budget_minutes} min</span>}</div></div>
              <div className="min-h-0 max-h-[45vh] flex-1 overflow-y-auto px-5 py-6 sm:px-7 lg:max-h-none"><div className="space-y-3"><h2 className="text-base font-semibold text-slate-950 sm:text-lg">Problem statement</h2><p className="whitespace-pre-line text-[15px] leading-7 text-slate-600">{question.problem_statement}</p></div>{question.examples.length > 0 && <div className="mt-6 grid gap-3">{question.examples.map((example, index) => <div key={index} className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs"><p className="mb-2 font-semibold text-slate-700">Example {index + 1}</p><pre className="overflow-auto whitespace-pre-wrap leading-5 text-slate-500">{JSON.stringify(example, null, 2)}</pre></div>)}</div>}{question.constraints.length > 0 && <div className="mt-6"><p className="mb-2 text-sm font-semibold text-slate-800">Constraints</p><ul className="grid gap-1.5 text-sm text-slate-600">{question.constraints.map((constraint) => <li key={constraint} className="flex gap-2"><span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-sky-500" />{constraint}</li>)}</ul></div>}</div>
            </article>
            <section className="flex min-h-[360px] min-w-0 flex-col overflow-hidden border border-slate-800 bg-[#20252b] text-white shadow-[0_8px_20px_rgba(15,23,42,0.12)]" aria-label="Coding workspace"><div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-white/10 px-4 py-3"><div className="flex items-center gap-2 text-sm font-medium"><Code2 className="h-4 w-4 text-sky-300" />Code answer</div><div className="flex items-center gap-2 text-xs text-white/50"><span>Language</span><select value={selectedLanguage} onChange={(event) => { setSelectedLanguage(event.target.value); if (question.starter_code[event.target.value]) setCode(question.starter_code[event.target.value]); }} className="rounded-md border border-white/10 bg-white/5 px-2 py-1.5 text-xs text-slate-200 outline-none"><option className="bg-slate-800" value="">Select</option>{(question.supported_languages.length ? question.supported_languages : Object.keys(question.starter_code)).map((language) => <option className="bg-slate-800" key={language} value={language}>{language}</option>)}</select></div></div><textarea value={code} onChange={(event) => setCode(event.target.value)} spellCheck={false} aria-label="Code answer" className="min-h-0 w-full flex-1 resize-none overflow-auto bg-transparent p-4 font-mono text-sm leading-6 text-slate-100 outline-none placeholder:text-white/30" placeholder="Write your solution here..." /><div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-t border-white/10 px-4 py-3"><span className="text-xs text-white/45">Submit once you are ready to finish the technical problem.</span><button type="button" onClick={handleCodeSubmit} className="inline-flex items-center gap-2 rounded-md bg-sky-500 px-3 py-2 text-xs font-semibold text-white transition hover:bg-sky-400"><Send className="h-3.5 w-3.5" />Submit answer</button>{codeStatus && <span className="sr-only" role="status">{codeStatus}</span>}</div></section>
          </div> : <article className="flex flex-col min-h-0 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-[0_2px_8px_rgba(15,23,42,0.04)]"><div className="shrink-0 border-b border-slate-100 px-5 py-4 sm:px-7 z-10 bg-white"><div className="flex flex-wrap items-center gap-2 text-xs"><span className="rounded-md bg-sky-50 px-2 py-1 font-semibold capitalize text-sky-700">{question?.difficulty || "Background Discussion"}</span>{question?.competency && <span className="rounded-md bg-slate-100 px-2 py-1 text-slate-600">{question.competency}</span>}{question?.time_budget_minutes && <span className="text-slate-400">{question.time_budget_minutes} min</span>}</div></div>{isCompleted ? <div className="flex-1 flex flex-col items-center justify-center gap-3 px-5 text-center bg-slate-50 min-h-[400px]"><span className="flex h-12 w-12 items-center justify-center rounded-xl bg-emerald-50 text-emerald-600"><CheckCircle2 className="h-6 w-6" /></span><h2 className="text-2xl font-semibold text-slate-950">Interview complete</h2><p className="text-sm text-slate-500">Your result is being prepared.</p></div> : question ? <div className="flex-1 overflow-y-auto space-y-6 px-5 py-6 sm:px-7"><div className="space-y-3"><h2 className="text-base font-semibold text-slate-950 sm:text-lg">Problem statement</h2><p className="whitespace-pre-line text-[15px] leading-7 text-slate-600">{question.problem_statement}</p></div></div> : <div className="flex-1 relative flex items-end justify-center overflow-hidden bg-slate-50/50 pt-8 min-h-[400px]"><InterviewerCharacter state={characterState} size="medium" presence={true} /></div>}</article>}

          <div className="sticky bottom-0 z-10 -mx-1 border-t border-slate-200 bg-[#f6f8fb]/95 px-1 py-3 backdrop-blur sm:py-4"><InterviewController isCompleted={isCompleted} allowedControls={state?.allowed_controls || []} isMicrophoneEnabled={isMicrophoneEnabled} onToggleMicrophone={() => room.localParticipant.setMicrophoneEnabled(!isMicrophoneEnabled)} onSendControl={handleControl} backendState={state} /></div>
        </section>

        <aside className="flex min-h-0 flex-col gap-4 lg:overflow-hidden"><section className="rounded-xl border border-slate-200 bg-white p-5 shadow-[0_2px_8px_rgba(15,23,42,0.04)]"><div className="flex items-center justify-between"><div><p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">Interviewer</p><p className="mt-2 text-sm font-semibold text-slate-950">{isAgentSpeaking ? "Speaking" : "Listening"}</p></div><div className={`flex h-12 w-12 items-center justify-center rounded-xl ${isAgentSpeaking ? "bg-sky-50 text-sky-600" : "bg-slate-100 text-slate-400"}`}>{isAgentSpeaking ? <Volume2 className="h-5 w-5 animate-pulse" /> : <Mic className="h-5 w-5" />}</div></div><div className="mt-5 h-1 overflow-hidden rounded-full bg-slate-100"><div className={`h-full rounded-full bg-sky-500 transition-all ${isAgentSpeaking ? "w-3/4" : "w-1/4"}`} /></div></section><section className="flex min-h-[280px] flex-1 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-[0_2px_8px_rgba(15,23,42,0.04)]"><div className="flex items-center justify-between border-b border-slate-100 px-5 py-4"><div><p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">Live transcript</p><p className="mt-1 text-xs text-slate-400">Finalized conversation turns</p></div><span className="rounded bg-slate-100 px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500">Live</span></div><div ref={transcriptRef} className="flex-1 space-y-4 overflow-y-auto p-5">{visibleTranscripts.length ? visibleTranscripts.map((message) => <div key={message.id} className="border-l-2 border-slate-200 pl-3"><p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-400">{message.speaker === "agent" ? "Interviewer" : "You"}</p><p className={`mt-1 text-sm leading-6 ${message.speaker === "agent" ? "text-slate-800" : "text-slate-500"}`}>{message.text}</p></div>) : <p className="text-sm leading-6 text-slate-400">Your conversation will appear here.</p>}</div></section><div className="flex items-center gap-2 px-1 text-xs text-slate-500">{isMicrophoneEnabled ? <Mic className="h-3.5 w-3.5 text-emerald-500" /> : <MicOff className="h-3.5 w-3.5 text-slate-400" />}<span>{isMicrophoneEnabled ? "Microphone on" : "Microphone muted"}</span><HelpCircle className="ml-auto h-3.5 w-3.5 text-slate-400" /></div></aside>
      </main>
    </div>
  );
}
