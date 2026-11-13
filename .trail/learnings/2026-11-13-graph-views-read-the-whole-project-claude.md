---
title: Graph views read the whole project and fold it; sorting thousands of names needs one shared collator
author: Claude
date: 2026-11-13
branch: claude/product-adversarial-review-wid901
cost: { minutes: 24, tokens: 564662 }
id: l-21cc347f
scope: repo
status: active
src: agent
touches:
  - frontend/e2e/desktopAudit.spec.js
  - frontend/e2e/palette.spec.js
  - frontend/e2e/productRefinement.spec.js
  - frontend/e2e/sharedFixes.spec.js
  - backend/graph/repository.py
  - backend/projects.py
  - tests/test_api_answer_cache.py
  - frontend/src/graphLayout.js
  - frontend/src/lineage.js
  - frontend/src/components/GraphView.jsx
---

## Decided
- Containers, Lineage and Field usage all read the compact whole-scope payload (`getLineage`). The limited `getGraph` slice (80 objects) is only for Neighbourhood and for object-level filters. A default view built from a slice showed 80 arbitrary objects of 13,731.
- Large pictures are reduced on the client, not by asking the server for less: Containers starts collapsed with counts by type and counted "bundle" links between shown owners; Lineage folds a lane of more than 40 rows by owner (by model/report when that is still over 60 rows) above 400 objects.
- In a large Containers picture the layout is recomputed on expand (reports placed after the opened model's content) and the viewport pins the toggled owner. Small pictures keep the anchored placement the older tests expect.
- With "related only" on, a selection packs its chain around the selected object in a second small lane layout. The big layout is not recomputed (the issue #53 rule still holds) and links with a hidden end are hidden.
- The desktop server is threaded like `brain serve`; the controller lock covers only picking the project application, and closing a project waits up to 5 s for the request in flight.

## Tried and ruled out
- Memoising `objectName` per node object in a WeakMap: a test (and real code) renames node objects in place, so the name went stale. The cache is keyed by the raw name string instead.
- Drawing every bundle link when a model is open: 173 links into one trunk. Above 40 bundles only the selection's are drawn.
- Server paging for the review queue was not done; the slim snapshot is still ~42 MB at 11,528 suggestions.

## Watch out
- `String.localeCompare(other, undefined, {numeric: true})` builds a collator per call. On 8,576 objects the explorer build took 3.6 s; with one `Intl.Collator` and names read once per sort it takes about 60 ms. The same pattern was in versions, lineage and matrix.
- A row component that does `edges.filter(...)` over the snapshot costs 21,000 comparisons per row; use `linksOf(edges, id)`.

In the code: `frontend/src/graphLayout.js` (`bundleExplorerEdges`, `reportsLast`), `frontend/src/lineage.js` (`foldLineage`), `frontend/src/components/GraphView.jsx` (`wholeScope`, `packed`, `pin`, `fit`), `frontend/src/presentation.js` (`linksOf`, `formatCount`), `backend/desktop/host.py` (`_ThreadingServer`), `frontend/test/graphScale.test.js`.
