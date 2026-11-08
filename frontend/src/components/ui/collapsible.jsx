import * as React from "react"
import { ChevronRight } from "lucide-react"
import { Collapsible as CollapsiblePrimitive } from "radix-ui"
import { cn } from "@/lib/utils"

const Collapsible = CollapsiblePrimitive.Root
const CollapsibleTrigger = CollapsiblePrimitive.Trigger
const CollapsibleContent = CollapsiblePrimitive.Content

function Disclosure({
  title,
  children,
  defaultOpen = false,
  open,
  onOpenChange,
  className,
  triggerClassName,
  contentClassName,
  badge,
  ...props
}) {
  const [internalOpen, setInternalOpen] = React.useState(defaultOpen)
  const isControlled = open !== undefined
  const isOpen = isControlled ? open : internalOpen
  const handleOpenChange = (next) => {
    if (!isControlled) setInternalOpen(next)
    onOpenChange?.(next)
  }

  return (
    <Collapsible
      open={isOpen}
      onOpenChange={handleOpenChange}
      className={cn("ui-collapsible rounded-md border border-[var(--border)] bg-[var(--card)] overflow-hidden", className)}
      {...props}>
      <CollapsibleTrigger
        className={cn(
          "flex w-full items-center justify-between px-3 py-2 text-left text-xs font-medium text-[var(--foreground)] transition-colors hover:bg-[var(--accent)] select-none cursor-pointer",
          triggerClassName
        )}>
        <span className="flex items-center gap-1.5">
          <ChevronRight
            className={cn("size-3.5 shrink-0 text-[var(--muted-foreground)] transition-transform duration-200", isOpen && "rotate-90")}
            aria-hidden="true"
          />
          <span>{title}</span>
        </span>
        {badge ? <span className="text-2xs text-[var(--muted-foreground)]">{badge}</span> : null}
      </CollapsibleTrigger>
      <CollapsibleContent
        className={cn(
          "px-3 pb-2.5 pt-1 text-xs text-[var(--foreground)]",
          contentClassName
        )}>
        {children}
      </CollapsibleContent>
    </Collapsible>
  )
}

export {
  Collapsible,
  CollapsibleTrigger,
  CollapsibleContent,
  Disclosure,
}
