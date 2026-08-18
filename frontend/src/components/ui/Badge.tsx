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
          "bg-success/10 text-success border-success/20": variant === "success",
          "bg-warning/10 text-warning-foreground border-warning/20": variant === "warning",
          "bg-destructive/10 text-destructive border-destructive/20": variant === "destructive",
          "text-foreground border-border bg-transparent": variant === "outline",
        },
        className
      )}
      {...props}
    />
  );
}
