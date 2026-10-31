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
