"use client"

import * as React from "react"
import { cn } from "@/lib/utils"
import { Checkbox as CheckboxPrimitive } from "radix-ui"

// UI design 6.1: size "target" (the default) gives a 24 x 24 px hit target around the 16 px box.
// size "default" is the bare 16 px box; use it only where a surrounding control supplies the hit area.
// checked="indeterminate" shows the mixed state. aria-invalid shows the error state.
// One svg holds the check path and the dash path; CSS shows the path of the state.
function Checkbox({
  className,
  size = "target",
  ...props
}) {
  const box = (
    <CheckboxPrimitive.Indicator
      data-slot="checkbox-indicator"
      forceMount
      className="ui-checkbox-indicator grid place-content-center text-current">
      <svg viewBox="0 0 12 12" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path className="ui-checkbox-check" d="M2.5 6.2 5 8.6 9.6 3.6" />
        <path className="ui-checkbox-dash" d="M3 6h6" />
      </svg>
    </CheckboxPrimitive.Indicator>
  )
  if (size === "target") {
    return (
      <CheckboxPrimitive.Root
        data-slot="checkbox"
        data-size="target"
        className={cn("ui-checkbox-target peer shrink-0 outline-none disabled:cursor-not-allowed", className)}
        {...props}>
        <span className="ui-checkbox ui-checkbox-box size-4 rounded-[4px]" aria-hidden="true">{box}</span>
      </CheckboxPrimitive.Root>
    )
  }
  return (
    <CheckboxPrimitive.Root
      data-slot="checkbox"
      className={cn("ui-checkbox peer size-4 shrink-0 rounded-[4px] outline-none disabled:cursor-not-allowed disabled:opacity-50", className)}
      {...props}>
      {box}
    </CheckboxPrimitive.Root>
  );
}

export { Checkbox }
