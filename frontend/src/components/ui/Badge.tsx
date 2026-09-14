import * as React from "react";
import { cn } from "./utils";

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "secondary" | "success" | "warning" | "destructive" | "outline";
}

export function Badge({ className, variant = "default", ...props }: BadgeProps) {
  return (
    <div
      className={cn(
        "inline-flex items-center rounded-md px-2.5 py-0.5 text-xs font-medium transition-colors border",
        {
          "bg-primary/10 text-primary border-primary/20": variant === "default",
          "bg-secondary text-secondary-foreground border-transparent": variant === "secondary",
          // Design audit (2026-09-01): was raw green-500/yellow-500 -- off-
          // system colors with no relationship to the app's own success/
          // warning tokens (index.css), so a future token change (like the
          // WCAG-contrast fix that motivated this pass) silently wouldn't
          // apply here. success/warning are now the corrected, AA-passing
          // values -- see index.css's own comment for the computation.
          "bg-success/10 text-success border-transparent": variant === "success",
          "bg-warning/10 text-warning border-transparent": variant === "warning",
          "bg-destructive/10 text-destructive border-destructive/20": variant === "destructive",
          "text-foreground border-border bg-transparent": variant === "outline",
        },
        className
      )}
      {...props}
    />
  );
}
