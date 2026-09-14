import * as React from "react"
import { cn } from "../ui/utils"

interface ContainerProps extends React.HTMLAttributes<HTMLDivElement> {
  size?: "default" | "reading" | "interview"
}

export const Container = React.forwardRef<HTMLDivElement, ContainerProps>(
  ({ className, size = "default", ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={cn(
          "mx-auto w-full px-4 md:px-8 lg:px-12",
          {
            "max-w-7xl": size === "default",
            "max-w-3xl": size === "reading",
            "max-w-[800px]": size === "interview",
          },
          className
        )}
        {...props}
      />
    )
  }
)
Container.displayName = "Container"
