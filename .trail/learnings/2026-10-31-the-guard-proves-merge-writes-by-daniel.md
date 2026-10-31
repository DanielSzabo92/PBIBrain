---
title: "The guard proves merge writes by a canonical model-file check and a full model compare, not by extending the line check"
author: Daniel
date: 2026-10-31
branch: docs/dev-center-spec
cost: { minutes: 4, tokens: 110682 }
id: l-2aab282e
scope: repo
status: active
touches:
  - backend/diff/snapshots.py
  - backend/diff/tmdl_source.py
  - change_guard/orchestrator.py
  - change_guard/policy/engine.py
  - change_guard/contracts/schema.py
  - ".scratch/dev-center/issues/08-guard-reuse.md"
---

## Decided
- For a merge, each changed model file must be byte-equal to what Microsoft's model library (TOM) writes for the new model. Then the guard compares the full old and new model trees, and each difference must match a planned operation. The line-by-line text check is not extended to added or removed blocks: that path is complex and easy to break.
- A model file that is not in the library's own format (comments, hand edits) blocks the merge apply. The app offers a separate "format only" apply first, which the guard accepts only when the model does not change.
- An "app write record" (candidate = baseline files + files from the app's write step, bound to the plan by hash) replaces the sandbox receipt. A separate "merge" policy profile does not require a live value test; high risk and unchecked impact need one explicit OK in the Apply dialog.
- The plan sets new lineageTags before the write. A rename of an object with no lineageTag is one linked delete-and-create pair. Each reference rewrite is its own exact expression operation, with no wildcard.

## Watch out
- The contract schema already lists create, delete, and rename. The blocks are in the raw source coverage gate, the isolation (security) gate, the runtime rule of the policy, and the identity-map change check.
- Backups and undo already handle new and removed files. Do not rebuild them.

In the code:
- backend/diff/snapshots.py (_raw_coverage, compare_objects), backend/diff/tmdl_source.py (account_tmdl)
- change_guard/orchestrator.py (validate_candidate security gate), change_guard/policy/engine.py, change_guard/contracts/schema.py
- Ticket: .scratch/dev-center/issues/08-guard-reuse.md
