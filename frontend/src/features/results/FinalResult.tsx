import { CheckCircle2 } from "lucide-react";
import type { InterviewSessionResponse } from "../../types/api";

interface FinalResultProps {
  session: InterviewSessionResponse;
}

export function FinalResult({ session }: FinalResultProps) {
  const firstName = session.candidate_name 
    ? session.candidate_name.split(" ")[0] 
    : "Candidate";

  return (
    <div className="flex-1 flex flex-col items-center justify-center p-6 bg-muted/10 min-h-[500px]">
      <div className="w-full max-w-md rounded-2xl border border-border bg-card p-10 text-center shadow-sm">
        <div className="flex justify-center mb-6">
          <div className="h-20 w-20 rounded-full bg-emerald-50 flex items-center justify-center border border-emerald-100">
            <CheckCircle2 className="h-10 w-10 text-emerald-600" />
          </div>
        </div>
        
        <div className="space-y-4">
          <h2 className="text-2xl font-semibold tracking-tight text-foreground">
            Thank you, {firstName}.
          </h2>
          <p className="text-muted-foreground leading-relaxed text-sm">
            Your interview has been successfully submitted. Our team will review your assessment and follow up with you shortly.
          </p>
        </div>
      </div>
    </div>
  );
}
