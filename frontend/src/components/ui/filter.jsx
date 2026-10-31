import * as React from "react"
import { ChevronDown, LoaderCircle, X } from "lucide-react"
import { Popover as PopoverPrimitive } from "radix-ui"
import { cn } from "@/lib/utils"
import { Checkbox } from "./checkbox"
import { Button } from "./button"

// Popover (UI design 6.1), on Radix Popover. The content has role "dialog".
function Popover({ open, onOpenChange, trigger, label, children, className }) {
  return (
    <PopoverPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <PopoverPrimitive.Trigger asChild>{trigger}</PopoverPrimitive.Trigger>
      <PopoverPrimitive.Portal>
        <PopoverPrimitive.Content data-slot="popover" className={cn("ui-popover", className)} aria-label={label} align="start" sideOffset={4}>
          {children}
        </PopoverPrimitive.Content>
      </PopoverPrimitive.Portal>
    </PopoverPrimitive.Root>
  )
}

// FilterButton: a button with the filter label and its value, and a popover with a checkbox list.
// options: [{ value, label, count? }]. selected: an array of values.
// With a value, the button has the selected style and a screen reader word "(active)".
function FilterButton({ label, options = [], selected = [], onSelectedChange, disabled = false, loading = false, error, onRetry }) {
  const active = selected.length > 0
  const summary = active ? (selected.length === 1 ? options.find((option) => option.value === selected[0])?.label || "1 selected" : `${selected.length} selected`) : "All"
  const toggle = (value, checked) => {
    const next = checked ? [...selected, value] : selected.filter((item) => item !== value)
    onSelectedChange?.(next)
  }
  const baseId = React.useId().replace(/:/g, "")
  return (
    <Popover
      label={`${label} filter`}
      trigger={
        <button type="button" className="ui-filter-button" data-active={active || undefined} disabled={disabled}>
          <span className="ui-filter-label">{label}</span>
          <span className="ui-filter-value">{summary}</span>
          {active ? <span className="sr-only">(active)</span> : null}
          <ChevronDown aria-hidden="true" />
        </button>
      }>
      {error ? (
        <div className="ui-popover-line is-error" role="alert"><span>{error}</span>{onRetry ? <Button variant="outline" size="sm" onClick={onRetry}>Try again</Button> : null}</div>
      ) : (
        <ul className="ui-filter-list" aria-busy={loading || undefined}>
          {options.map((option) => {
            const checkboxId = `${baseId}-${option.value}`
            return (
              <li key={option.value} className="ui-filter-row">
                <Checkbox id={checkboxId} size="target" checked={selected.includes(option.value)} onCheckedChange={(checked) => toggle(option.value, checked === true)} />
                <label htmlFor={checkboxId}>{option.label}</label>
                <span className="ui-filter-count">{loading ? <><LoaderCircle className="spin" aria-hidden="true" />Loading</> : option.count}</span>
              </li>
            )
          })}
        </ul>
      )}
    </Popover>
  )
}

// FilterChip: an active filter with a 24 x 24 px remove button.
function FilterChip({ label, onRemove, className }) {
  return (
    <span className={cn("ui-filter-chip", className)} data-slot="filter-chip">
      <span>{label}</span>
      <button type="button" className="ui-filter-chip-remove" aria-label={`Remove filter ${label}`} onClick={onRemove}><X aria-hidden="true" /></button>
    </span>
  )
}

export { Popover, FilterButton, FilterChip }
