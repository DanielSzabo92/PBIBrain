# Independent packaged-agent verification

Date: 2026-09-30 (Europe/Budapest)

Scope: `C:\Users\Daniel\AppData\Local\Programs\PBIBrain\PBIBrain-Agent.exe` only. No native UI tools used. Disposable projects only. No application source or production fixture edited.

## Method

- Created disposable PBIP projects with `tests.fixtures.pbip_sources.write_pbip_project(..., include_extra=True)`.
- Fixture paths included spaces, Unicode, `#`, parentheses, and deep evidence-path nesting.
- Agent runs used a per-process environment with `PATH=C:\Windows\System32;C:\Windows`; `PYTHON*`, `LBUG*`, `VIRTUAL_ENV`, and `NODE_PATH` were removed. A separate run set `PYTHONHOME`, `PYTHONPATH`, `LBUG_C_API_LIB_PATH`, and `LBUG_PYTHON_BACKEND` to nonexistent poison paths.
- Packaged `project-scan` succeeded in both environments: `{"edges": 31, "nodes": 20, "sources": 1}`; poisoned-variable run also exited `0` with no stderr.
- Packaged `serve` was exercised on loopback ports 18323–18328. All spawned agent servers were stopped after use; no `PBIBrain-Agent.exe` remained.

## V-001 — invalid validation on the standard PBIP fixture

Severity: HIGH (parent audit may choose MEDIUM if validation is treated as advisory)

Confidence: CONFIRMED

Location: packaged `/api/scan` and `/api/overview`; model/report graph publication.

Preconditions: Standard PBIP fixture with one semantic model and one report using `byPath` dataset reference.

Reproduction:

1. Run packaged `PBIBrain-Agent.exe --config <fixture>\\config\\brain.json project-scan`.
2. Start packaged `serve` against the same config with the stripped environment.
3. `POST /api/scan`, then `GET /api/overview` and `GET /api/brain`.

Expected: A valid standard PBIP model/report graph scans successfully and does not report an invalid containment relation.

Actual: HTTP scan returns `200`, `nodes=20`, `edges=31`, but overview returns `validation_state: "invalid"`. Brain validation contains one `ERROR` with `blocking: 0`:

```text
code/issue_type: invalid_containment
message: MODEL cannot contain REPORT
edge_id: edge:cfabf21d9c94f00e772af6ebfe0db9c8
from_id: model:11111111-1111-1111-1111-111111111111
to_id: report:Finance.Report
```

The same result reproduced on independent fixtures `Finance Unicode #1`, `#2`, and `#3`. The graph also contains the expected `USES_MODEL` edge for the same report reference. Source evidence points to `backend/graph/loader.py:201-203`, which adds both `CONTAINS(model, report)` and `USES_MODEL(report, model)`; containment validation at `backend/validation/graph.py:314-323` explicitly disallows `MODEL -> REPORT`.

User impact: a normal PBIP scan can appear successful while the persisted graph is marked invalid. The Overview can still show ready state, so the validation error is easy to miss.

Recommended fix: remove the `CONTAINS` edge for a report/model reference; retain `USES_MODEL`.

Regression scope: repeated initial scans, API rescans, moved-project reopen, and renamed-table rescan all reproduced the invalid validation result.

## V-002 — independent review approval result

Confidence: CONFIRMED (expected behavior observed); parent GUI report was not reproduced by this agent.

The standard fixture exposes two `DateKey` suggestions with distinct targets and candidate IDs:

```text
Sales.DateKey -> semantic:candidate:e3a8d731103c5e5f56eb90f8ea4a6ad6
Date.DateKey  -> semantic:candidate:37b830d447b6246c03b191d95a1c28f5
```

Using the exact frontend payload shape (`action`, `target`, `candidate_id`, `review_id`, `value`, `property`) to `POST /api/review` approved only the Sales edge `edge:semantic:11f6ac0e1bf08048a2e2bef1a8b3c1bc`; the Date edge `edge:semantic:717b755b4c74468d87fb258760c8e5d1` remained `candidate`. The result persisted after server restart, project-folder move, and table rename/rescan. This direct packaged-agent reproduction does not confirm a shared-meaning approval bug; retain the parent UI observation as `SUSPECTED / REQUIRES VERIFICATION` until repeated through the GUI.

