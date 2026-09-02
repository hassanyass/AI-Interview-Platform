import { useEffect, useRef } from "react";
import { AlertTriangle, Maximize2 } from "lucide-react";
import { requestFullscreen } from "../../lib/fullscreen";

/**
 * PR-B (docs/proctoring-architecture.md): fullscreen grace-period countdown
 * overlay shown when the candidate exits fullscreen mid-interview.
 *
 * ONLY renders during the active 10-second grace window (secondsRemaining != null).
 * Once the grace expires, the parent (InterviewSession.tsx) calls
 * onFullscreenTerminated() which navigates to the dedicated
 * FullscreenTerminatedScreen — this overlay is no longer responsible for
 * showing a "terminated" state.
 *
 * Focus is trapped inside the dialog so Tab cannot reach interview content
 * behind the overlay.
 */
interface FullscreenGraceOverlayProps {
  secondsRemaining: number | null;
  /** Kept for backward-compat — ignored, termination now handled by parent. */
  isBlocked?: boolean;
}

export function FullscreenGraceOverlay({ secondsRemaining }: FullscreenGraceOverlayProps) {
  const returnBtnRef = useRef<HTMLButtonElement>(null);
  const isVisible = secondsRemaining != null;

  // Trap focus inside dialog while visible.
  useEffect(() => {
    if (!isVisible) return;
    returnBtnRef.current?.focus();

    const trapFocus = (e: KeyboardEvent) => {
      if (e.key !== "Tab") return;
      e.preventDefault();
      returnBtnRef.current?.focus();
    };

    document.addEventListener("keydown", trapFocus);
    return () => document.removeEventListener("keydown", trapFocus);
  }, [isVisible]);

  if (!isVisible) return null;

  const pct = ((secondsRemaining ?? 10) / 10) * 100;
  const isUrgent = (secondsRemaining ?? 10) <= 3;

  return (
    <div
      className="absolute inset-0 z-[100] flex flex-col items-center justify-center bg-slate-950/80 p-4 backdrop-blur-md"
      role="dialog"
      aria-modal="true"
      aria-labelledby="fullscreen-overlay-title"
      aria-describedby="fullscreen-overlay-desc"
    >
      <div className={`flex flex-col items-center gap-5 rounded-2xl border bg-white p-8 text-center shadow-2xl max-w-sm w-full transition-all duration-300
        ${isUrgent ? "border-red-300 shadow-red-200/50 scale-[1.02]" : "border-amber-200/80"}`}>

        {/* Icon */}
        <div className={`flex h-16 w-16 items-center justify-center rounded-full transition-colors duration-300
          ${isUrgent ? "bg-red-100" : "bg-amber-100"}`}>
          {isUrgent
            ? <Maximize2 className="h-8 w-8 text-red-600" />
            : <AlertTriangle className="h-8 w-8 text-amber-600" />
          }
        </div>

        {/* Text */}
        <div>
          <h2
            id="fullscreen-overlay-title"
            className={`mb-2 text-xl font-bold transition-colors duration-300 ${isUrgent ? "text-red-700" : "text-slate-900"}`}
          >
            Return to Fullscreen
          </h2>
          <p id="fullscreen-overlay-desc" className="text-sm text-slate-600 leading-relaxed">
            {isUrgent
              ? "Your session will be terminated if you don't return now."
              : "Your interview requires fullscreen. Return now or the session will be automatically terminated."
            }
          </p>
        </div>

        {/* Circular countdown timer */}
        <div className="relative flex h-20 w-20 items-center justify-center">
          <svg className="absolute inset-0 -rotate-90" viewBox="0 0 80 80">
            <circle cx="40" cy="40" r="34" fill="none" stroke="#e2e8f0" strokeWidth="6" />
            <circle
              cx="40" cy="40" r="34" fill="none"
              stroke={isUrgent ? "#dc2626" : "#d97706"}
              strokeWidth="6"
              strokeDasharray={`${2 * Math.PI * 34}`}
              strokeDashoffset={`${2 * Math.PI * 34 * (1 - pct / 100)}`}
              strokeLinecap="round"
              className="transition-all duration-200"
            />
          </svg>
          <span className={`text-3xl font-bold tabular-nums transition-colors duration-300 ${isUrgent ? "text-red-600" : "text-amber-700"}`}>
            {secondsRemaining}
          </span>
        </div>

        <p className="text-xs text-slate-400 -mt-2">seconds remaining</p>

        <button
          ref={returnBtnRef}
          type="button"
          onClick={() => { void requestFullscreen(); }}
          className={`w-full rounded-xl px-4 py-3.5 text-sm font-semibold text-white shadow-sm transition-all
            focus:outline-none focus:ring-2 focus:ring-offset-2
            ${isUrgent
              ? "bg-red-600 hover:bg-red-700 focus:ring-red-500"
              : "bg-amber-600 hover:bg-amber-700 focus:ring-amber-500"
            }`}
        >
          Return to Fullscreen Now
        </button>
      </div>
    </div>
  );
}
