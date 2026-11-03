# 18: U7 plan view

Status: open. Lane: ui. Design step: U7 (docs/DEV_CENTER_UI_DESIGN.md section 13).

Depends on (tickets): [10](10-u3-shell-session-list.md), [11](11-s5-change-plan.md).

The goal, the code areas, and the acceptance tests are the design text below. Each acceptance test must be an automated test, except the items that the design marks as manual.

### Design text: U7. Plan view

- Goal: the Plan tab without Apply.
- Code areas: `frontend/src/devcenter/screens/plan/`, `frontend/e2e/devcenter-plan.spec.js`.
- Depends on: U3; S5 (`GET plan`, `POST plan-validate`, cheap `GET session` with cached plan status, `choice_source_removed` items).
- Acceptance tests:
  - Strip states (Invalid, Valid with warnings, Valid, empty, checking) with their copy; header status button and Plan tab count agree with `GET plan`.
  - "Apply plan" is disabled with the visible reason when blocks exist (`aria-describedby`).
  - Block list order and each fix action opens the right tab and filter.
  - Summary counts, phases, "All | Model | Report", text filter, expand to operations with old and new text.
  - "Check plan" runs full mode and shows the time. Empty plan state. Proposals info line with "Open Agent".
  - Kit gates (section 13 rule).

## Build record

- Files changed:
  - `frontend/src/devcenter/screens/plan/planModel.js` (new Plan view pure model: strip state, 5-category block list ordering and fix actions, summary table groups, phase groups, and operation diffs)
  - `frontend/src/devcenter/screens/plan/PlanTab.jsx` (new Plan tab component: status strip, Before you apply block list, empty state, Summary and Warnings cards, Plan steps with domain toggle, `/` search shortcut, expandable operations, and open proposals banner)
  - `frontend/src/devcenter/screens/WorkArea.jsx` (wired `PlanTab` and synchronized top bar status button and Plan tab badge count with `plan` read)
  - `frontend/src/devcenter/components/CompareGrid.jsx` (added `tabState.rowKey` deep-link support from Plan fix actions)
  - `frontend/src/devcenter/screens/screens.css` (added Plan view styles with token colors and lint-compliant dividers)
  - `tests/fixtures/devcenter_ui/default/plan.json`, `tests/fixtures/devcenter_ui/plan-invalid/plan.json`, `tests/fixtures/devcenter_ui/apply-ready/plan.json` (aligned to S5 `http/plan.reply.json` schema)
  - `tests/devcenter_ui_server.py`, `tests/test_devcenter_ui_server.py`, `tests/test_devcenter_ui_contract.py` (aligned `plan-validate` reply with `plan_hash`, `source_remove` with `choice_source_removed`, added `/__test__/plan` control route, and added S5 contract test)
  - `frontend/test/devcenter-plan.test.js` (unit tests for `planModel.js`)
  - `frontend/e2e/devcenter-plan.spec.js` (11 Playwright e2e tests covering all U7 acceptance criteria)
  - `.scratch/dev-center-build/gates/u7/` (U7 static snapshot harness for Kit gates)
- Kit gates:
  - `verify_states.mjs` (light): 63 element-states checked, OK
  - `verify_states.mjs --dark`: 63 element-states checked, OK
  - `verify_target_size.mjs`: 46 targets at 414/1280px, OK
  - `slop_tells.mjs --strict`: 0 slop tells, OK
- Tests run:
  - `python -m unittest tests/test_devcenter_ui_contract.py tests/test_devcenter_ui_server.py` (42 passed)
  - `python -m unittest discover -s tests` (590 passed)
  - `npm test` (120 passed)
  - `npx playwright test e2e/devcenter-plan.spec.js --repeat-each=3` (33 passed)
  - `npx playwright test` (149 passed)

