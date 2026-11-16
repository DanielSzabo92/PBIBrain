---
title: Two copies of one model in a project scan as separate versions instead of failing
author: Claude
date: 2026-11-16
branch: claude/nice-pasteur-ppkrv8
cost: { minutes: 16, tokens: 233135 }
id: l-7346fb6e
scope: repo
status: active
src: agent
touches:
  - backend/projects.py
  - tests/test_projects.py
  - README.md
---

## Decided
- Copies of one PBIP (Sales v1 / Sales v2) keep the same model lineageTag and report logicalId. The scan used to stop with "Conflicting model definitions share canonical identity" (issue #68). Now the first source read keeps the id; a later source whose model or report differs gets `<id>@<8-hex digest of its resolved path>`, and that source's reports are re-pointed to the renamed model. Identical roots are still merged.
- Children (tables, measures, ...) need no change: their ids are scoped under the model id.

## Watch out
- Which copy keeps the plain id follows the order of `sources` in brain.json; reordering them swaps which version gets the suffix on the next scan.
- The renamed report's model link is fixed on the keys model_id, modelId, dataset_id, datasetId, semanticModelId; bind_reports reads `model_id`.

In the code: backend/projects.py `_separate_versions` (called per source in `_scan_paths` before `_deduplicate_roots`), tests/test_projects.py test_two_copies_of_one_pbip_project_scan_as_versions.
