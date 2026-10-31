# How does the user review the plan, apply it, and undo it?

Type: grilling
Status: open
Blocked by: 02

## Question

Design the plan view, the Apply dialog, the apply progress, the result after verify, undo, the "format only" apply, and the change report.

## Context

- Apply sequence: technical design section 13 (12 steps). The dialog data is `GET apply/preview`: summary, approvals needed (HIGH and CRITICAL items, "not checked" items), Desktop status. One approval records all approval purposes.
- Plan: `GET plan` (status Invalid / Valid with warnings / Valid, summary counts for each object type and for model and report, plan steps with their operations, blocking items, warnings, plan hash). `POST plan-validate` with `quick` or `full` mode.
- Blocks before the dialog: unconfirmed source marks, plan Invalid, Desktop open with unsaved changes, non-canonical target file (offers "format only" apply: `format_only_apply`).
- Warnings: Desktop open and saved (after apply, tell the user to select "Apply external changes" in Power BI Desktop), Desktop bridge not reachable ("could not check").
- After apply: rescan and compare with the plan, report each difference. Undo: `undo_apply` restores all files from the backup. `change_report_write` writes a Markdown report. The app never commits or pushes.
- Apply uses accepted state only. Open agent proposals have no effect (ADR 0003).
- Existing screen to compare with: `frontend/src/components/GuardReview.jsx`.
- Destructive actions (Apply that deletes, Undo) wear the destructive token in the trigger and in the confirm dialog.
- Skills: `design-doctrine`, `design-screen`, `ux-writing`.

## Done when

The answer gives: the plan view layout, the pre-apply block list and how each block leads to its fix, the Apply dialog content and its one approval control, the progress view for the 12 steps, the result view (success, verify differences, failure with "nothing written"), the undo flow, the format-only flow, the change report action, and the copy for each state.
