import * as React from "react"
import { LoaderCircle } from "lucide-react"
import { RadioGroup as RadioPrimitive } from "radix-ui"
import { cn } from "@/lib/utils"

// ChoiceRadio group (UI design 6.1), on Radix RadioGroup, in a fieldset with a legend.
// items: [{ value, label, badge?, reason?, disabled?, children? }]. The selected item shows its children (sub-fields).
// A disabled item has aria-describedby on its reason (A17). Tab goes into the group; arrows move and select.
function ChoiceRadio({ legend, items = [], value, onValueChange, disabled = false, loading = false, loadingText = "Saving", className }) {
  const baseId = React.useId().replace(/:/g, "")
  return (
    <fieldset className={cn("ui-choice", className)} aria-busy={loading || undefined}>
      <legend className="ui-choice-legend">{legend}</legend>
      <RadioPrimitive.Root className="ui-choice-list" value={value} onValueChange={onValueChange} disabled={disabled} aria-label={legend}>
        {items.map((item) => {
          const itemId = `${baseId}-${item.value}`
          const reasonId = item.reason ? `${itemId}-reason` : undefined
          const selected = item.value === value
          return (
            <div
              key={item.value}
              className={cn("ui-choice-item", item.className, item.tone && `ui-choice-item-${item.tone}`)}
              data-selected={selected || undefined}
              data-disabled={item.disabled || disabled || undefined}
              data-tone={item.tone || undefined}
            >
              <div className="ui-choice-row">
                <RadioPrimitive.Item id={itemId} value={item.value} disabled={item.disabled} className="ui-radio" aria-describedby={reasonId}>
                  <RadioPrimitive.Indicator className="ui-radio-dot" />
                </RadioPrimitive.Item>
                <label htmlFor={itemId} className="ui-choice-label">{item.label}</label>
                {item.badge || null}
              </div>
              {item.reason ? <p id={reasonId} className="ui-choice-reason">{item.reason}</p> : null}
              {selected && item.children ? <div className="ui-choice-sub">{item.children}</div> : null}
            </div>
          )
        })}
      </RadioPrimitive.Root>
      {loading ? <p className="ui-choice-status" role="status"><LoaderCircle className="spin" aria-hidden="true" />{loadingText}</p> : null}
    </fieldset>
  )
}

export { ChoiceRadio }
