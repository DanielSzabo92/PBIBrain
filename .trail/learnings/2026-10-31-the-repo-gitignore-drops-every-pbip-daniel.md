---
title: "The repo .gitignore drops every .pbip and .pbir file, so a worker's fixture tests pass in its worktree but the files never reach git"
author: Daniel
date: 2026-10-31
branch: claude/dev-center-build-6abbf2
cost: { minutes: 12, tokens: 17016 }
id: l-1f15fc17
scope: repo
status: active
touches:
  - ".gitattributes"
  - ".scratch/dev-center-build/issues/01-s0-foundations.md"
  - backend/adapters/pbir/schemas/fabric/item/report/definition/bookmark/1.0.0/schema.json
  - backend/adapters/pbir/schemas/fabric/item/report/definition/bookmark/1.1.0/schema.json
  - backend/adapters/pbir/schemas/fabric/item/report/definition/bookmark/1.2.0/schema.json
  - backend/adapters/pbir/schemas/fabric/item/report/definition/bookmark/1.3.0/schema.json
  - backend/adapters/pbir/schemas/fabric/item/report/definition/bookmark/1.4.0/schema.json
  - backend/adapters/pbir/schemas/fabric/item/report/definition/bookmark/2.0.0/schema.json
  - backend/adapters/pbir/schemas/fabric/item/report/definition/bookmark/2.1.0/schema.json
  - backend/adapters/pbir/schemas/fabric/item/report/definition/bookmarksMetadata/1.0.0/schema.json
---

## Watch out
- `.gitignore` lists `*.pbip` and `*.pbir` (private Power BI artifacts). A new PBIP fixture loses its project file and `definition.pbir`; the tests pass in the worker worktree and fail after the merge ("Guarded PBIP scan requires exactly one project file").
- Fix: add a `!tests/fixtures/<set>/**/*.pbip` and `*.pbir` negation, and check `git status --porcelain --ignored` before a fixture commit.
- The TOM JSON reader refuses `relatedColumnDetails` (field parameter grouping), but the TMDL reader accepts it.
- `isDataTypeInferred` is lost in a TOM TMDL round trip, so the bridge reports "TOM roundtrip changed properties".
- Fixture bytes need `-text` in `.gitattributes`, because `core.autocrlf` is true on this PC.
- The DAX parser (`backend/dax/`) fails on any UDF (`=>`), so a model with a UDF cannot give a COMPLETE guarded scan until S1 fixes it.
