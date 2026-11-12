---
title: Graph reads are fast because answers are kept per graph revision and each read-only request shares one read of the store; anything that changes the graph must…
author: Claude
date: 2026-11-12
branch: claude/product-adversarial-review-wid901
cost: { minutes: 36, tokens: 653992 }
id: l-abd814f2
scope: repo
status: active
src: agent
touches:
  - backend/api/app.py
  - backend/api/review.py
  - backend/graph/repository.py
  - frontend/e2e/palette.spec.js
  - frontend/src/app.css
  - frontend/src/components/CommandPalette.jsx
  - tests/test_api_answer_cache.py
  - frontend/src/presentation.js
  - frontend/src/App.jsx
---

## Decided
- Read-only API answers (overview, review, graph, lineage, objects, search, brain) are kept until the repository revision, the decision-store revision or the database file time changes. A cached answer is returned without the request lock.
- Inside a read-only request, `all_nodes`/`all_edges` come from one shared read of the store. Writers still get fresh copies.
- The review screens load `/api/brain?view=review` (44 MB on a 14,000-object project, not 163 MB) and mount rows 50 at a time.
- The Overview widgets (most-used measures, hot unreviewed objects) are computed by the server.

## Tried and ruled out
- Caching inside `all_nodes()` for every caller: review decisions, sync and inference change the objects they get before they write, so a shared list could be left half-changed after an error.
- gzip for API answers: on loopback it costs CPU and saves no time.

## Watch out
- New code that writes the graph without `upsert_*`/`replace` (or sets a field on the repository, as the scan does with `last_scan`) must add 1 to `repository.revision`, or the UI shows the old answer.
- Code that runs under `repository.reading()` must not change the nodes or edges it reads.
- The desktop host server is still serial; only `brain serve` is threaded.
- The backend suite has 41 failures in this cloud container before any change (tools it lacks); compare against that list, not against zero. `graph.spec.js` clicks a tab named "Lineage" but the tab is "Lineage flow".

In the code: backend/api/app.py (`_graph_stamp`, `_CACHED_ROUTES`, `_review_snapshot`, `prime`), backend/graph/repository.py (`reading`, `revision`), backend/api/review.py (`_IndexedEdges`), frontend/src/presentation.js (`byId`), frontend/src/App.jsx (`REVIEW_PAGE`), tests/test_api_answer_cache.py.
