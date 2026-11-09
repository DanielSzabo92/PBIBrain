import * as React from "react"
import { cn } from "@/lib/utils"

function Input({
  className,
  type,
  onKeyDown,
  ...props
}) {
  const handleKeyDown = (event) => {
    if (type === "search" && event.key === "Escape" && !event.defaultPrevented) {
      if (event.target.value) {
        event.preventDefault();
        const nativeSetter = Object.getOwnPropertyDescriptor(globalThis.HTMLInputElement?.prototype || {}, "value")?.set;
        if (nativeSetter) {
          nativeSetter.call(event.target, "");
          event.target.dispatchEvent(new Event("input", { bubbles: true }));
          event.target.dispatchEvent(new Event("change", { bubbles: true }));
        } else {
          event.target.value = "";
        }
      } else {
        event.preventDefault();
        event.target.blur();
      }
    }
    onKeyDown?.(event);
  };

  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "ui-input h-8 w-full min-w-0 rounded-md px-2.5 text-sm outline-none placeholder:text-[var(--placeholder,var(--text-3))] disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50",
        "aria-invalid:border-destructive",
        className
      )}
      onKeyDown={handleKeyDown}
      {...props} />
  );
}

export { Input }
