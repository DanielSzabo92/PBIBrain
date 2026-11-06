import * as React from "react"
import { Tooltip as TooltipPrimitive } from "radix-ui"
import { cn } from "@/lib/utils"

// Tooltip (UI design 6.1), on Radix Tooltip: it opens on hover and on focus, and Escape closes it.
// The content is never the only place of an action.
function TooltipProvider({ children, delayDuration = 300 }) {
  return <TooltipPrimitive.Provider delayDuration={delayDuration}>{children}</TooltipPrimitive.Provider>
}

// Each tooltip carries its own provider, so a Tooltip works anywhere (no app-level provider needed).
// data-ui-tooltip names the content element, so UI checks (lintapple) can find the tooltip before it opens.
function Tooltip({ content, children, side = "top", className, delayDuration = 300 }) {
  const id = `tooltip-${React.useId().replace(/:/g, "")}`
  return (
    <TooltipPrimitive.Provider delayDuration={delayDuration}>
    <TooltipPrimitive.Root>
      <TooltipPrimitive.Trigger asChild data-ui-tooltip={id}>{children}</TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content id={id} side={side} sideOffset={6} className={cn("ui-tooltip", className)}>
          {content}
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
    </TooltipPrimitive.Provider>
  )
}

export { Tooltip, TooltipProvider }
