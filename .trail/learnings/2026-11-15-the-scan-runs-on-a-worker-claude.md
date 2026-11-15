---
title: The scan runs on a worker thread and takes the request lock only to publish; Cancel stops it between steps
author: Claude
date: 2026-11-15
branch: claude/vibrant-franklin-h8aafq
cost: { minutes: 1, tokens: 2640 }
id: l-ef376ead
scope: repo
status: active
src: agent
touches:
  - backend/api/app.py
  - backend/projects.py
  - frontend/src/transport.js
  - tests/test_scan_progress.py
  - tests/test_scale_budgets_large.py
---

## Decided
The scan runs on a worker thread and holds the request lock only while the new graph is published, because one blocking scan request made every other request wait for up to 21 s on a large project. The page starts it with one request and reads its status until it ends.
Cancel sets a flag checked at each step boundary, because nothing may be half published: the graph and the identity map change together.

## Watch out
Formula analysis is one step (15 of 18 s on the 13,731-object project), so a cancel during it takes effect only when that step ends, because the fact-graph build has no cancel check inside.
The page matches the scan number before it trusts "done", because the outcome of an earlier scan stays in the status answer.
The overview lists 50 validation issues and counts the rest, because right after a scan it carried every issue (1.4 MB); a server started on an existing database has no validation result, so this was not seen before.

In the code: backend/api/app.py (start_scan, scan_status), backend/projects.py (ScanCancelled, publish_lock, source_states), frontend/src/transport.js (scan, cancelScan), tests/test_scan_progress.py, tests/test_scale_budgets_large.py.
