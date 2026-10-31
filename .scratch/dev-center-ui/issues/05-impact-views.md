# How does the user see and resolve impact in the table, graph, and wireframe views?

Type: prototype
Status: resolved
Blocked by: 02

## Question

Design the three impact views (table as default, graph, page wireframe) for Breaks and Needs, for one row and for the full plan. How does the user act on an item, see the completeness, and select carry-over Offers?

## Context

- Data: technical design section 7 and 14.1 `GET impact` (Impact items, completeness block, Offer records; paging), `GET wireframe/{report}`.
- Impact item: direction (breaks or needs), cause, impacted object, severity (Breaks: breaks, changes value, needs review; Needs: will be added, mapped, missing, name clash), certainty (certain or possible; possible never blocks), reason (phrase ID + text), shortest path (+ count of other paths), blocking flag, allowed actions.
- Actions: `include_in_rewrite`, `set_policy_block`, `set_policy_cascade`, `set_policy_repoint`, `add_from_donor`, `map_to_target`, `drop_added_object`, `remove_field`. JS API `impact_action_apply`, `need_mapping_set`, `offer_select`.
- Graph: reuse the existing xyflow + dagre code (`frontend/src/components/GraphView.jsx`, `frontend/src/graphLayout.js`, `frontend/src/graphPresentation.js`). Decide what to reuse and what is new.
- Wireframe: pages with visual boxes from PBIR positions; status in priority order removed, breaks, changes, new, not checked, unchanged; wireframes for the target report after apply, donor reports now, and other reports of the target model. Status needs icon or pattern + text, not color only.
- Completeness (spec 8.5): not-checked types, unresolved bindings, unreadable remote reports, bookmarks, possible-only areas. The backend never truncates the list.
- Existing screen to compare with: `frontend/src/components/ImpactExplorer.jsx`.
- Skills: `design-doctrine`, `design-screen`, `data-dashboard`, "prototype". Prototype in `.scratch/dev-center-ui/prototypes/05/`.

## Done when

The answer gives: the layout of each view and the switch between them, the item row and its actions, the graph node and edge look and its keyboard and screen reader alternative, the wireframe drawing rules and its text alternative, the completeness block, the Offer selection flow, and the empty, loading, error, and large-list states. Prototype screenshots in both themes are linked. Contrast and layout claims are measured or marked UNMEASURED.

## Answer

Resolved on 2026-10-31. The orchestrator accepted all 15 recommendations of round 1 (one round), with one addition for Q14 (the "Proposed" tag and the proposals banner, see below). Prototype: `.scratch/dev-center-ui/prototypes/05/` (`index.html`, `app.css`, `app.js`, `tokens.css`, `screens.json`, `measure.mjs`, `gates.sh`, static gate pages in `pages/`, screenshots in `shots/`). The prototype is never shipped.

### Brief Inference

- Domain: dev-tool (Power BI model merge).
- Audience and tone: expert BI developer. Calm, utilitarian.
- Mood: precise.
- Motion depth: subtle feedback only (spinner, no choreography).
- Layout family: in the Impact tab of the work area (ticket 02): toolbar (2 rows), optional proposals banner, completeness strip, then the view region with the 360 px side pane.
- Reference anchor: the existing PBIBrain shell and the ticket 02 prototype. One accent (brand). Status by icon and text.

### Decisions of round 1

