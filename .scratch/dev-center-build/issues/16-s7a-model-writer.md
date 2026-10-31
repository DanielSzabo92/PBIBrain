# 16: S7 model writer

Status: open. Lane: backend. Design step: S7 (docs/DEV_CENTER_TECHNICAL_DESIGN.md section 16).

Depends on (tickets): [11](11-s5-change-plan.md).

The goal, the code areas, and the acceptance tests are the design text below. Each acceptance test must be an automated test, except the items that the design marks as manual.

## Lead notes

Scope of this ticket: the bridge part of S7 only (`write-model`, `canonical-check`, `tree-compare` in `Program.cs`, and `backend/adapters/tabular_metadata/bridge.py`). Acceptance tests: the S7 tests for the model writer, `canonical-check`, and `tree-compare`. Also measure the non-canonical rate (risk R3) on the merge lab and on the existing PBIP fixtures, and record it.

### Design text: S7. Writers

- Goal: produce candidate model and report files from operations.
- Code areas: `backend/adapters/tabular_metadata/dotnet/Program.cs` (`write-model`, `canonical-check`, `tree-compare`), `backend/adapters/tabular_metadata/bridge.py`, new `backend/adapters/pbir/writer.py`.
- Depends on: S5.
- Acceptance tests:
  - Each model operation type applied by `write-model` to a fixture gives the expected TMDL (golden), and the temp folder reloads.
  - The user `definition` folder is never a write destination (test that the command refuses it).
  - Non-`.tmdl` files near the model stay.
  - `canonical-check` finds the non-canonical fixture file; "format only" makes it canonical with an empty tree compare.
  - `tree-compare` reports a change in an object type that the graph does not model (perspective).
  - The PBIR writer: page copy with a name clash keeps the old-to-new map and fixes `pages.json`, groups, drillthrough, and interactions; `REBIND_FIELD` changes each field location; a changed file keeps its schema version; output validates against the vendored schemas; no BOM.
  - Refused items (bookmark copy, sync slicer groups, custom visuals, static resources) give fixed reasons.
