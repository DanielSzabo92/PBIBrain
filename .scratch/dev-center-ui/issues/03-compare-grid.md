# How does the N-way compare grid look and behave?

Type: prototype
Status: resolved
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

## Answer

Resolved on 2026-10-31. The orchestrator accepted all 18 recommendations of round 1, with one change: the proposal badge uses the "bot" icon (as in ticket 06). Prototype: `.scratch/dev-center-ui/prototypes/03/` (`index.html`, `tokens.css`, `measure.mjs`, screenshots in `shots/`). The prototype is never shipped.

### Brief Inference

- Domain: dev-tool. Audience: expert BI developer. Mood: precise. Motion: subtle feedback only (a 2 px load bar).
- One thing leads: the grid. The toolbar, chips and footer stay quiet. One accent (`brand`) for selection, the active row, and agent proposals.

### Decisions of round 1

1. Pattern: ARIA `role="grid"`, `aria-multiselectable="true"`, `aria-rowcount` (total + header), `aria-rowindex` on each virtual row, `aria-colcount`. Roving `tabindex` on cells.
2. Columns: checkbox, Object, Row state, Target, one column for each donor (session order), Merge Choice, Marks.
3. Fixed row height 36 px. Property phrases show in a tooltip and in the row detail, not in the row.
4. State look: icon plus word for each state (table below). New semantic tokens.
5. Default filter "State: not same" (Same rows hidden), as a removable chip.
6. Filter bar: search, 8 filter buttons with popovers, "Compare: Default | Strict" at the right end. Active filters show as chips with "Clear filters".
7. Backend change requests: `q`, `total` with state counts, `sort` (see below).
8. Virtual window with overscan 10, pages of 200, max 25 pages in memory, skeleton rows.
9. Click or Enter on a row = active row (row detail). Checkbox or Space = bulk selection. Two separate states.
10. The header checkbox selects the loaded rows. Then a link offers "Select all <N> rows that match the filters". The UI collects all row keys by paging and sends explicit keys (max 5,000) to `merge_choice_bulk_set`.
11. A bulk bar replaces the filter bar while rows are selected.
12. Confirm dialog only for "Remove from target" or when existing Merge Choices change. Rows where the choice is not possible are skipped and counted.
13. With the Marks filter on, the bulk bar offers "Confirm <N> rows" (`row_confirm`).
14. Proposal badge: "bot" icon plus "Proposed". The proposed choice is in the tooltip. Accept and reject stay in the row detail and the Agent tab.
15. Code diff in a large modal dialog (92 vw x 86 vh).
16. The compare mode switch keeps the filters, clears the bulk selection, and keeps the active row if it still exists.
17. Render budget (see below).
18. No grouping by table in version 1.

### Grid anatomy

```
| toolbar: [Search names] Type Table Display-folder State Source Page Changed-since Marks   Compare [Default|Strict] |
| chips:   (State: not same x) (Name contains "net" x)  Clear filters                                                 |
| +-----+-----------------+-------------+-----------------++-----------+-----------+-----+------------------+--------+ |
| | [ ] | Object          | Row state   | (o) Sales Master || Sales A   | Sales B   | ... | Merge Choice     | Marks  | |
| | [ ] | (S) Total Sales | != Different| (o) Target       || = Same    | != Diff(2)| ... | Take from Sales B| Changed| |
| |     |   Measure, Sales|   +1        |                  ||           |           |     | [bot] Proposed   | Confirm| |
| +-----+-----------------+-------------+-----------------++-----------+-----------+-----+------------------+--------+ |
| footer: 4,445 rows  Type conflict 174  Missing 1,483  Renamed 460  Moved 167  Different 2,161      Default compare  |
```

