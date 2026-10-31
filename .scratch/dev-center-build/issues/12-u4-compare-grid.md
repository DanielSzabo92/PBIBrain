# 12: U4 compare grid

Status: open. Lane: ui. Design step: U4 (docs/DEV_CENTER_UI_DESIGN.md section 13).

Depends on (tickets): [10](10-u3-shell-session-list.md), [07](07-s3-alignment-compare.md).

The goal, the code areas, and the acceptance tests are the design text below. Each acceptance test must be an automated test, except the items that the design marks as manual.

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
