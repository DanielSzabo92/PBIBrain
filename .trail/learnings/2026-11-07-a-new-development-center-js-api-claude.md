---
title: "A new Development Center JS API method is a design change request, and five test lists pin the method names"
author: Claude
date: 2026-11-07
branch: claude/fervent-fermat-wy7r7y
cost: { minutes: 2, tokens: 19411 }
id: l-8ce8c2f5
scope: repo
status: active
src: agent
touches:
  - backend/adapters/tabular_metadata/dotnet/ModelWriter.cs
  - backend/devcenter/apply/rescan.py
  - backend/devcenter/contracts/http/edit-preview.reply.json
  - backend/devcenter/contracts/http/edit-preview.request.json
  - backend/devcenter/contracts/jsapi/merge_choice_bulk_set.request.json
  - backend/devcenter/contracts/jsapi/merge_choice_set.request.json
  - backend/devcenter/contracts/jsapi/target_edit_apply.reply.json
  - backend/devcenter/contracts/jsapi/target_edit_apply.request.json
  - backend/devcenter/http_routes.py
  - backend/devcenter/plan/compiler.py
---

## Decided
- A JS API method added after the section 14.2 list is a change request: it gets a UC row in technical design section 14.4 ("| JS API `name` ...") and goes at the end of the method lists, after `cloud_items_list`, not next to its related method.

## Watch out
- Five lists fail on a new method until all are updated: the 14.4 table row (read by `state_change_names`), `jsapi_methods()` + count in the route-list test, `CHANGE_REQUEST_CALLS` and `LONG_METHODS` in the UI contract test, `JSAPI_METHODS` and a `_call_<name>` handler in the fake UI server, and the order of `frontend/src/devcenter/jsapi-methods.json` (plus `LONG` in the frontend jsapi test and `INVALIDATES`).

In the code: docs/DEV_CENTER_TECHNICAL_DESIGN.md 14.4, tests/test_devcenter_route_list.py, tests/test_devcenter_http_routes.py, tests/test_devcenter_ui_contract.py, tests/devcenter_ui_server.py, tests/test_devcenter_ui_server.py, frontend/src/devcenter/jsapi-methods.json, frontend/test/devcenter-jsapi.test.js, frontend/src/devcenter/invalidation.js.
