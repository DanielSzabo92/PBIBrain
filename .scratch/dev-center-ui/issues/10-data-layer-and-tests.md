# How does the UI get its data, and how do the UI tests run?

Type: grilling
Status: resolved
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

## Answer

Resolved on 2026-10-31. The orchestrator accepted all 20 recommendations of round 1 (one round). The orchestrator made the `stale_revision` reaction (decision 9) and the Apply progress read (decision 15) a shared rule for tickets 06 and 08.

Facts found before the round:

- The repo has no CI workflow file (no `.github/`).
- Python tests use `unittest`. Frontend unit tests use `node --test`, with no React render library.
- The existing pywebview replies (`backend/desktop/host.py`) use `{ok: true, ...}` or `{ok: false, error: "<text>"}`. `frontend/src/desktop.js` `desktopRequest` reads `ok`.
- `frontend/playwright.config.js` starts one fake server (`tests/graph_ui_server.py`, port 8765) and tests the built `dist`.
- The design kit is a local plugin. CI cannot run the kit scripts.

### Decisions of round 1

1. Module list: see "Client modules" below.
2. State management: no new library. A small store with `useSyncExternalStore`.
3. The mock state lives in the fake server (Python). A test shim forwards each JS API call to it.
4. The shim loads through the fake server (e2e) or a Vite plugin with `DEVCENTER_FAKE=1` (dev mode).
5. New fake server `tests/devcenter_ui_server.py`, port 8766, scenarios and test controls.
6. Fixtures: written by hand first, recorded from the real engine over the merge lab later.
7. Contract tests in Python `unittest` with `jsonschema`. No JS schema library.
8. One call queue. Each call sends the last known revision. Old read replies are dropped.
9. `stale_revision`: no automatic retry, refetch, generic toast. Shared rule.
10. Error reactions by code: see "Error flow".
11. Refresh: invalidation table after each call, 5 s poll of `GET session`, poll on focus.
12. Busy states: short calls queue, long calls lock the session.
13. Cancel: abort HTTP reads only. No cancel of JS API calls.
14. Backend change requests (a) revision on reads, (b) cheap `GET session`, (c) JS API schemas.
15. Backend change request `GET /api/devcenter/apply/progress`, polled every 500 ms. Shared rule.
16. Unit tests on the pure modules only.
17. E2e tests on the fake server, with axe and overflow.
18. Performance budget for 5,000 compare rows.
19. New CI workflow with the gate list below.
20. The CI workflow is a UI build step output. Ticket 11 puts it in order.

### Client modules

All new code is in `frontend/src/devcenter/`. Each module except `useDevCenter.js` is plain JS with no React import, so `node --test` can test it.

