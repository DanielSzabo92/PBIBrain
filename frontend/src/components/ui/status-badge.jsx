import * as React from "react"
import { Circle, CircleCheck, CircleHelp, CircleX, Info, Sparkles, TriangleAlert } from "lucide-react"
import { cn } from "@/lib/utils"
import { statusBadgeProps } from "./status-badge-rules.js"

const ICONS = { ok: CircleCheck, warn: TriangleAlert, bad: CircleX, info: Info, plain: Circle, proposal: Sparkles }

// A status: icon plus word, never color only (A4). With "description", the badge is a
// button that holds the description in its aria-label, for use as a tooltip trigger.
const StatusBadge = React.forwardRef(function StatusBadge({ tone, label, icon, help = false, description, className, ...props }, ref) {
  const checked = statusBadgeProps({ tone, label })
  const Icon = icon || (help ? CircleHelp : ICONS[checked.tone])
  const content = <><Icon aria-hidden="true" /><span>{checked.label}</span></>
  const common = { "data-slot": "status-badge", "data-status": checked.tone, "data-tone": checked.tone, className: cn("ui-status-badge", className) }
  if (description) {
    return <button ref={ref} type="button" {...common} data-trigger="true" aria-label={`${checked.label}. ${description}`} {...props}>{content}</button>
  }
  return <span ref={ref} {...common} {...props}>{content}</span>
})

export { StatusBadge }
