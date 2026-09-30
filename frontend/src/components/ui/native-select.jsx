import * as React from "react"
import { cn } from "@/lib/utils"
import { ChevronsUpDown } from "lucide-react"

function NativeSelect({
  className,
  size = "default",
  ...props
}) {
  return (
    <div
      className="group/native-select relative w-fit has-[select:disabled]:opacity-50"
      data-slot="native-select-wrapper">
      <select
        data-slot="native-select"
        data-size={size}
        className={cn(
          "ui-select h-8 w-full min-w-0 appearance-none rounded-md pl-2.5 pr-8 text-[13px] outline-none disabled:pointer-events-none disabled:cursor-not-allowed data-[size=sm]:h-7",
          "aria-invalid:border-destructive",
          className
        )}
        {...props} />
      <ChevronsUpDown
        className="pointer-events-none absolute top-1/2 right-2.5 size-3.5 -translate-y-1/2 text-[var(--text-3)] select-none"
        aria-hidden="true"
        data-slot="native-select-icon" />
    </div>
  );
}

function NativeSelectOption({
  className,
  ...props
}) {
  return (
    <option
      data-slot="native-select-option"
      className={cn("bg-[Canvas] text-[CanvasText]", className)}
      {...props} />
  );
}

function NativeSelectOptGroup({
  className,
  ...props
}) {
  return (
    <optgroup
      data-slot="native-select-optgroup"
      className={cn("bg-[Canvas] text-[CanvasText]", className)}
      {...props} />
  );
}

export { NativeSelect, NativeSelectOptGroup, NativeSelectOption }
