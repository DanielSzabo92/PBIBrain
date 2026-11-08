---
title: "Compare and freshness code must test through the real project scan, because the scanner adds a per-model hash and the config can sit beside the sources"
author: Claude
date: 2026-11-08
branch: claude/sweet-babbage-tu9meu
cost: { minutes: 37, tokens: 240781 }
id: l-4542a85f
scope: repo
status: active
src: agent
touches:
  - README.md
  - backend/api/app.py
  - backend/chat/__init__.py
  - backend/chat/credentials.py
  - backend/chat/providers.py
  - backend/chat/service.py
  - backend/chat/settings.py
  - backend/devcenter/agent_tools.py
  - backend/mcp_server.py
  - backend/tool_registry.py
---

## Decided
- The project-wide overview ignores `source_fingerprint` as well as `source_hash`. The scanner stamps both with the same per-node hash, and it differs between models even for identical objects, so comparing it put every object in "differs" and nothing was ever "identical".
- Source hashing for MCP freshness and the pending-changes watcher skips only PBIBrain's own files (config, snapshot, database and its WAL/lock files, identity map, overrides, connection marker), plus the config folder when a source is that folder or holds it. A source below the config folder is hashed.

## Tried and ruled out
- Skipping every file under the config folder: right for the app's `<project>/.pbibrain/brain.json`, but the README's CLI layout (`C:\Reports\brain.json` with `C:\Reports\Sales\Sales.pbip`) then tracks zero files, so every reply says "not stale" and the watcher never reports a change.

## Watch out
- Tests that build the graph with `build_fact_graph` skip the scanner pipeline and never see `source_fingerprint`. Add at least one test that scans a real PBIP through `ProjectService.scan`.

In the code:
- backend/commonality.py `_IGNORED`
- backend/mcp_snapshot.py `source_fingerprint`, `_own_files`
- backend/scanner/pipeline.py `_stamp_hashes` writes both hash fields
- tests: `ScannedProjectTests` (test_commonality.py), `ConfigBesideSourcesTests` (test_mcp_snapshot.py)
