# 10: U3 shell session list

Status: open. Lane: ui. Design step: U3 (docs/DEV_CENTER_UI_DESIGN.md section 13).

Depends on (tickets): [05](05-u1-shared-parts.md), [06](06-u2-data-layer.md), [04](04-s2-session-store.md).

The goal, the code areas, and the acceptance tests are the design text below. Each acceptance test must be an automated test, except the items that the design marks as manual.

## Lead notes

- Move the U3 fixtures to the S2 shape: `session_id` of 32 hex characters, source IDs `src-<n>`, `proposals.open`, `questions.open`, `counts.marks`. The old fixtures use `id`, `src-sales`, and `open_proposals`, and they fail the S2 schemas.
- The Development Center "No project" screen cannot show while the host has no project, because the app shows its onboarding page first. The fake GET sessions returns `action_not_allowed` with the reason `no_project`, as the real backend does, and the e2e switches to that scenario after the app loads.
- `GET session` shows the workspace name and IDs of a connected cloud source (S11).
- The fake server replies of `session_open` and `session_create` must follow the S2 reply schemas (no `session` field). Align all U3 fixtures to the schemas in `backend/devcenter/contracts/` and add them to the contract test.
- In e2e, run axe inside an open Radix overlay, and pause the fake clock (`pauseAt`) in timed specs (see the U1 learning).

### Design text: U3. Shell, session list, create flow, work area frame, Sources and Target

- Goal: the user can open, create, and close a session and see the work area frame.
- Code areas: `frontend/src/App.jsx` (sidebar item), `frontend/src/devcenter/screens/` (list, create, work area, sources), `frontend/e2e/devcenter-shell.spec.js`.
- Depends on: U1, U2; S2 (`GET sessions`, `GET session`, session and source JS API schemas, `revision` on reads).
- Acceptance tests:
  - e2e on `no-project`, `no-sessions`, `default`, `locked`, `newer-schema`, `damaged`, `sources-changed`, `source-missing`: each screen and banner of sections 4.1 and 4.2 with its copy.
  - Create flow: success opens Compare; a `fault` on `source_add` shows the partial failure and "Open session"; Cancel sends no JS API call.
  - The locked scenario disables each change control.
  - "Check sources" is a button at 1280 px and in "More" at 1279 px. The side pane is a 360 px column at 1280 px and a 400 px sheet at 1279 px.
  - Remove source: destructive confirm (text with no count, section 4.8), then the reply count in the toast.
  - The Settings switch "Use the / key to go to search" turns the "/" key off and on (A24).
  - `stale_revision` (injected) gives `shared.stale` and the refreshed view. A slow long call disables the change controls. A new revision from the poll updates the tab counts within 6 s.
  - A1, A8, A11, A15, A18 on these screens. Kit gates (section 13 rule).