| Module | Job | API |
|---|---|---|
| `httpClient.js` | Section 14.1 reads | `createDevCenterHttp({baseUrl = "/api/devcenter", fetcher})` returns `getSession()`, `getCompareRows({type, table, folder, state, source, page, changed, marks, limit = 200, offset})`, `getRowDiff(row, source)`, `getPlan({includeProposals})`, `getImpact({target, includeProposals, limit, offset})`, `getRemoval(object)`, `getWireframe(report)`, `getNamingRules()`, `proposeName(body)`, `validatePlan(mode)`, `getApplyPreview()`, `getApplyProgress()`, `getLog({limit, offset})`, `getSessions()`. Each takes an optional `{signal}` (AbortController). Each reply resolves to the JSON body. A non-2xx reply rejects with `DevCenterError`. |
| `errors.js` | One error type | `class DevCenterError {code, message, details, source}` (`source`: `http`, `jsapi`, `network`). `normalizeError(value)` reads the new shape `{error: {code, message, details}}`, the old shape `{ok: false, error: "<text>"}` (code `unknown`), and a thrown `Error` (code `network`). |
| `jsapi-methods.json` | The section 14.2 method list | Array of `{name, kind}`, `kind` is `short` or `long`. The client and the contract test read it. |
| `jsapiClient.js` | Section 14.2 calls | `createDevCenterJsApi({api, getRevision, setRevision})` returns one function for each method in `jsapi-methods.json` (for example `mergeChoiceSet(payload)`). Each call goes into one FIFO queue. When it runs, it adds `base_revision` from `getRevision()`. A success reply calls `setRevision(reply.revision)` and resolves to the reply. An error reply rejects with `DevCenterError`. The client also exposes `pending()` (running and queued calls) and `subscribe(listener)`. |
| `invalidation.js` | Which reads a call makes stale | `INVALIDATES: {[method]: resourceKey[]}`. Resource keys: `session`, `sessions`, `compareRows`, `rowDiff`, `plan`, `impact`, `removal`, `wireframe`, `namingRules`, `applyPreview`, `log`. Example: `merge_choice_set` makes `session`, `compareRows`, `plan`, `impact`, `applyPreview`, `log` stale. `sources_check`, `session_open`, `apply`, `undo_apply` make all keys stale. A unit test makes sure that each method in `jsapi-methods.json` has an entry. |
| `store.js` | Cache and session state | `createDevCenterStore({http, jsapi, clock})`. State: `revision`, `session`, `busy` (`idle`, `short`, `long`), `resources` (a map from resource key plus params to `{data, revision, status, error, stale}`), `notices`. Methods: `load(key, params)`, `markStale(keys)`, `refreshVisible()`, `run(method, payload)`, `startPoll()`, `stopPoll()`, `getState()`, `subscribe(listener)`. |
| `poller.js` | Poll rules | `createPoller({clock, isVisible, isBusy, tick})`. 5 s for `GET session`, 500 ms for `GET apply/progress` during Apply. |
| `useDevCenter.js` | React seam | `DevCenterProvider` (one store for the open session), `useDevCenterState(selector)` (`useSyncExternalStore`), `useResource(key, params)` (load on mount, refetch when stale and visible, abort on unmount), `useAction(method)` (returns `{run, pending, error}`). |
| `mock/pywebviewShim.js` | Test shim, never in the production build | Sets `window.pywebview = {api}` and dispatches `pywebviewready`. Each method posts to `/__test__/jsapi/<method>` and returns the JSON reply. It also gives the existing desktop methods that `desktop.js` needs (`get_session`, `choose_folder`, `choose_sources`) with fixture replies. |

State management reason: the app uses `useState` plus the transport object in `App.jsx`. A store with `useSyncExternalStore` keeps that style, adds no dependency, and keeps the cache, queue, and poll logic in plain JS that `node --test` tests without a browser.

### Mock design and fixtures

- One mock state, in the fake server. The JS API shim forwards each call to `POST /__test__/jsapi/<method>`. The fake server changes its in-memory scenario state, increments `revision`, and serves the HTTP reads from the same state. Thus a read after `merge_choice_set` shows the new Merge Choice. A mock in the browser would not agree with the HTTP reads.
- The shim and the `/__test__` routes exist only in `tests/` and in the test shim file. They never go into `backend/api/app.py` or `backend/desktop/host.py`. The S2 route list test ("no HTTP route changes session state") reads the real app only, so the fake server does not break it.
- Shim load in e2e: the fake server serves `frontend/dist` and adds `<script src="/__test__/pywebview-shim.js">` to `index.html` before the app script.
- Shim load in browser dev mode: a Vite plugin (`transformIndexHtml`) adds the same tag only when `DEVCENTER_FAKE=1`. The Vite proxy then sends `/api` and `/__test__` to the fake server. The production build never has the tag.
- Fixture folders: `tests/fixtures/devcenter_ui/<scenario>/`, one JSON file for each read (`session.json`, `sessions.json`, `compare-rows.json`, `plan.json`, `impact.json`, `naming-rules.json`, `log.json`, `apply-preview.json`, and more as needed).
- Fixture source, phase 1: written by hand. Each fixture must pass the contract test. A UI build step that needs a schema waits for the backend step that creates it (map decision 6).
- Fixture source, phase 2: when S3, S5 and S6 exist, `tools/record_devcenter_ui_fixtures.py` runs the real engine over the S0 merge lab set and writes the `default` and `large-5000-rows` reads. The recorded files replace the hand files. State scenarios that the merge lab cannot give (locked, newer schema, damaged) stay hand-written.

### Fake server plan

