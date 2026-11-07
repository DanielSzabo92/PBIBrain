---
title: "Bulk edits of the target are an edit Merge Choice on the target row, so the plan, guard, apply and undo stay unchanged"
author: Claude
date: 2026-11-07
branch: claude/fervent-fermat-wy7r7y
cost: { minutes: 17, tokens: 299724 }
id: l-d32530fb
scope: repo
status: active
src: agent
touches:
  - backend/adapters/tabular_metadata/dotnet/ModelWriter.cs
  - backend/devcenter/plan/edits.py
  - tests/test_devcenter_bulk_edits.py
  - backend/devcenter/sources/objects.py
  - frontend/src/devcenter/components/bulkEditModel.js
  - frontend/src/devcenter/components/BulkEditDialog.jsx
  - frontend/src/devcenter/components/CompareGrid.jsx
  - backend/devcenter/plan/compiler.py
  - backend/devcenter/apply/rescan.py
  - backend/devcenter/plan/service.py
---

## Decided
- "Edit target" (issue #12) needs no new session type and no new operation kinds: a target model row gets the Merge Choice `{kind: "edit", new_name, set}`. It compiles to the existing RENAME / RENAME_PAIR and SET_PROPERTIES operations with literal values, so impact, plan validation, the merge guard, apply, rescan and undo are reused as they are.
- References to an edited name are rewritten without the "renamed" block (`_Compiler.included` returns True when the cause row has an edit choice): the user asked for the rename. Name clashes still block.
- Bulk operations (rename by text or regex with `$1`, set property, move folder, apply confirmed Naming Rules, delete with a Removal Policy) only produce per-row edit choices. `POST edit-preview` is a READ_POSTS read; the only write is the JS API `target_edit_apply` (ADR 0003: no HTTP write). A second operation on a row merges into its edit choice; a rename starts from the planned name.

## Tried and ruled out
- Sending null to clear a property: the C# model writer skips JSON null (`props["x"] != null`). The compiler sends "" instead; the model library then drops the property from TMDL. Switching the writer to ContainsKey was not done because donor TAKE props carry null values that would then clear target properties.

## Watch out
- The TMDL object index (`backend/devcenter/sources/objects.py`) used to hash a child's `///` description lines into its table, so a column description edit failed the rescan as "table changed". The lines now belong to the child below them.
- The rescan must follow an object's own rename (`_object_renames` in rescan.py): a REWRITE_EXPRESSION or SET_PROPERTIES on a renamed measure names its old row key.
- Compare props use `hidden` / `key`; the writer and the guard use `is_hidden` / `is_key` (`COMPARE_NAMES`).

In the code: backend/devcenter/plan/compiler.py (EDIT, EDITABLE_PROPERTIES, build_edit), backend/devcenter/plan/edits.py, backend/devcenter/apply/rescan.py, backend/adapters/tabular_metadata/dotnet/ModelWriter.cs (column description, data category, isKey), frontend/src/devcenter/components/BulkEditDialog.jsx, tests/test_devcenter_bulk_edits.py.
