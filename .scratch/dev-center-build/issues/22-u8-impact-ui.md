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
