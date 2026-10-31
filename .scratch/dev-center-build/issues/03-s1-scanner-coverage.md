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

## Build record

Built (worker, base `bc19de4`):

- New node types (graph schema version 2, `backend/graph/schema.py`): `HIERARCHY`, `LEVEL`, `PARTITION`, `SECURITY_ROLE`, `ROLE_FILTER`, `OLS_PERMISSION`, `REPORT_MEASURE`, `BOOKMARK`. `SHARED_EXPRESSION` existed. The security role type is `SECURITY_ROLE`, because the semantic inference already uses `ROLE`. The node and edge tables do not change. `backend/graph/migrations.py` moves a version 1 JSON graph payload forward and stops the load of a newer version. The JSON payload now has `schema_version`.
- Model read (`backend/scanner/normalization.py`): TOM tables give hierarchies with levels, partitions (source type, mode, text), and the table calculation group with its items. TOM roles give a role, one role filter for each table filter, and one OLS permission for each table or column permission. Role members stay out of the graph (only `member_count`).
- Report read (`backend/scanner/pbip.py`, `normalization.py`): `reportExtensions.json` gives report measures; `bookmarks/*.bookmark.json` gives bookmarks in the order of `bookmarks.json` (read only). Visuals carry `x`, `y`, `z`, `width`, `height`, `tab_order`, `parentGroupName` (and `is_group` for a group container). Pages carry `width`, `height`, `display_option`. A visual binding to a `HierarchyLevel` resolves to the hierarchy. A measure binding that is not a model measure resolves to a report measure of the same report.
- Links of section 3.2 (`backend/graph/loader.py`, DAX analyzer): LEVEL REFERENCES COLUMN; VISUAL USES HIERARCHY; ROLE_FILTER DAX edges and ROLE_FILTER FILTERS TABLE; OLS_PERMISSION REFERENCES table or column; REPORT_MEASURE DAX edges (also to another report measure of the same report); VISUAL USES and filter FILTERS REPORT_MEASURE; BOOKMARK REFERENCES page, visuals, filter fields; PARTITION (and shared expression) REFERENCES SHARED_EXPRESSION. The M check removes comments and string literals and finds the name as an identifier or as `#"Name"`. M is not parsed. A calculated partition is DAX and gets its dependencies.
- DAX: `parse_dax_function` (`backend/dax/parser.py`) reads `(name : TYPE [SUBTYPE] [VAL|EXPR], ...) => body`. It replaces the header with spaces, thus body positions are positions in the full text. New AST nodes `FunctionDefinitionNode`, `FunctionParameterNode`. The grammar did not change. The analyzer uses this parser for each `USER_DEFINED_FUNCTION`. UDF calls already parsed.
- Guarded scan (`backend/snapshots/scan.py`): the new types are fact objects. `roles` is a known model property. A calculation group no longer blocks when the scan extracted it. A calculated table no longer blocks when the DAX analysis of its partition passed. The completeness block has `not_checked` (unknown model object types and unknown report files). It is not an error. The impact report copies `not_checked` into its completeness block. `SCANNER_VERSION` is `guarded-3`.
- PBIR validation: bookmarks and report extensions are no longer `PBIR_UNSUPPORTED_ARTIFACT`. A bookmarks file without a known schema still fails closed (`PBIR_SCHEMA_UNSUPPORTED`).
- Validation and impact: containment, orphan, binding, and reference rules know the new types (`backend/validation/graph.py`). The impact analyzer goes from a level to its hierarchy, from a partition to its table, and from a role filter or OLS permission to its role. Each security type gives the security warning.
- Lightweight TMDL text reader: it now reads hierarchies and levels, and a partition line ends the block before it. It does not read roles, partitions, or calculation groups. The TOM reader (guarded scan) reads all of them.
- `Program.cs`: no change. The bridge output already has hierarchies, partitions, roles, and calculation groups.
- Merge lab (`tools/build_merge_lab.py`, regenerated): Finance has the shared expression `SalesRows`, and its Sales partition uses it. SalesA detail page has the matrix `calendarmatrix` (Calendar hierarchy) and the group `targetgroup` that contains `target`. The bookmark `ytdview` has a Store Region filter and the `timeslicer` container. EXPECTED.json has the new cases (`shared_expressions`, `visual_hierarchies`, `visual_groups`, bookmark page, visuals, filter fields).
- Guarded scan gaps now: SalesB, Finance COMPLETE. SalesA: `RLS_OLS_RUNTIME_VERIFICATION_REQUIRED` only (reason: the graph holds the role, but only a query that runs as the role can prove the effect of a change). Legacy: the 5 PBIR-Legacy items (fail closed for write).
- Old test changed: `tests/test_pbir_coverage.py` expected `PBIR_UNSUPPORTED_ARTIFACT` for an empty `bookmarks.json`. This ticket closes that gap. The test now expects `PBIR_SCHEMA_UNSUPPORTED` for that file, and `PBIR_UNSUPPORTED_ARTIFACT` for an unknown JSON file.

Tests:

- `python -m unittest tests.test_s1_scanner_coverage`: 15 tests, OK. TMDL and TMSL (a TMSL copy of SalesA and Finance, written through the bridge) for each node type and each link.
- `python -m unittest discover -s tests`: 334 tests, OK (baseline 319).
- `npm test` in `frontend/`: 31 of 31 pass (no frontend change).
- No screen in this step, thus no kit gates.

Open items:

- The lightweight TMDL text reader (non-guarded project scan) does not read roles, partitions, calculation groups, or functions. The guarded scan reads them through TOM.
- `frontend/src/graphPresentation.js` does not list the new types in its type list. The graph view puts them in the correct group (model or report), because the backend sends `artifact_group`. A UI ticket can add them to the type list.