1. Scope: the Impact tab shows the full plan by default. A scope trigger in the toolbar shows "Whole plan" or "Row: <name>". The row detail pane (ticket 04) shows only the counts and a "Show impact" link. The link opens the Impact tab with the row scope.
2. View switch: a segmented control "Table | Graph | Wireframe" at the right of toolbar row 1. Table is the default. The app keeps the view and the selected item in memory for each session (not on disk). The selected item stays selected when the user changes the view.
3. Groups: a segmented control "Breaks (n) | Needs (n) | Offers (n)". Breaks and Needs show their blocking count with a bad tint. Default: the first group with blocking items, else Breaks. Breaks and Needs are never in one list.
4. Item row: two lines (see "Item row and its actions"). Sort: blocking first, then severity, then name. No group-by in version 1.
5. Actions: one primary button on the row, the other allowed actions in a row menu. Actions that need input open the side pane. Destructive actions use a confirm step. A toast tells the new blocking count.
6. Bulk: checkboxes on rows. Bulk only for "Include in rewrite" and "Add from donor", when all selected items allow the action. Backend change request 1.
7. Filters and large lists: toolbar filters, virtual scroll, pages of 500. Backend change request 2.
8. Item detail pane: full reason, path as a step list, cause link, actions with one line each, "Show other paths" on request. Backend change request 3.
9. Graph: reuse `layoutGraph`, `routePath`, and the routed edge. New impact node. Limit 150 nodes.
10. Graph keyboard and screen reader alternative: focusable nodes in rank order, Enter opens the item, an aria-label on each node, the table is the full text alternative, a "Show as table" button.
11. Wireframe: report trigger, page list, scaled page canvas, status by pattern + icon + text, "Hidden" tag, filter list, "Visual list" text alternative.
12. Completeness strip above every view (see "Completeness block").
13. Offers group with a donor report tree and checkboxes (`offer_select`). Offer boxes in the donor wireframe also have a checkbox.
14. "Include open proposals" switch, off by default, sets `include_proposals`. Orchestrator addition: items that come only from a proposal show the `bot` icon plus the text "Proposed". When the switch is on, an info banner shows "This view includes <n> open agent proposals. Apply uses only accepted choices." (the same as tickets 03, 04, 06).
15. Refresh after a change: the UI keeps the scroll position and the selection, and shows "Updating" on the list. The toast says "1 item resolved. <n> blocking left." Items from other reports of the target model show the tag "Not changed by this plan".

### Layout of the Impact tab and the switch between views

```
| Sales master merge (h1)            [x Plan not valid: 6 blocking] [Check sources] [...] |
| Compare | Impact | Plan (6) | Agent (4) | Sources | Log                                 |
| [Scope Whole plan v] [Breaks 8 (4) | Needs 6 (2) | Offers 7]   [Table | Graph | Wireframe] |
| [x Blocking only] [Severity All v] [Certainty All v] [Model or report All v] [Type All v] |
| [Find object or reason        ]                         ( ) Include open proposals       |
| [bot] This view includes 4 open agent proposals. Apply uses only accepted choices.      |
| [! Incomplete: 5 areas] Static impact is a safe superset. ...          v Show areas     |
| +------------------------------------------------+ +------------------------------+ |
| | view region (table, graph, or wireframe)       | | side pane 360 px (>= 1280)   | |
| | scrolls inside its own region                  | | sheet 400 px (< 1280)        | |
| +------------------------------------------------+ +------------------------------+ |
```

- Toolbar row 1: scope trigger (Radix Select, ticket 09), group control, view control. Row 2: filters and the proposals switch. Row 2 is hidden in the Offers group. Both rows wrap. At 1024 px the search field goes to its own line (measured, no overflow).
- The view switch changes only the region. Scope, group, filters, and selection stay. Each segmented button has `aria-pressed`.
- The filters also apply in the Graph and Wireframe views: the graph draws only the filtered items.
- The region and the side pane follow the ticket 02 pane rule: a 360 px column at 1280 px and wider, a `min(400px, 92vw)` sheet below 1280 px at full height. Escape closes the sheet.

### Item row and its actions

The table is a real `<table>` with a hidden caption and 3 columns: select, item, actions.

```
[ ] [x Blocking] (sigma) [Net Sales]  Sales Master  Breaks               [Repoint] [...]
    Uses a removed column.  Sales[Discount] > used by [Net Sales]   1 other path
```

