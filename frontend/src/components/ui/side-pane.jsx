import * as React from "react"
import { ChevronDown, ChevronUp, X } from "lucide-react"
import { Dialog as DialogPrimitive } from "radix-ui"
import { cn } from "@/lib/utils"
import { Button } from "./button"

// SidePane (UI design 6.1, 9.2, A10). At 1280 px and wider it is an aside next to the main region.
// Below 1280 px it is a modal sheet (Radix Dialog, min(400px, 92vw)) with a focus trap.
// Previous and Next stay in place at the first and the last row (aria-disabled), so that focus
// stays on the same button (UI design 9.2). When it opens, focus goes to the h2. Close or Escape returns focus to the opener,
// else to returnFocusRef.
const SIDE_PANE_WIDE = "(min-width: 1280px)"

function useWide() {
  const query = React.useMemo(() => (typeof window !== "undefined" && window.matchMedia ? window.matchMedia(SIDE_PANE_WIDE) : null), [])
  const [wide, setWide] = React.useState(() => (query ? query.matches : true))
  React.useEffect(() => {
    if (!query) return undefined
    const change = () => setWide(query.matches)
    query.addEventListener("change", change)
    return () => query.removeEventListener("change", change)
  }, [query])
  return wide
}

const SheetTitle = React.forwardRef(function SheetTitle(props, ref) {
  return <DialogPrimitive.Title asChild><h2 ref={ref} {...props} /></DialogPrimitive.Title>
})

function SidePane({ open, onClose, title, onPrevious, onNext, canPrevious = true, canNext = true, previousLabel = "Previous row", nextLabel = "Next row", returnFocusRef, children, className, busy = false }) {
  const wide = useWide()
  const heading = React.useRef(null)
  const opener = React.useRef(null)
  const titleId = React.useId().replace(/:/g, "")

  React.useLayoutEffect(() => {
    if (open) {
      const current = document.activeElement
      if (current && current !== document.body && !heading.current?.closest("[data-slot=side-pane]")?.contains(current)) opener.current = current
    }
  }, [open])

  React.useEffect(() => {
    if (open && wide) heading.current?.focus()
  }, [open, wide])

  const returnFocus = React.useCallback(() => {
    const target = opener.current?.isConnected ? opener.current : returnFocusRef?.current
    target?.focus?.()
  }, [returnFocusRef])

  const close = React.useCallback(() => {
    onClose?.()
    // The opener can be in an inert region while the sheet is open, so wait one frame.
    requestAnimationFrame(returnFocus)
  }, [onClose, returnFocus])

  if (!open) return null

  const header = (TitleTag) => (
    <div className="ui-pane-header">
      <TitleTag ref={heading} {...(TitleTag === "h2" ? { id: titleId } : {})} tabIndex={-1} className="ui-pane-title">{title}</TitleTag>
      <div className="ui-pane-nav">
        {onPrevious ? <Button variant="ghost" size="icon-sm" aria-label={previousLabel} aria-disabled={!canPrevious || undefined} onClick={canPrevious ? onPrevious : undefined}><ChevronUp /></Button> : null}
        {onNext ? <Button variant="ghost" size="icon-sm" aria-label={nextLabel} aria-disabled={!canNext || undefined} onClick={canNext ? onNext : undefined}><ChevronDown /></Button> : null}
        <Button variant="ghost" size="icon-sm" aria-label="Close" onClick={close}><X /></Button>
      </div>
    </div>
  )

  if (wide) {
    return (
      <aside
        data-slot="side-pane"
        aria-labelledby={titleId}
        aria-busy={busy || undefined}
        className={cn("ui-side-pane", className)}
        onKeyDown={(event) => { if (event.key === "Escape") { event.stopPropagation(); close() } }}>
        {header("h2")}
        <div className="ui-pane-body">{children}</div>
      </aside>
    )
  }

  return (
    <DialogPrimitive.Root open onOpenChange={(next) => { if (!next) close() }}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="ui-scrim" />
        <DialogPrimitive.Content
          data-slot="side-pane"
          data-mode="sheet"
          aria-modal="true"
          aria-describedby={undefined}
          aria-busy={busy || undefined}
          className={cn("ui-side-pane ui-sheet", className)}
          onOpenAutoFocus={(event) => { event.preventDefault(); heading.current?.focus() }}
          onCloseAutoFocus={(event) => { event.preventDefault(); returnFocus() }}>
          {header(SheetTitle)}
          <div className="ui-pane-body">{children}</div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}

export { SidePane }