Snapshot check: after approval, the live packaged `GET /api/brain` response was inspected for both edge IDs, `semantic_candidates`, and `review_items`. It contained:

```text
edge:semantic:11f6... candidate_id=e3a8... status=approved
edge:semantic:717b... candidate_id=37b8... status=candidate
```

The live `semantic_candidates` response contained only the second DateKey candidate with `status=candidate`; `review_items` also contained only that second candidate. This matches the raw persisted edge statuses. The snapshot builder (`backend/api/app.py:118-160, 189-203`) copies each edge status into `semantic_candidates` and raw `edges`; it does not merge candidates by shared `to_id`. The parent `a-after-approve.json` state, where both raw edges and both semantic candidates are `approved`, was not produced by this direct packaged-agent API flow and needs a GUI request trace or repeat reproduction.

## Project state and recovery results

- Review persistence: one approved candidate remained approved after server restart.
- Folder move: the complete fixture moved to `verification\\fixtures\\moved\\Finance Unicode #2 (audit)`; relative config reopened successfully with 20 nodes, 31 edges, one approved candidate, and the second DateKey candidate still pending.
- Stable identity: renamed source table `Sales` to `SalesRenamed` while preserving lineage tag `22222222-2222-2222-2222-222222222222`; rescan kept the table ID, child IDs, and approved DateKey decision unchanged.
- Missing source: temporarily moved `Finance.pbip`; `POST /api/scan` returned HTTP `400` with the exact missing path. Existing graph remained 20 nodes/31 edges. Restoring the source allowed a successful rescan.
- Malformed source: temporarily replaced the `.pbip` JSON with `{"version":`; scan returned HTTP `400` with the exact file path and JSON parse position. Restoring the original bytes allowed a successful rescan.
- Source immutability: SHA-256/length manifest for all PBIP, TMDL, PBIR, report, and visual source files was identical before and after a packaged rescan (`Unchanged: true`). `.pbibrain` state was separate.
- Unicode/path handling: packaged CLI and server succeeded with fixture path containing `Unicode #`, spaces, `#`, parentheses, and nested directories.

Additional path isolation: a real non-ASCII directory (`Audit á (test)`) reproduced the native failure independently. With the database configured under that Unicode directory, packaged `project-scan` exited `2`:

```text
LadybugDB is required for the production graph repository:
IO exception: Cannot open file. path: ...\Audit á (test)\.pbibrain\brain.lbug
Error 3: The system cannot find the path specified.
```

This happened both when `.pbibrain` was absent and after explicitly creating it. A control fixture with the same spaces, `#`, and parentheses but an ASCII-only directory (`Audit B # (test)`) succeeded (`nodes=20`, `edges=31`). A Unicode project root with the database and identity map moved to an ASCII-only sibling path also succeeded; the identity map could still be written back under the Unicode project root. This isolates the failure to the native LadybugDB database path, not PBIP parsing or Python Unicode filesystem access. A `\\?\\` path prefix did not fix it.

Finding V-003 — Unicode database path blocks packaged project scan

Severity: HIGH

Confidence: CONFIRMED

Location: packaged `PBIBrain-Agent.exe` project scan; `.pbibrain\\brain.lbug` under a project path containing non-ASCII characters.

Expected: normal Windows Unicode project folders open and scan successfully.

Actual: native LadybugDB cannot create/open the project database and the packaged scan exits with an internal production-runtime error. The app creates the `.pbibrain` directory but no database file.

Evidence: `Audit á (test)` fails with Error 3; `Audit B # (test)` succeeds; the same Unicode project succeeds when only the DB path is relocated to an ASCII sibling. The failure therefore follows the database path encoding.

User impact: projects in ordinary non-ASCII Windows folders cannot be opened/scanned when PBIBrain stores `.pbibrain` beside the project.

Likely cause: the bundled LadybugDB native Windows file-open path receives the Unicode database path through a narrow/unsupported encoding boundary. This is a supported-cause hypothesis backed by path isolation; the native library source was not available in this audit.

Recommended fix: use a Unicode-safe native DB path API/runtime, or deliberately place the internal database under a verified ASCII application-data location while retaining project identity/source paths; surface a clear actionable error if neither is possible.

Regression scope: absent/precreated `.pbibrain`, actual non-ASCII `á` with and without `#`, ASCII special-character control, ASCII DB path with Unicode source root, and `\\?\\` path prefix.

