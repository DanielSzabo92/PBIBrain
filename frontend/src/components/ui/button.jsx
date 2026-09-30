import * as React from "react"
import { cva } from "class-variance-authority";
import { cn } from "@/lib/utils"
import { Slot } from "radix-ui"

const buttonVariants = cva(
  "ui-button inline-flex shrink-0 items-center justify-center gap-1.5 rounded-md text-[13px] font-medium whitespace-nowrap select-none disabled:pointer-events-none disabled:opacity-45 aria-invalid:border-destructive [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-[15px]",
  {
    variants: {
      variant: {
        default: "ui-button-primary",
        destructive: "ui-button-destructive",
        outline: "ui-button-outline",
        secondary: "ui-button-secondary",
        ghost: "ui-button-ghost",
        link: "ui-button-link",
      },
      size: {
        default: "h-8 px-3 has-[>svg]:px-2.5",
        xs: "h-6 gap-1 rounded-[5px] px-2 text-xs [&_svg:not([class*='size-'])]:size-3",
        sm: "h-7 gap-1.5 rounded-[6px] px-2.5 text-[12.5px] has-[>svg]:px-2",
        lg: "h-10 rounded-lg px-5 text-sm",
        icon: "size-8",
        "icon-xs": "size-6 rounded-[5px] [&_svg:not([class*='size-'])]:size-3",
        "icon-sm": "size-7 rounded-[6px]",
        "icon-lg": "size-10",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

const Button = React.forwardRef(function Button({
  className,
  variant = "default",
  size = "default",
  asChild = false,
  ...props
}, ref) {
  const Comp = asChild ? Slot.Root : "button"
  return (
    <Comp
      ref={ref}
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props} />
  );
});

export { Button, buttonVariants }
