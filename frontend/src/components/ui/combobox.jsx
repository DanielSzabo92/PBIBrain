import * as React from "react"
import { Check, ChevronDown, FolderPlus, LoaderCircle, TriangleAlert } from "lucide-react"
import { cn } from "@/lib/utils"
import { Field, hasHint, useFieldIds } from "./field"

// Combobox (UI design 6.1, 9.3): an input with role "combobox" and a listbox of groups.
// groups: [{ label, options: [{ value, label, warn? }] }].
// createLabel(text): optional first option, for example `Use new folder "<text>"`.
// Keys: typing filters; Down opens; Up, Down move; Enter selects; Escape closes, a second Escape clears.
function Combobox({ id, label, value = "", onValueChange, groups = [], placeholder, createLabel, disabled = false, loading = false, loadingText = "Loading", listError, error, hint, className }) {
  const ids = useFieldIds(id)
  const [text, setText] = React.useState(value)
  const [open, setOpen] = React.useState(false)
  const [active, setActive] = React.useState(-1)
  const wrapper = React.useRef(null)

  React.useEffect(() => {
    const known = groups.flatMap((group) => group.options).find((option) => option.value === value)
    setText(known ? known.label : value)
    // Only a new value resets the text; a new groups array does not.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value])

  const query = text.trim().toLowerCase()
  const filtered = groups
    .map((group) => ({ ...group, options: group.options.filter((option) => !query || option.label.toLowerCase().includes(query)) }))
    .filter((group) => group.options.length)
  const items = []
  if (createLabel && text.trim() && !groups.some((group) => group.options.some((option) => option.label.toLowerCase() === query))) {
    items.push({ value: text.trim(), label: createLabel(text.trim()), create: true })
  }
  for (const group of filtered) for (const option of group.options) items.push(option)
  const optionId = (index) => `${ids.list}-option-${index}`

  const choose = (item) => {
    setText(item.create ? item.value : item.label)
    setOpen(false)
    setActive(-1)
    onValueChange?.(item.value, item)
  }

  const onKeyDown = (event) => {
    if (event.key === "ArrowDown") {
      event.preventDefault()
      if (!open) { setOpen(true); setActive(items.length ? 0 : -1); return }
      setActive((current) => Math.min(current + 1, items.length - 1))
    } else if (event.key === "ArrowUp") {
      event.preventDefault()
      if (open) setActive((current) => Math.max(current - 1, 0))
    } else if (event.key === "Enter") {
      if (open && items[active]) { event.preventDefault(); choose(items[active]) }
    } else if (event.key === "Escape") {
      if (open) { event.preventDefault(); event.stopPropagation(); setOpen(false); setActive(-1) }
      else if (text) { event.preventDefault(); event.stopPropagation(); setText(""); onValueChange?.("", null) }
    } else if (event.key === "Home" && open) {
      event.preventDefault(); setActive(0)
    } else if (event.key === "End" && open) {
      event.preventDefault(); setActive(items.length - 1)
    }
  }

  React.useEffect(() => {
    if (!open) return undefined
    const close = (event) => { if (!wrapper.current?.contains(event.target)) setOpen(false) }
    document.addEventListener("pointerdown", close)
    return () => document.removeEventListener("pointerdown", close)
  }, [open])

  let index = -1
  const renderOption = (item) => {
    index += 1
    const current = index
    const selected = !item.create && item.value === value
    return (
      <li
        key={`${item.create ? "create" : "option"}-${item.value}`}
        id={optionId(current)}
        role="option"
        aria-selected={selected}
        data-active={current === active || undefined}
        className="ui-option"
        onPointerDown={(event) => event.preventDefault()}
        onClick={() => choose(item)}
        onPointerMove={() => setActive(current)}>
        <span className="ui-option-check" aria-hidden="true">{item.create ? <FolderPlus /> : selected ? <Check /> : null}</span>
        <span className="ui-option-text">
          <span>{item.label}</span>
          {item.warn ? <small className="ui-option-warn"><TriangleAlert aria-hidden="true" />{item.warn}</small> : null}
        </span>
      </li>
    )
  }

  const described = hasHint({ hint, error }) ? ids.hint : undefined
  return (
    <Field ids={ids} label={label} hint={hint} error={error} className={className}>
      <div ref={wrapper} className="ui-combobox" data-open={open || undefined}>
        <input
          id={ids.control}
          className="ui-input ui-combobox-input"
          role="combobox"
          aria-autocomplete="list"
          aria-expanded={open}
          aria-controls={ids.list}
          aria-activedescendant={open && active >= 0 && items[active] ? optionId(active) : undefined}
          aria-invalid={error ? true : undefined}
          aria-describedby={described}
          autoComplete="off"
          placeholder={placeholder}
          disabled={disabled}
          value={text}
          onChange={(event) => { setText(event.target.value); setOpen(true); setActive(0) }}
          onKeyDown={onKeyDown} />
        <ChevronDown className="ui-combobox-chevron" aria-hidden="true" />
        <div className="ui-listbox ui-combobox-popup" hidden={!open}>
          <ul id={ids.list} role="listbox" aria-labelledby={label ? ids.label : undefined} aria-label={label ? undefined : placeholder} aria-busy={loading || undefined} className="ui-listbox-viewport">
            {loading ? null : items.filter((item) => item.create).map(renderOption)}
            {loading ? null : filtered.map((group, groupIndex) => (
              <li key={group.label} role="presentation">
                <ul role="group" aria-labelledby={`${ids.list}-group-${groupIndex}`}>
                  <li role="presentation" id={`${ids.list}-group-${groupIndex}`} className="ui-listbox-group">{group.label}</li>
                  {group.options.map((option) => renderOption(option))}
                </ul>
              </li>
            ))}
          </ul>
          {loading ? <p className="ui-listbox-line" role="status"><LoaderCircle className="spin" aria-hidden="true" />{loadingText}</p> : null}
          {!loading && listError ? <p className="ui-listbox-line is-error">{listError}</p> : null}
          {!loading && !listError && !items.length ? <p className="ui-listbox-line">No match</p> : null}
        </div>
      </div>
    </Field>
  )
}

export { Combobox }
