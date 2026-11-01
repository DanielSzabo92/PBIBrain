import * as React from "react"
import { Check, CircleDashed, CircleX, LoaderCircle } from "lucide-react"
import { cn } from "@/lib/utils"

// StepIndicator (UI design 6.1): an ordered list of steps.
// steps: [{ label, state: "todo" | "current" | "done" | "error" }]. The current step has aria-current="step".
function StepIndicator({ steps = [], label = "Steps", className }) {
  return (
    <ol className={cn("ui-steps", className)} aria-label={label}>
      {steps.map((step, index) => (
        <li key={step.label} className="ui-step" data-state={step.state || "todo"} aria-current={step.state === "current" ? "step" : undefined}>
          <span className="ui-step-mark" aria-hidden="true">
            {step.state === "done" ? <Check /> : step.state === "error" ? <CircleX /> : index + 1}
          </span>
          <span className="ui-step-label">{step.label}</span>
          {step.state === "done" ? <span className="sr-only">(done)</span> : null}
          {step.state === "error" ? <span className="sr-only">(failed)</span> : null}
        </li>
      ))}
    </ol>
  )
}

const LINE_ICONS = { pending: CircleDashed, running: LoaderCircle, done: Check, failed: CircleX }
const LINE_WORDS = { pending: "Waiting", running: "Running", done: "Done", failed: "Failed" }

// ProgressList (UI design 6.1): lines with an icon, a text, and a state, and a footer line.
// The wrapper div is the polite live region, never the ul.
// lines: [{ text, state: "pending" | "running" | "done" | "failed", fix? }].
function ProgressList({ lines = [], footer, label, className }) {
  return (
    <div className={cn("ui-progress", className)} aria-live="polite">
      <ul className="ui-progress-list" aria-label={label}>
        {lines.map((line) => {
          const Icon = LINE_ICONS[line.state] || CircleDashed
          return (
            <li key={line.text} className="ui-progress-line" data-state={line.state || "pending"}>
              <Icon className={line.state === "running" ? "spin" : undefined} aria-hidden="true" />
              <span className="ui-progress-text">
                {line.text}
                <span className="sr-only">: {LINE_WORDS[line.state] || LINE_WORDS.pending}</span>
                {line.state === "failed" && line.fix ? <small className="ui-progress-fix">{line.fix}</small> : null}
              </span>
            </li>
          )
        })}
      </ul>
      {footer ? <p className="ui-progress-footer">{footer}</p> : null}
    </div>
  )
}

export { StepIndicator, ProgressList }
