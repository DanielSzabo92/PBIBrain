---
title: "The merge feature reuses only the change guard's safety checks, without the Docker isolation"
author: Daniel
date: 2026-10-30
branch: docs/dev-center-spec
cost: { minutes: 3, tokens: 37467 }
id: l-15ea9646
scope: repo
status: active
touches:
  - ".scratch/dev-center/issues/01-tmdl-write.md"
  - ".scratch/dev-center/issues/02-xmla-access.md"
  - ".scratch/dev-center/issues/03-fabric-report-api.md"
  - ".scratch/dev-center/issues/04-pbir-copy.md"
  - ".scratch/dev-center/issues/05-desktop-open.md"
  - ".scratch/dev-center/issues/06-object-coverage.md"
  - ".scratch/dev-center/issues/07-compare-rules.md"
  - ".scratch/dev-center/issues/08-guard-reuse.md"
  - ".scratch/dev-center/issues/09-change-plan.md"
  - ".scratch/dev-center/issues/10-impact-data.md"
---

## Decided
- The Development Center reuses the change guard only for its safety checks: the scope check, the file coverage check, backups, and undo.
- It does not use the Docker isolation. The isolation exists to contain an agent that edits files. In the Development Center the app itself writes the files, and the agent can only propose merge choices.
- The guard must learn to accept create, delete, and rename for a merge Change Plan, and still reject every change outside the plan.

## Watch out
- Do not give the agent a tool that applies changes. The no-Docker decision is only safe while the agent stays outside the write path.
- The word "decision" already means review decisions. Use "Merge Choice" for the choice on one merge row.

In the code:
- change_guard/ (orchestrator.py, contracts/contract-v1.schema.json)
- Plan: .scratch/dev-center/map.md (Notes), ticket .scratch/dev-center/issues/08-guard-reuse.md
