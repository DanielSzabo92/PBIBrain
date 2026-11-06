# 22: U8 impact ui

Status: open. Lane: ui. Design step: U8 (docs/DEV_CENTER_UI_DESIGN.md section 13).

Depends on (tickets): [19](19-u6-row-detail.md), [15](15-s6-impact-data.md).

The goal, the code areas, and the acceptance tests are the design text below. Each acceptance test must be an automated test, except the items that the design marks as manual.

### Design text: U8. Impact views and removal policy

- Goal: the Impact tab in all three views, Offers, completeness, and the removal policy dialog.
- Code areas: `frontend/src/devcenter/screens/impact/`, `ImpactItemRow`, `ImpactNode`, `WireframeBox`, `CompletenessStrip`, `PathStepList`, `RemovalPolicyDialog`, `frontend/src/graphLayout.js` (reuse only), `frontend/e2e/devcenter-impact.spec.js`.
- Depends on: U6; S6 (`GET impact` with filters, totals, and facets; `GET impact/{item}/paths`; `GET impact/removal/{object}`; `GET wireframe/{report}`; bulk `impact_action_apply`).
- Acceptance tests:
  - Scope, group, and view switches; the view switch keeps scope, filters, and selection.
  - Status rule and primary action order; row menu; pane actions; bulk "Include in rewrite" and "Add from donor"; the toast gives the blocking count.
  - Completeness strip default rule and "Show 20 more".
  - Graph: 150 nodes limit with "Open table"; Tab in rank order and arrow keys along edges; node names (A12); "Show as table" keeps the selection.
  - Wireframe: each status has pattern, icon, and word (A4); "Visual list" in reading order; Offer checkboxes.
  - Offers: page checkbox mixed state; Needs banner with "Open Needs".
  - "Include open proposals" switch and banner.
  - Removal policy dialog: Block, Cascade (destructive), Repoint (disabled until a candidate); focus rules (A9).
  - Budgets P1 to P5 on the 5,000-item scenario.
  - Kit gates (section 13 rule).

## Build record

Branch `dc/22-u8-impact-ui` (Linux cloud session).

Built:
- `frontend/src/devcenter/screens/impact/`: `ImpactTab.jsx` (scope Select, group control with blocking count, view control, filter row, "Include open proposals" switch and banner, completeness strip, bulk bar, virtual table with pages of 500, item pane, toast "<n> items resolved. <m> blocking left."), `ImpactGraph.jsx` (layoutGraph and routePath reuse, 150 node limit, rank order Tab, arrows along edges, zoom and fit buttons), `ImpactWireframe.jsx` (report trigger, page list, scaled canvas, Drawing and Visual list, offer checkboxes), `ImpactOffers.jsx` (tree, page mixed state, Needs banner with "Open Needs"), `ImpactPane.jsx`, `impactModel.js` (pure rules), `impact.css`.
- `frontend/src/devcenter/components/`: `ImpactItemRow`, `ImpactNode`, `WireframeBox`, `CompletenessStrip`, `PathStepList`, `RemovalPolicyDialog` (Block, Cascade destructive with effects table, Repoint disabled until a candidate, initial focus on the policy radio group, focus return to the trigger, else the h1).
- `WorkArea.jsx` shows the Impact tab. The Compare row link sends the row name for "Row: <name>".
- Fake server: GET impact follows the S6 contract (filters, facets and total before paging, sort), `impact/{item}/paths`, removal and wireframe for each object or report, `impact_action_apply`, `need_mapping_set`, `offer_select`, the removal blocking rule, the `/__test__/impact` control, and S6-shaped items in `large-5000-rows`.

Tests:
- `python -m unittest tests.test_devcenter_ui_impact tests.test_devcenter_ui_server tests.test_devcenter_ui_contract`: 51 tests, OK (new module: 8 tests).
- `npm test`: 144 pass, 0 fail (new `test/devcenter-impact.test.js`: 13 tests).
- `npm run build`: OK.
- `npx playwright test e2e/devcenter-impact.spec.js`: 14 pass (each acceptance test, A1 axe in both themes, A18 overflow at 1280 x 900, P1 to P5 at 2 times the budget).

Not run here (Linux): the full Python suite, the full e2e suite, the .NET bridge tests, and the kit gates (`verify_states` light and dark, `verify_target_size`, `slop_tells --strict`, `verify_focustrap`). The kit is not on this machine. These gates are OPEN for the lead on Windows.

Limits:
- The S6 impact item has no proposal field and no policy field. The "Proposed" tag marks an item of a row with an open proposal while the switch is on. The pane shows the policy that the user set in this view, else "Block" for a blocking removal item.
