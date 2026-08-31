import { useState, useEffect } from "react";
import { Mic, MicOff, RefreshCcw, HelpCircle, SkipForward, LogOut, Loader2 } from "lucide-react";
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
}

export function InterviewController({
  isCompleted,
  allowedControls,
  isMicrophoneEnabled,
  onToggleMicrophone,
  onSendControl,
  backendState,
  hasNextSection = true,
}: InterviewControllerProps) {
  const [controlState, setControlState] = useState<ControlState>(isCompleted ? "ENDED" : "IDLE");
  const [processingAction, setProcessingAction] = useState<string | null>(null);
  const [isEndSectionDialogOpen, setIsEndSectionDialogOpen] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

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
    }
  }, [isCompleted]);

  useEffect(() => {
    if (isCompleted) return;
    if (controlState === "ENDING" && backendState?.phase === "CLOSING") {
      const timer = setTimeout(() => {
        if (!isCompleted) setControlState("IDLE");
      }, 15000);
      return () => clearTimeout(timer);
    }
  }, [backendState?.phase, controlState, isCompleted]);

  const handleAction = (action: string) => {
    if (controlState !== "IDLE" || isCompleted) return;
    
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
  // The user requested buttons to be permanently visible but disabled if not allowed.
  // This provides a stable UI layout for Verbal, Coding, and MCQ.

  return (
    <div className="w-full flex flex-col items-center gap-4 relative">
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

        {/* Right Side: Skip, End Section Early */}
        {/* We removed "End Interview" to the global header */}
        <div className="flex items-center gap-2 flex-1 justify-start">
          <SecondaryButton 
            icon={<SkipForward className="h-4 w-4" />}
            label={processingAction === "SKIP_QUESTION" ? "Skipping..." : "Skip"}
            disabled={isCompleted || isProcessing || !allowedControls.includes("SKIP_QUESTION")}
            onClick={() => handleAction("SKIP_QUESTION")}
            isLoading={processingAction === "SKIP_QUESTION"}
            tooltip="Skip this question"
          />

          <SecondaryButton
            icon={<LogOut className="h-4 w-4" />}
            label={processingAction === "END_SECTION_EARLY" ? "Ending section..." : "End Section"}
            disabled={isCompleted || isProcessing || !allowedControls.includes("END_SECTION_EARLY")}
            onClick={() => handleAction("END_SECTION_EARLY")}
            isLoading={processingAction === "END_SECTION_EARLY"}
            tooltip="End this section early"
            variant="warning"
          />
        </div>
      </div>

      <EndSectionEarlyDialog
        isOpen={isEndSectionDialogOpen}
        hasNextSection={hasNextSection}
        onCancel={() => setIsEndSectionDialogOpen(false)}
        onConfirm={handleConfirmEndSection}
      />
    </div>
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
