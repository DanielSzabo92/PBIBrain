import * as React from "react"
import { CircleAlert, CircleCheck, CircleX, Inbox, X } from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "./button"

const RESULT_ICONS = { success: CircleCheck, differences: CircleAlert, failure: CircleX }

// ResultPanel (UI design 6.1, 9.2): icon, title, text, optional table, actions, close.
// role "status" for success and differences, role "alert" for failure.
// The title has tabindex -1, so that the caller can move focus to it (titleRef).
function ResultPanel({ tone = "success", title, children, actions, onClose, titleRef, headingLevel = 2, className }) {
  const Icon = RESULT_ICONS[tone] || CircleCheck
  const Heading = `h${headingLevel}`
  return (
    <section role={tone === "failure" ? "alert" : "status"} data-slot="result-panel" data-tone={tone} className={cn("ui-result", className)}>
      <Icon className="ui-result-icon" aria-hidden="true" />
      <div className="ui-result-body">
        <Heading ref={titleRef} tabIndex={-1} className="ui-result-title">{title}</Heading>
        {children ? <div className="ui-result-text">{children}</div> : null}
        {actions ? <div className="ui-result-actions">{actions}</div> : null}
      </div>
      {onClose ? <Button variant="ghost" size="icon-sm" className="ui-result-close" aria-label="Close result" onClick={onClose}><X /></Button> : null}
    </section>
  )
}

// EmptyState (UI design 6.1): icon, title, text, primary action. The error variant has role "alert".
function EmptyState({ icon: Icon = Inbox, title, children, action, variant = "default", headingLevel = 3, className }) {
  const Heading = `h${headingLevel}`
  const error = variant === "error"
  return (
    <div role={error ? "alert" : undefined} data-slot="empty-state" data-variant={variant} className={cn("ui-empty", className)}>
      <span className="ui-empty-icon" aria-hidden="true">{error ? <CircleX /> : <Icon />}</span>
      <Heading className="ui-empty-title">{title}</Heading>
      {children ? <p className="ui-empty-text">{children}</p> : null}
      {action ? <div className="ui-empty-action">{action}</div> : null}
    </div>
  )
}

// Skeleton (UI design 6.1): surface-3 bars. The region has aria-busy and a visible status text.
function Skeleton({ lines = 3, label = "Loading", className }) {
  return (
    <div data-slot="skeleton" aria-busy="true" className={cn("ui-skeleton", className)}>
      <p className="ui-skeleton-status" role="status">{label}</p>
      {Array.from({ length: lines }, (_, index) => <span key={index} className="ui-skeleton-bar" aria-hidden="true" />)}
    </div>
  )
}

export { ResultPanel, EmptyState, Skeleton }
