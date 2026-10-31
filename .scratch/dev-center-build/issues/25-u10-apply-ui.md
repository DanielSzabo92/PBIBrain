# 25: U10 apply ui

Status: open. Lane: ui. Design step: U10 (docs/DEV_CENTER_UI_DESIGN.md section 13).

Depends on (tickets): [18](18-u7-plan-view.md), [23](23-s9-local-apply.md).

The goal, the code areas, and the acceptance tests are the design text below. Each acceptance test must be an automated test, except the items that the design marks as manual.

### Design text: U10. Apply, Undo, format only, change report

- Goal: the full apply flow of section 5.5 and 5.6.
- Code areas: `frontend/src/devcenter/screens/plan/Apply*`, `ProgressList`, `ResultPanel`, `frontend/e2e/devcenter-apply.spec.js`.
- Depends on: U7; S9 (`GET apply/preview` with blocks, `GET apply/progress`, `GET apply/last`, `apply`, `format_only_apply`, `undo_apply`, `change_report_write`, error `details.step` and `details.check`).
- Acceptance tests:
  - Preview blocks go to the block list and the dialog does not open.
  - The approval checkbox shows only with approval items and gates the confirm. "Apply plan" is destructive when the plan deletes objects (trigger and confirm).
  - Progress maps `step_index` to the list (poll 500 ms); fallback with elapsed time when the endpoint fails; no close and no Escape while it runs.
  - Success, differences, and failure panels with their copy; focus on the panel title; one sentence for each `details.check`.
  - Stale plan copy with "Check plan".
  - Undo: available only with a backup; refused with the file list when the target changed; progress and toast.
  - Format only: dialog, progress, result, automatic "Check plan".
  - Change report: save dialog default name, toast with "Show in folder", failure toast.
  - Desktop lines in the dialog and the banner after the apply.
  - Kit gates (section 13 rule).
