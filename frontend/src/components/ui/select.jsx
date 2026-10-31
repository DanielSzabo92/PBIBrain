import * as React from "react"
import { Check, ChevronDown, LoaderCircle } from "lucide-react"
import { Select as SelectPrimitive } from "radix-ui"
import { cn } from "@/lib/utils"
import { Field, hasHint, useFieldIds } from "./field"

// Select (UI design 6.1, house rule 4: no native select in new screens).
// options: [{ value, label, description?, disabled?, reason? }]. A disabled option shows its reason as text (A17).
// Keys (Radix): Enter, Space, Up, Down open; typeahead; Home, End; Enter selects; Escape closes.
function Select({ id, label, "aria-label": ariaLabel, value, defaultValue, onValueChange, options = [], placeholder = "Select", disabled = false, loading = false, error, hint, className, triggerClassName }) {
  const ids = useFieldIds(id)
  const described = hasHint({ hint, error }) ? ids.hint : undefined
  return (
    <Field ids={ids} label={label} hint={hint} error={error} className={className}>
      <SelectPrimitive.Root value={value} defaultValue={defaultValue} onValueChange={onValueChange} disabled={disabled}>
        <SelectPrimitive.Trigger
          id={ids.control}
          data-slot="select-trigger"
          className={cn("ui-select-trigger", triggerClassName)}
          aria-labelledby={label ? ids.label : undefined}
          aria-label={label ? undefined : ariaLabel}
          aria-haspopup="listbox"
          aria-invalid={error ? true : undefined}
          aria-describedby={described}>
          <SelectPrimitive.Value placeholder={placeholder} />
          <SelectPrimitive.Icon className="ui-select-chevron"><ChevronDown aria-hidden="true" /></SelectPrimitive.Icon>
        </SelectPrimitive.Trigger>
        <SelectPrimitive.Portal>
          <SelectPrimitive.Content data-slot="select-content" className="ui-listbox" position="popper" sideOffset={4}>
            <SelectPrimitive.Viewport className="ui-listbox-viewport">
              {loading ? (
                <SelectPrimitive.Item value="__loading" disabled className="ui-option is-loading">
                  <LoaderCircle className="spin" aria-hidden="true" />
                  <SelectPrimitive.ItemText>Loading</SelectPrimitive.ItemText>
                </SelectPrimitive.Item>
              ) : options.map((option) => <SelectOption key={option.value} option={option} baseId={ids.control} />)}
            </SelectPrimitive.Viewport>
          </SelectPrimitive.Content>
        </SelectPrimitive.Portal>
      </SelectPrimitive.Root>
    </Field>
  )
}

function SelectOption({ option, baseId }) {
  const reasonId = option.reason ? `${baseId}-reason-${option.value}` : undefined
  return (
    <SelectPrimitive.Item value={option.value} disabled={option.disabled} className="ui-option" aria-describedby={reasonId}>
      <span className="ui-option-check" aria-hidden="true"><SelectPrimitive.ItemIndicator><Check /></SelectPrimitive.ItemIndicator></span>
      <span className="ui-option-text">
        <SelectPrimitive.ItemText>{option.label}</SelectPrimitive.ItemText>
        {option.description ? <small className="ui-option-line">{option.description}</small> : null}
        {option.reason ? <small id={reasonId} className="ui-option-reason">{option.reason}</small> : null}
      </span>
    </SelectPrimitive.Item>
  )
}

export { Select }
