import React, { useRef, useState } from "react";
import { WorkspaceHeader } from "../../features/interview-session/WorkspaceHeader";
import { InterviewController } from "../../features/interview-session/InterviewController";
import { VerbalSectionView } from "../../features/interview-session/VerbalSectionView";
import { CodingSectionView } from "../../features/interview-session/CodingSectionView";
import { McqSectionView } from "../../features/interview-session/McqSectionView";
import type { ActiveQuestion, StateUpdatePayload } from "../../types/realtime";

/**
 * DEV-ONLY visual harness for the live workspace's chrome (registered in
 * App.tsx only under import.meta.env.DEV). Unlike VerbalPreview, which
 * copies the header markup, this renders the REAL WorkspaceHeader and the
 * REAL InterviewController around each of the three section views with
 * mock state -- so the phone-width behaviour of the header's End Session /
 * Fullscreen buttons and the controller bar (R6's P0/P1 findings) can be
 * seen and iterated on without a LiveKit room. Not rendered here: the
 * SelfViewVideo PiP (needs a real LocalVideoTrack) and the overlays.
 * Controls are inert (no data channel); toggling state is local only.
 */
type Section = "verbal" | "coding" | "mcq";

const baseQuestion: ActiveQuestion = {
  id: "q-1", title: "Rate limiter", problem_statement: "Implement a sliding-window rate limiter that allows at most N requests per rolling window of W seconds. Explain the trade-offs of your data structure choice.",
  difficulty: "mid", competency: "system design", expected_concepts: [], hints: [], follow_up_topics: [], time_budget_minutes: 15,
  coding_required: false, examples: [], constraints: ["O(1) amortised per request", "Memory bounded by N"], starter_code: {}, test_cases: [],
  supported_languages: ["python", "typescript"], hints_used: 0, config: {},
};

const questions: Record<Section, ActiveQuestion> = {
  verbal: { ...baseQuestion, id: "v-1", title: "Ownership", problem_statement: "Tell me about a system you owned end to end.", competency: "ownership", time_budget_minutes: 0 },
  coding: { ...baseQuestion, coding_required: true, config: { starter_code: "def allow(request):\n    ...\n", supported_languages: ["python", "typescript"], constraints: "O(1) amortised per request; memory bounded by N." } },
  mcq: { ...baseQuestion, id: "m-1", title: "Consistency models", problem_statement: "Which guarantee does a quorum read (R + W > N) give you in a Dynamo-style store?", competency: "distributed systems",
    config: { options: [{ id: "a", text: "Linearizability" }, { id: "b", text: "Read-your-writes for the writing client only" }, { id: "c", text: "Eventual consistency with no read guarantee" }, { id: "d", text: "That a read sees the latest acknowledged write" }], correct_answers: ["d"], is_multi_select: false } },
};

