# What is in the UI design document, and what are the UI build steps?

Type: grilling
Status: open
Blocked by: 01, 02, 03, 04, 05, 06, 07, 08, 09, 10

## Question

Write `docs/DEV_CENTER_UI_DESIGN.md` from the decisions of tickets 01 to 10. Define the UI build steps (U0, U1, ...), their order against the backend build steps S0 to S11, and the acceptance tests of each step.

## Context

- Destination (map): screens, flows, layout, components with the 8 states, copy, a11y contract, and UI build steps with unit, contract (section 14 JSON Schemas), and Playwright e2e tests. Version 1 only. Complete enough to split into UI build tickets.
- Format model: the technical design `docs/DEV_CENTER_TECHNICAL_DESIGN.md` (one home ticket for each decision; section 16 build step shape: goal, code areas, depends on, acceptance tests).
- Backend lanes (section 16): S3 and S4 after S2; S5 and S6 after S3; S10 after S6; S11 after S2. Each U-step names the S-steps whose schemas and endpoints it needs.
- Fog on the map to settle here: shortcut map, UI performance budgets, U-step order.
- Run `design-review` on the full design (6 dimensions, Nielsen heuristics). Put the findings table in the answer and fix the document before close.
- Render gates: each contrast, a11y, and layout claim in the document is measured (ticket 01 setup) or marked UNMEASURED.
- Skills: `design-doctrine`, `design-review`.

## Done when

`docs/DEV_CENTER_UI_DESIGN.md` exists and the orchestrator accepts it. Each U-step has a goal, code areas, dependencies (U and S), and acceptance tests. The map fog is empty or ruled out. The design review has no open high-severity finding.
