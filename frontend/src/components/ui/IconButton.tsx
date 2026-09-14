import * as React from "react";
import { cn } from "./utils";

export interface IconButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  "aria-label": string; // Explicitly required for accessibility
  variant?: "primary" | "secondary" | "ghost" | "destructive";
  shape?: "circle" | "square";
}

export const IconButton = React.forwardRef<HTMLButtonElement, IconButtonProps>(
  ({ className, variant = "ghost", shape = "square", "aria-label": ariaLabel, ...props }, ref) => {
    return (
      <button
        ref={ref}
        aria-label={ariaLabel}
        className={cn(
          "inline-flex items-center justify-center transition-colors",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
          "disabled:pointer-events-none disabled:opacity-50",
          "h-10 w-10 shrink-0", // Default size, can be overridden via className
          {
            "rounded-full": shape === "circle",
            "rounded-md": shape === "square",
            "bg-primary text-primary-foreground hover:bg-primary/90": variant === "primary",
            "bg-secondary text-secondary-foreground hover:bg-secondary/80": variant === "secondary",
            "hover:bg-accent hover:text-accent-foreground text-muted-foreground": variant === "ghost",
            "bg-destructive text-destructive-foreground hover:bg-destructive/90": variant === "destructive",
          },
          className
        )}
        {...props}
      />
    );
  }
);
IconButton.displayName = "IconButton";