export default function WorkspacePreview() {
  const [section, setSection] = useState<Section>("verbal");
  const [speaking, setSpeaking] = useState(true);
  const [mic, setMic] = useState(true);
  const [waiting, setWaiting] = useState(false);
  const [code, setCode] = useState("");
  const [language, setLanguage] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const transcriptRef = useRef<HTMLDivElement>(null!) as React.RefObject<HTMLDivElement>;
  const question = questions[section];

  const state = {
    session_id: "preview", phase: waiting ? "WAITING_ROOM" : "BACKGROUND", sub_phase: null, current_question: question,
    question_index: 0, total_questions: 4, questions_completed: 0, questions_skipped: 0, hints_used: 0, max_hints: 2,
    last_question_outcome: null,
    allowed_controls: ["REPEAT_QUESTION", "SKIP_QUESTION", "END_SECTION_EARLY", "END_INTERVIEW", ...(section === "coding" ? ["REQUEST_HINT"] : []), ...(section === "verbal" ? ["SKIP_BACKGROUND"] : [])],
    time_remaining_seconds: 598,
    sections_progress: { total: 3, completed: 0, current_index: 1, current_section_type: section.toUpperCase() },
    verbal_subsection: section === "verbal" ? "BACKGROUND" : null, background_total: 3, background_index: 1, background_time_remaining_seconds: 298,
    discussion_index: null, discussion_total: 2,
  } as unknown as StateUpdatePayload;

  return (
    <div className="h-[100dvh] flex flex-col w-full bg-background text-foreground overflow-hidden">
      <WorkspaceHeader
        role="Senior Machine Learning Engineer"
        subtitle={`Section 1 of 3 · ${section === "verbal" ? "Verbal" : section === "coding" ? "Coding" : "Multiple choice"}`}
        isCompleted={false}
        isCameraEnabled
        isWaitingRoom={waiting}
        formattedTime="09:58"
        isFullscreenNow={false}
        onToggleFullscreen={() => {}}
        isEndingSession={false}
        onEndSession={() => {}}
      />
      <div data-responsive-ignore className="border-b bg-amber-50 px-4 py-1.5 text-xs text-amber-800 flex flex-wrap gap-3 items-center">
        <strong>DEV PREVIEW</strong>
        {(["verbal", "coding", "mcq"] as const).map((s) => <button key={s} className={`underline ${section === s ? "font-bold" : ""}`} onClick={() => setSection(s)}>{s}</button>)}
        <button className="underline" onClick={() => setSpeaking((v) => !v)}>toggle speaking</button>
        <button className="underline" onClick={() => setWaiting((v) => !v)}>toggle waiting room</button>
      </div>

      <div className="relative flex flex-1 min-h-0 flex-col">
        <main className="mx-auto grid w-full flex-1 min-h-0 max-w-[1440px] grid-cols-1 gap-4 p-3 sm:p-4 lg:grid-cols-[minmax(0,1fr)_340px] lg:gap-6 lg:overflow-hidden">
          {section === "coding" ? (
            <CodingSectionView
              question={question} isAgentSpeaking={speaking}
              code={code} setCode={setCode} selectedLanguage={language} setSelectedLanguage={setLanguage}
              hasConfigStarterCode codingConfigConstraints={question.config?.constraints}
              codeStatus={null} onCodeSubmit={() => {}} formattedTime="09:58"
            />
          ) : section === "mcq" ? (
            <McqSectionView
              question={question} isAgentSpeaking={speaking}
              mcqOptions={question.config?.options ?? []} selectedOptionIds={selected}
              onToggleOption={(id) => setSelected([id])} mcqIsMultiSelect={false}
              mcqSubmitted={false} onMcqSubmit={() => {}} formattedTime="09:58"
            />
          ) : (
            <VerbalSectionView
              question={question} isCompleted={false} isAgentSpeaking={speaking} isTechnical={false} hasEditor={false}
              characterState={speaking ? "speaking" : "listening"} agentAudioTrack={undefined}
              code="" setCode={() => {}} selectedLanguage="" setSelectedLanguage={() => {}}
              hasConfigStarterCode={false} codeStatus={null} onCodeSubmit={() => {}}
              ReportLoadingState={() => null} backendState={state}
              visibleTranscripts={[{ id: "t1", speaker: "agent", text: "Tell me about a system you owned end to end." }, { id: "t2", speaker: "user", text: "I led the ingestion pipeline for..." }]}
              transcriptRef={transcriptRef} formattedTime="09:58"
            />
          )}
        </main>

        {!waiting && (
          <div className="sticky bottom-0 z-20 w-full border-t bg-background/95 px-4 py-3 backdrop-blur sm:py-4">
            <div className="mx-auto max-w-[1440px]">
              <InterviewController
                isCompleted={false}
                isLocked={false}
                allowedControls={state.allowed_controls}
                isMicrophoneEnabled={mic}
                onToggleMicrophone={() => setMic((v) => !v)}
                onSendControl={() => {}}
                backendState={state}
                hasNextSection
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
