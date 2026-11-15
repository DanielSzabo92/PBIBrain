---
title: "Reads stay fast during a scan: previous answers while publishing, garbage collection paused, the JSON store written a record at a time"
author: Claude
date: 2026-11-15
branch: claude/vibrant-franklin-h8aafq
cost: { minutes: 119, tokens: 1417550 }
id: l-50707394
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
- While a background scan publishes its graph and rebuilds the first answers, cached reads get the previous graph's answers (`_answering_previous`, set by the publish lock wrapper in `start_scan`). The worker rebuilds overview, search and the review index before it reports done.
- Automatic garbage collection is off for the scan. Afterwards the scan's objects are frozen and collection is turned back on; the full pass waits until no request has come for 2 s (`_collect_when_idle`).
- `/api/pending-changes` is answered without the request lock, because the watcher has its own state.
- Result: the slowest overview, search or pending-changes read during a full scan of the large project dropped from 2.4 s to 42 ms (review 04's budget is 200 ms).

## Tried and ruled out
- `gc.freeze()` alone: pauses stayed at 0.2–0.3 s, because the scan itself makes the garbage.
- `gc.enable()` straight after the scan: one 0.27 s pass over everything the scan left.
- Serialising the JSON store with a non-one-shot (pure Python) encoder: it lets threads switch but is several times slower while the publish lock is held.

## Watch out
- One-shot `json.dumps` of the whole graph is a single C call that holds the GIL (0.7 s). The JSON store now writes a record at a time; the file is byte-identical and is moved into place.
- Gzip is applied in WSGI `_encoded` (above 1 kB, cached by bytes identity or file mtime). The lineage payload has no edge ids or status; the client rebuilds `type|from|to`.

In the code: backend/api/app.py (start_scan, _warm_answers, _collect_when_idle, _cached_answer, _encoded), backend/graph/repository.py (_persist), backend/api/graph.py (get_lineage), tests/test_scan_progress.py.
