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

## Build record

Branch: `dc/10-u3-shell-session-list`. Base: `424ff6b`.

### What I built

- Fixtures in the S2 shape (lead note 1): `session_id` of 32 hex characters, source IDs `src-<n>`, `proposals.open`, `questions.open`, `counts` with `marks` and `marks_by_kind`, list rows with `session_id`, `location`, `updated_at`, `is_open`. The default session has 5 sources: 2 local donors, the target model and the target report (role `target`), and 1 cloud donor with the workspace name and IDs (S11). The target names come from the source list (GET session has no name fields).
- Fake server (`tests/devcenter_ui_server.py`): GET sessions gives `revision: null` with no open session and `action_not_allowed` with the reason `no_project` in the `no-project` scenario (flag `no_project` in its `scenario.json`). `session_open`, `session_create`, and `session_close` replies follow the S2 reply schemas (no `session` field). New handlers: `source_add` (refuses PBIX and a duplicate), `source_remove` (`choice_count`), `source_relink`, `target_set` (`copy_of` and `empty` add a target source), `sources_check`. The fake `choose_sources` picker gives Sales, Finance, Budget in turn.
- Contract test: new class `SessionFixtureContractTest` validates each `session.json`, GET session and GET sessions of each scenario, and the request and reply of each session and source call against `backend/devcenter/contracts/`.
- UI (`frontend/src/devcenter/screens/`): `DevCenter.jsx` (sidebar item, breadcrumb, one store for the window, tab memory for each session, toasts from the store), `SessionList.jsx` (no project, no sessions, list, newer and damaged rows with a reason and no link, locked rows), `CreateSession.jsx` and `TargetChoice.jsx` (three steps, draft only until "Create session"; then `session_create`, `source_add` in list order, `target_set`; partial failure with "Open session"), `WorkArea.jsx` (header, plan status button, "Check sources", "More" with "Close session", banner stack, long-call status line, six tabs with the Plan and Agent counts), `SourcesTab.jsx` (sources table with "Find source" and "Remove", destructive confirm with no count, toast with the reply count, Target section with "Change target"), `sessionModel.js` (pure helpers), `screens.css`.
- Compare, Impact, Plan, Agent, and Log show a "not ready yet" empty state until U4 to U10.
- App: the sidebar item "Development Center", the Settings switch "Use the / key to go to search" (`frontend/src/devcenter/preferences.js`, localStorage), and the brain error banner is hidden on the Development Center view (the fake server has no brain API).
- Scope cuts: one layout (1280 x 900); "Check sources" is a button; no 1279 px checks. No cloud items in the "Add source" menu (cloud UI is a future feature).

### Changes to tests of other areas

- `tests/test_devcenter_ui_server.py`: GET sessions of `no-project` is now `action_not_allowed`, the revision of GET sessions is null with no open session, and the tests use the S2 field names and IDs (`proposals.open`, `src-2`, the new session ID).
- `frontend/e2e/devcenterHarness.spec.js`: `after.open_proposals` is now `after.proposals.open`.

### Tests

| Command | Result |
|---|---|
| `python -m unittest tests.test_devcenter_ui_contract tests.test_devcenter_ui_server` | 39 tests OK |
| `node --test` (`npm test` in `frontend/`) | 114 pass, 0 fail (new `test/devcenter-screens.test.js`: 12 tests) |
| `npm run build` | OK |
| `npx playwright test e2e/devcenter-shell.spec.js` | 19 passed |
| `npx playwright test e2e/devcenterHarness.spec.js` | 3 passed |

The e2e spec covers: each scenario screen and banner with its copy, axe (A1) and page overflow (A18) at 1280 x 900 in both themes on the list and the work area, the create flow (success, `source_add` fault, Cancel with no JS API call), the locked controls, Remove source, Change target, `stale_revision`, a slow long call, the poll count update (fake clock with `pauseAt`), the "/" switch (A24), focus order (A8), the polite live region (A11), and reduced motion (A15).

### Kit gates (`DS_REQUIRE_BROWSER=1`, `gate.mjs` with the fake `argv[1]`)

Snapshots: `.scratch/dev-center-build/gates/u3/` (IIFE build of one screen with fixture data, as in U1; `build/` and `snaps/` are not in git).

| Gate | List light | List dark | Create light | Create dark | Work (Sources) light | Work (Sources) dark |
|---|---|---|---|---|---|---|
| `verify_states` | OK, 9 | OK, 9 | OK, 9 | OK, 9 | OK, 48 | OK, 48 |
| `verify_target_size` | OK, 3 | OK, 3 | OK, 6 | OK, 6 | OK, 36 | OK, 36 |
| `slop_tells --strict` | OK (MED: one shadow) | OK (MED: one shadow) | OK (MED: one shadow) | OK (MED: one shadow) | OK, no tells | OK, no tells |
| `verify_focustrap --open=".dc-section-head button"` (Change target) | | | | | OK, 14 focusables | OK, 14 focusables |

The first `verify_focustrap` run failed: focus did not go back to "Change target" after close, because the button was not a `DialogTrigger`. Fixed; the e2e spec now checks the focus return. The first `verify_states` run on create dark stopped at the runner time limit of 180 s and gave no result; the second run passed.

### Open items

- The plan status button and the Plan tab count read GET plan (S5). The real backend has no GET plan before S5, so the button falls back to "Valid with warnings" or "Plan not valid" with no count.
- AlertDialog (Remove source): the kit focus trap gate accepts only `role="dialog"`. The e2e spec covers its initial focus on Cancel, Escape, and the focus return.