- File: `tests/devcenter_ui_server.py`. Start: `python -m tests.devcenter_ui_server --port 8766` from the repo root. The existing `tests/graph_ui_server.py` stays as it is.
- Playwright: a second `webServer` entry in `frontend/playwright.config.js`, URL `http://127.0.0.1:8766/__test__/health`. Development Center specs use base URL `http://127.0.0.1:8766`.
- Reads: `GET /api/devcenter/...` (all section 14.1 endpoints and the change request endpoints), from the scenario state.
- Mock JS API: `POST /__test__/jsapi/<method>` for each method in `jsapi-methods.json`. Body: the call arguments with `base_revision`. A wrong `base_revision` gives `stale_revision`, as the real host does.
- Test controls (test only):
  - `POST /__test__/scenario {name}`: load a scenario and reset the state.
  - `POST /__test__/fault {method, code, message, details, once}`: the next call of the method returns this error.
  - `POST /__test__/delay {method or path, ms}`: slow reply, for busy and skeleton tests.
  - `POST /__test__/agent-proposal {...}`: add a proposal and increment `revision`, as an agent would. For the poll test.
- Scenarios: `default`, `no-project`, `no-sessions`, `locked`, `newer-schema`, `damaged`, `sources-changed`, `source-missing`, `plan-invalid`, `apply-ready`, `large-5000-rows`.

### Revision flow

1. `GET session` gives the first `revision`. The store keeps it.
2. Each JS API call goes into one FIFO queue. When the call runs, the client adds `base_revision` from the store.
3. A success reply sets the store `revision` to `reply.revision`. The next queued call uses this value.
4. Each read reply carries `revision` (change request a). The store drops a read reply with a `revision` lower than the store value, and refetches.
5. A `GET session` poll reply with a higher `revision` than the store sets the new value and makes the visible reads stale (see "Refresh rules").

### Error flow

| Code | UI reaction |
|---|---|
| `stale_revision` | Shared rule (tickets 06 and 08 align). No automatic retry. The store refetches `GET session` and the visible reads. The user stays on the same view. Toast: "This session changed in another place. The view shows the latest state. Do the action again." The failed control does not keep a loading or pending state. The queued calls after it are dropped, with no second toast. |
| `session_not_open` | Show the session list with a banner. Ticket 09 gives the copy. |
| `source_changed` | Open Compare with the marks filter, as "Show these rows" does (ticket 02). |
| `action_not_allowed`, `invalid_payload`, `not_found`, `user_choice_exists` | Inline error at the control. Use ticket 09 fixed text for the code. Use the backend `message` only when ticket 09 has no fixed text. |
| `network`, `unknown`, HTTP 5xx | Error banner in the region that failed, with "Try again". The region keeps its last data, marked as not current. |

The ticket 06 codes for agent proposals (`confidence_below_threshold`, `reason_required`, `naming_rule_violation`) come only from the HTTP proposal endpoints. The UI shows them only in the Agent tab and Log (ticket 06).

### Refresh rules

Version 1 has no push from the backend.

1. After each successful call: the store reads `INVALIDATES[method]`. It refetches the visible reads in that list at once. It marks the other cached reads stale. A stale read refetches when its view shows.
2. Poll: while a session is open, the window is visible (`document.visibilityState`), and no call runs, the store polls `GET session` every 5 s. A new `revision` makes all reads stale and refetches the visible reads. New agent proposals and questions thus show in the Agent tab count within about 5 s.
3. Window focus: one poll at once.
4. "Check sources" (`sources_check`): all reads stale, visible reads refetch.
5. While a long call runs, the 5 s poll stops. The Apply progress poll (500 ms) runs only during `apply`, `format_only_apply` and `undo_apply`.

### Busy states and long calls

- Short calls (`kind: short` in `jsapi-methods.json`, for example `merge_choice_set`, `row_confirm`, `proposal_accept`, `proposal_reject`, `compare_mode_set`): they go into the queue. Only the changed control shows its loading state. Other controls stay usable.
- Long calls (`kind: long`): `session_create`, `session_open`, `sources_check`, `apply`, `format_only_apply`, `undo_apply`, `pull_to_local`, `cloud_connect`, `cloud_sign_in`, `merge_choice_bulk_set`, `proposal_accept_all`. They set `busy: long`. Each change control in the session is disabled until the reply. The trigger control shows its loading state and a text (for example "Checking sources").
- Cancel: HTTP reads abort with AbortController when a filter changes, a page changes, or the view closes. JS API calls cannot be cancelled (pywebview has no cancel, and Apply is all or nothing). The UI shows no Cancel button for them.
- Apply progress: the UI polls `GET /api/devcenter/apply/progress` every 500 ms and shows the section 13 step list with the current step (shared rule, change request d). If the endpoint is not there, the UI shows only "Applying plan" and the elapsed time.
- Compare reads that take more than 1 s: the grid shows a skeleton and the text "Comparing sources". The budget for a compare is 10 s.

