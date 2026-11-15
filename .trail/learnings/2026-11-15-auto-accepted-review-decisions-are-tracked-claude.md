---
title: "Auto-accepted review decisions are tracked in a side file, because a scan rebuilds the graph records and keeps only their status"
author: Claude
date: 2026-11-15
branch: claude/vibrant-franklin-h8aafq
cost: { minutes: 29, tokens: 403728 }
id: l-bf67abcf
scope: repo
status: active
src: agent
touches:
  - backend/api/app.py
  - backend/projects.py
  - frontend/src/App.jsx
  - frontend/src/app.css
  - frontend/src/components/GraphView.jsx
  - frontend/src/components/ImpactMatrix.jsx
  - frontend/src/components/LaneChips.jsx
  - frontend/src/components/ObjectContents.jsx
  - frontend/src/components/VersionGroups.jsx
  - frontend/src/presentation.js
---

## Decided
Auto-accept (Settings > Review) accepts suggestions that restate the object's own name or description at or above a threshold. It is off by default and the threshold is 90 %: it changes what "reviewed" means, so a project opts in.
Which decisions the app made, and which of those a person reopened, are kept in a small file beside the override file. A reopened suggestion is never accepted automatically again; turning the setting off returns only the automatic decisions to the queue.
A bulk decision is one write and answers with an undo token that restores the status each suggestion had before, so an earlier rejection inside the selection survives the undo.

## Tried and ruled out
Marking the node or edge itself (a property like review_decision): every scan regenerates the records and carries over only their status by ID, so the mark was gone after the next scan and a human approval could no longer be told from an automatic one.
Storing the "not versions" correction in the override file: an override on a model marks the model as Edited in every view. It is in the project file (version_links) instead.

## Watch out
The earlier bulk status change compared every record with every identifier (11,000 x 13,000). Any new bulk path must look identifiers up in a set.
Bulk replies with reply "summary" carry no snapshot; the page reloads its slim review view. The full snapshot is 163 MB on a large project.

In the code: backend/api/review.py (DecisionMarks, apply_auto_accept, _set_status_many, restore_statuses), backend/api/app.py (_bulk_review, sync_auto_accept, _sync_review_settings), review-marks.json, tests/test_review_bulk_auto.py, frontend/src/components/ReviewSettings.jsx.
