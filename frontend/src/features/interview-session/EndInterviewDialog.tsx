import { useEffect, useRef } from "react";
import { X } from "lucide-react";
import { useTranslation } from "react-i18next";

interface EndInterviewDialogProps {
  isOpen: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  /** "preStart": candidate is ending from the intro screen, before Start
   *  Session was clicked — no progress exists yet to "save". Defaults to
   *  the in-session copy. */
  variant?: "default" | "preStart";
}

export function EndInterviewDialog({ isOpen, onConfirm, onCancel, variant = "default" }: EndInterviewDialogProps) {
  const { t } = useTranslation();
  const dialogRef = useRef<HTMLDivElement>(null);
  
  useEffect(() => {
    if (!isOpen) return;
    dialogRef.current?.focus();
    
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
    <div
      className="fixed inset-0 z-[100] grid min-h-screen place-items-center bg-slate-950/55 p-4 backdrop-blur-[2px]"
      onMouseDown={(event) => { if (event.target === event.currentTarget) onCancel(); }}
    >
      <div 
        ref={dialogRef}
        tabIndex={-1}
        role="dialog"
        aria-labelledby="end-dialog-title"
        aria-describedby="end-dialog-description"
        aria-modal="true"
        className="relative w-full max-w-md overflow-hidden rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl outline-none sm:p-7"
      >
        <button type="button" onClick={onCancel} aria-label="Close dialog" className="absolute end-4 top-4 rounded-md p-1.5 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700">
          <X className="h-4 w-4" />
        </button>
        <div className="mb-5 flex h-10 w-10 items-center justify-center rounded-xl bg-red-50 text-red-600">
          <span className="h-2.5 w-2.5 rounded-full bg-current" />
        </div>
        <h2 id="end-dialog-title" className="mb-2 text-xl font-semibold text-slate-950">
          {variant === "preStart" ? t("endInterview.titlePreStart") : t("endInterview.title")}
        </h2>
        <p id="end-dialog-description" className="mb-7 text-sm leading-6 text-slate-500">
          {variant === "preStart" ? t("endInterview.descriptionPreStart") : t("endInterview.description")}
        </p>

        <div className="flex flex-col-reverse gap-2.5 sm:flex-row sm:justify-end">
          <button
            onClick={onCancel}
            className="rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-sky-500"
          >
            {t("endInterview.cancel")}
          </button>
          <button
            onClick={onConfirm}
            className="rounded-lg bg-red-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500"
            autoFocus
          >
            {t("endInterview.confirm")}
          </button>
        </div>
      </div>
    </div>
  );
}
