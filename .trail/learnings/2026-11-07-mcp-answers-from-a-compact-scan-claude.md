---
title: "MCP answers from a compact scan snapshot when the app is closed, and every brain tool reply is cut to a per-tool character budget"
author: Claude
date: 2026-11-07
branch: claude/mcp-snapshot-budgets-18
cost: { minutes: 19, tokens: 240501 }
id: l-f03bc91b
scope: repo
status: active
src: agent
touches:
  - backend/mcp_snapshot.py
  - backend/projects.py
  - tests/fixtures/large_project.py
  - backend/mcp_budget.py
  - tests/test_mcp_snapshot.py
  - backend/mcp_server.py
  - backend/agent.py
  - backend/cli/main.py
  - tests/test_mcp_adapter.py
  - backend/api/app.py
---

## Decided
- Each project scan writes `.pbibrain/agent-snapshot.json` (graph + SHA-256 of every source file). The MCP process never opens the native DB (single owner); when no app has the project open, or the connection marker is stale, it loads this file into an in-memory GraphRepository and answers through the same `BrainApp.handle` routes, so snapshot replies equal live replies minus `dax_ast`.
- The live/snapshot choice is made per tool call (ProjectClient), so one agent session survives the app opening, closing or crashing. The snapshot is reloaded when its mtime/size change.
- Budgets live in one table (`TOOL_BUDGETS`, characters of compact JSON, compact/full per tool) applied after the route answers, not inside each route. brain_commonality keeps its own route-side paging (#14) and gets `budget - META_RESERVE` as max_chars; the generic cut is only a guard there.
- The cut is top-down water-filling: small fields stay whole, a per-tool primary field (search items, graph nodes, context target) gets 4 shares, big lists keep a leading slice, maps with too many keys keep a leading slice of keys. Every cut is listed in `budget.trimmed_lists`; a cut search page fixes `has_more`/`next_offset`.

## Tried and ruled out
- Writing the snapshot with `serialize_nodes`/`serialize_edges` as is: 129 MB for 500 measures. `to_dict` repeats every property at the top level, `dax_ast` is large, and the nested `behavior` lists inside CONTROLLED_BY edge evidence grow with the square of the measures that read a table. Dropping the copies and dax_ast and keeping 3 behaviors per evidence item brings it to ~27 MB.
- Shrinking by halving the largest list repeatedly: re-serializes an 80 MB context reply many times, and never fits a map with 18k keys (`confidence`).

## Watch out
- `live_client` moved to `backend/mcp_server.py` (agent.py re-exports it). Tests that mock its HTTP client must patch `backend.mcp_server.BrainClient`, not `agent.BrainClient`.
- The source walk skips hidden folders/files (`.pbi`, `.git`), `cache.abf`, `localSettings.json`, and anything inside the config folder, or the snapshot would mark itself stale.
- brain_context on a big model is slow (seconds) because the context builder returns tens of MB; the budget only cuts it afterwards.

In the code:
- backend/mcp_snapshot.py (write_agent_snapshot, SnapshotClient, freshness, app_freshness), backend/mcp_budget.py (TOOL_BUDGETS, fit_reply), backend/mcp_server.py (ProjectClient, create_server(url=None, config_path=...)), backend/projects.py ProjectService.scan.
- tests/test_mcp_snapshot.py with tests/fixtures/large_project.py (500 measures, 50 pages).
