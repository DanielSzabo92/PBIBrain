# 06: U2 data layer

Status: open. Lane: ui. Design step: U2 (docs/DEV_CENTER_UI_DESIGN.md section 13).

Depends on (tickets): [02](02-u0-test-harness.md).

The goal, the code areas, and the acceptance tests are the design text below. Each acceptance test must be an automated test, except the items that the design marks as manual.

## Lead notes

The error shape schema comes from ticket 04 (S2). If ticket 04 is not merged at your base, validate against a local copy of the shape of technical design section 12 and mark the test to use the S2 schema when it exists.

### Design text: U2. Data layer and copy

- Goal: the client modules and the copy catalog, tested without a browser.
- Code areas: `frontend/src/devcenter/` (`httpClient.js`, `errors.js`, `jsapi-methods.json`, `jsapiClient.js`, `invalidation.js`, `store.js`, `poller.js`, `useDevCenter.js`, `copy.js`), `frontend/test/devcenter*.test.js`, `tests/test_devcenter_ui_contract.py`.
- Depends on: U0.
- Acceptance tests:
  - Unit: URL and filter params, paging, error normalization (new shape, old shape, thrown error), queue order and revision handoff, drop of an old read reply, `stale_revision` drops the queued calls, each method has an invalidation entry, poll rules with a fake clock (visible, hidden, busy, focus).
  - Unit: each `copy.js` key has text; no em dash, en dash, emoji, ellipsis character, or "(s)".
  - Contract: `jsapi-methods.json` equals the section 14.2 list plus the change request calls of technical design section 14.4. The error shape fixture validates against its schema when S2 provides it.

## Build record

Built on base 446ee4e.

- `frontend/src/devcenter/`: `errors.js` (`DevCenterError`, `normalizeError` for the new shape, the old shape, a thrown error, the shim error, and an abort; `errorReaction` for the section 10 reactions), `httpClient.js` (each section 14.1 read and the change request reads, filters, sort, paging, abort signal), `jsapi-methods.json` (33 methods: section 14.2 plus UC13 `cloud_items_list`, each `short` or `long`), `jsapiClient.js` (one FIFO queue, `base_revision` from the store, `stale_revision` drops the queued calls with code `dropped`), `invalidation.js` (one entry for each method), `poller.js` (5 s session poll, focus poll, 500 ms Apply progress poll), `store.js` (cache, revision drop and refetch, stale toast, `session_not_open` banner, `source_changed` move to Compare), `useDevCenter.js` (provider and hooks, the only React module), `copy.js` (the catalog of ticket 09 section 3 with the tables of tickets 07 and 08, `t`, `tn`, `errorCopy`, `longCallText`).
- Unit tests: `frontend/test/devcenter-http.test.js`, `devcenter-jsapi.test.js`, `devcenter-store.test.js` (fake clock), `devcenter-copy.test.js`, `devcenter-react.test.js` (import smoke test only).
- Contract test: `tests/test_devcenter_ui_contract.py`. It compares `jsapi-methods.json` with the section 14.2 list plus UC13, the fake server `JSAPI_METHODS`, and the host (skipped until the host has the methods). The error fixture `tests/fixtures/devcenter_ui/errors.json` validates against a local copy of the section 12 shape. The S2 schema check is skipped until ticket 04 puts the schema in `backend/devcenter/contracts/` (file names that the test looks for: `error.schema.json`, `error-shape.schema.json`, `error_shape.schema.json`, `errors.schema.json`).
- Apply step IDs in `copy.js` (`source_check`, `plan_status`, `desktop_check`, `canonical_check`, `full_validation`, `approval`, `candidate_write`, `guard`, `promotion`, `rescan`, `fingerprints`) are a proposal. S9 fixes the real `details.step` IDs.
- No screen in this step, so no kit gates and no e2e.

Tests:

- `python -m unittest tests.test_devcenter_ui_contract`: 10 tests, OK, 2 skipped (host methods, S2 schema).
- `python -m unittest discover -s tests`: 371 tests, OK, 2 skipped.
- `npm test` in `frontend/`: 97 tests, 97 pass.
- `npm run build` in `frontend/`: pass. A separate Vite lib build of `useDevCenter.js` proved that Vite 5 accepts the JSON import attribute.