### Test layers

| Layer | Tool and place | What it proves |
|---|---|---|
| Unit | `node --test`, `frontend/test/devcenter*.test.js` | URL and filter params, paging, error normalization (old and new shape), queue order and revision handoff, drop of old read replies, `stale_revision` drops the queued calls, each method has an invalidation entry, poll rules with a fake clock (visible, hidden, busy, focus). No React render tests. |
| Contract | Python `unittest`, `tests/test_devcenter_ui_contract.py`, `jsonschema` | (a) Each fixture file validates against its schema in `backend/devcenter/contracts/`. (b) The test starts the fake server state, runs each JS API method once for each scenario where it applies, and validates each reply and each error against the schemas (change request c). (c) `jsapi-methods.json` equals the section 14.2 list, the host JS API method names, and the fake server method names. |
| E2e | Playwright, `frontend/e2e/devcenter*.spec.js`, fake server on port 8766 | One spec for each flow of tickets 02 to 08, with scenarios. Injected `stale_revision` gives the toast and the refreshed view. Slow calls give the busy and disabled states. A proposal added through `/__test__/agent-proposal` shows after the poll. axe on each Development Center screen in both themes. No page overflow at 1024 x 640, 1280 x 900, 1440 x 900. Performance budget (below). |

Performance budget (from the map list "Not yet specified"), measured in e2e with `performance.mark` on `large-5000-rows`:

- The first 200 compare rows show within 1.5 s after the reply arrives.
- A filter change shows the new rows within 500 ms after its reply.
- `GET compare-rows` pages have 200 rows. Ticket 03 owns the grid render method.

These budgets are targets. They are UNMEASURED until the UI build step runs them.

### CI gate list

New file `.github/workflows/ci.yml`, Windows runner, on each push and pull request. Ticket 11 puts it in the UI build steps.

1. Python `unittest` for the full suite. This includes the contract test and a theme token contrast test (`tests/test_theme_contrast.py`, moved from ticket 01 `gates/theme_contrast.py`): each text and status token pair at 4.5:1 or more, and `control-border` at 3:1 or more, in both themes, also for the new semantic tokens.
2. `npm test` in `frontend/`.
3. `npm run build` in `frontend/`.
4. Playwright e2e in `frontend/` (both fake servers), with `axe-core@4.10.2` (new devDependency, the ticket 01 rule tags: wcag2a, wcag2aa, wcag21a, wcag21aa, wcag22aa) and the overflow check. Zero axe violations on Development Center screens. The existing Graph and Inspector failures of ticket 01 are not in this gate; ticket 09 owns them.
5. Repo lint test for `frontend/src/devcenter/**` only (a `node --test` file): no native `<select>`, no hex color, no emoji, no em dash or en dash, no one-sided border (`border-left`, `border-right`, `border-top`, `border-bottom`, `border-inline-*`, `border-block-*` with a color).

Not in CI: the kit gates `verify_states.mjs`, `verify_target_size.mjs`, `slop_tells.mjs`. The kit is a local plugin, not in the repo. They stay a manual release check with `DS_REQUIRE_BROWSER=1` and the ticket 01 scripts. Caution: do not trust `verify_states` for a hover background with alpha (ticket 01). Measure it in the live page.

### Backend change requests

- (a) Each `/api/devcenter/*` read reply carries `revision` (the session revision it was computed from). Reason: the UI must drop a reply that is older than its last state change.
- (b) `GET /api/devcenter/session` must be cheap: it returns the cached plan status, or null with `plan_state: "computing"`, and never runs a plan compute. Reason: the UI polls it every 5 s.
- (c) `backend/devcenter/contracts/`: one JSON Schema for each section 14.2 call request and reply, plus the error shape `{error: {code, message, details}}`. Reason: the contract test validates each mock reply.
- (d) `GET /api/devcenter/apply/progress`: `apply_id`, `step` (section 13 step ID), `step_index`, `step_count`, `state` (`running`, `done`, `failed`). Reason: the Apply dialog shows the current step. The UI polls it every 500 ms.

### Inputs for later tickets

- 03: pages of 200 rows, the skeleton above 1 s, the performance budget.
- 06, 08: the `stale_revision` rule and the Apply progress poll are shared rules.
- 09: copy for `session_not_open`, the inline error codes, and the error banner.
- 11: order the CI workflow, the fake server, and the shim as UI build steps. Each UI step waits for the backend step of its schema.
