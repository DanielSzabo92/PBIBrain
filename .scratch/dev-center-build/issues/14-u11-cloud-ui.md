# 14: U11 cloud ui

Status: open. Lane: ui. Design step: U11 (docs/DEV_CENTER_UI_DESIGN.md section 13).

Depends on (tickets): [10](10-u3-shell-session-list.md), [09](09-s11-cloud-read.md).

The goal, the code areas, and the acceptance tests are the design text below. Each acceptance test must be an automated test, except the items that the design marks as manual.

## Lead notes

- `cloud_connect` adds the cloud source itself; `add: false` only runs the test. Do not call `source_add` after it.
- `pull_to_local` takes `as_target: true` for the flow from the Target step.
- The check IDs of the test lines are in the build record of ticket 09.

### Design text: U11. Cloud sources and Pull to local

- Goal: the cloud connect dialog and the pull flow.
- Code areas: `frontend/src/devcenter/screens/sources/Cloud*`, `PullToLocal*`, `frontend/e2e/devcenter-cloud.spec.js`.
- Depends on: U3; S11 (`cloud_items_list`, `cloud_sign_in` with `prompt`, `cloud_connect` test lines, `pull_to_local`).
- Acceptance tests:
  - Each step and state of the dialog (ticket 07 table), with a silent token that skips step 1.
  - Sign-in failure copies (closed window, admin consent, no network, other).
  - Workspace with no XMLA capacity; disabled unsupported model with its reason; paste fallback with the bad connection error (A16).
  - Access type default "Read"; no line about a later change.
  - Test result groups "Checked" and "Not checked"; a cloud report that is not readable is not added.
  - In the create flow the dialog adds a draft item only (no call).
  - Pull: folder not empty disables "Pull model"; progress; success adds a local source (and selects it as target from the Target step); failure with "Try again".
  - Kit gates (section 13 rule).
