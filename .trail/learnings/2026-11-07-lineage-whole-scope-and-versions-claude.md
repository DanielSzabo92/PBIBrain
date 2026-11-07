---
title: "Lineage and Matrix read the whole scope from a compact payload, and versions are matched with the Merge models rules"
author: Claude (graph lineage follow-up)
date: 2026-11-07
branch: claude/affectionate-fermi-rgourh
id: l-lineage-whole-scope-versions
scope: repo
status: active
touches:
  - backend/api/graph.py
  - frontend/src/versions.js
  - frontend/src/lineage.js
  - frontend/src/components/GraphView.jsx
  - frontend/src/components/ImpactMatrix.jsx
---

## Decided
- Raising the 1000-object graph limit was ruled out: full node payloads (dax_ast, raw_source) are the cost. `get_lineage` sends only ids, names, owner ids and hashes with lineage links, and has no limit. Lineage and Matrix share one load of it; the other views keep the limited `get_graph`.
- "Same object in two versions" uses the Merge models alignment rules (type + table + name for model objects, page/visual source IDs for report objects). Two roots are versions when ≥50% of the smaller one's keys match. Folded nodes keep the first version's id so details still load.
- Lane chips switched off in Lineage are bridged with THROUGH_HIDDEN links instead of breaking the chains.

## Watch out
- `source_hash` includes the scan ids, so it differs for identical copies. Version "differs" uses `definition_hash` (hash of raw_source) from the lineage payload.
- Folded nodes must have model_id/report_id/table_id/parent_id re-pointed to the folded owners, or objects only in v2 land under a stub "Model" row in the Matrix.
- e2e tests that mock `/api/graph` for Lineage must also mock `/api/lineage`.
