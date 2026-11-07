import * as React from "react"
import { CircleCheck, CircleDashed, CircleX, Info, TriangleAlert } from "lucide-react"
import { cn } from "@/lib/utils"

const ICONS = { info: Info, warn: TriangleAlert, bad: CircleX, ok: CircleCheck, brand: CircleDashed }

// Notice and Banner (UI design 6.1): icon, body, optional list, optional actions.
// A full hairline border on surface-2, never a one-sided colored border (house rule 5).
// role "alert" for tone "bad" or a blocking item; else role "status".
function Notice({ tone = "info", title, children, actions, blocking = false, banner = false, className, ...props }) {
  const Icon = ICONS[tone] || Info
  return (
    <div
      role={tone === "bad" || blocking ? "alert" : "status"}
      data-slot={banner ? "banner" : "notice"}
      data-tone={tone}
      className={cn("ui-notice", banner && "ui-banner", className)}
      {...props}>
      <Icon className="ui-notice-icon" aria-hidden="true" />
      <div className="ui-notice-body">
        {title ? <p className="ui-notice-title">{title}</p> : null}
        {children ? <div className="ui-notice-text">{children}</div> : null}
      </div>
      {actions ? <div className="ui-notice-actions" data-ui-actions="">{actions}</div> : null}
    </div>
  )
}

function Banner(props) {
  return <Notice banner {...props} />
}

export { Notice, Banner }
