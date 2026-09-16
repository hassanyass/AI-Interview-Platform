import React, { useRef, useState } from "react";
import { VerbalSectionView } from "../../features/interview-session/VerbalSectionView";
import type { StateUpdatePayload } from "../../types/realtime";

/**
 * DEV-ONLY visual harness for the verbal stage (registered in App.tsx only
 * when import.meta.env.DEV). The real workspace needs a LiveKit room and a
 * live agent; this renders VerbalSectionView with mock state so the header,
 * stepper, caption and transition strip can be reviewed and iterated on
 * without starting an interview. Not shipped in production builds.
 */
export default function VerbalPreview() {
  const [subsection, setSubsection] = useState<"BACKGROUND" | "DISCUSSION" | null>("BACKGROUND");
  const [speaking, setSpeaking] = useState(true);
  const [bgIndex, setBgIndex] = useState(1);
  const [bonus, setBonus] = useState(0);
  const transcriptRef = useRef<HTMLDivElement>(null!) as React.RefObject<HTMLDivElement>;

  const question = subsection === "BACKGROUND"
    ? { id: "bg-1", title: "Current role responsibilities", problem_statement: "In your most recent position as a Senior Machine Learning Engineer, what did you own day to day?", difficulty: "mid", competency: "background:recent_role", hints: [], expected_concepts: [], follow_up_topics: [], time_budget_minutes: 0, coding_required: false, examples: [], constraints: [], starter_code: {}, supported_languages: [], config: {} }
    : subsection === "DISCUSSION"
      ? { id: "hr-1", title: "Ownership", problem_statement: "Tell me about a system you owned end to end.", difficulty: "mid", competency: "ownership", hints: [], expected_concepts: [], follow_up_topics: [], time_budget_minutes: 0, coding_required: false, examples: [], constraints: [], starter_code: {}, supported_languages: [], config: {} }
      : null;

  const state = {
    session_id: "preview", phase: "BACKGROUND", sub_phase: null, current_question: question as any,
    question_index: 0, total_questions: 4, questions_completed: 0, questions_skipped: 0, hints_used: 0, max_hints: 0,
    last_question_outcome: null, allowed_controls: ["SKIP_QUESTION", "END_INTERVIEW", ...(subsection === "BACKGROUND" ? ["SKIP_BACKGROUND"] : [])],
    time_remaining_seconds: 598, verbal_subsection: subsection, background_total: subsection ? 3 : 0,
    background_index: subsection === "BACKGROUND" ? bgIndex : null,
    background_time_remaining_seconds: subsection === "BACKGROUND" ? 298 : null,
    discussion_index: subsection === "DISCUSSION" ? 1 : null, discussion_total: subsection ? 2 : 0,
    time_bonus_granted_seconds: bonus ? 120 : null, time_bonus_total_seconds: bonus,
  } as unknown as StateUpdatePayload;

  return (
    <div className="h-[100dvh] flex flex-col w-full bg-background text-foreground overflow-hidden">
      <header className="border-b bg-white">
        <div className="mx-auto flex min-h-16 max-w-[1440px] items-center justify-between gap-4 px-4 py-3 sm:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex items-center gap-2 font-bold text-xl tracking-tight text-primary"><span dir="ltr">e&</span> <span className="text-muted-foreground font-normal">|</span> هِمّة</div>
            <div className="min-w-0 sm:ms-4 sm:ps-4 sm:border-s">
              <p className="truncate text-sm font-semibold text-foreground">AI Engineer</p>
              <p className="text-xs text-muted-foreground">Section 1 of 1 · Verbal</p>
            </div>
          </div>
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            <span className="rounded-md border bg-muted/30 px-2.5 py-1.5 font-semibold tabular-nums text-foreground">09:58</span>
            <span className="rounded-md bg-destructive/10 px-3 py-1.5 text-xs font-semibold text-destructive">End Session</span>
          </div>
        </div>
      </header>
      <div className="border-b bg-amber-50 px-4 py-1.5 text-xs text-amber-800 flex flex-wrap gap-3 items-center">
        <strong>DEV PREVIEW</strong>
        <button className="underline" onClick={() => setSubsection("BACKGROUND")}>background</button>
        <button className="underline" onClick={() => setSubsection("DISCUSSION")}>discussion</button>
        <button className="underline" onClick={() => setSubsection(null)}>plain verbal</button>
        <button className="underline" onClick={() => setBgIndex((i) => (i % 3) + 1)}>next bg question</button>
        <button className="underline" onClick={() => setSpeaking((v) => !v)}>toggle speaking</button>
        <button className="underline" onClick={() => setBonus((b) => b + 120)}>grant +2:00</button>
      </div>
      <main className="mx-auto grid w-full flex-1 min-h-0 max-w-[1440px] grid-cols-1 gap-4 p-3 sm:p-4 lg:grid-cols-[minmax(0,1fr)_340px] lg:gap-6 lg:overflow-hidden">
        <VerbalSectionView
          question={question as any}
          isCompleted={false}
          isAgentSpeaking={speaking}
          isMicrophoneEnabled={!speaking}
          isTechnical={false}
          hasEditor={false}
          characterState={speaking ? "speaking" : "listening"}
          agentAudioTrack={undefined}
          code="" setCode={() => {}} selectedLanguage="" setSelectedLanguage={() => {}}
          hasConfigStarterCode={false} codeStatus={null} onCodeSubmit={() => {}}
          currentSectionType="VERBAL"
          ReportLoadingState={() => null}
          allowedControls={state.allowed_controls}
          onToggleMicrophone={() => {}}
          onSendControl={() => {}}
          backendState={state}
          hasNextSection={false}
          visibleTranscripts={[]}
          transcriptRef={transcriptRef}
          formattedTime={bonus ? `${9 + Math.floor(bonus / 60)}:58` : "09:58"}
        />
      </main>
      <div className="sticky bottom-0 z-20 w-full border-t bg-background/95 px-4 py-3 text-center text-xs text-muted-foreground">(controls bar renders here in the real workspace)</div>
    </div>
  );
}
