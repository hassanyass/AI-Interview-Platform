import { useState, useEffect } from "react";
import { Mic, MicOff, RefreshCcw, HelpCircle, SkipForward, Square, Loader2 } from "lucide-react";
import { EndInterviewDialog } from "./EndInterviewDialog";

export type ControlState = "IDLE" | "PROCESSING" | "ENDING" | "ENDED";

interface InterviewControllerProps {
  isCompleted: boolean;
  allowedControls: string[];
  isMicrophoneEnabled: boolean;
  onToggleMicrophone: () => void;
  onSendControl: (control: string) => void;
  backendState: any; // Used to trigger reset from processing
}

export function InterviewController({
  isCompleted,
  allowedControls,
  isMicrophoneEnabled,
  onToggleMicrophone,
  onSendControl,
  backendState,
}: InterviewControllerProps) {
  const [controlState, setControlState] = useState<ControlState>(isCompleted ? "ENDED" : "IDLE");
  const [processingAction, setProcessingAction] = useState<string | null>(null);
  const [isEndDialogOpen, setIsEndDialogOpen] = useState(false);
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

  const isProcessing = controlState === "PROCESSING" || controlState === "ENDING";

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

        {/* Right Side: Skip and End */}
        <div className="flex items-center gap-2 flex-1 justify-start">
          <SecondaryButton 
            icon={<SkipForward className="h-4 w-4" />}
            label={processingAction === "SKIP_QUESTION" ? "Skipping..." : "Skip"}
            disabled={isCompleted || isProcessing || !allowedControls.includes("SKIP_QUESTION")}
            onClick={() => handleAction("SKIP_QUESTION")}
            isLoading={processingAction === "SKIP_QUESTION"}
            tooltip="Skip this question"
          />
          
          <button 
            disabled={isCompleted || isProcessing}
            onClick={() => handleAction("END_INTERVIEW")} 
            title="End Interview"
            className="flex items-center gap-2 px-4 py-2.5 text-sm font-medium text-destructive hover:bg-destructive/10 border border-destructive/20 rounded-full transition-colors disabled:opacity-50 disabled:cursor-not-allowed ml-2"
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
  tooltip
}: { 
  icon: React.ReactNode, 
  label: string, 
  disabled: boolean, 
  onClick: () => void,
  isLoading?: boolean,
  tooltip?: string
}) {
  return (
    <button 
      disabled={disabled}
      onClick={onClick} 
      title={disabled ? tooltip : undefined}
      className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium rounded-full transition-colors
        ${disabled 
          ? "bg-secondary/40 text-muted-foreground/60 cursor-not-allowed" 
          : "bg-secondary text-secondary-foreground hover:bg-secondary/80 cursor-pointer"
        }
      `}
    >
      {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : icon}
      <span className="hidden sm:inline">{label}</span>
    </button>
  );
}
