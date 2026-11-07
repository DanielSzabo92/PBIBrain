---
title: "Agent edits without Docker run on a local copy tier marked weaker, TMDL creates and deletes are proven by model-library regeneration, and one Breaks/Needs repo…"
author: Claude
date: 2026-11-07
branch: claude/safety-layer-17
cost: { minutes: 23, tokens: 338827 }
id: l-6bb5417c
scope: repo
status: active
src: agent
touches:
  - backend/safety.py
  - change_guard/coverage.py
  - change_guard/policy/engine.py
  - backend/pending_changes.py
  - backend/api/app.py
  - tests/test_safety_layer.py
  - change_guard/workspace/candidate.py
  - change_guard/orchestrator.py
  - backend/mcp_server.py
---

## Decided
- No-container tier (`LOCAL_COPY`, on by default): the agent edits the guard's candidate copy (`run-agent --backend local`, or its own tools then `local-edit` / `record_local_edit`). The receipt and the security evidence say `isolation_strength: WEAKER_NO_CONTAINER`. Its safety comes from the copy plus the baseline check: an edit to the real sources makes the operation BASELINE_STALE. `Policy(allow_local_copy=False)` turns it off; only the non-default value enters the policy hash, so old operations keep their hash.
- TMDL create/delete/rename coverage reuses the merge guard's canonical-file rule instead of extending the line check: the model library (bridge `write-model` with no operations) regenerates the candidate model; a created/changed file is proven when it equals that output with line endings made equal (agents on Linux write LF), a deleted file when the library no longer writes it. Unproven files still go to the line check, which fails closed (comments, hand formatting).
- One safety report (`backend/safety.py assess_change`) on two graphs: changes, Breaks (still uses a deleted object, or the old name of a renamed one), Needs (DAX names a missing object). The guard puts it in evidence `safety` for both profiles; only the standard (agent) profile turns Breaks into the approval purpose BREAKS_DEPENDENTS, because the DevCenter Impact tab already makes the user decide blocking Breaks before apply.
- File watcher = polling (5 s while read), not OS events: hash cache makes it cheap and it works on network drives. It scans a preview with `ProjectService.preview_graph()` (`_scan_paths(publish=False)`), which never writes the graph, identity map or snapshot.

## Watch out
- Node IDs come from lineage tags, so a rename keeps its ID: a rename is `name` differing on the same ID. Without a lineage tag it is a delete plus a create.
- Compare node properties with sorted JSON, not repr (dict order differs between scans), and ignore `dax_*` parser output, or every dependent of a changed measure shows as changed.
- The guard's impact analyzer raises KeyError on an empty target list; a contract whose targets are all deleted (candidate) or all new (preflight) needs `_empty_impact`.
- In TMDL, `///` is a description, not a comment; `//` makes the model library fail to load the file.
- The reference fixture's report fails PBIR validation; guard tests that need static PASSED use the model only.

In the code: backend/safety.py, backend/pending_changes.py (compute_pending_changes, SourceWatcher), change_guard/coverage.py (prove_tmdl_changes), change_guard/workspace/candidate.py (LocalCopyIsolation), change_guard/orchestrator.py (record_local_edit, validate_candidate, _empty_impact), change_guard/policy/engine.py, backend/api/app.py (GET /api/pending-changes), backend/mcp_server.py (brain_pending_changes), frontend/src/components/PendingChanges.jsx, tests/test_safety_layer.py.
