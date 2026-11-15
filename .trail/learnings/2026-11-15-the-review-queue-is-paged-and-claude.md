---
title: The review queue is paged and decided on the server; the page never loads the graph snapshot
author: Claude
date: 2026-11-15
branch: claude/vibrant-franklin-h8aafq
cost: { minutes: 119, tokens: 1417550 }
id: l-baa898fc
scope: repo
status: active
src: agent
touches:
  - frontend/e2e/graph.spec.js
  - frontend/e2e/graphExplorer.spec.js
  - frontend/src/components/GraphView.css
  - frontend/src/components/GraphView.jsx
  - backend/desktop/host.py
  - frontend/e2e/searchPreview.spec.js
  - frontend/e2e/sourceDrop.spec.js
  - frontend/src/App.jsx
  - frontend/src/components/AppShell.css
  - frontend/src/components/CommandPalette.jsx
---

## Decided
- The Review queue, the Inspector's suggestions and the Overview's counts read server answers only. `GET /api/review/page` returns 25 rows (up to 500), counts, facets and pattern groups; `ReviewIndex` builds them once per graph stamp. A page must stay under 100 kB on the 13,731-object project (25 rows: 58–87 kB JSON, 9 kB gzipped).
- Bulk decisions by filter or pattern send `{action, view, except}`; the server resolves the ids (`matching_decision_ids`). Single decisions send `reply: "summary"`, so no snapshot comes back.
- Rows carry `links` counts and up to 3 names each way instead of edges. Only a row's own target node is sent whole; owners are slim.
- Scrolling holds 60 fps because rows are memoised (`ReviewRow`, with handlers read through a ref, and each row keeps its own page's nodes), new rows mount a few per frame in a transition (`useRevealed`), and `.review-item` has `content-visibility: auto`.

## Tried and ruled out
- A 30- or 50-row page: 102 kB and 314 kB on the large project.
- Giving rows the merged node list: every appended page re-rendered every row (150–230 ms per append).

## Watch out
- Candidate rows' nested `item` is slimmed. Stale and conflict rows keep the full record, because undo writes it back.
- A test that mocks review data must route `/api/review/page**`; `/api/brain?view=review` no longer exists.

In the code: backend/api/review_page.py, backend/api/app.py (get_review_page, _bulk_review, apply_review reply), frontend/src/views/ReviewQueue.jsx (useReviewPages, ReviewRow, useRevealed), frontend/src/transport.js (getReviewPage, reviewBulk).
