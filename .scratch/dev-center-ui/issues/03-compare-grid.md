# How does the N-way compare grid look and behave?

Type: prototype
Status: open
Blocked by: 02

## Question

Design the compare grid: one row for each aligned object, one column for each source, one cell state for each source. How does the user scan, filter, select in bulk, and set a Merge Choice for many rows? How does the grid stay fast and usable at 5,000 rows and 5 sources? Where does the code diff open?

## Context

- Data: technical design section 14.1 `GET compare-rows` (row key, object type, name, state and changed mark for each source, notes such as "same after rename", property phrases with short old and new values, Merge Choice, proposal status, source marks, paging with `has_more`) and `GET compare-rows/{row}/diff`.
- States and precedence: Type conflict, Missing, Renamed, Moved, Different, Same (spec 6.3, technical design 4.2). Each state needs icon + text (charting decision 3).
- Filters (spec 6.5): object type, table, display folder, state, source, page, changed since snapshot, marks. Compare mode default or strict (`compare_mode_set`).
- Bulk: `merge_choice_bulk_set`. The row editor itself is ticket 04; this ticket decides how the grid opens it and how bulk selection works.
- Code diff is an extra view on request, never the default (spec 6.4).
- Budget: compare under 10 s on the backend (section 17, R6). The UI needs its own render budget; propose one.
- Keyboard: a grid pattern (ARIA grid or table with row actions). Decide which, and the key map.
- No native select (charting decision 4).
- Skills: `design-doctrine`, `design-screen`, `data-dashboard`, "prototype". Prototype in `.scratch/dev-center-ui/prototypes/03/` with fixture rows that copy the section 14.1 shape.

## Done when

The answer gives: the grid anatomy (columns, cell content, row content, sticky parts), the cell state look for each state, the filter bar, bulk selection and bulk action flow, the code diff view, the virtualization and paging approach, the keyboard map, the empty, loading, error, and "no match for filter" states, and a UI render budget. Prototype screenshots in both themes are linked. Contrast and layout claims are measured or marked UNMEASURED.
