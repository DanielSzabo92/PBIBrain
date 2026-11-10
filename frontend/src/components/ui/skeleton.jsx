import * as React from "react"
import { cn } from "@/lib/utils"

function Skeleton({ className, lines, label, ...props }) {
  const lineCount = lines ?? (label ? 3 : 0);
  if (lineCount > 0) {
    return (
      <div data-slot="skeleton" aria-busy="true" className={cn("ui-skeleton", className)} {...props}>
        {label ? <p className="ui-skeleton-status" role="status">{label}</p> : null}
        {Array.from({ length: lineCount }, (_, index) => (
          <span key={index} className="ui-skeleton-bar" aria-hidden="true" />
        ))}
      </div>
    )
  }
  return (
    <div
      data-slot="skeleton"
      aria-hidden="true"
      className={cn("animate-pulse rounded-md bg-[var(--surface-3)]", className)}
      {...props}
    />
  )
}

export { Skeleton }
