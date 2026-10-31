---
title: "The graph node type for a security role is SECURITY_ROLE, because ROLE already means a semantic role"
author: Daniel
date: 2026-10-31
branch: claude/dev-center-build-6abbf2
cost: { minutes: 1, tokens: 2848 }
id: l-2e9da1cd
scope: repo
status: active
touches:
  - backend/graph/schema.py
  - backend/snapshots/manifest.py
  - tests/test_guarded_development.py
  - tests/fixtures/change_guard/reference_expected.json
  - backend/projects.py
---

## Decided
- RLS and OLS roles are `SECURITY_ROLE` nodes in `backend/graph/schema.py`, because the type `ROLE` is in use by the semantic inference and the model summary. A shared type would mix the two meanings.

## Watch out
- `SCANNER_VERSION` in `backend/snapshots/manifest.py` is part of each snapshot ID, so a change of it fails `tests/test_guarded_development.py` until the IDs in `tests/fixtures/change_guard/reference_expected.json` are written again. Run the full suite after the version change.
- The text-only TMDL reader of the project scan (`backend/projects.py`) reads hierarchies, but not roles, partitions, calculation groups, or functions. Only the guarded scan (TOM) reads them, because S1 extended only the guarded path.
