import { useEffect, useMemo, useState } from "react";
import { useLocalParticipant, useRoomContext } from "@livekit/components-react";
import { CheckCircle2, Code2, HelpCircle, Mic, MicOff, Send, Timer } from "lucide-react";
import { InterviewRealtimeService } from "../../services/livekit/InterviewRealtimeService";
import { useInterviewStore } from "../../stores/InterviewContext";
import { InterviewController } from "./InterviewController";
import type { InterviewSessionResponse } from "../../types/api";

interface InterviewWorkspaceProps { session: InterviewSessionResponse; }

const PHASE_LABELS: Record<string, string> = {
  CREATED: "Preparation", BRIEFING: "Introduction", WELCOME: "Introduction", BACKGROUND: "Background",
  TECHNICAL_INTRO: "Technical interview", TECHNICAL: "Technical interview", CODING: "Technical interview",
  CLOSING: "Closing", COMPLETED: "Completed", TERMINATED: "Terminated",
};

function formatTime(seconds = 0) {
  const minutes = Math.floor(seconds / 60).toString().padStart(2, "0");
  const remainder = Math.max(0, seconds % 60).toString().padStart(2, "0");
  return `${minutes}:${remainder}`;
}

export function InterviewWorkspace({ session }: InterviewWorkspaceProps) {
  const room = useRoomContext();
  const { isMicrophoneEnabled } = useLocalParticipant();
  const { state, updateState, isAgentSpeaking, setIsAgentSpeaking, transcriptMessages, updateTranscript } = useInterviewStore();
  const [realtimeService, setRealtimeService] = useState<InterviewRealtimeService | null>(null);
  const [code, setCode] = useState("");
  const [codeStatus, setCodeStatus] = useState<string | null>(null);
  const question = state?.current_question;
  const isCompleted = state?.phase === "COMPLETED" || state?.phase === "TERMINATED";
  const isTechnical = ["TECHNICAL_INTRO", "TECHNICAL", "CODING"].includes(state?.phase || "");
  const hasEditor = Boolean(question?.coding_required);
  const phaseLabel = state?.phase ? (PHASE_LABELS[state.phase] || state.phase) : "Connecting";

  useEffect(() => {
    if (!room) return;
    const service = new InterviewRealtimeService(room, updateState, updateTranscript);
    setRealtimeService(service);
    const onSpeakersChanged = (speakers: Array<{ identity: string }>) => {
      setIsAgentSpeaking(speakers.some((speaker) => speaker.identity !== room.localParticipant.identity));
    };
    room.on("activeSpeakersChanged", onSpeakersChanged);
    return () => { room.off("activeSpeakersChanged", onSpeakersChanged); service.cleanup(); };
  }, [room, updateState, updateTranscript, setIsAgentSpeaking]);

  useEffect(() => {
    if (question?.starter_code && Object.keys(question.starter_code).length > 0) setCode(Object.values(question.starter_code)[0]);
    else setCode("");
    setCodeStatus(null);
  }, [question?.id, question?.starter_code]);

  useEffect(() => {
    if (!isCompleted || !session.id) return;
    const timer = setTimeout(() => { window.location.href = `/interviews/${session.id}/result`; }, 2000);
    return () => clearTimeout(timer);
  }, [isCompleted, session.id]);

  const visibleTranscripts = useMemo(() => transcriptMessages.slice(-8), [transcriptMessages]);
  const handleControl = (control: string) => { if (!isCompleted) realtimeService?.sendControlIntent(control as never); };
  const handleCodeSubmit = () => {
    setCodeStatus("Answer submitted.");
    handleControl("SUBMIT_CODE");
  };

  return (
    <div className="min-h-screen w-full bg-[#f6f7f9] text-foreground">
      <header className="border-b border-border bg-white">
        <div className="mx-auto flex min-h-16 max-w-[1440px] items-center justify-between gap-4 px-4 py-3 sm:px-8">
          <div className="flex min-w-0 items-center gap-4">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-primary text-sm font-semibold text-primary-foreground">P</div>
            <div className="min-w-0"><p className="truncate text-sm font-semibold">{session.role || "Interview session"}</p><p className="text-xs text-muted-foreground">{phaseLabel}</p></div>
          </div>
          <div className="flex items-center gap-4 text-xs text-muted-foreground sm:gap-6">
            <span className="hidden items-center gap-2 sm:flex"><span className={`h-2 w-2 rounded-full ${isCompleted ? "bg-muted-foreground" : "bg-emerald-500"}`} />{isCompleted ? "Ended" : "Live connection"}</span>
            <span className="flex items-center gap-1.5 font-medium text-foreground"><Timer className="h-4 w-4 text-muted-foreground" />{formatTime(state?.time_remaining_seconds)}</span>
          </div>
        </div>
      </header>

      <main className="mx-auto grid min-h-[calc(100vh-64px)] max-w-[1440px] grid-cols-1 gap-4 p-4 sm:p-6 lg:h-[calc(100vh-64px)] lg:grid-cols-[minmax(0,1fr)_340px] lg:gap-6 lg:overflow-hidden">
        <section className="flex min-w-0 flex-col gap-4 lg:min-h-0 lg:overflow-y-auto">
          <div className="flex items-center justify-between px-1"><div><p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">{isTechnical ? "Technical assessment" : "Interview"}</p><h1 className="mt-1 text-xl font-semibold tracking-tight sm:text-2xl">{question?.title || "Preparing your interview"}</h1></div>{question && <span className="shrink-0 text-xs text-muted-foreground">Question {state?.question_index} / {state?.total_questions}</span>}</div>

          <article className="border border-border bg-white p-5 shadow-sm sm:p-7 lg:max-h-[38vh] lg:overflow-y-auto">
            {isCompleted ? <div className="flex min-h-64 flex-col items-center justify-center gap-3 text-center"><CheckCircle2 className="h-10 w-10 text-emerald-600" /><h2 className="text-2xl font-semibold">Interview complete</h2><p className="text-sm text-muted-foreground">Your result is being prepared.</p></div> : question ? <div className="space-y-6">
              <div className="flex flex-wrap items-center gap-2 text-xs"><span className="rounded-md bg-primary/10 px-2 py-1 font-medium text-primary">{question.difficulty}</span><span className="rounded-md bg-muted px-2 py-1 text-muted-foreground">{question.competency}</span><span className="text-muted-foreground">{question.time_budget_minutes} min</span></div>
              <div className="max-w-4xl space-y-3"><h2 className="text-lg font-semibold sm:text-xl">Problem statement</h2><p className="whitespace-pre-line text-[15px] leading-7 text-muted-foreground">{question.problem_statement}</p></div>
              {question.examples.length > 0 && <div className="grid gap-3 sm:grid-cols-2">{question.examples.slice(0, 2).map((example, index) => <div key={index} className="border border-border bg-[#fafafa] p-3 text-xs"><p className="mb-2 font-semibold text-foreground">Example {index + 1}</p><pre className="overflow-auto whitespace-pre-wrap text-muted-foreground">{JSON.stringify(example, null, 2)}</pre></div>)}</div>}
              {question.constraints.length > 0 && <div><p className="mb-2 text-sm font-semibold">Constraints</p><ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">{question.constraints.map((constraint) => <li key={constraint}>{constraint}</li>)}</ul></div>}
            </div> : <div className="flex min-h-64 items-center justify-center text-sm text-muted-foreground">Waiting for the interviewer...</div>}
          </article>

          {isTechnical && question && hasEditor && <section className="border border-border bg-[#20252b] text-white shadow-sm lg:flex lg:min-h-0 lg:flex-1 lg:flex-col" aria-label="Coding workspace">
            <div className="flex items-center justify-between border-b border-white/10 px-4 py-3"><div className="flex items-center gap-2 text-sm font-medium"><Code2 className="h-4 w-4 text-sky-300" />Code answer</div><span className="text-xs text-white/50">{Object.keys(question.starter_code)[0] || "editor"}</span></div>
            <textarea value={code} onChange={(event) => setCode(event.target.value)} spellCheck={false} aria-label="Code answer" className="min-h-40 w-full resize-y bg-transparent p-4 font-mono text-sm leading-6 text-slate-100 outline-none placeholder:text-white/30 lg:min-h-0 lg:flex-1" placeholder="Write your solution here..." />
            <div className="flex flex-wrap items-center gap-2 border-t border-white/10 px-4 py-3"><button type="button" onClick={handleCodeSubmit} className="inline-flex items-center gap-2 rounded-md bg-sky-500 px-3 py-2 text-xs font-semibold text-white hover:bg-sky-400"><Send className="h-3.5 w-3.5" />Submit answer</button>{codeStatus && <span className="text-xs text-white/60" role="status">{codeStatus}</span>}</div>
          </section>}

          <InterviewController isCompleted={isCompleted} allowedControls={state?.allowed_controls || []} isMicrophoneEnabled={isMicrophoneEnabled} onToggleMicrophone={() => room.localParticipant.setMicrophoneEnabled(!isMicrophoneEnabled)} onSendControl={handleControl} backendState={state} />
        </section>

        <aside className="flex min-h-0 flex-col gap-4 lg:overflow-hidden">
          <section className="border border-border bg-white p-5 shadow-sm"><div className="flex items-center justify-between"><div><p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Interviewer</p><p className="mt-1 text-sm font-semibold">{isAgentSpeaking ? "Speaking" : "Listening"}</p></div><div className={`flex h-14 w-14 items-center justify-center rounded-full border ${isAgentSpeaking ? "border-primary/40 bg-primary/10" : "border-border bg-muted/40"}`}><span className={`h-5 w-5 rounded-full bg-primary ${isAgentSpeaking ? "animate-pulse" : "opacity-60"}`} /></div></div><div className="mt-5 h-1 overflow-hidden rounded-full bg-muted"><div className={`h-full rounded-full bg-primary transition-all ${isAgentSpeaking ? "w-3/4" : "w-1/4"}`} /></div></section>
          <section className="flex min-h-[280px] flex-1 flex-col border border-border bg-white shadow-sm"><div className="border-b border-border px-5 py-4"><p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Live transcript</p></div><div className="flex-1 space-y-4 overflow-y-auto p-5">{visibleTranscripts.length ? visibleTranscripts.map((message) => <div key={message.id} className="space-y-1"><p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">{message.speaker === "agent" ? "Interviewer" : "You"}</p><p className={`text-sm leading-6 ${message.speaker === "agent" ? "text-foreground" : "text-muted-foreground"}`}>{message.text}</p></div>) : <p className="text-sm leading-6 text-muted-foreground">Your conversation will appear here.</p>}</div></section>
          <div className="flex items-center gap-2 px-1 text-xs text-muted-foreground">{isMicrophoneEnabled ? <Mic className="h-3.5 w-3.5" /> : <MicOff className="h-3.5 w-3.5" />}<span>{isMicrophoneEnabled ? "Microphone on" : "Microphone muted"}</span><HelpCircle className="ml-auto h-3.5 w-3.5" /></div>
        </aside>
      </main>
    </div>
  );
}
