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

## Build record

Built on base `bd04f6d`.

- Fake server `tests/devcenter_ui_server.py` (port 8766, standard library only, threaded). It serves all reads of technical design sections 14.1 and 14.4, the proposal and question endpoints of section 14.3, the JS API mock `POST /__test__/jsapi/<method>` (section 14.2 list plus `cloud_items_list`), the old desktop methods at `POST /__test__/desktop/<method>`, the test controls `health`, `scenario`, `fault`, `delay`, `agent-proposal`, the shim at `/__test__/pywebview-shim.js`, and `frontend/dist` with the shim tag before the app module.
- Fixtures `tests/fixtures/devcenter_ui/<scenario>/` for the 11 scenarios of section 10. A scenario has `scenario.json` with an optional `base`; a missing file comes from the base. `large-5000-rows` is made in memory (5 sources, 5000 rows, 5000 impact items).
- Rules of the mock: each read reply carries `revision`; a JS API call with a `base_revision` that is not the current revision gives `stale_revision`; a locked session refuses changes with `action_not_allowed`; no open session gives `session_not_open`. JS API errors come as an HTTP 200 error body, as the host returns a dict. A `network` fault is HTTP 503, so the shim throws.
- Shim `frontend/src/devcenter/mock/pywebviewShim.js`: sets `window.pywebview.api`, `__PBIBRAIN_DESKTOP__`, and dispatches `pywebviewready`. The fake server puts the method lists in front of the shim.
- Vite plugin `frontend/vite-plugins/devcenterFake.js`: with `DEVCENTER_FAKE=1`, the shim tag goes into `index.html`, and the dev proxy sends `/api` and `/__test__` to `DEVCENTER_FAKE_URL` (default `http://127.0.0.1:8766`).
- Playwright: second `webServer` (8766, URL `/__test__/health`). The main config now ignores `guardedDevelopment.spec.js`: that spec failed 7 of 7 in the main config at the base too, because it needs its own server (`playwright.guard.config.js`, port 8773). The guard config reads `GUARD_PYTHON` (default `.venv\Scripts\python.exe`). The derived configs ignore the Development Center specs.
- CI `.github/workflows/ci.yml` (windows-latest, each push and pull request): native runtime script, `pip install -e .[mcp]`, TOM bridge, `npm ci`, then gate 1 Python unittest, gate 2 `npm test`, gate 3 `npm run build` with a check for no shim tag, gate 4 Playwright (main config and guard config, one step each, so that each failure fails its step), gate 5 the lint test. Not run on GitHub (no push in this build).
- Lint `frontend/test/devcenter-lint.test.js` for `frontend/src/devcenter/**`: native select, hex color, emoji, em or en dash, one-sided colored border (CSS, inline style, Tailwind side color classes).
- Contrast `tests/test_theme_contrast.py`: computes each ticket 01 pair again from `theme.css` (pure Python WCAG formula) and compares with the ticket 01 values, 2 decimals. `line`, `line-strong`, `line-focus` are in `DECORATIVE_ONLY`, and the test asserts that each is below 3:1.
- Route list `tests/test_devcenter_route_list.py`: probes the real `BrainApp` with each section 14.2 method name (POST, PUT, PATCH, DELETE under `/api/devcenter/`, `/api/`, `/api/devcenter/session/`) and each `/__test__` route; each must give 404 or 405. A self-check makes sure that the probe sees a real route. No `backend/**/*.py` file names the fake server or the shim. S2 can add its route table checks to this file.
- Other tests: `tests/test_devcenter_ui_server.py` (24), `tests/test_ci_workflow.py` (6, with a check that each native command is the last line of its step or has an exit code check), `frontend/test/devcenter-shim-build.test.js` (4, runs two real Vite builds, about 12 s), `frontend/e2e/devcenterHarness.spec.js` (3).

Test commands and results:

- `python -m unittest discover -s tests`: 344 tests, 1 failure (the known `test_mcp_adapter` baseline failure, ticket 01).
- `npm test` in `frontend/`: 38 tests, 38 pass.
- `npm run build` in `frontend/`: pass; `dist/index.html` has no shim tag.
- `npx playwright test` in `frontend/`: 50 passed (47 old, 3 new).
- `npx playwright test -c playwright.guard.config.js` with `GUARD_PYTHON=python`: 7 passed.
- Kit gates: not applicable, because U0 adds no screen.

Rework 1: Gate 4 is 2 steps; Gate 3 checks the exit code of the build; the lint test inputs use escapes only.