| Column | Width | Content |
|---|---|---|
| Checkbox | 40 px | Bulk selection checkbox (label "Select <name>"). Header: "Select loaded rows". |
| Object | 260 px | Object type icon (accessible name = type), name (500 weight), second line "<type>, <table>" in `text-2` 12 px. |
| Row state | 116 px | The highest-precedence state of all cells, plus "+N" for the count of other non-same states in the row. |
| Target | 132 px | Header: target icon + target name (sr-only "(target)"). Cell: "Target" or "Missing" (donor-only row). |
| One for each donor | 132 px | State icon + word, property count "(2)", and a changed dot (sr text ", changed", title "Changed since the snapshot"). |
| Merge Choice | 228 px | The accepted Merge Choice text, or "Not set" in `text-3`. A "Proposed" badge with the bot icon when an agent proposal is open. |
| Marks | 112 px | "Confirm" badge (flag icon, `warn`) for a source mark. "Changed" badge (dot icon) when a cell changed since the snapshot. |

Sticky parts: the header row (top). At 1280 px and wider: the checkbox, Object, Row state and Target columns (left), with a `line-strong` divider after Target. Below 1280 px: only the checkbox and Object columns stay sticky, because 4 sticky columns leave too little room for donors at 1024 px. The donor, Merge Choice and Marks columns scroll horizontally inside the grid region. The footer shows the row count and the state counts. Below 1280 px it shows only the row count and the mode.

Report rows (pages, visuals, report measures) use the same anatomy. The Page filter lists pages only when the session has a report source.

### Cell state look

The tokens are new aliases in `theme.css`, so both themes follow the aliased token. The contrast comes from the aliased tokens, measured in ticket 01 on all 6 surfaces.

| State | Token | Icon (lucide) | Word | Extra |
|---|---|---|---|---|
| Type conflict | `--cmp-conflict` = `bad` | x-octagon | "Type conflict" | 600 weight |
| Missing | `--cmp-missing` = `text-2` | dashed circle | "Missing" | |
| Renamed | `--cmp-renamed` = `info` | pencil | "Renamed" | tooltip note "name: <donor name>" |
| Moved | `--cmp-moved` = `info` | arrow-right-left | "Moved" | |
| Different | `--cmp-different` = `warn` | equal-not | "Different" | "(N)" property count in `text-2` |
| Same | `--cmp-same` = `text-3` | equal | "Same" | tooltip note "same after rename" when the backend gives it |
| Target (target column only) | `text` | target | "Target" | |
| Changed mark | `--cmp-changed` = `brand` | filled dot, 10 px | sr-only ", changed" | |
| Proposal | `--proposal` = `brand-strong` on `--proposal-soft` | bot | "Proposed" | |

Row backgrounds: hover `surface-hover`, bulk-selected `--row-selected` = `surface-3`, active row `--row-active` = opaque brand tint. The opaque tints (`--brand-tint`, `--warn-tint`) are `color-mix(brand 12% (dark) or 9% (light), surface)`: the same color as the soft tint on `surface`. Interactive parts use them, because the kit state gate drops alpha.

Fact found: `brand` text on the soft brand tint over `surface-3` (a selected row) is 4.29:1 in light (axe). For this reason `--proposal` uses `brand-strong`. After the change: 0 axe violations.

### Filter bar

- Order: "Search names" box (200 px; `q`, 150 ms debounce), Type, Table, Display folder, State, Source, Page, Changed since, Marks, then the "Compare" label and the "Default | Strict" radio group at the right end. The bar wraps to a second line when it does not fit (at 1440 px with the side pane, and below).
- Each filter button opens a Radix Popover (`role="dialog"`) with a checkbox list and counts. Table and Display folder use the Combobox (charting decision 4), because the lists can be long. Changed since lists the snapshots ("Session start", "Last check"). Page shows "This session has no report source, so no pages." when there is no report source.
- A filter button with a value shows the `brand` border and text, plus sr-only "(active)".
- Chips under the bar: one chip for each active value, each with a remove button ("Remove filter <label>"), then "Clear filters".
- "Show these rows" (ticket 02 banner) sets the Marks filter.
- The key `/` moves the focus to the search box.

