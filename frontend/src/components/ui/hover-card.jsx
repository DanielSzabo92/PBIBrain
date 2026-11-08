import * as React from "react";
import { HoverCard as HoverCardPrimitive } from "radix-ui";
import { cn } from "@/lib/utils";

function HoverCard({ children, open, onOpenChange, ...props }) {
  return (
    <HoverCardPrimitive.Root open={open} onOpenChange={onOpenChange} openDelay={200} closeDelay={150} {...props}>
      {children}
    </HoverCardPrimitive.Root>
  );
}

function HoverCardTrigger({ ...props }) {
  return <HoverCardPrimitive.Trigger data-slot="hover-card-trigger" {...props} />;
}

function HoverCardContent({ className, align = "start", side = "top", sideOffset = 6, ...props }) {
  return (
    <HoverCardPrimitive.Portal>
      <HoverCardPrimitive.Content
        data-slot="hover-card-content"
        align={align}
        side={side}
        sideOffset={sideOffset}
        className={cn("ui-hover-card", className)}
        {...props}
      />
    </HoverCardPrimitive.Portal>
  );
}

export { HoverCard, HoverCardTrigger, HoverCardContent };
