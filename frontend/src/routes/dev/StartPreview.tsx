import { useState } from "react";
import { StartSequenceView } from "../../features/interview-session/InterviewWorkspace";

/** DEV-ONLY harness for the start sequence's four stages and its slow/stuck states. */
export default function StartPreview() {
  const [stage, setStage] = useState<"connecting" | "joining" | "preparing" | "starting">("joining");
  const [elapsed, setElapsed] = useState(6);
  return (
    <div>
      <div data-responsive-ignore className="border-b bg-amber-50 px-4 py-1.5 text-xs text-amber-800 flex flex-wrap gap-3">
        <strong>DEV PREVIEW</strong>
        {(["connecting", "joining", "preparing", "starting"] as const).map((s) => <button key={s} className="underline" onClick={() => setStage(s)}>{s}</button>)}
        <button className="underline" onClick={() => setElapsed(6)}>6s</button>
        <button className="underline" onClick={() => setElapsed(25)}>25s</button>
        <button className="underline" onClick={() => setElapsed(65)}>65s</button>
      </div>
      <StartSequenceView stage={stage} hasCv={true} elapsedSeconds={elapsed} />
    </div>
  );
}