### Bulk selection and bulk action flow

1. The user selects rows: checkbox click, Space, Shift+click or Shift+Space (range from the anchor), Shift+Arrow (extend), or the header checkbox or Ctrl+A (loaded rows).
2. A bulk bar replaces the filter bar: "<N> selected", "Set Merge Choice" (menu button), "Confirm <N> rows" (only with the Marks filter), "Clear selection". The chips stay visible.
3. When all loaded rows are selected and more rows match, a line shows: "All 200 loaded rows are selected. Select all 4,445 rows that match the filters". After the click: "All 4,445 rows that match the filters are selected."
4. "Set Merge Choice" menu (Radix DropdownMenu, key M): Keep target, group "Take from" with one item for each donor, Skip, separator, Remove from target (`bad`).
5. A confirm dialog (`alertdialog`) shows only when the choice is "Remove from target" or when selected rows have a different Merge Choice:
   - Title: `Set "Take from Sales B" for 169 rows?` or `Remove 12 objects from the target?`
   - Lines: "26 rows already have a different Merge Choice. This replaces it." / "31 rows are skipped: the object is missing in Sales B." / Remove only: "The plan deletes these objects from the target model when you apply it." and "Each removal uses the Block policy. Objects with dependents stay blocked until you set a policy in the row detail."
   - Buttons: "Cancel" (focus on open), and "Set Merge Choice" (primary) or "Remove from target" (destructive fill).
6. The UI calls `merge_choice_bulk_set` with `base_revision`, the row keys where the choice is possible, and the choice. Then it clears the selection and fetches the visible pages again.
7. Toast: "Merge Choice set for 138 rows. 31 rows skipped." The live region also says the selection count after each change.

Rows where the choice is not possible: "Take from <source>" where that source is Missing; "Remove from target" where the target is Missing. "Take properties" and "Add as new name" are single-row only (ticket 04).

### Row detail and code diff

- A click or Enter opens the row detail (ticket 04) in the 360 px column (1280 px and wider) or in the 400 px sheet (below). Escape closes it when no selection is active. Measured: column 360 px at 1280, 1366, 1440; sheet 400 px at 1024, 1152, 1279.
- Code diff: a modal dialog, 92 vw x 86 vh. Open it from "Show code diff" in the row detail, or with the key D on a donor cell that is not Same. Header: "Code diff: <name>", the compare mode and the languages, a radio group "Compare target with" (one item for each donor), and Close. Body: the target on the left and the donor on the right, side by side at 1280 px and wider; unified below 1280 px. Lines have numbers, a "-" or "+" mark, and the `bad-soft` or `ok-soft` row tint. Each changed line has sr-only "Removed: " or "Added: ". Data: `GET compare-rows/{row}/diff` for one row and one donor. Escape closes it.

### Virtualization and paging

- Fixed row height 36 px (header 34 px). Only the visible rows plus 10 above and 10 below are in the DOM (TanStack Virtual in the build).
- Keyed row reuse: a row element stays while its index is visible and its content does not change. In the prototype this cut the median frame time for a 900 px jump from about 106 ms to 58 ms.
- Pages of 200 rows (`limit` 200, `offset`). The UI requests a page when the visible range reaches a range that is not loaded. Skeleton rows (`aria-busy="true"`) fill the gap. At most 25 pages stay in memory. The page farthest from the view goes first.
- The first reply sets `total` and the state counts. A later page renders only the rows, not the full screen. A filter or mode change drops all pages and starts at page 0.

### Keyboard map (grid)

| Key | Action |
|---|---|
| Tab | Into the grid (the last focused cell), then out of the grid |
| Arrow keys | Move one cell |
| Home / End | First / last cell in the row |
| Ctrl+Home / Ctrl+End | First / last row (same column) |
| Page Up / Page Down | One view up / down |
| Enter | Open the row detail of the focused row |
| Space | Toggle the bulk checkbox |
| Shift+Space, Shift+Arrow Up/Down | Range select from the anchor |
| Ctrl+A | Select the loaded rows |
| D | Code diff for the focused donor cell |
| M | Open "Set Merge Choice" (when rows are selected) |
| Escape | Clear the selection; then close the row detail; in a dialog or popover, close it |
| / | Focus "Search names" (anywhere in the Compare tab) |

