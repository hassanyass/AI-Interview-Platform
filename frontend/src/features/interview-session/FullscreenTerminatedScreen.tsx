import { ShieldX } from "lucide-react";
import { LanguageToggle } from "../../components/ui/LanguageToggle";
import type { InterviewSessionResponse } from "../../types/api";

/**
 * PR-B (docs/proctoring-architecture.md): dedicated full-page screen shown
 * when a candidate's session is automatically terminated after the 10-second
 * fullscreen grace period expires. Deliberately separate from
 * SessionEndedScreen (which shows the normal "Thank you, your interview was
 * successfully submitted" message) — a terminated-by-proctoring session must
 * never show the normal success copy.
 */
interface FullscreenTerminatedScreenProps {
  session: InterviewSessionResponse;
}

export function FullscreenTerminatedScreen({ session }: FullscreenTerminatedScreenProps) {
  const firstName = session.candidate_name
    ? session.candidate_name.split(" ")[0]
    : "Candidate";

  return (
    <div className="min-h-screen w-full bg-slate-950 text-white flex flex-col">
      {/* Minimal header — same structure as SessionEndedScreen for chrome consistency */}
      <header className="border-b border-slate-800/60 bg-slate-950/90 backdrop-blur-sm">
        <div className="mx-auto flex min-h-16 max-w-[1440px] items-center justify-between gap-4 px-4 py-3 sm:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex items-center gap-2 font-bold text-xl tracking-tight text-white/80 hidden sm:flex">
              <span dir="ltr" className="inline-block">e&</span>{" "}
              <span className="text-white/40 font-normal">|</span> هِمّة
            </div>
            <div className="min-w-0 sm:ms-4 sm:ps-4 sm:border-s sm:border-slate-700">
              <p className="truncate text-sm font-semibold text-white/70">{session.role || "Interview Session"}</p>
              <p className="text-xs text-slate-500">Session Terminated</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <LanguageToggle />
            <span className="hidden items-center gap-2 sm:flex text-xs text-slate-500">
              <span className="h-2 w-2 rounded-full bg-red-600" />
              Terminated
            </span>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="flex-1 flex flex-col items-center justify-center p-6 relative">
        {/* Subtle dot-grid background */}
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.04]"
          style={{
            backgroundImage: "radial-gradient(circle, #fff 1px, transparent 1px)",
            backgroundSize: "28px 28px",
          }}
        />

        <div className="relative z-10 w-full max-w-lg text-center flex flex-col items-center gap-8">
          {/* Icon */}
          <div className="flex h-24 w-24 items-center justify-center rounded-full bg-red-950/60 border border-red-800/50 shadow-2xl shadow-red-950/50">
            <ShieldX className="h-12 w-12 text-red-400" />
          </div>

          {/* Heading */}
          <div className="space-y-3">
            <h1 className="text-3xl font-bold text-white tracking-tight">
              Session Terminated
            </h1>
            <p className="text-slate-400 leading-relaxed text-base max-w-md mx-auto">
              Hi {firstName}, your interview session was automatically terminated
              because fullscreen mode was exited and not restored within the required
              10-second window.
            </p>
          </div>

          {/* Reason card */}
          <div className="w-full rounded-2xl border border-slate-800/80 bg-slate-900/60 divide-y divide-slate-800/60 text-left overflow-hidden">
            <div className="px-5 py-4">
              <p className="text-xs font-semibold uppercase tracking-widest text-slate-500 mb-1">Reason</p>
              <p className="text-sm text-slate-300">
                Fullscreen enforcement violation — interview requires fullscreen for the entire session duration.
              </p>
            </div>
            <div className="px-5 py-4">
              <p className="text-xs font-semibold uppercase tracking-widest text-slate-500 mb-1">Session Status</p>
              <p className="text-sm text-slate-300">
                Your answers up to this point have been saved and will be reviewed by the hiring team.
              </p>
            </div>
          </div>

          {/* Footer note */}
          <p className="text-xs text-slate-600 max-w-sm">
            If you believe this was a technical error, please contact the company that sent you this interview link directly.
          </p>
        </div>
      </main>
    </div>
  );
}