- Line 1: status chip (Blocking = `bad` + x icon, Warning = `warn` + alert icon, Information = plain + info icon), type icon with an accessible name, object name (a button that opens the side pane), model or report (and page), severity text, and the tags "Possible" (help icon), "Not changed by this plan", "Proposed" (bot icon).
- Line 2: the reason text from the backend phrase, the shortest path with chevrons and edge phrases ("used by", "in visual", "filters"), and "<n> other paths".
- Status rule: Blocking = the blocking flag. Information = severity "mapped" or the mark "not changed by this plan". Warning = all other items. Possible items are never Blocking.
- Primary button: the first allowed action that resolves the block, in this order: `include_in_rewrite`, `set_policy_repoint`, `set_policy_cascade`, `map_to_target`, `add_from_donor`. An item that does not block shows no primary button, only the row menu.
- Row menu (Radix DropdownMenu): all other allowed actions. Labels: "Include in rewrite", "Repoint", "Cascade", "Keep blocked", "Add from donor", "Map to target", "Drop added object", "Remove field".
- Actions that need input open the side pane: Cascade (preview from `GET impact/removal/{object}`, then "Set Cascade"), Repoint (Combobox of same-kind candidates; a candidate with a type warning shows an alert icon and "Different data type"), Map to target (Combobox of target objects). JS calls: `impact_action_apply` for item actions, `removal_policy_set` for a policy set in the pane, `need_mapping_set` for "Map to target".
- "Set Cascade", "Drop added object", and "Remove field" are destructive: a `bad` outline button with a trash icon, in the pane or in a confirm dialog.
- Bulk: when one or more rows are selected, a bar shows "<n> selected", the bulk actions that all selected items allow, and "Clear selection".
- After each action the impact is computed again. The toast says "1 item resolved. 5 blocking left." Scroll position and selection stay.

### Item detail pane

The pane shows: status and severity, the object name (h2), type and place, and the full reason. A blocking item adds "The plan stays not valid until you resolve this item." Then "Shortest path" as a vertical step list (first step "Change: <kind>", last step marked) and "Show other paths". Then a key-value list: Cause (link to its Compare row), Certainty (in words), Policy. Last, "Actions" with one line of text for each action. The current policy shows a disabled "Current" button.

### Graph view

- Reuse from `frontend/src/graphLayout.js`: `layoutGraph` (dagre, stable order, `rankdir` LR) and `routePath`. Reuse the `RoutedEdge` renderer of `GraphView.jsx` and the zoom and fit panel pattern. Do not reuse `BrainFlowNode`, `ArtifactGroup`, the artifact palettes of `graphPresentation.js`, the minimap, or the explorer expand buttons.
- New: an `ImpactNode` renderer, 224 x 76 px. The prototype showed clipped names at 64 px high, so the node needs 76 px for 3 lines. Line 1: type icon + type. Line 2: name (ellipsis). Line 3: status with icon and text from status tokens ("Blocking, breaks", "Warning, changes value", "Information", "On the path"). A cause node has the `surface-3` background and "Change: <kind>" (Removed, Renamed to <name>, Replaced, Changed, Added, Copied). Selected node: 2 px brand border on all sides. No colored bar on one side.
- Content: the union of the shortest paths of the filtered items, and nothing else. Edge: solid = certain, dashed (6 4) = possible, label = the edge phrase near the target end. The edges of the selected item use the brand color at 2.2 px. A legend shows "Certain", "Possible", and the node and link counts.
- Limit: above 150 nodes the region shows "Too many items for the graph" / "The graph can show 150 objects. These filters give <n> items. Use filters, or open the table." / "Open table".
- Keyboard: each node is one button. No button is inside a node, so the axe `nested-interactive` failure of ticket 01 cannot occur. Tab order is rank order, then top to bottom. Arrow keys move along the edges (right = next step, left = previous step, up and down = same rank). Enter or Space selects the item and opens the side pane. Edges are not focusable.
- Screen reader: the region label is "Impact graph. Tab moves between objects. Enter opens the item." Each node has an aria-label, for example "Measure [Net Sales], blocking, Breaks, 1 step from the change". The SVG edges are `aria-hidden`. The table is the full text alternative. "Show as table" switches to it with the same selection.

### Wireframe view

