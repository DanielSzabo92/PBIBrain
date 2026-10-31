# 13: U5 naming rules ui

Status: open. Lane: ui. Design step: U5 (docs/DEV_CENTER_UI_DESIGN.md section 13).

Depends on (tickets): [10](10-u3-shell-session-list.md), [08](08-s4-naming-rules.md).

The goal, the code areas, and the acceptance tests are the design text below. Each acceptance test must be an automated test, except the items that the design marks as manual.

### Design text: U5. Naming rules

- Goal: the naming rules section and the rule editor.
- Code areas: `frontend/src/devcenter/screens/sources/NamingRules*`, `frontend/e2e/devcenter-rules.spec.js`.
- Depends on: U3; S4 (`GET naming-rules` with rule counts, rule JS API calls, duplicate refusal).
- Acceptance tests:
  - Status filter and its default; groups by object type; sticky actions.
  - Actions by status (ticket 07 table); "Confirm selected" calls in sequence and stops at a failure with the copy.
  - Add rule and Edit rule in the side pane; the backend error shows under the field (A16); the duplicate rule error shows "Edit that rule".
  - Delete user rule: destructive confirm, focus on Cancel.
  - "Copy rules from" lists the models with their counts; a model with 0 rules is disabled.
  - Empty, no target, detection running, and locked states.
  - Kit gates (section 13 rule).
