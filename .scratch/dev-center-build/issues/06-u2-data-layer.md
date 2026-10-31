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
