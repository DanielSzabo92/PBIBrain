---
title: "Cloud items in a Brain project live in a separate cloud_sources list, read live only through the app's sign-in, and an unreadable model or report stays as a No…"
author: Claude
date: 2026-11-07
branch: main
cost: { minutes: 17, tokens: 231123 }
id: l-d1f359e1
scope: repo
status: active
src: agent
touches:
  - backend/project_cloud.py
  - tests/test_project_cloud_sources.py
  - frontend/src/components/CloudSourcePicker.jsx
  - README.md
  - backend/projects.py
  - backend/scanner/normalization.py
  - backend/graph/loader.py
  - backend/desktop/host.py
---

## Decided
- `brain.json` keeps cloud items in a new `cloud_sources` array (kind, workspace id/name, item id, name, dataset_id for reports, access type). `sources` stays a list of paths, because the desktop add/remove code, the agent and the CLI all treat `sources` as paths.
- A project scan reads cloud items live only when the project service has a cloud service: the desktop host attaches the Development Center `cloud_service` (the one in-memory sign-in). The CLI and stand-alone agent have none, so they use the cached export in `<config folder>/tmp/cloud/<item id>/` (gitignored with `.pbibrain/tmp/`). One unreadable cloud item never fails the scan.
- A model that cannot be read, or that a report binds to byConnection but is not a project source, becomes a MODEL root with `check_status: not_checked` (and a reason). The report keeps a USES_MODEL edge to it, so Lineage, Matrix and the MCP overview show the gap. Model/report counts of the scan exclude these roots. "No semantic models" is no longer an error; only "no models and no reports" is.
- Cloud model and report roots use the cloud item id (dataset id / report id) as source id, so a cloud report binds to its model by dataset id. Local thin reports bind by `semanticmodelid`, then by `Initial Catalog` name (narrowed by the powerbi:// workspace).
- Each cloud workspace is a WORKSPACE node (the type already existed and the Lineage model lane already listed it) with CONTAINS edges to its cloud models and reports. That alone groups them in Lineage; the Matrix sorts local roots first, then by workspace.

## Watch out
- The collision-checking identity of a project scan refuses a second `object_id` call for the same id, so the normalizer creates one WORKSPACE node per workspace and caches it (`_workspaces`).
- `cloud_source` is excluded from `raw_source`, so a cloud copy and a local copy of the same model keep the same definition hash for version grouping.
- Cloud listing calls (`cloud_sign_in`, `cloud_items_list`) stay JS API only; the project view calls them through pywebview and saves with the new host method `add_cloud_source`.

In the code: backend/project_cloud.py, backend/projects.py (_read_cloud_source, _scan_paths), backend/scanner/normalization.py (_cloud_properties), backend/graph/loader.py, backend/desktop/host.py (add_cloud_source), frontend/src/components/CloudSourcePicker.jsx, OriginBadge.jsx, tests/test_project_cloud_sources.py.