Measured in the prototype (Playwright): Arrow Down two times moved the focus to row 2. Space selected 1 row. Shift+Arrow Down two times gave 3 rows and the bulk bar. Escape cleared the selection to 0. Enter opened the row detail. End went to the last column. Ctrl+End went to the last row (4444 of 4445). D opened the diff, and Escape closed it. UNMEASURED: the Tab-out behavior and the real Radix popover focus (static prototype markup).

### Empty, loading, error, no match

| State | Look | Copy |
|---|---|---|
| Loading (first page) | Header row, 30 skeleton rows, 2 px load bar, `aria-busy="true"`, footer "Loading rows" | none |
| Loading (later page) | Skeleton rows in that range only | none |
| Empty (no rows in the session) | Centered state, compare icon | "Nothing to compare yet" / "Add at least one source on the Sources tab. Then the app aligns the objects and shows one row for each object." / "Open Sources" |
| Error | Centered state, alert icon in `bad` | "Could not load the compare" / "<backend message> Check the source on the Sources tab, then try again." / "Try again" |
| No match for filter | Centered state, filter-x icon | "No rows match the filters" / "<N> rows are hidden by the filters. Remove a filter or clear all filters." / "Clear filters" |

### UI render budget

Budget (5,000 rows, 5 sources, fake server on localhost): the first rows show within 300 ms after the first page reply. A filter change shows new rows within 500 ms (fetch included). Scroll gives no long task over 50 ms. At most 80 row elements are in the DOM.

Measured with `measure.mjs`: 5 runs, 1440 x 900, headless Chrome 156 (software raster), fake reply delay 40 ms. Other agents used this PC at the same time, so the values change between runs.

| Item | Budget | Measured (5 runs) | Result |
|---|---|---|---|
| First page reply to rows painted | 300 ms | 60 to 109 ms (an earlier set: 147 to 197 ms) | pass |
| Filter change to rows painted | 500 ms | 76 to 93 ms (an earlier set: 133 to 171 ms) | pass |
| Wheel scroll, 120 px per frame, 250 frames | no long task over 50 ms | 0 long tasks; median frame 18.7 to 18.9 ms, p95 19.5 to 19.8 ms | pass |
| Jump scroll, 900 px per frame (scroll bar drag), 5,000 rows | no long task over 50 ms | 11 to 44 long tasks, max 71 to 100 ms; p95 frame 48.7 to 68.1 ms | FAIL |
| Row elements in the DOM | 80 | max 40 | pass |

The jump scroll replaces every row in every frame. Build rule for the grid U-step: during a fast scroll (more than one view in each frame), render light rows (name and row state only), and fill the cells when the scroll stops. Measure again in the real app with GPU raster. The real app value is UNMEASURED.

### Measurements (2026-10-31, Chrome 156.0.8078.49, playwright 1.63.0, axe-core 4.10.2)