- Region bar: a report trigger with three sets: "<report> (target, after apply)", the donor reports ("<report> (donor, now)"), and other reports of the target model ("<report> (not changed by this plan)"). At the right: "Drawing | Visual list".
- Left: page list (200 px). Each page shows its name and status counts with icons (for example "1 breaks, 1 changes, 1 removed, 1 new, 1 not checked", or "No change"). Hidden pages show the "Hidden" tag.
- Canvas: the page box keeps the PBIR page ratio, scaled to the region width. Each visual is a button at x, y, width, height in percent of the page, drawn in z order, minimum 24 x 24 px. Groups (`parentGroupName`) are not drawn as boxes in version 1; the visual list shows the group name.
- Drawing rules. Each visual shows one status, the first in this order: removed, breaks, changes, new, not checked, unchanged.

  | Status | Border | Fill | Icon and text | Other |
  |---|---|---|---|---|
  | Removed | 1 px solid `impact-removed` | 45 degree hatch of the `impact-removed` tint | trash, "Removed" | title struck through |
  | Breaks | 3 px solid `impact-breaks` | surface | x, "Breaks" | |
  | Changes | 2 px dashed `impact-changes` | surface | alert, "Changes" | |
  | New | 2 px dotted `impact-new` | `impact-new` tint | plus, "New" | |
  | Not checked | 1 px dashed `impact-unchecked` | surface | help, "Not checked" | |
  | Unchanged | 1 px solid `control-border` | surface | no status line | |

  Line order in a box: status line, title, visual type (the prototype showed that small cards clip the last line, so the status comes first). Hidden visuals show the "Hidden" tag (eye-off icon). The selected visual has a 2 px brand outline. A legend under the canvas repeats the 6 statuses with the same swatch, icon, and text, and the priority order sentence.
- Filters: a "Filters" list under the canvas with report filters and page filters, each with its status chip and cause text. Visual filters show in the pane of the visual.
- A click on a visual opens the side pane with the Impact items that cause the status (the cause item IDs of the wireframe data).
- Text alternative: "Visual list" is a table of the visuals of the page in reading order (top to bottom, then left to right): visual, type, status (icon + text), cause. Each visual button also has an aria-label with type, title, status, cause, and "hidden".
- Donor reports: Offer visuals show a checkbox in the box (`offer_select`), with the same state as the Offers group.

### Completeness block

- One strip above the view region in every view and group. Closed: status chip ("Complete" with check icon, `ok`; or "Incomplete: <n> areas" with alert icon, `warn`), one sentence, and "Show areas" or "Hide areas". The strip is a button with `aria-expanded` and `aria-controls`.
- Open: one section for each area, with an icon, a title, and a count: "Not checked object types", "Unresolved bindings", "Remote reports not read" (with the reason, for example "access refused (403)"), "Bookmarks that refer to a changed object", "Possible only". Each list shows every entry. An area with more than 20 entries pages inside the area ("Show 20 more"). The backend never truncates.
- Default: closed. When the status is incomplete and the user did not close the strip in this session, it is open. Copy when complete: "All object types and report bindings were checked." Copy when incomplete: "Static impact is a safe superset. Some areas were not checked."

### Offer selection flow

1. The user adds a model object in Compare (ticket 04). The Offers count on the group control changes.
2. The user opens Impact, then Offers. The region shows "Donor report items that use an added model object. Select items to copy into the target report."
3. The list groups by donor report, then page, then visuals and filters. Each item tells what it uses (for example "Line chart, uses [Net Margin]").
4. A page checkbox selects all its visuals and filters. It shows the mixed state when only some are selected. Each change calls `offer_select`.
5. Donor bookmarks show as rows with no checkbox and the tag "Information only" ("Bookmarks are not copied in version 1.").
6. Selected visuals can need fields that the target does not have. These become Needs. A banner shows "<n> fields need an action before the copy can work." with "Open Needs".
7. In Needs, each such field has the actions "Add from donor", "Map to target", "Remove field".
8. Alternative: the Wireframe view with a donor report gives the same checkboxes on the Offer boxes.

### States

