---
title: "A new git worktree fails about 13 Python tests until you build the TOM bridge, set the Ladybug DLL path, and install node_modules"
author: Daniel
date: 2026-10-31
branch: claude/dev-center-build-6abbf2
cost: { minutes: 8, tokens: 130642 }
id: l-246842e5
scope: repo
status: active
touches:
  - ".scratch/dev-center-build/WORKER.md"
  - ".scratch/dev-center-build/board.md"
  - backend/adapters/tabular_metadata/dotnet/TabularMetadata.csproj
  - tests/test_mcp_adapter.py
  - backend/mcp_server.py
  - docs/DEV_CENTER_TECHNICAL_DESIGN.md
  - docs/DEV_CENTER_UI_DESIGN.md
---

## Watch out
- A new worktree has no `frontend/node_modules`, no built TOM bridge, and no `runtime/native/lbug_shared.dll` (all are not in git). The Python suite then gives about 13 errors that look like code faults.
- "Build the trusted TOM bridge before model verification": run `dotnet build -c Release backend/adapters/tabular_metadata/dotnet/TabularMetadata.csproj`.
- "Could not find lbug C API shared library": set `LBUG_C_API_LIB_PATH` to the `runtime/native/lbug_shared.dll` of the main checkout.
- "'vite' is not recognized": run `npm ci` in `frontend/` (`test_phase4_inspector_contract` runs the build).
- With all three, the suite at the start of the Development Center build was 302 tests and 1 failure: `tests/test_mcp_adapter.py` expected 5 tools, but `backend/mcp_server.py` registers 7 `brain_*` tools.
