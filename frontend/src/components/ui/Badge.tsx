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
          "bg-green-500/10 text-green-500 border-transparent": variant === "success",
          "bg-yellow-500/10 text-yellow-500 border-transparent": variant === "warning",
          "bg-destructive/10 text-destructive border-destructive/20": variant === "destructive",
          "text-foreground border-border bg-transparent": variant === "outline",
        },
        className
      )}
      {...props}
    />
  );
}
