---
title: A new git worktree fails some Python tests until you build the TOM bridge and install node_modules
author: Claude
date: 2026-11-16
branch: claude/practical-ramanujan-3xd2o3
cost: { minutes: 25, tokens: 164566 }
id: l-502bb437
scope: repo
status: active
replaces: l-246842e5
src: agent
touches:
  - backend/adapters/tabular_metadata/dotnet/TabularMetadata.csproj
---

## Watch out
- A new worktree has no `frontend/node_modules` and no built TOM bridge (neither is in git). The Python suite then gives errors that look like code faults.
- "Build the trusted TOM bridge before model verification": run `dotnet build -c Release backend/adapters/tabular_metadata/dotnet/TabularMetadata.csproj`.
- "'vite' is not recognized": run `npm ci` in `frontend/` (`test_phase4_inspector_contract` runs the build).
- The Ladybug DLL step of the earlier version of this learning is gone: the graph is SQLite through Python's built-in `sqlite3`, and no native database library is needed.
