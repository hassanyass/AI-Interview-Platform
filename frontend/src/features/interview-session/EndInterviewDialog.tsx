import { useEffect, useRef } from "react";

interface EndInterviewDialogProps {
  isOpen: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function EndInterviewDialog({ isOpen, onConfirm, onCancel }: EndInterviewDialogProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  
  useEffect(() => {
    if (!isOpen) return;
    
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onCancel();
      }
    };
    
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onCancel]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm">
      <div 
        ref={dialogRef}
        role="dialog"
        aria-labelledby="end-dialog-title"
        aria-describedby="end-dialog-description"
        aria-modal="true"
        className="w-full max-w-md rounded-xl border bg-card p-6 shadow-lg sm:p-8"
      >
        <h2 id="end-dialog-title" className="text-xl font-semibold mb-2 text-foreground">End interview?</h2>
        <p id="end-dialog-description" className="text-muted-foreground mb-6">
          Are you sure you want to end this interview?<br />
          Your current progress will be saved.
        </p>
        
        <div className="flex flex-col-reverse sm:flex-row justify-end gap-3">
          <button 
            onClick={onCancel}
            className="rounded-md border border-input bg-background px-4 py-2 text-sm font-medium text-foreground hover:bg-accent hover:text-accent-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2"
          >
            Continue Interview
          </button>
          <button 
            onClick={onConfirm}
            className="rounded-md bg-destructive px-4 py-2 text-sm font-medium text-destructive-foreground hover:bg-destructive/90 focus:outline-none focus:ring-2 focus:ring-destructive focus:ring-offset-2"
            autoFocus
          >
            End Interview
          </button>
        </div>
      </div>
    </div>
  );
}
