import * as React from "react"
import { Toaster as Sonner } from "sonner"

const Toaster = ({ ...props }) => {
  return (
    <Sonner
      className="toaster group"
      richColors
      toastOptions={{
        classNames: {
          toast:
            "group toast group-[.toaster]:bg-[var(--surface-3)] group-[.toaster]:text-[var(--text)] group-[.toaster]:border-[var(--line-strong)] group-[.toaster]:shadow-lg group-[.toaster]:rounded-md",
          description: "group-[.toast]:text-[var(--text-2)]",
          actionButton:
            "group-[.toast]:bg-[var(--surface-2)] group-[.toast]:text-[var(--text)] group-[.toast]:border group-[.toast]:border-[var(--control-border)]",
          cancelButton:
            "group-[.toast]:bg-[var(--surface-2)] group-[.toast]:text-[var(--text-2)]",
        },
      }}
      {...props}
    />
  )
}

export { Toaster }
