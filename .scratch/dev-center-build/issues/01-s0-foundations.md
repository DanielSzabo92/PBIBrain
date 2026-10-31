# 01: S0 foundations

Status: open. Lane: backend. Design step: S0 (docs/DEV_CENTER_TECHNICAL_DESIGN.md section 16).

Depends on (tickets): none.

The goal, the code areas, and the acceptance tests are the design text below. Each acceptance test must be an automated test, except the items that the design marks as manual.

## Lead notes

Also fix the stale old test `tests/test_mcp_adapter.py`: it expects 5 tools, but the server has 7 `brain_*` tools. The merge lab fixtures go in `tests/fixtures/merge_lab/` as real files on disk (PBIP folders), because later steps copy, scan, and write them.

### Design text: S0. Foundations

- Goal: remove the blockers that all later steps share.
- Code areas: `backend/adapters/pbir/schemas/`, `tools/vendor_pbir_schemas.py`, `backend/desktop/host.py`, `backend/agent.py`, `backend/adapters/tabular_metadata/dotnet/TabularMetadata.csproj`, `tests/fixtures/`.
- Work: update the vendored PBIR schemas (section 9.2); rename `session_id` to `connection_id` with old-key read; update the TOM package; create the "merge lab" fixture set: 3 TMDL models, 2 PBIR reports, 1 TMSL model, 1 PBIR-Legacy report, with known renames, name clashes, moved measures, possible renames, duplicate lineageTags, objects with no lineageTag, a field parameter, a calculation group, a UDF, RLS and OLS, a hierarchy, bookmarks, and a non-canonical TMDL file.
- Depends on: nothing.
- Acceptance tests:
  - A PBIR report with each current schema version validates. An unknown `$schema` still fails closed.
  - An old `connection.json` with `session_id` loads; the next save writes `connection_id` only.
  - The existing native bridge tests pass with the new TOM version. TMDL serialization of the same model twice gives equal bytes.
  - The merge lab fixtures scan without errors.

## Build record

Built (worker, branch `worktree-agent-a2f5d1541558f2a6d`, base `bd04f6d`):

- PBIR schemas: `tools/vendor_pbir_schemas.py` pins each published version of report (1.0.0 to 3.3.0), page (to 2.1.0), visualContainer (to 2.13.0), pagesMetadata (to 1.1.0), bookmark (to 2.1.0), bookmarksMetadata 1.0.0, reportExtension 1.0.0, versionMetadata 1.0.0, and definitionProperties 1.0.0 and 2.0.0. Upstream revision `d07416c7cf0df4640af94900914dc575979f80ce`, 81 schema files.
- Validator (`backend/adapters/pbir/validation.py`): it now checks `version.json`, `bookmarks.json`, `*.bookmark.json`, and `reportExtensions.json` against their schemas. Bookmarks and report extensions still give `PBIR_UNSUPPORTED_ARTIFACT`, because the usage extraction does not cover them yet (S1). The family check is now exact. The old substring check accepted a page schema on `report.json`, because each URI contains "/report/".
- Connection marker: `connection.json` now has `connection_id`. The agent and the desktop host also read the old key `session_id` (`backend/connection_marker.py`). The `/desktop/session` reply has `connection_id`. The `X-PBIBrain-Session` header did not change.
- TOM: `Microsoft.AnalysisServices` 19.114.12 to 19.118.3 (csproj, lock file, provenance text).
- Merge lab: `tests/fixtures/merge_lab/` (63 files), written by `tools/build_merge_lab.py`. Projects: SalesA (TMDL, PBIR current versions), SalesB (TMDL, PBIR older versions), Finance (TMDL, no report), Legacy (TMSL `model.bim`, PBIR-Legacy `report.json`). `EXPECTED.json` lists each known case and the known coverage gaps of the guarded scan. `.gitattributes` keeps the fixture bytes (`-text`).
- Guard manifest: `.pbism` is now a source suffix. Before, the guarded scan refused each real PBIP model folder, because each one has `definition.pbism`.
- Old tests changed: `tests/test_mcp_adapter.py` (7 tools), `tests/test_desktop.py` (marker key `connection_id`).

Tests:

- `python -m unittest tests.test_s0_foundations`: 17 tests, OK.
- `python -m unittest discover -s tests`: 319 tests, OK (baseline 302 with 1 failure).
- The native bridge tests (`tests/test_native_cli_contract.py`) pass with TOM 19.118.3.
- No frontend change. No kit gates (no screen in this step).

Known coverage gaps (in `EXPECTED.json`, for S1): the DAX parser does not read the UDF syntax (`(amount : NUMERIC) => ...`); report measures are not read (a visual that uses one gives `missing_object_reference`); calculation group and field parameter extraction; RLS and OLS; bookmarks and report extensions; the guarded scan certifies PBIR only (PBIR-Legacy fails closed).
