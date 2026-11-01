---
title: "Each S-step must remove its JS API methods from HOST_PENDING, because the UI contract test fails on a stale pending list"
author: Daniel
date: 2026-11-01
branch: claude/dev-center-build-6abbf2
cost: { minutes: 19, tokens: 243697 }
id: l-3ae8711b
scope: repo
status: active
touches:
  - ".scratch/dev-center-build/WORKER.md"
  - ".scratch/dev-center-build/issues/12-u4-compare-grid.md"
  - ".scratch/dev-center-build/issues/06-u2-data-layer.md"
  - frontend/src/devcenter/copy.js
  - frontend/src/devcenter/errors.js
  - frontend/src/devcenter/store.js
  - frontend/test/devcenter-copy.test.js
  - frontend/test/devcenter-http.test.js
  - frontend/test/devcenter-jsapi.test.js
  - frontend/test/devcenter-store.test.js
---

## Decided
- `tests/test_devcenter_ui_contract.py` checks the host against `frontend/src/devcenter/jsapi-methods.json` with an explicit `HOST_PENDING` list (method and owner step), because a skip "until all methods exist" can stay for ever and is not a pass.
- The test fails when the host has a method that the list does not have, when a list method is missing and not pending, and when a pending method already exists.

## Watch out
- S2 binds its JS API methods onto `DesktopController` at run time (`backend/devcenter/jsapi.py`, `AREA_MODULES`). A later step that adds methods must take them out of `HOST_PENDING` in the same change, otherwise the contract test fails on purpose.
- The S2 contract files have an absolute `$id` (`https://pbibrain.local/devcenter/contracts/...`) and refer to `defs.json` by that URL. Load them with `backend.devcenter.contracts.validator(...)`, because a path-based loader cannot resolve the refs.
- The S2 reply of `session_open` and `session_create` has no `session` field, so `frontend/src/devcenter/store.js` always loads GET session after them.