- Page overflow: 15 screens x 6 sizes (1024 x 640, then 1152, 1279, 1280, 1366, 1440 at 900 high) x 2 themes = 180 measurements. Page-level horizontal overflow 0 px, and 0 elements past the right edge outside a scroll container, on all 180. The grid scrolls horizontally inside its own region.
- axe (ticket 01 rule tags), 15 screens at 1440 x 900, dark and light: 0 violations on all 30 (after the `--proposal` fix).
- Kit `verify_states.mjs` through the gate wrapper, light and `--dark`: 39 element-states each, pass. It covers the toolbar controls (search, filter buttons, mode radios, chip remove, Clear filters). The grid cells have `tabindex="-1"` (roving), so the gate does not test them. The text contrast in hover, selected and active rows is covered by axe on the `grid-pane` and `bulk-selected` screens, and by the ticket 01 token table on `surface-hover` and `surface-3`.
- Kit `verify_target_size.mjs`: 42 targets, all at least 24 x 24 or covered by an exception. Pass.
- Kit `slop_tells.mjs --strict`: 0 HIGH. 1 LOW: near-same neutrals `bg-sidebar` and `surface-hover` in light (existing theme tokens, a ticket 01 fact). The first run flagged the tab underline (a 2 px bottom border on the active tab). The prototype now marks the active tab with a `surface-3` fill. Ticket 09 must decide the tab style for the real Radix Tabs.
- Kit `check_no_emoji.py`: no emoji, no em or en dash. Kit `lint_native_select.py`: 0 native selects.
- Raw results: `prototypes/03/shots/result.json`.

UNMEASURED: the real Radix Popover, DropdownMenu, Dialog and Combobox focus behavior; the screen reader output of the virtual grid (NVDA, Narrator); the render budget in the real app.

### Screenshots

`prototypes/03/shots/<screen>-<theme>-<width>.png`, dark and light, 1440 and 1024 wide (60 files). The repo `.gitignore` excludes `*.png`. To make them again, run `node measure.mjs shots` in `prototypes/03/`. Screens: `grid`, `grid-tooltip`, `grid-pane`, `filter-state`, `bulk-selected`, `bulk-all-matching`, `bulk-menu`, `bulk-confirm`, `bulk-confirm-remove`, `code-diff`, `loading`, `empty`, `error`, `no-match`, `strict`. Examples: [grid with tooltip, dark 1440](../prototypes/03/shots/grid-tooltip-dark-1440.png), [grid with pane, light 1440](../prototypes/03/shots/grid-pane-light-1440.png), [bulk menu, dark 1024](../prototypes/03/shots/bulk-menu-dark-1024.png), [bulk confirm, light 1440](../prototypes/03/shots/bulk-confirm-light-1440.png), [code diff, dark 1440](../prototypes/03/shots/code-diff-dark-1440.png), [no match, light 1024](../prototypes/03/shots/no-match-light-1024.png).

### Backend change requests

- `GET compare-rows`: add `q` (name contains, case-insensitive). Reason: the filter bar has a name search, and the contract has no text filter.
- `GET compare-rows`: add `total` (row count for the current filter) and `state_counts` (a count for each row state). Reason: `aria-rowcount`, the scroll height, "Select all <N> rows", the footer counts, and the no-match text.
- `GET compare-rows`: add `sort` (state, name, type, table; asc or desc). Reason: sortable columns; this replaces grouping by table.
- `GET compare-rows`: add a `row_state` field for each row (the highest precedence over all cells), and use it for the `state` filter. Reason: the Row state column and the state filter must agree with the backend precedence.
- JS API `row_confirm`: accept a list of row keys. Reason: "Confirm <N> rows" in the bulk bar. This is necessary only if `row_confirm` takes one row now.

### Inputs for later tickets

- 04: the row detail opens from Enter or a row click. It must show "Show code diff" and the property phrases for each donor. Accept and reject of a proposal are there.
- 09: new parts: Popover filter button with a checkbox list, filter chip, bulk bar, segmented radio group, state cell, proposal badge (bot icon), code diff dialog. New tokens: `--cmp-*`, `--proposal`, `--proposal-soft`, `--row-active`, `--row-selected`, `--brand-tint`, `--warn-tint`. Decide the active tab style (not a border on one side).
- 10: contract fixtures copy the prototype row shape (`row_key`, `object_type`, `name`, `table`, `display_folder`, `cells.<source_id>.{state, changed, notes, properties[{phrase_id, text, old, new}]}`, `merge_choice`, `proposal`, `source_marks`). Add an e2e test for the keyboard map and a render-budget test.
- 11: add the jump-scroll rule (light rows during a fast scroll) to the grid U-step.
