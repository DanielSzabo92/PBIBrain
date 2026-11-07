---
title: "Cloud targets deploy the TMDL the guard accepted on a local working copy, guarded by LastSchemaUpdate, and merge templates key sources by display name"
author: Claude
date: 2026-11-07
branch: claude/ticket-16-cloud-targets
cost: { minutes: 31, tokens: 339645 }
id: l-9769ec74
scope: repo
status: active
src: agent
touches:
  - backend/adapters/tabular_metadata/dotnet/CloudDeploy.cs
  - backend/adapters/tabular_metadata/dotnet/Program.cs
  - backend/devcenter/sources/cloud.py
  - backend/devcenter/session/manager.py
  - backend/adapters/tabular_metadata/dotnet/ConvertTmdl.cs
  - backend/devcenter/apply/cloud_target.py
  - tests/test_devcenter_cloud_target.py
  - backend/devcenter/sources/convert.py
  - backend/devcenter/session/templates.py
  - tests/test_devcenter_migration.py
---

## Decided
- A Read/Write cloud model (and its Read/Write cloud report) is a merge target. The apply reads the service again, refuses when the objects differ from the last source-check baseline, copies the export to `apply/cloud/<apply id>/backup/`, and builds a PBIP working copy in `tmp/cloud-work/<item id>/`. The guard, canonical check and journaled promotion run unchanged on that copy.
- The deploy sends the guarded files, not a replay of the operations: bridge `cloud-deploy` deserializes the TMDL folder, `Model.CopyTo(live.Model)` and `SaveChanges()` (TOM sends only the delta). The request carries the LastSchemaUpdate of the fresh read; any other value in the service stops it with `target_changed` before a change. This replaces the design's "apply the operation list to the live tree": the service gets exactly what the guard checked.
- Rescan reads model and report from the service again. Undo redeploys the backup only while the service LastSchemaUpdate is still the one after the apply. A refused report write restores the model at once (`recovered: true`).
- Each apply to a cloud target needs the approval `CLOUD_WRITE` (the service blocks the PBIX download after an XMLA write). Local model + cloud report, or cloud model + local report, is refused as `mixed_target`.
- `model.bim` becomes a target only through `target_convert_tmdl` with `consent: true` (bridge `convert-tmdl` proves the TOM round trip; model.bim goes to `apply/tmsl-backup/`).
- Merge templates live in `.pbibrain/templates/<name>.json` and store each source by display name, because source IDs differ per session; a choice whose source name is missing is skipped with a reason.

## Watch out
- The guard scan needs exactly one `.pbip` in the working copy, and it checks the report against the model, so the copy rewrites `definition.pbir` to `byPath`; the upload puts the service's own `byConnection` file back.
- The PBIR writer's schema check fails when `definition.pbir` has no `$schema`. The fake service parts in the tests include it; a real getDefinition reply without it would fail the write step.
- Nothing here is tested against a real workspace yet (all tests use fakes for XMLA and Fabric). The earlier "cloud write is version 1.1" learning was set aside because issue #16 asked for it.

In the code: backend/devcenter/apply/cloud_target.py, backend/devcenter/apply/service.py (_target, _apply, _undo), backend/adapters/tabular_metadata/dotnet/CloudDeploy.cs and ConvertTmdl.cs, backend/devcenter/sources/cloud.py (deploy_model, update_report, write_checks), backend/devcenter/sources/convert.py, backend/devcenter/session/templates.py, tests/test_devcenter_cloud_target.py, tests/test_devcenter_migration.py.
