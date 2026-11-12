import { Button } from "./button";
import * as React from "react"
import { cn } from "@/lib/utils"
import { X as XIcon } from "lucide-react"
import { Dialog as SheetPrimitive } from "radix-ui"

function Sheet({
  ...props
}) {
  return <SheetPrimitive.Root data-slot="sheet" {...props} />;
}

function SheetTrigger({
  ...props
}) {
  return <SheetPrimitive.Trigger data-slot="sheet-trigger" {...props} />;
}

function SheetPortal({
  ...props
}) {
  return <SheetPrimitive.Portal data-slot="sheet-portal" {...props} />;
}

function SheetContent({
  className,
  children,
  side = "right",
  showCloseButton = true,
  ...props
}) {
  // Non-modal: the sheet floats over the canvas without a scrim so the graph stays readable.
  return (
    <SheetPortal>
      <SheetPrimitive.Content
        data-slot="sheet-content"
        data-ui-container=""
        data-side={side}
        className={cn("ui-sheet fixed z-50 flex flex-col", className)}
        {...props}>
        {children}
        {showCloseButton && (
          <div className="ui-sheet-close"><SheetPrimitive.Close asChild><Button variant="ghost" size="icon-sm" aria-label="Close">
            <XIcon className="size-4" aria-hidden="true" />
          </Button></SheetPrimitive.Close></div>
        )}
      </SheetPrimitive.Content>
    </SheetPortal>
  );
}

function SheetHeader({
  className,
  ...props
}) {
  return (
    <div
      data-slot="sheet-header"
      className={cn("flex flex-col gap-1.5", className)}
      {...props} />
  );
}

function SheetTitle({
  className,
  ...props
}) {
  return (
    <SheetPrimitive.Title
      data-slot="sheet-title"
      className={cn("font-semibold text-foreground", className)}
      {...props} />
  );
}

function SheetDescription({
  className,
  ...props
}) {
  return (
    <SheetPrimitive.Description
      data-slot="sheet-description"
      className={cn("text-sm text-muted-foreground", className)}
      {...props} />
  );
}

export {
  Sheet,
  SheetTrigger,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
}
