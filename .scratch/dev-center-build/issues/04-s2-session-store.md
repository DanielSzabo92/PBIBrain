# 04: S2 session store

Status: open. Lane: backend. Design step: S2 (docs/DEV_CENTER_TECHNICAL_DESIGN.md section 16).

Depends on (tickets): [01](01-s0-foundations.md).

The goal, the code areas, and the acceptance tests are the design text below. Each acceptance test must be an automated test, except the items that the design marks as manual.

## Lead notes

Extension points: create `backend/devcenter/jsapi.py` (one registry of JS API methods, each area adds its module) and `backend/devcenter/http_routes.py` (one table of read routes and proposal routes that `backend/api/app.py` mounts with one line). Later tickets add methods and routes there, so that parallel workers do not edit the same lines. The route list test must read the real app.

### Design text: S2. Session store and local sources

- Goal: create, save, open, and lock a merge session with local sources and a target.
- Code areas: `backend/devcenter/session/`, `backend/devcenter/sources/`, `backend/snapshots/manifest.py` (reuse `source_manifest`, `content_hash`), `backend/desktop/host.py` (JS API methods of section 14.2 for sessions and sources), `backend/devcenter/contracts/`.
- Depends on: S0.
- Acceptance tests:
  - Round trip: create, change, save, open gives an equal `session.json`; the bytes are canonical.
  - An atomic save interrupted after the temp write leaves the old file valid.
  - The secret check refuses a token-like string and an absolute user path.
  - A second open of a locked session is read-only.
  - An older `schema_version` migrates with a backup; a newer one is refused; conflict markers are refused.
  - A changed source file marks the rows ("source changed", "source object missing", "new since start"); Apply-check reports a blocking state until each row is confirmed.
  - "Empty" target writes a skeleton that the bridge loads; "Copy of" leaves the original unchanged (hash compare).
  - A TMSL or PBIR-Legacy target is refused with the fixed message.
  - `.pbibrain/.gitignore` has the runtime entries.
  - No HTTP route changes session state (route list test).
  - UC1: `GET sessions` lists each session with its fields (section 14.4); a locked session gives `locked`, a newer `schema_version` gives `newer`, and invalid JSON gives `damaged`.
  - UC2: each read reply of this step carries `revision`, equal to the session revision.
  - UC4: each JS API call of this step has a request and reply JSON Schema, and each error reply validates against the error shape.
  - UC27: `row_confirm` with a list of row keys confirms each row in one revision step.
