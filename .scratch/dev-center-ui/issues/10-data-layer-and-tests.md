# How does the UI get its data, and how do the UI tests run?

Type: grilling
Status: open
Blocked by: 02

## Question

Design the UI data layer and the UI test strategy. Which client modules exist? How does the JS API mock work in browser dev mode and in e2e? How does the UI handle revisions, errors, and refresh after a state change? How do the contract tests and the Playwright e2e tests run, and which gates run in CI?

## Context

- Charting decision 6: an HTTP read client (`/api/devcenter/...`, section 14.1) and a JS API client (section 14.2). One JS API mock plus a fake HTTP server with fixture JSON from the "merge lab" (backend build step S0) for dev mode and e2e. Contract tests validate each fixture and each mock reply against the JSON Schemas in `backend/devcenter/contracts/`. A UI step that needs a schema waits for the backend step that creates it.
- Existing code: `frontend/src/transport.js` (HTTP client, `createBrainTransport`), `frontend/src/desktop.js` (`subscribeToDesktopBridge`, `desktopRequest`; the bridge check uses `get_session`). Unit tests: `node --test` in `frontend/test/`. E2e: `frontend/playwright.config.js` with `tests/graph_ui_server.py`; also `tests/guard_ui_server.py`.
- Each JS API call takes `base_revision` and returns `revision` or the error shape `{error: {code, message, details}}`. `stale_revision` needs a defined UI reaction.
- No push from the backend in version 1. Decide refresh rules (after each state change, on "Check sources", for new agent proposals).
- Long calls: compare up to 10 s, apply many steps. Decide cancel, progress, and busy states.
- Render gates in CI: depend on ticket 01 facts.
- Skills: `design-doctrine` (verification protocol), `design-qa`.

## Done when

The answer gives: the client module list and their API, the mock design and where its fixtures come from, the revision and error flow, the refresh rules, the state management approach (reuse the existing React state pattern or add a library, with the reason), the test layers (unit, contract, e2e) with what each proves, the fake server plan, and the CI gate list.
