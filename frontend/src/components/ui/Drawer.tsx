import * as React from "react";
import { X } from "lucide-react";
import { cn } from "./utils";

/**
 * Responsive plan R0 (docs/responsive-design-plan.md §3): off-canvas panel.
 * R1 uses it for the admin sidebar below `lg`; R6 uses the "bottom" side as
 * the transcript sheet on phones. Logical sides ("start"/"end") so the same
 * markup is correct in RTL without a second code path.
 *
 * Deliberately small: overlay + panel, ESC/overlay click to close, focus
 * moved into the panel on open and returned on close, body scroll locked
 * while open. No portal -- it renders where it is used, at z-50, which is
 * above the admin header (z-40 nowhere yet) and below the interview's
 * z-[100] fullscreen/end dialogs, which must always win.
 */
export interface DrawerProps {
  open: boolean;
  onClose: () => void;
  /** Which edge the panel slides in from. Logical: "start" is left in LTR, right in RTL. */
  side?: "start" | "end" | "bottom";
  title?: React.ReactNode;
  /** Accessible name when `title` is not rendered (e.g. an icon-only header). */
  "aria-label"?: string;
  className?: string;
  children: React.ReactNode;
}

export function Drawer({ open, onClose, side = "start", title, "aria-label": ariaLabel, className, children }: DrawerProps) {
  const panelRef = React.useRef<HTMLDivElement>(null);
  const restoreFocusRef = React.useRef<HTMLElement | null>(null);

  React.useEffect(() => {
    if (!open) return;
    restoreFocusRef.current = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    // Focus the panel itself (tabIndex -1) so the next Tab lands on its first control.
    panelRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
      restoreFocusRef.current?.focus?.();
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50" role="presentation">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} aria-hidden="true" />
      <div
        ref={panelRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={ariaLabel}
        className={cn(
          "absolute flex flex-col bg-background text-foreground shadow-xl outline-none",
          {
            "inset-y-0 start-0 w-[min(20rem,85vw)] border-e": side === "start",
            "inset-y-0 end-0 w-[min(20rem,85vw)] border-s": side === "end",
            "inset-x-0 bottom-0 max-h-[85dvh] rounded-t-2xl border-t pb-[var(--safe-bottom)]": side === "bottom",
          },
          className,
        )}
      >
        {(title || side === "bottom") && (
          <div className="flex shrink-0 items-center justify-between gap-3 border-b px-4 py-3">
            <div className="min-w-0 text-sm font-semibold">{title}</div>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="touch-target -me-2 flex items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        )}
        <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
      </div>
    </div>
  );
}
