# 02: U0 test harness

Status: open. Lane: ui. Design step: U0 (docs/DEV_CENTER_UI_DESIGN.md section 13).

Depends on (tickets): none.

The goal, the code areas, and the acceptance tests are the design text below. Each acceptance test must be an automated test, except the items that the design marks as manual.

### Design text: U0. Test harness and CI

- Goal: the fake server, the shim, and CI exist before the first screen.
- Code areas: `tests/devcenter_ui_server.py`, `tests/fixtures/devcenter_ui/`, `frontend/src/devcenter/mock/pywebviewShim.js`, `frontend/vite.config.js` (plugin with `DEVCENTER_FAKE=1` and the proxy), `frontend/playwright.config.js` (second `webServer`, port 8766), `.github/workflows/ci.yml`, `frontend/test/devcenter-lint.test.js`, `tests/test_theme_contrast.py`.
- Depends on: nothing.
- Acceptance tests:
  - `GET /__test__/health` answers on port 8766. `POST /__test__/scenario` loads each scenario of section 10 and resets the state.
  - `POST /__test__/jsapi/<method>` with a wrong `base_revision` returns `stale_revision`. `fault`, `delay`, and `agent-proposal` change the next reply as stated.
  - The production `npm run build` output has no shim tag. The dev build with `DEVCENTER_FAKE=1` has it.
  - The lint test fails on test inputs with a native `<select>`, a hex color, an emoji, an em dash, and a one-sided colored border, and passes on `frontend/src/devcenter/**`.
  - `tests/test_theme_contrast.py` gives the ticket 01 values for the existing tokens (`line`, `line-strong`, `line-focus` are listed as decorative only).
  - The CI workflow runs the 5 gates on a Windows runner. The existing Python tests and e2e suite pass.
  - The S2 route list test ("no HTTP route changes session state") still passes, because it reads the real app only.
