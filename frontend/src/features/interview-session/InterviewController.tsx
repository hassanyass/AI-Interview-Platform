import { useState, useEffect, useRef } from "react";
import { Mic, MicOff, RefreshCcw, HelpCircle, SkipForward, Square, Loader2, LogOut, MoreHorizontal } from "lucide-react";
import { EndInterviewDialog } from "./EndInterviewDialog";
import { EndSectionEarlyDialog } from "./EndSectionEarlyDialog";

export type ControlState = "IDLE" | "PROCESSING" | "ENDING" | "ENDED";

interface InterviewControllerProps {
  isCompleted: boolean;
  allowedControls: string[];
  isMicrophoneEnabled: boolean;
  onToggleMicrophone: () => void;
  onSendControl: (control: string) => void;
  backendState: any; // Used to trigger reset from processing
  /** Whether another section follows the current one (for dialog copy) */
  hasNextSection?: boolean;
  /** CODING/MCQ: a single slim icon-only toolbar row instead of the wide
   *  three-zone bar VERBAL uses — same buttons, same handlers/dialogs, just
   *  sized to sit above a code editor or quiz card instead of full-width
   *  beneath the page. */
  variant?: "default" | "compact";
}

export function InterviewController({
  isCompleted,
  allowedControls,
  isMicrophoneEnabled,
  onToggleMicrophone,
  onSendControl,
  backendState,
  hasNextSection = true,
  variant = "default",
}: InterviewControllerProps) {
  const [controlState, setControlState] = useState<ControlState>(isCompleted ? "ENDED" : "IDLE");
  const [processingAction, setProcessingAction] = useState<string | null>(null);
  const [isEndDialogOpen, setIsEndDialogOpen] = useState(false);
  const [isEndSectionDialogOpen, setIsEndSectionDialogOpen] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [isOverflowOpen, setIsOverflowOpen] = useState(false);
  const overflowRef = useRef<HTMLDivElement>(null);

  // Compact toolbar's overflow menu (Skip/End section/End) — close on
  // outside click or Escape, same dismissal pattern the two dialogs below
  // already use.
  useEffect(() => {
    if (!isOverflowOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (overflowRef.current && !overflowRef.current.contains(e.target as Node)) {
        setIsOverflowOpen(false);
      }
    };
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setIsOverflowOpen(false);
    };
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOverflowOpen]);

  // Reset processing state when backend state updates, indicating a turn transition or update
  useEffect(() => {
    if (controlState === "PROCESSING" && processingAction !== "END_INTERVIEW") {
      setControlState("IDLE");
      setProcessingAction(null);
    }
  }, [backendState]);

  // Keep state synced if external completion happens
  useEffect(() => {
    if (isCompleted) {
      setControlState("ENDED");
      setIsEndDialogOpen(false);
    }
  }, [isCompleted]);

  useEffect(() => {
    if (isCompleted) return;
    if (controlState === "ENDING" && backendState?.phase === "CLOSING") {
      // The agent has accepted the end request and is producing its final turn.
      // Keep the button stable, but do not wait forever if the completion event
      // is delayed by the voice pipeline.
      const timer = setTimeout(() => {
        if (!isCompleted) setControlState("IDLE");
      }, 15000);
      return () => clearTimeout(timer);
    }
  }, [backendState?.phase, controlState, isCompleted]);

  // Remove artificial timeout. The state update from the backend is the only source of truth.
  // The command will remain in PROCESSING ("Skipping...", "Thinking...") until the agent
  // finishes generation and emits the next UI state.

  const handleAction = (action: string) => {
    if (controlState !== "IDLE" || isCompleted) return;
    
    if (action === "END_INTERVIEW") {
      setIsEndDialogOpen(true);
      return;
    }

    if (action === "END_SECTION_EARLY") {
      setIsEndSectionDialogOpen(true);
      return;
    }

    setControlState("PROCESSING");
    setProcessingAction(action);
    setErrorMsg(null);
    
    try {
      onSendControl(action);
    } catch (e) {
      setControlState("IDLE");
      setProcessingAction(null);
      setErrorMsg("Failed to send command.");
      setTimeout(() => setErrorMsg(null), 3000);
    }
  };

  const handleConfirmEnd = () => {
    setControlState("ENDING");
    setIsEndDialogOpen(false);
    try {
      onSendControl("END_INTERVIEW");
    } catch (e) {
      setControlState("IDLE");
      setErrorMsg("Failed to end interview.");
      setTimeout(() => setErrorMsg(null), 3000);
    }
  };

  const handleConfirmEndSection = () => {
    setIsEndSectionDialogOpen(false);
    setControlState("PROCESSING");
    setProcessingAction("END_SECTION_EARLY");
    try {
      onSendControl("END_SECTION_EARLY");
    } catch (e) {
      setControlState("IDLE");
      setProcessingAction(null);
      setErrorMsg("Failed to end section.");
      setTimeout(() => setErrorMsg(null), 3000);
    }
  };

  const isProcessing = controlState === "PROCESSING" || controlState === "ENDING";
  const canEndSectionEarly = allowedControls.includes("END_SECTION_EARLY");

  if (variant === "compact") {
    // Rebrand consolidation pass (2026-08-26): split by frequency of use
    // instead of six equal-weight circles. Mic is the one thing a
    // candidate touches constantly, so it's the dominant element; Repeat/
    // Hint are frequent-but-secondary and sit right beside it; Skip/End
    // section/End are rare, high-consequence, and already confirmation-
    // gated (or, for Skip, low-stakes but infrequent), so they move into
    // one overflow menu rather than staying permanently exposed.
    return (
      <div className="flex items-center gap-2 relative">
        {errorMsg && (
          <div className="absolute -top-10 start-0 px-3 py-1.5 bg-destructive/10 text-destructive text-xs rounded-md border border-destructive/20 shadow-sm whitespace-nowrap animate-in fade-in slide-in-from-bottom-2">
            {errorMsg}
          </div>
        )}

        <CompactButton
          icon={<RefreshCcw className="h-3.5 w-3.5" />}
          label="Repeat"
          disabled={isCompleted || isProcessing || !allowedControls.includes("REPEAT_QUESTION")}
          onClick={() => handleAction("REPEAT_QUESTION")}
          isLoading={processingAction === "REPEAT_QUESTION"}
          size="sm"
        />
        <CompactButton
          icon={<HelpCircle className="h-3.5 w-3.5" />}
          label="Hint"
          disabled={isCompleted || isProcessing || !allowedControls.includes("REQUEST_HINT")}
          onClick={() => handleAction("REQUEST_HINT")}
          isLoading={processingAction === "REQUEST_HINT"}
          size="sm"
        />

        {/* Mic — the dominant control */}
        <button
          disabled={isCompleted}
          onClick={onToggleMicrophone}
          title={isMicrophoneEnabled ? "Mute microphone" : "Unmute microphone"}
          className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full shadow-sm transition-colors
            ${isCompleted ? "bg-muted text-muted-foreground opacity-50 cursor-not-allowed" :
              isMicrophoneEnabled ? "bg-primary text-primary-foreground hover:bg-primary/90" : "bg-muted text-muted-foreground border border-border hover:bg-muted/80"}
          `}
        >
          {isMicrophoneEnabled ? <Mic className="h-4.5 w-4.5" /> : <MicOff className="h-4.5 w-4.5" />}
        </button>

        <div className="relative" ref={overflowRef}>
          <button
            onClick={() => setIsOverflowOpen((v) => !v)}
            title="More controls"
            aria-label="More controls"
            aria-expanded={isOverflowOpen}
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-secondary hover:text-secondary-foreground"
          >
            <MoreHorizontal className="h-4 w-4" />
          </button>
          {isOverflowOpen && (
            <div className="absolute end-0 top-full z-20 mt-2 w-44 overflow-hidden rounded-xl border bg-card py-1 shadow-md">
              <OverflowItem
                icon={<SkipForward className="h-3.5 w-3.5" />}
                label="Skip"
                disabled={isCompleted || isProcessing || !allowedControls.includes("SKIP_QUESTION")}
                onClick={() => { setIsOverflowOpen(false); handleAction("SKIP_QUESTION"); }}
                isLoading={processingAction === "SKIP_QUESTION"}
              />
              {canEndSectionEarly && (
                <OverflowItem
                  icon={<LogOut className="h-3.5 w-3.5" />}
                  label="End section"
                  disabled={isCompleted || isProcessing}
                  onClick={() => { setIsOverflowOpen(false); handleAction("END_SECTION_EARLY"); }}
                  isLoading={processingAction === "END_SECTION_EARLY"}
                  tone="warning"
                />
              )}
              <OverflowItem
                icon={controlState === "ENDING" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Square className="h-3.5 w-3.5" />}
                label={controlState === "ENDING" ? "Ending…" : "End interview"}
                disabled={isCompleted || isProcessing}
                onClick={() => { setIsOverflowOpen(false); handleAction("END_INTERVIEW"); }}
                tone="danger"
              />
            </div>
          )}
        </div>

        <EndInterviewDialog isOpen={isEndDialogOpen} onCancel={() => setIsEndDialogOpen(false)} onConfirm={handleConfirmEnd} />
        <EndSectionEarlyDialog isOpen={isEndSectionDialogOpen} hasNextSection={hasNextSection} onCancel={() => setIsEndSectionDialogOpen(false)} onConfirm={handleConfirmEndSection} />
      </div>
    );
  }

  return (
    <div className="w-full flex flex-col items-center gap-4 relative">
      {/* Optional error toast within controller */}
      {errorMsg && (
        <div className="absolute -top-12 px-4 py-2 bg-destructive/10 text-destructive text-sm rounded-md border border-destructive/20 shadow-sm animate-in fade-in slide-in-from-bottom-2">
          {errorMsg}
        </div>
      )}

      <div className="flex flex-col sm:flex-row items-center justify-center gap-4 w-full px-4">
        
        {/* Left Side: Repeat and Hint */}
        <div className="flex items-center gap-2 flex-1 justify-end">
          <SecondaryButton 
            icon={<RefreshCcw className="h-4 w-4" />}
            label={processingAction === "REPEAT_QUESTION" ? "Repeating..." : "Repeat"}
            disabled={isCompleted || isProcessing || !allowedControls.includes("REPEAT_QUESTION")}
            onClick={() => handleAction("REPEAT_QUESTION")}
            isLoading={processingAction === "REPEAT_QUESTION"}
            tooltip="Repeat the last interviewer message"
          />
          <SecondaryButton 
            icon={<HelpCircle className="h-4 w-4" />}
            label={processingAction === "REQUEST_HINT" ? "Thinking..." : "Hint"}
            disabled={isCompleted || isProcessing || !allowedControls.includes("REQUEST_HINT")}
            onClick={() => handleAction("REQUEST_HINT")}
            isLoading={processingAction === "REQUEST_HINT"}
            tooltip="Available during technical questions"
          />
        </div>

        {/* Center: Microphone */}
        <div className="flex flex-col items-center shrink-0 mx-2 sm:mx-6">
          <button
            disabled={isCompleted}
            onClick={onToggleMicrophone}
            className={`relative flex h-16 w-16 items-center justify-center rounded-full transition-all duration-300 shadow-sm
              ${isCompleted ? "bg-muted text-muted-foreground opacity-50 cursor-not-allowed" :
                isMicrophoneEnabled 
                ? "bg-primary text-primary-foreground hover:bg-primary/90 hover:scale-105 hover:shadow-md" 
                : "bg-muted text-muted-foreground border border-border hover:bg-muted/80 hover:scale-105"
              }
            `}
            aria-label={isMicrophoneEnabled ? "Mute microphone" : "Unmute microphone"}
          >
            {isMicrophoneEnabled ? (
              <Mic className="h-7 w-7" />
            ) : (
              <MicOff className="h-7 w-7" />
            )}
          </button>
          <span className="text-xs font-medium text-muted-foreground mt-2 tracking-wide uppercase">
            {isMicrophoneEnabled ? "Listening" : "Muted"}
          </span>
        </div>

        {/* Right Side: Skip, End Section Early, and End */}
        <div className="flex items-center gap-2 flex-1 justify-start">
          <SecondaryButton 
            icon={<SkipForward className="h-4 w-4" />}
            label={processingAction === "SKIP_QUESTION" ? "Skipping..." : "Skip"}
            disabled={isCompleted || isProcessing || !allowedControls.includes("SKIP_QUESTION")}
            onClick={() => handleAction("SKIP_QUESTION")}
            isLoading={processingAction === "SKIP_QUESTION"}
            tooltip="Skip this question"
          />

          {/* End Section Early — only shown when allowed (phase=BACKGROUND with active section) */}
          {canEndSectionEarly && (
            <SecondaryButton
              icon={<LogOut className="h-4 w-4" />}
              label={processingAction === "END_SECTION_EARLY" ? "Ending section..." : "End section"}
              disabled={isCompleted || isProcessing}
              onClick={() => handleAction("END_SECTION_EARLY")}
              isLoading={processingAction === "END_SECTION_EARLY"}
              tooltip="End this section early"
              variant="warning"
            />
          )}
          
          <button 
            disabled={isCompleted || isProcessing}
            onClick={() => handleAction("END_INTERVIEW")} 
            title="End Interview"
            className="flex items-center gap-2 px-4 py-2.5 text-sm font-medium text-destructive hover:bg-destructive/10 border border-destructive/20 rounded-full transition-colors disabled:opacity-50 disabled:cursor-not-allowed ms-2"
          >
            {controlState === "ENDING" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Square className="h-4 w-4" />}
            <span className="hidden sm:inline">{controlState === "ENDING" ? "Ending..." : "End"}</span>
          </button>
        </div>
      </div>

      <EndInterviewDialog 
        isOpen={isEndDialogOpen}
        onCancel={() => setIsEndDialogOpen(false)}
        onConfirm={handleConfirmEnd}
      />
      <EndSectionEarlyDialog
        isOpen={isEndSectionDialogOpen}
        hasNextSection={hasNextSection}
        onCancel={() => setIsEndSectionDialogOpen(false)}
        onConfirm={handleConfirmEndSection}
      />
    </div>
  );
}

// Icon-only variant for the compact toolbar (CODING/MCQ) — same click/
// loading/disabled semantics as SecondaryButton, no label text, always a
// tooltip since there's no visible label to fall back on. size="sm" is the
// frequent-but-secondary tier (Repeat/Hint, next to the dominant mic
// button) — smaller and quieter than the default compact size.
function CompactButton({
  icon,
  label,
  disabled,
  onClick,
  isLoading,
  variant = "default",
  size = "default",
}: {
  icon: React.ReactNode,
  label: string,
  disabled: boolean,
  onClick: () => void,
  isLoading?: boolean,
  variant?: "default" | "warning",
  size?: "default" | "sm",
}) {
  const warningClasses = disabled
    ? "bg-amber-50/40 text-amber-400/60 cursor-not-allowed"
    : "bg-amber-50 text-amber-700 border border-amber-200 hover:bg-amber-100 cursor-pointer";

  const defaultClasses = disabled
    ? "text-muted-foreground/50 cursor-not-allowed"
    : "text-muted-foreground hover:bg-secondary hover:text-secondary-foreground cursor-pointer";

  return (
    <button
      disabled={disabled}
      onClick={onClick}
      title={label}
      aria-label={label}
      className={`flex shrink-0 items-center justify-center rounded-full transition-colors
        ${size === "sm" ? "h-7 w-7" : "h-8 w-8"}
        ${variant === "warning" ? warningClasses : defaultClasses}
      `}
    >
      {isLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : icon}
    </button>
  );
}

// One row inside the compact toolbar's overflow menu (Skip/End section/End
// interview) — a real menu item (icon + label, left-aligned, full-width
// hit target) rather than another small icon circle.
function OverflowItem({
  icon,
  label,
  disabled,
  onClick,
  isLoading,
  tone = "default",
}: {
  icon: React.ReactNode,
  label: string,
  disabled: boolean,
  onClick: () => void,
  isLoading?: boolean,
  tone?: "default" | "warning" | "danger",
}) {
  const toneClasses = disabled
    ? "text-muted-foreground/50 cursor-not-allowed"
    : tone === "danger"
    ? "text-destructive hover:bg-destructive/10 cursor-pointer"
    : tone === "warning"
    ? "text-amber-700 hover:bg-amber-50 cursor-pointer"
    : "text-foreground hover:bg-muted cursor-pointer";

  return (
    <button
      disabled={disabled}
      onClick={onClick}
      className={`flex w-full items-center gap-2.5 px-3.5 py-2 text-sm font-medium transition-colors ${toneClasses}`}
    >
      {isLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : icon}
      {label}
    </button>
  );
}

// Sub-component for standard secondary controls
function SecondaryButton({
  icon, 
  label, 
  disabled, 
  onClick, 
  isLoading,
  tooltip,
  variant = "default",
}: { 
  icon: React.ReactNode, 
  label: string, 
  disabled: boolean, 
  onClick: () => void,
  isLoading?: boolean,
  tooltip?: string,
  variant?: "default" | "warning",
}) {
  const warningClasses = disabled
    ? "bg-amber-50/40 text-amber-400/60 cursor-not-allowed"
    : "bg-amber-50 text-amber-700 border border-amber-200 hover:bg-amber-100 cursor-pointer";

  const defaultClasses = disabled
    ? "bg-secondary/40 text-muted-foreground/60 cursor-not-allowed"
    : "bg-secondary text-secondary-foreground hover:bg-secondary/80 cursor-pointer";

  return (
    <button 
      disabled={disabled}
      onClick={onClick} 
      title={disabled ? tooltip : undefined}
      className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium rounded-full transition-colors
        ${variant === "warning" ? warningClasses : defaultClasses}
      `}
    >
      {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : icon}
      <span className="hidden sm:inline">{label}</span>
    </button>
  );
}
