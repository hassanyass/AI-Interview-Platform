import { useEffect, useRef } from "react";
import { X, AlertTriangle } from "lucide-react";
import { useTranslation } from "react-i18next";

interface EndSectionEarlyDialogProps {
  isOpen: boolean;
  /** Whether there is another section after this one (affects description copy) */
  hasNextSection: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function EndSectionEarlyDialog({
  isOpen,
  hasNextSection,
  onConfirm,
  onCancel,
}: EndSectionEarlyDialogProps) {
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
      className="fixed inset-0 z-[100] grid min-h-screen place-items-center bg-slate-950/60 p-4 backdrop-blur-[2px]"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onCancel();
      }}
    >
      <div
        ref={dialogRef}
        tabIndex={-1}
        role="dialog"
        aria-labelledby="end-section-dialog-title"
        aria-describedby="end-section-dialog-description"
        aria-modal="true"
        className="relative w-full max-w-md overflow-hidden rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl outline-none sm:p-7"
      >
        {/* Close button */}
        <button
          type="button"
          onClick={onCancel}
          aria-label="Close dialog"
          className="absolute end-4 top-4 rounded-md p-1.5 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
        >
          <X className="h-4 w-4" />
        </button>

        {/* Icon */}
        <div className="mb-5 flex h-10 w-10 items-center justify-center rounded-xl bg-amber-50 text-amber-600">
          <AlertTriangle className="h-5 w-5" />
        </div>

        {/* Title */}
        <h2
          id="end-section-dialog-title"
          className="mb-2 text-xl font-semibold text-slate-950"
        >
          {t("endSectionEarly.title")}
        </h2>

        {/* Description - context-aware */}
        <p
          id="end-section-dialog-description"
          className="mb-7 text-sm leading-6 text-slate-500"
        >
          {hasNextSection
            ? t("endSectionEarly.description")
            : t("endSectionEarly.descriptionLast")}
        </p>

        {/* Actions */}
        <div className="flex flex-col-reverse gap-2.5 sm:flex-row sm:justify-end">
          <button
            onClick={onCancel}
            className="rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-primary/50"
          >
            {t("endSectionEarly.cancel")}
          </button>
          <button
            onClick={onConfirm}
            autoFocus
            className="rounded-lg bg-amber-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-amber-700 focus:outline-none focus:ring-2 focus:ring-amber-500"
          >
            {t("endSectionEarly.confirm")}
          </button>
        </div>
      </div>
    </div>
  );
}
