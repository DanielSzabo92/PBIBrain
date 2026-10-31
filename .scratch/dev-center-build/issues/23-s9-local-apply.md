# 23: S9 local apply

Status: open. Lane: backend. Design step: S9 (docs/DEV_CENTER_TECHNICAL_DESIGN.md section 16).

Depends on (tickets): [15](15-s6-impact-data.md), [20](20-s8-guard-merge.md).

The goal, the code areas, and the acceptance tests are the design text below. Each acceptance test must be an automated test, except the items that the design marks as manual.

### Design text: S9. Local apply

- Goal: the full apply sequence of section 13, with undo.
- Code areas: `backend/devcenter/apply/`, `backend/desktop/host.py` (`apply`, `format_only_apply`, `undo_apply`, `change_report_write`), `change_guard/promotion/local.py`, the Desktop bridge client.
- Depends on: S6, S8.
- Acceptance tests:
  - End to end on a temp copy of the merge lab: apply, rescan, and the rescan matches the plan with no difference.
  - A failure in the report write leaves the model files unchanged (all or nothing).
  - Undo restores all files byte-equal to the backup.
  - A fake Desktop bridge with "unsaved changes" blocks; "open, saved" warns; "not reachable" warns.
  - Unconfirmed source marks block.
  - Agent proposals that are not accepted have no effect on the written files.
  - After apply, no row shows "source changed".
  - The change report has the plan summary.
  - End-to-end budget: the full apply of the merge lab in a fixed time (record the value in S9 and keep it as a regression limit).
  - UC5: `GET apply/progress` during `apply`, `format_only_apply`, and `undo_apply` gives `apply_id`, `step`, `step_index`, `step_count`, and `state` in step order, and `done` or `failed` at the end.
  - UC6: `GET apply/preview` returns the mark count and row keys, each Desktop state of the fake bridge, the non-canonical file list, the full validation result, and the plan hash.
  - UC7: `GET apply/last` gives the last apply with the backup state; after a target file change it gives `target changed` and the file list; after a rescan difference it lists object, expected, and found.
  - UC32: a guard rejection of each kind gives `details.step` and the matching `details.check`.
