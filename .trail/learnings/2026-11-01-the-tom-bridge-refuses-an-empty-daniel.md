---
title: "The TOM bridge refuses an empty model that has a model property, so the Empty target writes model.tmdl with only 'model Model'"
author: Daniel
date: 2026-11-01
branch: claude/dev-center-build-6abbf2
cost: { minutes: 6, tokens: 6943 }
id: l-48e89e0c
scope: repo
status: active
touches:
  - backend/devcenter/session/secrets.py
---

## Decided
- The "Empty" target skeleton (`backend/devcenter/sources/`) writes `definition/model.tmdl` with only `model Model`, because the bridge refuses a model with no tables that has a model property such as `culture`: it fails with "TOM roundtrip changed properties".
- The secret check (`backend/devcenter/session/secrets.py`) decides that a string is an object name from its position only (path fields, row keys, dict keys of row-key maps), because a prefix rule let `token: <t>` and URLs with tokens pass. A display name always gets the full check.

## Watch out
- TOM writes no `model.tmdl` for such an empty model, so the S9 canonical check must permit this one file.
- `ROW_KEY_KINDS` in `secrets.py` is a copy of the kinds in `sources/objects.py`. A new row-key kind must go in both places.
- Version 1 is the first `schema_version`. The migration test sets `store.SCHEMA_VERSION` and `store.MIGRATIONS` to temporary values, because no real older version exists.
