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

## Build record

What I built:
- `backend/devcenter/apply/` (new): `steps` (the 12 step IDs of section 13, the undo steps, the UC32 checks, `ApplyFailure`), `desktop` (Desktop-open check through `powerbi-desktop status`: `not_open`, `open_saved`, `open_unsaved`, `not_reachable`), `pipeline` (`GuardPipeline`: `ChangeGuard` with the merge policy, the app write step, the guard checks, the approvals, the journaled promotion with recovery; `PromotionJournal`: target change list, backup state, undo), `rescan` (compare of the target object index with the plan operations), `report` (Markdown change report with the plan summary), `service` (`ApplyService`: apply, format only apply, undo, change report, UC5 progress, UC6 preview, UC7 last apply).
- JS API: `apply`, `format_only_apply`, `undo_apply`, `change_report_write` (removed from `HOST_PENDING`). HTTP reads: `GET apply/preview`, `GET apply/progress`, `GET apply/last`. Each has its JSON Schema in `backend/devcenter/contracts/`.
- `change_guard/promotion/local.py`: `LocalPromotion.undo` restores a committed promotion from its backup. It refuses a target that changed after the apply.
- Design S9: the budget value (300 s, `APPLY_BUDGET_SECONDS`) is recorded.
- Old tests changed: `tests/test_devcenter_http_routes.py` and `tests/test_devcenter_agent_tools.py` refused each route path part equal to a JS API name. The design reads `apply/preview`, `apply/progress`, `apply/last` start with `apply`, so they get a narrow exception (GET reads only).

Tests and results:
- `python -m unittest tests.test_devcenter_apply`: 22 tests, OK (1 skipped: the Windows end-to-end test with the real guard).
- `python -m unittest tests.test_devcenter_ui_contract tests.test_devcenter_route_list tests.test_devcenter_http_routes tests.test_devcenter_session_store tests.test_git_guard_promotion`: OK.
- `tests.test_devcenter_agent_tools`: the same 4 failures with and without this change (TOM bridge and MCP SDK not on Linux).
- `npm test`: 144 pass, 0 fail. `npm run build`: OK. No e2e spec (no screen in this ticket).

Not run because of Linux: `GuardPipelineEndToEndTests` (real plan, guard, promotion, undo, budget), `tests.test_change_guard_merge`, and each test that reads a model with the TOM bridge. The Linux tests use a fake pipeline: the real app write step with the real PBIR writer, a small Python model writer, and the real `LocalPromotion`.

Open kit gates: none apply (no screen).

Open items:
- Measure the real apply time on Windows and make `APPLY_BUDGET_SECONDS` smaller.
- A rescan failure after the promotion leaves the files written and the fingerprint old (the rows show "source changed"; undo is available).
- The target model and the target report must be in one PBIP folder, and the guard state is in the session folder, so the session folder must not be inside the target folder.

Review verdicts: review 1 PASS (Sonnet). Note 1 fixed: the preview made the guard folder.

Learning: a PBIP `LocalSource.root` is the `.pbip` file, not the folder, because `detect_local_source` keeps the selected path; the guard needs the parent folder.
Learning: on Linux the plan is empty for the merge lab, because the compare reads the model through the TOM bridge; S9 tests on Linux must inject the plan builder.
Learning: `LocalPromotion.recover` does not roll back a COMMITTED journal, because it is a crash recovery; undo needs its own method.
