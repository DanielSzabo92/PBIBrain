---
title: "The in-app chat runs answers on a worker thread polled by the page, calls the MCP tools in process from one shared registry, and binds the API key to its exact…"
author: Claude
date: 2026-11-07
branch: claude/ticket-7-chat
cost: { minutes: 22, tokens: 450091 }
id: l-b8d87e87
scope: repo
status: active
src: agent
touches:
  - backend/tool_registry.py
  - backend/chat/credentials.py
  - backend/chat/settings.py
  - backend/chat/providers.py
  - backend/chat/service.py
  - backend/chat/__init__.py
  - tests/chat_fake_provider.py
  - tests/test_chat.py
  - frontend/src/transport.js
  - frontend/src/chat.js
---

## Decided
- One tool registry (`backend/tool_registry.py`, `build_tools`) returns the 17 tools as plain functions. The MCP server adds each with `server.add_tool`; the chat derives the provider JSON schema from the same signatures (`tool_schema`). A contract test checks both expose the same names and parameters. `agent_tools.register` was removed; the MCP client name now comes from `server.get_context()` instead of a `ctx: Context` parameter (the chat labels its proposals "Brain chat").
- An answer runs on a worker thread; the page polls `GET /api/chat/runs/{id}?after=N` every 120 ms. The desktop server is one serialized WSGI server, so a long streaming HTTP response would have blocked every other request while the model writes.
- Tools run in process against `BrainApp.handle` (`InProcessClient`), behind the same `TOOL_ROUTES` allowlist as the HTTP MCP client, so the chat can propose but never accept or apply. `BrainApp.request_lock` serializes the worker's tool calls with HTTP requests.
- Chat routes are plain local HTTP (`/api/chat/...`), not the pywebview JS API: the chat only reads and proposes, exactly like MCP, which is already HTTP, and the e2e can drive it in a browser.
- Anthropic goes through the official `anthropic` SDK (optional extra `[chat]`, pinned in packaging). OpenAI-compatible and local (Ollama) endpoints use a small stdlib streaming client; a loopback base URL bypasses proxies, so a local endpoint works offline.
- Removing the merge-session chip also removes the eight Merge models tools from that turn.

## Watch out
- The local API has no authentication, so a local process can edit the AI settings. The key is stored under provider + exact base URL (`credential_name`); a changed URL has no key until the user types one, so a key can never be redirected to another server. Do not store one key per provider.
- `anthropic` 2.x sends the key as `Authorization: Bearer` (API version 2026-10-21), not `x-api-key`; fake servers must accept both.
- A proposal reply names its row `target_id`, not `target`.
- The chat e2e (`frontend/e2e/chat.spec.js`) uses its own server on port 8767 (`tests.graph_ui_server --chat`: scripted provider in `tests/chat_fake_provider.py` plus a merge-lab session). The other Playwright configs ignore it via `chatSpec`.

In the code: backend/tool_registry.py, backend/chat/{service,providers,settings,credentials}.py, BrainApp.chat in backend/api/app.py, frontend/src/chat.js, frontend/src/components/ChatPanel.jsx, frontend/src/components/AISettings.jsx.
