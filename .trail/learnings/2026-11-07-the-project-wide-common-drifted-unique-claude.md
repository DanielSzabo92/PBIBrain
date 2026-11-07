---
title: "The project-wide common/drifted/unique overview aligns graph nodes with the merge alignment and no target, and merges renamed rows itself"
author: Claude
date: 2026-11-07
branch: claude/ecstatic-archimedes-qnhbhw
cost: { minutes: 12, tokens: 207931 }
id: l-9fbbfb9c
scope: repo
status: active
src: agent
touches:
  - backend/commonality.py
  - tests/test_commonality.py
  - frontend/src/commonality.js
  - frontend/test/commonality.test.js
  - frontend/src/components/CommonObjects.jsx
  - README.md
  - backend/api/app.py
  - backend/mcp_server.py
---

## Decided
- The overview (issue #14) builds CompareObjects from the project graph nodes, not from the TOM bridge (`load_objects`). That way cloud models from #9 take part and no app or bridge is needed. The compared properties are the node properties minus bookkeeping, links and layout (raw_source, *_id, *_ids, field_roles, query, x/y/width/height...). DAX expressions compare as `dax_key`, M as `exact_text`.
- `align_domain` runs with `target_id=None`. With no target it does not run the "moved" or "possible rename" steps. A post pass does the N-way rename instead: rows whose members all share one logic signature (type + normalized expression) are merged into one `renamed` group, but only when they hold at most one object per source and their names differ. Otherwise (the same logic twice in one model) they stay apart and show up only in `duplicate_logic`.
- The MCP tool asks for `compact=true&max_chars=12000` (about 3,000 tokens): it leaves out object ids (ask again with `group_id`) and drops groups from the end until the JSON fits, with `has_more`/`next_offset`. #18 can make this budget general.
- No new nav view: the panel sits on the Overview screen, because a new view means a new shortcut slot (VIEW_ORDER, Ctrl+N) and contract tests. Merge only navigates to Merge models with a notice; the DevCenter has no API to start a session with given sources.

## Watch out
- RLS roles are `SECURITY_ROLE` nodes, not `ROLE`.
- Sources get short refs (m1, r1) sorted by name. They are stable only for the same project content, so agents should not store them across scans.

In the code: backend/commonality.py, backend/api/app.py (/api/commonality), backend/mcp_server.py (brain_commonality, COMMONALITY_MAX_CHARS), frontend/src/commonality.js, frontend/src/components/CommonObjects.jsx, tests/test_commonality.py.
