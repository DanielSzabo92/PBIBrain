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

## Build record

Built (branch `dc/25-u10-apply-ui`, base `dc/24-u9-agent-log-ui`):
- `frontend/src/devcenter/screens/plan/applyModel.js`: pure logic (approval items and purposes, deletes, Desktop line, progress rows from `step_index`, elapsed fallback line, result copy, one sentence for each `details.check`, undo state, change report name).
- `ApplyFlowDialog.jsx` (Apply, format only, Undo: confirm, progress, result), `ApplyProgressList.jsx`, `ApplyResultPanel.jsx`, `ApplyReportDialog.jsx`, `apply.css`.
- `PlanTab.jsx`: "Apply plan" reads `GET apply/preview`. Blocks go to the block list (focus on its title) and the dialog does not open. "Undo apply" shows only with a backup (`GET apply/last`). "Write change report" after an apply. Format only runs "Check plan" automatically after success. Undo toast.
- `WorkArea.jsx`: Desktop banner after an apply with the `apply_external_changes` notice.
- `copy.js`: new keys for the U10 dialogs.
- Backend: `change_report_write` takes an optional `file_name` (plain file name, `.md`), so the saved file has the default name of the dialog.
- Fake server: handlers for `apply`, `format_only_apply`, `undo_apply`, `change_report_write`, and the test control `POST /__test__/apply` (apply-last, apply-progress, apply-preview, reply fields).

Tests:
- `python -m unittest tests.test_devcenter_apply tests.test_devcenter_ui_apply tests.test_devcenter_ui_server tests.test_devcenter_ui_contract`: 69 tests, OK (1 skipped). New: `tests/test_devcenter_ui_apply.py` (3), `test_08b` in `tests/test_devcenter_apply.py`.
- `npm test`: 161 pass (new `test/devcenter-apply.test.js`, 10 tests).
- `npm run build`: OK.
- `npx playwright test e2e/devcenter-apply.spec.js --trace off`: 13 pass (one test for each acceptance test, axe in light and dark).
- `e2e/devcenter-plan.spec.js` "axe has zero violations ..." fails on this branch and on the base branch too (light theme contrast in "apply-ready (dark)"). Not caused by this ticket.

Not run (Linux): tests that need the TOM bridge, `lbug_shared.dll`, or Power BI Desktop; the full Python suite and the full e2e suite (by instruction).

Open:
- Kit gates (`verify_states` light and dark, `verify_target_size`, `slop_tells --strict`, `verify_focustrap`): not run, the kit is not on this machine.
- No native save dialog: the S9 contract has no path. The app dialog shows the default name and the session folder.
- The host has no "show in folder" method. The toast action calls `pywebview.api.show_in_folder(path)` only when the host has it.
- "Plan applied with 1 differences" has no one form in the copy catalog.

Review: reviewer 1 (Sonnet): PASS, no blocking findings.

Learning: the fake server serves `frontend/dist`, so run `npm run build` again after each frontend change before an e2e run, because an old build gives false failures.
Learning: a dialog that opens on its result must focus the title in `onOpenAutoFocus` (with preventDefault), because Radix moves the initial focus after the effects run.
Learning: do not set `max-height` and `overflow` on `.ui-dialog-body` in a long dialog, because axe then reports `scrollable-region-focusable`.
