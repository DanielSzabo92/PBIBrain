import * as React from "react"
import { cva } from "class-variance-authority";
import { cn } from "@/lib/utils"
import { Slot } from "radix-ui"
import { LoaderCircle } from "lucide-react"
import { Tooltip } from "./tooltip"

const buttonVariants = cva(
  "ui-button inline-flex shrink-0 items-center justify-center gap-1.5 rounded-[4px] text-sm font-medium whitespace-nowrap select-none disabled:pointer-events-none disabled:opacity-45 aria-invalid:border-destructive [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default: "ui-button-primary",
        destructive: "ui-button-destructive",
        "destructive-outline": "ui-button-destructive-outline",
        status: "ui-button-status",
        outline: "ui-button-outline",
        secondary: "ui-button-secondary",
        ghost: "ui-button-ghost",
        link: "ui-button-link",
      },
      size: {
        default: "h-8 px-3 has-[>svg]:px-2.5",
        xs: "h-6 gap-1 rounded-[4px] px-2 text-xs [&_svg:not([class*='size-'])]:size-3",
        sm: "h-7 gap-1.5 rounded-[4px] px-2.5 text-xs has-[>svg]:px-2 [&_svg:not([class*='size-'])]:size-3.5",
        lg: "h-10 rounded-[6px] px-5 text-sm",
        icon: "size-8",
        "icon-xs": "size-6 rounded-[4px] [&_svg:not([class*='size-'])]:size-3",
        "icon-sm": "size-7 rounded-[4px]",
        "icon-lg": "size-10",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

// tone: ok, warn, or bad for the "status" variant (UI design 6.1).
// loading: the button shows a spinner and loadingText, and it does not act (aria-busy, aria-disabled).
const Button = React.forwardRef(function ButtonBase({
  className,
  variant = "default",
  size = "default",
  tone,
  loading = false,
  loadingText,
  asChild = false,
  children,
  onClick,
  tooltip,
  ...props
}, ref) {
  const Comp = asChild ? Slot.Root : "button"
  const busy = Boolean(loading)
  // An icon-only button gets a visible text tooltip from its accessible name (or the tooltip prop),
  // instead of a native title, which is slow, unstyled and invisible to keyboard users.
  const tip = tooltip === false ? null : tooltip || (String(size).startsWith("icon") && typeof props["aria-label"] === "string" ? props["aria-label"] : null)
  if (tip && !asChild) {
    const { title: _title, ...rest } = props
    const buttonNode = <Button ref={ref} variant={variant} size={size} tone={tone} loading={loading} loadingText={loadingText} className={className} onClick={onClick} tooltip={false} title={typeof tip === "string" ? tip : undefined} {...rest}>{children}</Button>
    return (
      <Tooltip content={tip}>
        {rest.disabled ? <span tabIndex={0} className="inline-flex cursor-not-allowed">{buttonNode}</span> : buttonNode}
      </Tooltip>
    )
  }
  return (
    <Comp
      {...props}
      ref={ref}
      data-slot="button"
      data-variant={variant}
      data-size={size}
      data-tone={variant === "status" ? tone || "ok" : undefined}
      data-loading={busy || undefined}
      aria-busy={busy || undefined}
      aria-disabled={busy || props["aria-disabled"] || undefined}
      className={cn(buttonVariants({ variant, size, className }))}
      onClick={busy ? (event) => event.preventDefault() : onClick}>
      {busy && !asChild ? <><LoaderCircle className="spin" aria-hidden="true" />{loadingText || children}</> : children}
    </Comp>
  );
});

Button.displayName = "Button"

export { Button, buttonVariants }
