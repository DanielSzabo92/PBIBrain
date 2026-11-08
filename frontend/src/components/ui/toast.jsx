import * as React from "react"
import { CircleCheck, Info, TriangleAlert, X } from "lucide-react"
import { cn } from "@/lib/utils"

const ICONS = { ok: CircleCheck, info: Info, warn: TriangleAlert }
// A23: a toast stays at least 8 s, and it stays while the pointer is on it or it has focus.
export const TOAST_MIN_MS = 8000

const ToastContext = React.createContext(null)

// Toast (UI design 6.1, A11, A23): one polite live region for all toasts. A toast never takes
// focus by itself, and it never holds the only copy of a needed action or of a blocking error.
function ToastProvider({ children, duration = TOAST_MIN_MS }) {
  const existing = React.useContext(ToastContext)
  if (existing) {
    return children
  }
  return <ToastRoot duration={duration}>{children}</ToastRoot>
}

function ToastRoot({ children, duration }) {
  const [toasts, setToasts] = React.useState([])
  const next = React.useRef(0)
  const dismiss = React.useCallback((id) => setToasts((list) => list.filter((toast) => toast.id !== id)), [])
  const show = React.useCallback((toast) => {
    next.current += 1
    const id = next.current
    setToasts((list) => [...list, { tone: "ok", ...toast, id }])
    return id
  }, [])
  const value = React.useMemo(() => ({ show, dismiss }), [show, dismiss])
  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="ui-toast-region" role="status" aria-live="polite" aria-label="Notifications">
        {toasts.map((toast) => <ToastItem key={toast.id} toast={toast} duration={Math.max(duration, TOAST_MIN_MS)} dismiss={dismiss} />)}
      </div>
    </ToastContext.Provider>
  )
}

function ToastItem({ toast, duration, dismiss }) {
  const [held, setHeld] = React.useState(false)
  const [exiting, setExiting] = React.useState(false)
  const remaining = React.useRef(duration)

  const onDismiss = React.useCallback(() => {
    setExiting(true)
    const timer = setTimeout(() => {
      dismiss(toast.id)
    }, 180)
    return () => clearTimeout(timer)
  }, [dismiss, toast.id])

  React.useEffect(() => {
    if (held || exiting) return undefined
    const started = Date.now()
    const timer = setTimeout(onDismiss, remaining.current)
    return () => {
      clearTimeout(timer)
      remaining.current = Math.max(remaining.current - (Date.now() - started), 0)
    }
  }, [held, exiting, onDismiss])

  const Icon = ICONS[toast.tone] || Info
  return (
    <div
      className={cn("ui-toast", exiting && "ui-toast-out")}
      data-tone={toast.tone}
      onPointerEnter={() => setHeld(true)}
      onPointerLeave={() => setHeld(false)}
      onFocus={() => setHeld(true)}
      onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setHeld(false) }}>
      <Icon className="ui-toast-icon" aria-hidden="true" />
      <p className="ui-toast-text">{toast.text}</p>
      {toast.action ? (
        <button
          type="button"
          className="ui-toast-action"
          onClick={() => {
            toast.action.onClick?.()
            onDismiss()
          }}>
          {toast.action.label}
        </button>
      ) : null}
      <button type="button" className="ui-toast-close" aria-label="Close notification" onClick={onDismiss}>
        <X aria-hidden="true" />
      </button>
    </div>
  )
}

function useToast() {
  const context = React.useContext(ToastContext)
  if (!context) throw new Error("useToast needs a ToastProvider.")
  return context
}

export const Toaster = ToastProvider
export { ToastProvider, useToast }
