import * as React from "react"
import { X } from "lucide-react"
import { AlertDialog as AlertPrimitive, Dialog as DialogPrimitive } from "radix-ui"
import { cn } from "@/lib/utils"

// Dialog and AlertDialog (UI design 6.1, 8.4, A9), on Radix Dialog and AlertDialog.
// Radix gives aria-modal, the focus trap, and the focus return to the trigger.
// Initial focus: the first field (Dialog) or Cancel (AlertDialog, for destructive or bulk actions).
// Progress mode: no close button, Escape and an outside click do nothing.
const Dialog = DialogPrimitive.Root
const DialogTrigger = DialogPrimitive.Trigger
const DialogClose = DialogPrimitive.Close

function guard(progress, handler) {
  return (event) => {
    if (progress) event.preventDefault()
    handler?.(event)
  }
}

function DialogContent({ title, description, progress = false, children, footer, className, onEscapeKeyDown, onPointerDownOutside, onInteractOutside, ...props }) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="ui-scrim" />
      <DialogPrimitive.Content
        data-slot="dialog"
        data-progress={progress || undefined}
        aria-modal="true"
        className={cn("ui-dialog", className)}
        onEscapeKeyDown={guard(progress, onEscapeKeyDown)}
        onPointerDownOutside={guard(progress, onPointerDownOutside)}
        onInteractOutside={guard(progress, onInteractOutside)}
        {...(description ? {} : { "aria-describedby": undefined })}
        {...props}>
        <DialogPrimitive.Title className="ui-dialog-title">{title}</DialogPrimitive.Title>
        {description ? <DialogPrimitive.Description className="ui-dialog-description">{description}</DialogPrimitive.Description> : null}
        <div className="ui-dialog-body">{children}</div>
        {footer ? <div className="ui-dialog-footer" data-ui-actions="">{footer}</div> : null}
        {progress ? null : <DialogPrimitive.Close className="ui-dialog-close" aria-label="Close"><X aria-hidden="true" /></DialogPrimitive.Close>}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  )
}

const AlertDialog = AlertPrimitive.Root
const AlertDialogTrigger = AlertPrimitive.Trigger
const AlertDialogCancel = AlertPrimitive.Cancel
const AlertDialogAction = AlertPrimitive.Action

// AlertDialog: footer holds AlertDialogCancel and AlertDialogAction. Radix puts the initial focus on Cancel.
function AlertDialogContent({ title, description, progress = false, children, footer, className, onEscapeKeyDown, ...props }) {
  return (
    <AlertPrimitive.Portal>
      <AlertPrimitive.Overlay className="ui-scrim" />
      <AlertPrimitive.Content
        data-slot="alert-dialog"
        data-progress={progress || undefined}
        aria-modal="true"
        className={cn("ui-dialog", className)}
        onEscapeKeyDown={guard(progress, onEscapeKeyDown)}
        {...(description ? {} : { "aria-describedby": undefined })}
        {...props}>
        <AlertPrimitive.Title className="ui-dialog-title">{title}</AlertPrimitive.Title>
        {description ? <AlertPrimitive.Description className="ui-dialog-description">{description}</AlertPrimitive.Description> : null}
        {children ? <div className="ui-dialog-body">{children}</div> : null}
        {footer ? <div className="ui-dialog-footer" data-ui-actions="">{footer}</div> : null}
      </AlertPrimitive.Content>
    </AlertPrimitive.Portal>
  )
}

export { Dialog, DialogTrigger, DialogClose, DialogContent, AlertDialog, AlertDialogTrigger, AlertDialogCancel, AlertDialogAction, AlertDialogContent }
