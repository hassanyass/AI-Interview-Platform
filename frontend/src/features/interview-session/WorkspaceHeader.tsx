import { Loader2, Timer, LogOut, Video, VideoOff, Maximize2, Minimize2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { LanguageToggle } from "../../components/ui/LanguageToggle";

/**
 * Responsive plan R0 (docs/responsive-design-plan.md): the live workspace's
 * header, moved verbatim out of InterviewWorkspace.tsx so the DEV harness
 * (/dev/workspace-preview) renders the REAL header rather than a copy of
 * its markup -- the old VerbalPreview copied it, which is exactly how the
 * `hidden sm:flex` End Session / Fullscreen buttons (R6's P0) went unseen.
 * Pure move: same classes, same conditions, same copy. R6 is where the
 * phone layout of this header changes.
 */
export interface WorkspaceHeaderProps {
  /** Job title shown as the headline; falls back to the generic session label. */
  role: string | null | undefined;
  /** "Section 1 of 3 · Verbal" when sections_progress is known, else the phase label. */
  subtitle: string;
  isCompleted: boolean;
  isCameraEnabled: boolean;
  isWaitingRoom: boolean;
  /** Preformatted mm:ss from the workspace's local countdown. */
  formattedTime: string;
  isFullscreenNow: boolean;
  onToggleFullscreen: () => void | Promise<void>;
  isEndingSession: boolean;
  onEndSession: () => void;
}

export function WorkspaceHeader({
  role,
  subtitle,
  isCompleted,
  isCameraEnabled,
  isWaitingRoom,
  formattedTime,
  isFullscreenNow,
  onToggleFullscreen,
  isEndingSession,
  onEndSession,
}: WorkspaceHeaderProps) {
  const { t } = useTranslation();

  return (
    <header className="border-b bg-white">
      <div className="mx-auto flex min-h-16 max-w-[1440px] items-center justify-between gap-4 px-4 py-3 sm:px-8">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex items-center gap-2 font-bold text-xl tracking-tight text-primary hidden sm:flex">
            <span dir="ltr" className="inline-block">e&</span> <span className="text-muted-foreground font-normal">|</span> هِمّة
          </div>
          <div className="min-w-0 sm:ms-4 sm:ps-4 sm:border-s">
            <p className="truncate text-sm font-semibold text-foreground">{role || t('workspace.session')}</p>
            <p className="text-xs text-muted-foreground">{subtitle}</p>
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
            <span className="flex items-center gap-1.5" title={isCameraEnabled ? t('workspace.cameraOn') : t('workspace.cameraOff')}>
              {isCameraEnabled ? (
                <Video className="h-3.5 w-3.5 text-success" />
              ) : (
                <VideoOff className="h-3.5 w-3.5 text-muted-foreground" />
              )}
            </span>
          )}
          <span className="hidden items-center gap-2 md:flex">
            <span className={`h-2 w-2 rounded-full ${isCompleted ? "bg-muted-foreground" : isWaitingRoom ? "bg-blue-400" : "bg-success"}`} />
            {isCompleted ? t('workspace.sessionEnded') : isWaitingRoom ? t('workspace.phase.waitingRoom') : t('workspace.liveConnection')}
          </span>
          {/* Show timer always except during WAITING_ROOM (clock is paused). */}
          {!isWaitingRoom && (
            <span className="flex items-center gap-1.5 rounded-md border bg-muted/30 px-2.5 py-1.5 font-semibold tabular-nums text-foreground">
              <Timer className="h-3.5 w-3.5 text-muted-foreground" />
              {/* B4 (docs/verbal-section-flow-plan.md): the digits plus the
                  follow-up time-grant moment and running tally. The
                  countdown itself already re-seeds on every
                  time_remaining_seconds update (effect above), so the
                  number jumps correctly on its own; this only adds the
                  *moment* so a grant reads as earned, not as a glitch. */}
              {/* Redesign 2026-09-16: the header clock updates silently (it
                  re-seeds on every time_remaining_seconds update, so a grant
                  simply shows up in the digits); the "+2:00" moment now lives
                  beside the discussion time in the verbal stepper. */}
              {formattedTime}
            </span>
          )}

          <button
              onClick={() => { void onToggleFullscreen(); }}
              className="flex min-h-11 min-w-11 items-center justify-center gap-1.5 rounded-md border border-border bg-background/60 px-3 py-1.5 text-xs font-semibold text-foreground/80 transition hover:bg-muted sm:min-w-0 lg:min-h-10"
              title={isFullscreenNow ? t('workspace.exitFullscreen') : t('workspace.enterFullscreen')}
            >
              {isFullscreenNow
                ? <><Minimize2 className="h-3.5 w-3.5" /><span className="hidden sm:inline">{t('workspace.exitFullscreen')}</span></>
                : <><Maximize2 className="h-3.5 w-3.5" /><span className="hidden sm:inline">{t('workspace.enterFullscreen')}</span></>
              }
            </button>

          <button
            onClick={onEndSession}
            disabled={isCompleted || isEndingSession}
            aria-label={t('workspace.endSession')}
            className="flex min-h-11 min-w-11 items-center justify-center gap-1.5 rounded-md bg-destructive/10 px-3 py-1.5 text-xs font-semibold text-destructive transition hover:bg-destructive hover:text-destructive-foreground disabled:opacity-50 sm:min-w-0 lg:min-h-10"
          >
            {isEndingSession ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <LogOut className="h-3.5 w-3.5" />}
            <span className="hidden sm:inline">{t('workspace.endSession')}</span>
          </button>
        </div>
      </div>
    </header>
  );
}
