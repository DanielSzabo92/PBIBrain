import * as React from "react"
import { CircleCheck, Info, TriangleAlert } from "lucide-react"
import { Toaster as SonnerToaster, toast as sonnerToast } from "sonner"
import { cn } from "@/lib/utils"

const ICONS = { ok: CircleCheck, info: Info, warn: TriangleAlert }
// A23: a toast stays at least 8 s, and it stays while the pointer is on it or it has focus.
export const TOAST_MIN_MS = 8000

const ToastContext = React.createContext(null)

// Toast (UI design 6.1, A11, A23): unified on single Sonner toaster.
function ToastProvider({ children, duration = TOAST_MIN_MS }) {
  const existing = React.useContext(ToastContext)
  if (existing) {
    return children
  }
  return <ToastRoot duration={duration}>{children}</ToastRoot>
}

function ToastRoot({ children, duration = TOAST_MIN_MS }) {
  const dismiss = React.useCallback((id) => {
    sonnerToast.dismiss(id)
  }, [])

  const show = React.useCallback((t) => {
    const tone = t.tone || "ok"
    const text = t.text || t.title || ""
    const opts = {
      duration: Math.max(t.duration || duration, TOAST_MIN_MS),
      action: t.action ? {
        label: t.action.label,
        onClick: (event) => t.action.onClick?.(event),
      } : undefined,
    }
    if (tone === "bad" || tone === "error") {
      return sonnerToast.error(text, opts)
    }
    if (tone === "warn" || tone === "warning") {
      return sonnerToast.warning(text, opts)
    }
    if (tone === "info") {
      return sonnerToast.info(text, opts)
    }
    return sonnerToast.success(text, opts)
  }, [duration])

  const value = React.useMemo(() => ({ show, dismiss }), [show, dismiss])

  return (
    <ToastContext.Provider value={value}>
      {children}
      <SonnerToaster
        className="toaster group"
        richColors
        duration={duration}
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
      />
    </ToastContext.Provider>
  )
}

function useToast() {
  const context = React.useContext(ToastContext)
  if (!context) throw new Error("useToast needs a ToastProvider.")
  return context
}

export const toast = sonnerToast
export const Toaster = ToastProvider
export { ToastProvider, useToast }
