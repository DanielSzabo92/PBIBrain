---
title: "Accept and apply of merge choices exist only inside the app window, never as a local web endpoint"
author: Daniel
date: 2026-10-31
branch: docs/dev-center-spec
cost: { minutes: 4, tokens: 82672 }
id: l-c0ac18f4
scope: repo
status: active
touches:
  - ".scratch/dev-center/issues/12-agent-tools.md"
  - ".scratch/dev-center/issues/13-session-storage.md"
  - ".scratch/dev-center/issues/14-first-version.md"
  - ".scratch/dev-center/map.md"
  - CONTEXT.md
  - backend/api/app.py
  - backend/desktop/host.py
  - backend/mcp_server.py
---

## Decided
- Accept, reject, accept-all, and Apply exist only in the in-process desktop JS API. They are never HTTP routes.
- The HTTP API and the MCP tools can only write agent proposals with the status "proposed". The server rejects a proposal with confidence below 0.9 or with an empty reason.

## Tried and ruled out
- A secret header on the local API: the existing session ID is on disk and any local process can read it. A token in the served page is also readable through a local GET.

## Watch out
- The local API has no authentication. It checks only the host and the origin. Each local HTTP client (curl, an agent shell, the MCP adapter) can call each route. Do not add a write or accept route to it.
- An agent with shell access as the same Windows user can still edit project files directly. This is a stated limit, not a blocked path.

In the code:
- backend/api/app.py (host and origin check only)
- backend/desktop/host.py:95 (pywebview JS API), :397 (X-PBIBrain-Session is a stale check, not a secret)
- backend/mcp_server.py (POST allowlist: impact, compare)
- Decision: .scratch/dev-center/issues/12-agent-tools.md
