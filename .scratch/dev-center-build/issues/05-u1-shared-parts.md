# 05: U1 shared parts

Status: open. Lane: ui. Design step: U1 (docs/DEV_CENTER_UI_DESIGN.md section 13).

Depends on (tickets): [02](02-u0-test-harness.md).

The goal, the code areas, and the acceptance tests are the design text below. Each acceptance test must be an automated test, except the items that the design marks as manual.

### Design text: U1. Shared fixes, tokens, parts

- Goal: the shared parts and tokens exist and pass their gates on a specimen.
- Code areas: `frontend/src/theme.css`, `frontend/src/devcenter/devcenter.css`, `frontend/src/components/ui/` (button, tabs, checkbox, and the new generic parts of section 6.1), a dev-only specimen route, `tests/test_theme_contrast.py`.
- Depends on: U0.
- Acceptance tests:
  - U-fix-1: the contrast test passes `--bad-ink` on `bad` and on `--bad-strong` at 4.5:1 or more in both themes. e2e axe on an old screen with a destructive button has no `color-contrast` violation.
  - U-fix-2: e2e axe on Graph has no `aria-valid-attr-value` violation. The active tab is a fill, not an underline (the ticket 08 prototype still shows an underline; this document wins). The existing e2e suite passes.
  - The contrast test passes each new pair of section 7.4 in both themes.
  - The specimen route (only with `DEVCENTER_FAKE=1`) renders each part in each of its states. e2e axe: 0 violations in both themes. Click test: checkbox, switch, radio, and segmented control change state.
  - e2e keyboard specs for Select, Combobox, Menu, SegmentedControl, Tabs, Dialog, and SidePane (A6, A9, A10).
  - Unit: StatusBadge refuses a tone with no label (A4).
  - Kit gates on the specimen snapshot (section 13 rule), recorded.
