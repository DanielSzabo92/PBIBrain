import * as React from "react"
import { CircleX, LoaderCircle } from "lucide-react"
import { cn } from "@/lib/utils"

// Shared label and hint of a form part (UI design 6.2: error and loading rows, A16, A17).
// The hint id goes into aria-describedby of the control.
export function useFieldIds(id) {
  const auto = React.useId()
  const base = id || `field-${auto.replace(/:/g, "")}`
  return { control: base, label: `${base}-label`, hint: `${base}-hint`, list: `${base}-list` }
}

function FieldHint({ id, error, loading, children }) {
  if (!error && !loading && !children) return null
  return (
    <p id={id} className={cn("ui-field-hint", error && "is-error")}>
      {error ? <CircleX aria-hidden="true" /> : loading ? <LoaderCircle className="spin" aria-hidden="true" /> : null}
      <span>{error || children}</span>
    </p>
  )
}

export function hasHint({ hint, error, loading }) {
  return Boolean(hint || error || loading)
}

export function Field({ ids, label, hint, error, loading, className, children }) {
  return (
    <div className={cn("ui-field", className)}>
      {label ? <label id={ids.label} htmlFor={ids.control} className="ui-field-label">{label}</label> : null}
      {children}
      <FieldHint id={ids.hint} error={error} loading={loading}>{hint}</FieldHint>
    </div>
  )
}