## Suspected / contract-dependent behavior

After a successful scan, restarting the packaged server restored graph and review state but returned `overview.last_scan: null` and `validation_state: "not_run"`. During the running server the same scan returned a timestamp and `validation_state: "invalid"`. The source comments describe validation as runtime-only, so this is recorded as a suspected persistence/UI contract gap, not a confirmed defect without an explicit requirement that scan timestamp and validation state survive reopen.

## V-004 — duplicate review rows omit parent scope

Severity: MEDIUM

Confidence: CONFIRMED as a review-clarity/usability finding.

The review evidence contains two distinct candidate IDs and edge IDs for `Sales.DateKey` and `Date.DateKey`, but the native Review Queue rendered both rows identically: `DateKey`, `Meaning: DateKey`, `Column`, the same reason, and `Object name: DateKey`. The saved accessibility capture is `..\review-ambiguous.txt`; the screenshot is `..\review-ambiguous.png`.

Source evidence: `frontend/src/App.jsx:787-799` renders only `labelFor(targetNode)`, suggestion label, object type, reason/evidence, confidence, and decision buttons. The target node's parent table/model is not shown in the row. The queue does expose model/report filters at `frontend/src/App.jsx:739-785`, but where multiple same-name columns are present the row itself does not identify which filter scope applies.

User impact: a reviewer can approve or reject the wrong same-named column when rows are adjacent or when the queue is filtered to all objects. Stable target IDs exist in the API but are not visible in the decision row.

Recommended fix: display parent table and model context, or another stable disambiguator, in every review row and in the selected-object affordance.

## V-005 — Overview does not surface invalid validation state

Severity: MEDIUM

Confidence: CONFIRMED as a frontend contract gap; severity is usability/trust judgment.

The saved API payload `..\a-overview.json` contains `validation_state: "invalid"`, `warning_count: 0`, and `state: "ready"`. The same scan's `/api/brain` validation payload contains the `invalid_containment` ERROR documented in V-001. The Overview still presents the project as `Ready for review` with normal counts and no validation status or issue link.

Source evidence: `frontend/src/App.jsx:522-557` renders object counts, review state, and scan controls but never reads `overview.validation_state`; exhaustive `graft grep "validation_state" --in frontend/` returned no hits. The backend emits the field at `backend/api/app.py:52-85`.

User impact: an invalid graph can look ready, and the user receives no visible signal that validation found an ERROR. This weakens trust in the counts and review workflow even when the scan request returned HTTP 200.

Recommended fix: show validation state near scan status and link or expand the exact issue(s); distinguish `invalid` from ordinary pending review.

## Installed GUI startup control (no native UI interaction)

The installed `PBIBrain.exe` was launched twice from the evidence directory with a .NET `ProcessStartInfo` harness. The harness redirected and continuously drained stdout/stderr, then probed the loopback server after 10 seconds and closed the main window through `CloseMainWindow()`.

- Sanitized child environment (`PATH=C:\\Windows\\System32;C:\\Windows`; `PYTHON*`, `LBUG*`, `VIRTUAL_ENV`, and `NODE_PATH` removed): PID 29604, listener `127.0.0.1:65337`, root `200` (514 bytes), `/desktop/session` `200` (79 bytes), `/desktop/bootstrap.js` `200` (33 bytes), clean exit code `0` after a 1,998 ms close wait.
- Ordinary inherited environment: PID 2512, listener `127.0.0.1:63788`, the same three `200` responses and lengths, clean exit code `0` after a 1,892 ms close wait.

Evidence: `startup-sanitized.json`, `startup-ordinary.json`, their `.log.txt` files, and `startup-check.ps1` in this directory. WSGI request lines were captured in both logs, including the static CSS/JS requests. Therefore the earlier blank-window result is not reproduced when redirected handles are actively drained; it remains a harness/timing suspicion, not a confirmed installed dependency failure.

## Coverage limits

This verification covered the packaged agent CLI/API/runtime and installed `PBIBrain.exe` HTTP/process startup, including sanitized and ordinary environments, redirected-log startup, and graceful close. It did not cover native GUI rendering, keyboard/mouse behavior, or DPI/layout acceptance; the parent audit owns those checks. Parent evidence separately confirms a file-backed installed launch rendered native onboarding and created an empty-project database (`sanitized-file-ready.jpg`).
