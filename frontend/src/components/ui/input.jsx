import * as React from "react"
import { cn } from "@/lib/utils"

function Input({
  className,
  type,
  ...props
}) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "ui-input h-8 w-full min-w-0 rounded-md px-2.5 text-[13px] outline-none placeholder:text-[var(--text-3)] disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50",
        "aria-invalid:border-destructive",
        className
      )}
      {...props} />
  );
}

export { Input }
