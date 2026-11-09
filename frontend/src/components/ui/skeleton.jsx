import * as React from "react"
import { cn } from "@/lib/utils"

function Skeleton({ className, lines, label, ...props }) {
  if (lines) {
    return (
      <div data-slot="skeleton" aria-busy="true" className={cn("ui-skeleton", className)} {...props}>
        {label ? <p className="ui-skeleton-status" role="status">{label}</p> : null}
        {Array.from({ length: lines }, (_, index) => (
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
