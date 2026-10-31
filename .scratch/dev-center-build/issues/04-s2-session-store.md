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

## Build record

Built:

- `backend/devcenter/jsapi.py`: the one registry of JS API methods. An area adds one line to `AREA_MODULES`. `DevCenterJSAPI` is a mixin of `DesktopController`, with one public method for each registered name. Each call checks the request and the reply against `contracts/jsapi/<method>.request.json` and `.reply.json`, and gives the error shape on each failure.
- `backend/devcenter/http_routes.py`: the one table of read routes (GET) and proposal routes (POST). `BrainApp.handle` mounts it with one line. The order of checks: unknown path 404, wrong method 405, then the session check (409 `session_not_open`). The desktop host gives the same 404 or 405 when no project is open.
- `backend/devcenter/session/`: `store.py` (canonical bytes, atomic save, lock file with process ID and owner, schema version check, migration with backup, conflict marker and invalid JSON refusal, `.pbibrain/.gitignore`), `secrets.py` (token, full path, user profile, and e-mail check before each save and each log line), `manager.py` (the open session, revision, `log.jsonl`, sources, target, source check, marks, row confirm, `apply_source_check` for apply step 1), `jsapi_methods.py`.
- `backend/devcenter/sources/`: `kinds.py` (source kinds and the fixed refusal messages), `objects.py` (row hashes for TMDL, TMSL, PBIR, and PBIR-Legacy), `fingerprint.py` (reuses `source_manifest` and `content_hash`), `targets.py` ("Empty" skeleton and "Copy of").
- JS API methods: `session_create`, `session_open`, `session_close`, `source_add`, `source_remove`, `source_relink`, `target_set`, `sources_check`, `row_confirm`. HTTP reads: `GET /api/devcenter/sessions`, `GET /api/devcenter/session`.
- `packaging/pbibrain.spec`: the contracts folder and the area module go into the build.

Notes for later steps:

- Row keys of S2 are object keys of one source: `<type>:<qualified name>`, for example `measure:Sales/Total Sales`. S3 must map its aligned row keys to these keys (or replace the index).
- `source_remove` keeps the Merge Choices and gives `choice_count`. The blocking plan item `choice_source_removed` (UC33) is S5.
- `GET session` gives `plan_status: null`. `plan_state` and the cached plan status (UC3) are S5. Proposal and question fields (UC9) are S10.
- The "Empty" skeleton has `model.tmdl` with only `model Model`. A model property (for example `culture`) on a model with no tables fails the round trip check of the bridge ("TOM roundtrip changed properties"). TOM also writes no `model.tmdl` for such a model, so the canonical check of S9 must permit this file.
- The migration test patches `store.SCHEMA_VERSION` and `store.MIGRATIONS`, because version 1 is the first version.

Tests:

- `python -m unittest tests.test_devcenter_session_store`: 35 tests, OK.
- `python -m unittest tests.test_devcenter_http_routes`: 5 tests, OK (the route list test reads the method names from section 14.2 and 14.4 of the design and sends POST, PUT, PATCH, DELETE to the real app).
- `python -m unittest discover -s tests`: 359 tests, OK (319 before this step).
- Frontend: no change in this step.

### Rework 1

- Finding 1: the generic long-run token rule does not apply to object names (dict keys, row-key strings, and the fields `row_key`, `path`, `display_name` of a source, and similar). The run class has no `/`. The explicit token formats (JWT, bearer, prefixed keys, secret pairs) still apply to names. New tests: a PBIR page `ReportSection<hex>` with a hex visual name, and a TMDL column name of 48 mixed-case characters with digits, both save; explicit token formats in row keys are still refused.
- Small finding: `SessionLock.acquire` takes a lock only with an exclusive create. A stale lock is renamed away and compared with the stale bytes that the call read; a lock that is not readable and is younger than 10 s is not stale. New test: only one owner takes the lock.
- Tests: S2 modules 43 tests OK. Full suite 362 tests, 0 failures.
