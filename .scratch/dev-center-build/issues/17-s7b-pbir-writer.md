# 17: S7 pbir writer

Status: open. Lane: backend. Design step: S7 (docs/DEV_CENTER_TECHNICAL_DESIGN.md section 16).

Depends on (tickets): [11](11-s5-change-plan.md).

The goal, the code areas, and the acceptance tests are the design text below. Each acceptance test must be an automated test, except the items that the design marks as manual.

## Lead notes

Scope of this ticket: the Python PBIR writer part of S7 only (`backend/adapters/pbir/writer.py`). Acceptance tests: the S7 tests for the PBIR writer and the refused items.

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


## Build record

- Files changed:
  - `backend/adapters/pbir/writer.py` (new PBIR report writer: `PBIRWriter`, `write_report`, `PBIRWriteError`, `REFUSED_REASONS`)
  - `backend/adapters/pbir/__init__.py` (exports `PBIRWriter`, `write_report`, `PBIRWriteError`, `REFUSED_REASONS`)
  - `tests/test_devcenter_pbir_writer.py` (8 acceptance and integration tests for S7b)
- Tests run:
  - `python -m unittest tests/test_devcenter_pbir_writer.py -v` (8 passed)
  - Full Python test suite via `ag.py gates 17`
- Notes:
  - Supports `COPY_PAGE`, `COPY_VISUAL`, `DELETE_PAGE`, `DELETE_VISUAL`, `REBIND_FIELD` (pointer-based and document-tree walk across projections, `queryRef`, `nativeQueryRef`, `sortDefinition`, `filterConfig` with `From`/`Where`, `pageBinding.parameters`, formatting `objects`, `Hierarchy`/`HierarchyLevel`/`Aggregation`, and `reportExtensions.json`), `REMOVE_FIELD`, `CREATE_REPORT_MEASURE`, `REPLACE_REPORT_MEASURE`, `DELETE_REPORT_MEASURE`, and `REWRITE_EXPRESSION`.
  - Preserves `$schema` versions on modified and copied files, writes UTF-8 without BOM, validates output with `validate_report_documents`, and refuses unsupported version 1 items (`bookmark_copy_not_supported`, `sync_slicer_group_not_supported`, `custom_visual_not_supported`, `static_resource_not_supported`, `destination_is_source_folder`, `pbir_legacy_not_supported`).