| State | Look | Copy |
|---|---|---|
| Loading | Region bar with a spinner (no spin with reduced motion) and skeleton rows; `aria-busy` on the region; completeness strip hidden | "Computing impact for the whole plan" (or "for row <name>") |
| Updating (after an action) | The old list stays; "Updating" with a spinner in the region bar; controls stay usable | "Updating" |
| Error | Centered state, x icon in `bad`, `role="alert"` | "The impact could not be computed" / "The backend stopped with "<error text>". Check the source, then try again." / "Try again" (primary), "Open Sources" |
| Empty, plan | Centered state, check icon; completeness strip "Complete" | "Nothing breaks" / "The plan breaks no object in the target model or its reports." |
| Empty, row | Same | "This row has no impact" / "No object uses <name>, and it needs nothing that the target does not have." / "Show whole plan" |
| Empty, filter | Centered state in the table | "No items match these filters." / "Clear filters" |
| Empty, Needs | Centered state | "The target has everything that the added objects need." |
| Empty, Offers | Centered state | "No donor report item uses an added object." |
| Large list | Virtual scroll; counts from the backend totals; a line under the table | "Showing rows 1 to 40 of 5,214. The list loads more rows when you scroll (pages of 500)." |
| Large, graph | Centered state | "Too many items for the graph" (see "Graph view") |
| Proposals on | Info banner with the bot icon; "Proposed" tags | "This view includes <n> open agent proposals. Apply uses only accepted choices." |
| Session locked (ticket 02) | Each action button and checkbox disabled; the views stay readable | Ticket 02 banner |

The prototype shows these states: loading, error, empty row, large list, large graph, proposals on. The other empty states are copy only (UNMEASURED).

### New tokens (proposal for ticket 09)

- `theme.css`, both themes: `--impact-removed`, `--impact-breaks`, `--impact-changes`, `--impact-new`, `--impact-unchecked` (they map to `bad`, `bad`, `warn`, `ok`, `info`) and `--impact-unchanged` (maps to `control-border`), each with a tint.
- Opaque tints `--ok-tint`, `--warn-tint`, `--bad-tint`, `--info-tint`, `--brand-tint`. Each one is the `-soft` token composited on `--surface`. Dark: `#1c2b28`, `#2d2921`, `#2e2225`, `#1e2833`, `#222535`. Light: `#e9f5f0`, `#f8f1e7`, `#fbefef`, `#eaf2f9`, `#eff0fc`. Reason: the kit state gate drops alpha and reports 1.00:1 for a status button on a `-soft` tint. With the opaque tints the gate passes, and the color on `surface` is the same.

### Screenshots

The files are `prototypes/05/shots/<screen>-<theme>-<width>.png`, dark and light, 1440 and 1024 wide (64 files). The repo `.gitignore` excludes `*.png`. To make them again, run `node measure.mjs shots` in `prototypes/05/`. Screens (queries in `screens.json`): `table-breaks-pane`, `table-breaks-bulk` (with toast), `table-needs`, `table-proposals`, `completeness-open`, `cascade-pane`, `offers`, `graph`, `graph-pane`, `graph-too-many`, `wireframe`, `wireframe-list`, `loading`, `error`, `empty-row`, `large`.

Examples: [table, dark 1440](../prototypes/05/shots/table-breaks-pane-dark-1440.png), [table, light 1440](../prototypes/05/shots/table-breaks-pane-light-1440.png), [graph, dark 1440](../prototypes/05/shots/graph-pane-dark-1440.png), [graph, light 1440](../prototypes/05/shots/graph-light-1440.png), [wireframe, dark 1024](../prototypes/05/shots/wireframe-dark-1024.png), [wireframe, light 1440](../prototypes/05/shots/wireframe-light-1440.png), [offers, light 1024](../prototypes/05/shots/offers-light-1024.png), [completeness, dark 1024](../prototypes/05/shots/completeness-open-dark-1024.png), [cascade sheet, dark 1024](../prototypes/05/shots/cascade-pane-dark-1024.png).

### Measurements (2026-10-31, Chrome 156.0.8078.49, playwright 1.63.0, axe-core 4.10.2, kit 3.0.0)

