import * as React from "react"
import { ChevronDown } from "lucide-react"
import { Accordion as AccordionPrimitive } from "radix-ui"
import { cn } from "@/lib/utils"

const Accordion = AccordionPrimitive.Root

const AccordionItem = React.forwardRef(({ className, ...props }, ref) => (
  <AccordionPrimitive.Item
    ref={ref}
    className={cn("border-b border-[var(--border)]", className)}
    {...props}
  />
))
AccordionItem.displayName = "AccordionItem"

const AccordionTrigger = React.forwardRef(({ className, children, ...props }, ref) => (
  <AccordionPrimitive.Header className="flex">
    <AccordionPrimitive.Trigger
      ref={ref}
      className={cn(
        "flex flex-1 items-center justify-between py-2.5 text-xs font-medium text-[var(--foreground)] transition-all hover:underline [&[data-state=open]>svg]:rotate-180 cursor-pointer",
        className
      )}
      {...props}>
      {children}
      <ChevronDown className="size-4 shrink-0 text-[var(--muted-foreground)] transition-transform duration-200" />
    </AccordionPrimitive.Trigger>
  </AccordionPrimitive.Header>
))
AccordionTrigger.displayName = AccordionPrimitive.Trigger.displayName

const AccordionContent = React.forwardRef(({ className, children, ...props }, ref) => (
  <AccordionPrimitive.Content
    ref={ref}
    className={cn(
      "overflow-hidden text-xs transition-all data-[state=closed]:animate-accordion-up data-[state=open]:animate-accordion-down",
      className
    )}
    {...props}>
    <div className="pb-3 pt-0">{children}</div>
  </AccordionPrimitive.Content>
))
AccordionContent.displayName = AccordionPrimitive.Content.displayName

export {
  Accordion,
  AccordionItem,
  AccordionTrigger,
  AccordionContent,
}
