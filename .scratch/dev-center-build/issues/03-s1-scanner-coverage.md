# 03: S1 scanner coverage

Status: open. Lane: backend. Design step: S1 (docs/DEV_CENTER_TECHNICAL_DESIGN.md section 16).

Depends on (tickets): [01](01-s0-foundations.md).

The goal, the code areas, and the acceptance tests are the design text below. Each acceptance test must be an automated test, except the items that the design marks as manual.

## Lead notes

Ticket 01 pinned the guarded scan gaps of the merge lab in `tests/fixtures/merge_lab/EXPECTED.json` (`guarded_scan_gaps`). Close each gap that belongs to a version 1 object type, and remove it from the list. This includes the DAX parser in `backend/dax/`: it fails on the UDF syntax (`=>`); make it parse UDF definitions and calls. Extra acceptance test: the guarded scan of SalesA, SalesB, and Finance is COMPLETE, or each item that stays has a written reason. PBIR-Legacy stays fail-closed for write.

### Design text: S1. Scanner coverage

- Goal: the graph knows the version 1 object types, the new links, and PBIR positions.
- Code areas: `backend/scanner/model_reader.py`, `backend/scanner/report_reader.py`, `backend/scanner/metadata_reader.py`, `backend/graph/schema.py`, `backend/graph/migrations.py`, `backend/adapters/tabular_metadata/dotnet/Program.cs`, `backend/impact/analyzer.py`.
- Depends on: S0.
- Acceptance tests:
  - Each new node type (hierarchy, level, role, role filter, OLS permission, report measure, partition, shared expression, bookmark) is in the graph for the merge lab, from TMDL and from TMSL.
  - Each link of section 3.2 exists for a fixture case.
  - Visual nodes carry x, y, z, width, height, `parentGroupName`; page nodes carry width and height.
  - An unknown object type gives a "not checked" entry, not an error.
  - Existing graph contract tests pass (schema migration forward).
