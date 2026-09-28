import * as React from "react";
import { MoreHorizontal } from "lucide-react";
import { cn } from "./utils";

/**
 * Responsive plan R2 (docs/responsive-design-plan.md): the overflow ("...")
 * menu that keeps an action bar to one primary + one secondary control at
 * every width. Rare and destructive actions (Unpublish, Delete) live here
 * so they never compete with the primary action or get fat-fingered on a
 * phone. Decided 2026-09-17: used at every width, not just below a
 * breakpoint, so the bar reads the same on desktop and phone.
 *
 * Small on purpose: a trigger + a popover of buttons. Closes on outside
 * click, ESC, or after an item runs. `placement="up"` is for a bar pinned
 * to the bottom of the viewport.
 */
export interface ActionMenuItem {
  label: React.ReactNode;
  icon?: React.ReactNode;
  onSelect: () => void;
  destructive?: boolean;
  disabled?: boolean;
}

export interface ActionMenuProps {
  items: ActionMenuItem[];
  /** Accessible name of the trigger, e.g. t('common.moreActions'). */
  label: string;
  placement?: "up" | "down";
  className?: string;
}

export function ActionMenu({ items, label, placement = "down", className }: ActionMenuProps) {
  const [open, setOpen] = React.useState(false);
  const rootRef = React.useRef<HTMLDivElement>(null);
  const triggerRef = React.useRef<HTMLButtonElement>(null);

  React.useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div ref={rootRef} className={cn("relative", className)}>
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        className="touch-target inline-flex items-center justify-center rounded-md border border-input bg-background text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
      >
        <MoreHorizontal className="h-5 w-5" />
      </button>
      {open && (
        <div
          role="menu"
          aria-label={label}
          className={cn(
            "absolute end-0 z-40 min-w-[11rem] overflow-hidden rounded-lg border border-border bg-background py-1 shadow-lg",
            placement === "up" ? "bottom-full mb-2" : "top-full mt-2",
          )}
        >
          {items.map((item, index) => (
            <button
              key={index}
              type="button"
              role="menuitem"
              disabled={item.disabled}
              onClick={() => {
                setOpen(false);
                item.onSelect();
              }}
              className={cn(
                "flex w-full min-h-11 items-center gap-2.5 px-3.5 py-2 text-start text-sm transition-colors disabled:opacity-50",
                item.destructive ? "text-destructive hover:bg-destructive/10" : "text-foreground hover:bg-muted",
              )}
            >
              {item.icon && <span className="shrink-0 [&>svg]:h-4 [&>svg]:w-4">{item.icon}</span>}
              <span>{item.label}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
