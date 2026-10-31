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
