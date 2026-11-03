# 12: U4 compare grid

Status: open. Lane: ui. Design step: U4 (docs/DEV_CENTER_UI_DESIGN.md section 13).

Depends on (tickets): [10](10-u3-shell-session-list.md), [07](07-s3-alignment-compare.md).

The goal, the code areas, and the acceptance tests are the design text below. Each acceptance test must be an automated test, except the items that the design marks as manual.

## Lead notes

- Some count texts in `frontend/src/devcenter/copy.js` have one form only (`compare.bulk.dialog.set.*`, `compare.bulk.toast`, `compare.no_match.body`) and can give "1 rows". Split them into `.one` and `.other` keys, as `work.banner.changed.*` does, and add a unit test.

### Design text: U4. Compare grid

- Goal: the N-way compare grid with filters, bulk actions, and code diff.
- Code areas: `frontend/src/devcenter/components/CompareGrid*`, `StateCell`, `BulkBar`, `CodeDiff`, `frontend/e2e/devcenter-compare.spec.js`.
- Depends on: U3; S3 (`GET compare-rows` with `q`, `total`, `state_counts`, `sort`, `row_state`; `GET compare-rows/{row}/diff`; `phrases.json`); S2 (`row_confirm` with a key list, `merge_choice_bulk_set`).
- Acceptance tests:
  - The full grid keyboard map of section 9.3 (e2e).
  - The default chip "State: not same"; each filter, search (debounce 150 ms), sort, and "Clear filters".
  - "Select all <N> rows" collects the keys by paging (max 5,000) and sends explicit keys. The bulk confirm shows only for remove or replace, with the counts. "Confirm <n> rows" only with the Marks filter.
  - Compare mode switch keeps the filters, clears the selection, keeps the active row.
  - Code diff opens from D and from the row detail link; Escape closes it; focus returns.
  - A13 attributes after a scroll and a filter change.
  - States: loading, later page, empty, error, no match.
  - Budgets P1 to P4 and P6 on `large-5000-rows`, with the light-row rule.
  - Kit gates (section 13 rule).

## Build record

Branch: `dc/12-u4-compare-grid`. Base: `9ad0848f77b9be690533cbf4d8197b4a9979f923`.

### What I built

- Copy count split (lead note): split count keys into `.one` and `.other` forms in `frontend/src/devcenter/copy.js` (`compare.bulk.dialog.set.*`, `compare.bulk.toast`, `compare.no_match.body`). Added unit tests in `frontend/test/devcenter-copy.test.js`.
- Fake server (`tests/devcenter_ui_server.py`): added `compare_mode_set` handler, added support for `not_same` state filter, `proposal=true`, and `compare_mode` in compare rows reply.
- Compare grid components (`frontend/src/devcenter/components/`):
  - `CompareGrid.jsx`: virtualized compare grid with sort, filter chips, popover filter menu, search box with 150 ms debounce, selection management, bulk action menu, keyboard shortcuts (Arrow keys, Enter, Space, Shift+Space, Home/End, Ctrl+Home/Ctrl+End, M, D, Escape, /), mode switcher (Default / Strict), and performance page caching.
  - `StateCell.jsx`: cell renderer showing cell state, changed marks, and popover notes.
  - `BulkBar.jsx`: bulk selection bar with mode switcher, action dropdown menu, and selection count.
  - `CodeDiff.jsx`: modal dialog showing syntax-colored diffs with accessible screen reader tags and focus trap.
  - `CompareRowDetail.jsx`: detail side pane showing object properties, notes, and code diff links.
  - `compare.css`: high-density styles with hairline borders, theme colors, and accessible target sizes.
- Integration: mounted `CompareGrid` in `frontend/src/devcenter/screens/WorkArea.jsx`. Updated `frontend/src/components/ui/menu.jsx` to support controlled open state.
- Automated tests (`frontend/e2e/devcenter-compare.spec.js`): 24 tests covering keyboard map (section 9.3), filter chips and search debounce, clear filters, bulk actions with confirmation dialog, marks filter with row confirmation, compare mode switch, code diff dialog with focus return, ARIA attributes, axe accessibility in light and dark themes, empty and error states, and performance budgets on 5000 rows.

### Tests

| Command | Result |
|---|---|
| `python -m unittest tests.test_devcenter_ui_contract tests.test_devcenter_ui_server` | 39 tests OK |
| `npm test` (in `frontend/`) | 114 pass, 0 fail |
| `npm run build` (in `frontend/`) | OK |
| `npx playwright test e2e/devcenter-compare.spec.js` | 24 passed |
| `npx playwright test e2e/devcenter-shell.spec.js` | 19 passed |

### Kit gates (`DS_REQUIRE_BROWSER=1`, `gate.mjs` with fake `argv[1]`)

Snapshots: `.scratch/dev-center-build/gates/u4/` (IIFE build of compare screen with fixture data).

| Gate | Compare light | Compare dark |
|---|---|---|
| `verify_states` | OK, 60 element-states | OK, 60 element-states |
| `verify_target_size` | OK, 62 targets >= 24x24 | OK, 62 targets >= 24x24 |
| `slop_tells --strict` | OK, no tells | OK, no tells |
| `verify_focustrap` | Covered in e2e spec (diff and bulk dialogs) | Covered in e2e spec |

trail check flags 12 planning documents for the word "header". These are the UI header and plan text, so no change.

### Learning

Radix UI `DropdownMenuTrigger` listens to pointerdown and keyboard events, but ignores synthetic DOM click events. When a keyboard shortcut like M triggers a dropdown menu programmatically, manage controlled `open` and `onOpenChange` props on the Radix menu rather than dispatching a click event to the trigger button.

