import * as React from "react"
import { Switch as SwitchPrimitive } from "radix-ui"
import { cn } from "@/lib/utils"

// Switch (UI design 6.1), on Radix Switch: role "switch", aria-checked, Space toggles.
function Switch({ id, label, description, className, ...props }) {
  const auto = React.useId().replace(/:/g, "")
  const controlId = id || `switch-${auto}`
  const descriptionId = description ? `${controlId}-description` : undefined
  return (
    <div className={cn("ui-switch-field", className)}>
      <SwitchPrimitive.Root id={controlId} className="ui-switch" aria-describedby={descriptionId} {...props}>
        <SwitchPrimitive.Thumb className="ui-switch-thumb" />
      </SwitchPrimitive.Root>
      <div className="ui-switch-text">
        <label htmlFor={controlId}>{label}</label>
        {description ? <small id={descriptionId}>{description}</small> : null}
      </div>
    </div>
  )
}

export { Switch }
