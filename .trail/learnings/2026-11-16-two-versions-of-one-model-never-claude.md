---
title: "Two versions of one model never stop a scan: the later copy gets its own id and its folder name"
author: Claude
date: 2026-11-16
branch: claude/nice-pasteur-ppkrv8
cost: { minutes: 35, tokens: 41161 }
id: l-942e922d
scope: repo
status: active
replaces: l-7346fb6e
src: agent
touches:
  - README.md
  - backend/api/app.py
  - backend/documentation_pdf.py
  - backend/pdf_writer.py
  - frontend/components.json
  - frontend/e2e/documentationExport.spec.js
  - frontend/package-lock.json
  - frontend/package.json
  - frontend/src/components/DocumentationExport.jsx
  - frontend/src/components/pdf/data-table/data-table.jsx
---

## Decided
- Copies of one model (Sales v1 / Sales v2) keep the same lineageTag or logicalId; the scan used to fail with "Conflicting model definitions share canonical identity" (issue #68). Now a later copy that differs gets `<id>@<8-hex digest of its path>`, never an error. Across sources this happens per source (its reports follow the renamed model); inside one source the last de-duplication step does it too. Identical copies are still merged.
- When the renamed copy has the same name as the first, its folder name is added: "SalesA (SalesA v2)", so Overview, Search and Merge models tell them apart. Merge models compares the two copies normally (checked: one Different row for one edited measure).

## Watch out
- Which copy keeps the plain id follows the order of sources in brain.json.
- Inside one source a report cannot tell which of two same-id models it means; it stays bound to the first.

In the code: backend/projects.py `_separate_versions` and `_deduplicate_roots`; tests/test_projects.py test_two_versions_inside_one_source_scan_side_by_side, test_two_model_bim_files_with_the_same_id_scan_as_versions.
