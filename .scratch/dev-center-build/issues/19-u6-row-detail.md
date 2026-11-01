# 19: U6 row detail

Status: open. Lane: ui. Design step: U6 (docs/DEV_CENTER_UI_DESIGN.md section 13).

Depends on (tickets): [12](12-u4-compare-grid.md), [07](07-s3-alignment-compare.md), [08](08-s4-naming-rules.md), [11](11-s5-change-plan.md).

The goal, the code areas, and the acceptance tests are the design text below. Each acceptance test must be an automated test, except the items that the design marks as manual.

## Lead notes

- `copy.js` has the log labels `alignment_override.split`, `join`, and `reject`, but the S3 backend actions are `confirm`, `break`, `reject_rename`, and `clear`, and the log action is `alignment_override`. Align the copy keys to the backend values, and test it.

### Design text: U6. Row detail and Merge Choice

- Goal: the row detail pane with all Merge Choices, names, folders, and alignment actions.
- Code areas: `frontend/src/devcenter/components/RowDetail*`, `NameField`, `ProposalCard` (display only until U9), `frontend/e2e/devcenter-row.spec.js`.
- Depends on: U4; S3 (`GET display-folders`, `alignment_override` break), S4 (`POST name-propose` with `candidate`), S5 (`merge_choice_set` with `promote` and `copy_to_report`, plan items for each row).
- Acceptance tests:
  - Enter opens the pane with focus on the h2; Close and Escape return focus (A10). Previous and Next follow the grid order and the filter.
  - Each choice of section 4.4 with its fields and its disabled reason (A17). Report measure rows show the two extra choices.
  - Save is immediate; the radio shows "Saving"; a second commit waits for the first.
  - Property picker: zero checked gives the error and no call.
  - Name check after 300 ms: rule break warning, clash error, "Use proposed name", empty required name error.
  - Display folder Combobox groups, new folder option, and the load failure fallback.
  - Split row (confirm, the choice is removed, the selection moves), Join with a row, Confirm and Reject rename.
  - Source mark "Confirm row"; many rows selected; read-only session.
  - Kit gates (section 13 rule).