- Page overflow (`measure.mjs`): 16 screens x 6 sizes (1024 x 640, then 1152, 1279, 1280, 1366, 1440 at 900 high) x 2 themes = 192 measurements. Page-level horizontal overflow 0 px, and 0 elements past the right edge outside a scroll container, on all 192.
- Side pane mode: column 360 px at 1280, 1366, 1440; sheet 400 px at 1024, 1152, 1279 (3 pane screens). The sheet fills the viewport height. The first run showed a sheet that stopped at its content height; `height: 100vh` fixed it.
- Target size in `measure.mjs` (each button and input, or its wrapping label, at least 24 x 24 px): 0 small targets on all 192 measurements. Two fixes were necessary: the 16 px checkboxes now sit in a 24 x 24 label, and the object name buttons have `min-height: 24px`.
- axe (rule tags of ticket 01), 16 screens at 1440 x 900, dark and light: 0 violations on all 32.
- Kit `verify_states.mjs` (default, hover, focus), run through the `gate.mjs` wrapper of the orchestrator note on the 32 static pages in `pages/` (16 screens x 2 themes): OK on 32 of 32. Example: 158 element-states on `table-breaks-pane-light`. The first run failed on the plan status button on `bad-soft` with 1.00:1 (the gate alpha error). The opaque tints fixed it.
- Kit `verify_target_size.mjs` on the 32 pages: OK on 32 of 32 (414 and 1280 px). The first run failed: the wireframe visual boxes were 14 px wide at 414 px. `min-width: 24px` fixed it. The app has no 414 px layout (map decision 5).
- Kit `slop_tells.mjs --strict` on the 32 pages: 15 dark pages have no tells. 16 light pages: LOW "near-duplicate neutrals" `rgb(239,239,236)` and `rgb(240,240,238)`. These are the theme tokens `bg-sidebar` (`#efefec`) and `surface-3` (`#f0f0ee`): a theme fact for ticket 09, not a prototype defect. `table-breaks-bulk` (both themes): MED "only one distinct shadow". The toast is the only raised part on that screen, so this is correct; not changed.
- Kit `check_no_emoji.py` and `lint_native_select.py` on the prototype folder: OK (no emoji, no em or en dash, no native select).
- Status token contrast on all surfaces: ticket 01 (5.02:1 or more).

UNMEASURED:

- The real Radix behavior (Select, DropdownMenu, Sheet focus trap) and the graph keyboard model (arrow keys along edges). The prototype uses static markup.
- The xyflow render of the new node. The prototype draws the graph with a simple rank layout, not dagre.
- Virtual scroll speed with 5,000 items, and the time from an action to the new impact. Performance budgets are in the map list "Not yet specified" (tickets 03 and 10).
- Rendered contrast of the "Removed" title text on the hatch pattern. axe found no contrast violation on the wireframe screens, but axe does not sample gradients.
- Wireframe drawing of very small or overlapped visuals at real PBIR sizes (the prototype draws one fixture page).
- The empty states for filter, Needs, and Offers (copy only).

### Backend change requests

1. JS API `impact_action_apply` for many items: fields `item_ids` (array), `action`, `base_revision`. One revision step, all or nothing. The reply lists the items that it could not change. Reason: bulk "Include in rewrite" and "Add from donor" (Q6). One call for each item needs a new `base_revision` for each call.
2. `GET impact` filters and totals: query parameters `direction`, `blocking`, `severity`, `certainty`, `source` (model or report), `object_type`, `q` (text), with `limit` and `offset`. The reply adds `total` and facet counts (by direction, blocking, severity, certainty, source, object type) for the full result before paging. Reason: filters and counts on large lists without a download of all pages (Q7).
3. `GET impact/{item}/paths`: all paths of one Impact item, paged. Each path is a list of steps with object ID, name, type, and edge phrase. Reason: "Show other paths" in the item pane (Q8). The technical design says "the full list comes on request", but it has no endpoint.

### Inputs for later tickets

- 04: the row detail shows the impact counts of the row and "Show impact" (opens Impact with the row scope).
- 06: the "Proposed" tag and the proposals banner use the same copy as this ticket.
- 08: the plan status button and the Plan tab count use the blocking count that the impact actions change.
- 09: new parts: segmented control, filter trigger (Select), switch, item row, completeness strip, impact node, wireframe box with the 6 status styles, step list. Add the opaque tint tokens and the impact tokens. Status chips and swatches always carry icon and text.
- 10: fixtures for each screen above, with a 5,000 item result, a result with every completeness area, and a donor report with Offers.
