import * as React from "react"
import { cn } from "@/lib/utils"

// SegmentedControl (UI design 6.1, 9.3): 2 to 4 buttons in one track.
// mode "toggle": buttons with aria-pressed; Tab and Space. mode "radio": role "radiogroup"; arrows move and select.
function SegmentedControl({ mode = "toggle", options = [], value, onValueChange, disabled = false, "aria-label": ariaLabel, className }) {
  const refs = React.useRef([])
  const enabled = options.filter((option) => !option.disabled && !disabled)
  const move = (from, step) => {
    if (!enabled.length) return
    const position = enabled.findIndex((option) => option.value === from)
    const next = enabled[(position + step + enabled.length) % enabled.length]
    onValueChange?.(next.value)
    refs.current[options.indexOf(next)]?.focus()
  }
  const onKeyDown = (event, option) => {
    if (mode !== "radio") return
    if (event.key === "ArrowRight" || event.key === "ArrowDown") { event.preventDefault(); move(option.value, 1) }
    else if (event.key === "ArrowLeft" || event.key === "ArrowUp") { event.preventDefault(); move(option.value, -1) }
    else if (event.key === "Home") { event.preventDefault(); move(enabled[0]?.value, 0) }
    else if (event.key === "End") { event.preventDefault(); move(enabled[enabled.length - 1]?.value, 0) }
  }
  const tabStop = options.some((option) => option.value === value) ? value : enabled[0]?.value
  return (
    <div
      role={mode === "radio" ? "radiogroup" : "group"}
      aria-label={ariaLabel}
      aria-disabled={disabled || undefined}
      className={cn("ui-segmented", className)}
      data-mode={mode}>
      {options.map((option, index) => {
        const on = option.value === value
        const radio = mode === "radio"
        return (
          <button
            key={option.value}
            ref={(node) => { refs.current[index] = node }}
            type="button"
            role={radio ? "radio" : undefined}
            aria-checked={radio ? on : undefined}
            aria-pressed={radio ? undefined : on}
            tabIndex={radio ? (option.value === tabStop ? 0 : -1) : undefined}
            disabled={disabled || option.disabled}
            data-state={on ? "on" : "off"}
            className="ui-segment"
            onClick={() => onValueChange?.(option.value)}
            onKeyDown={(event) => onKeyDown(event, option)}>
            {option.icon ? <option.icon aria-hidden="true" /> : null}
            <span>{option.label}</span>
          </button>
        )
      })}
    </div>
  )
}

export { SegmentedControl }
