---
title: "Agents answer Power BI questions from the graph in one call, never by reading project files; Copilot and Antigravity are the only subscription CLIs"
author: Claude
date: 2026-11-16
branch: claude/charming-dirac-kg461o
cost: { minutes: 18, tokens: 397722 }
id: l-440184de
scope: repo
status: active
replaces: l-0e72dd00
src: agent
touches:
  - README.md
  - backend/chat/cli_providers.py
  - backend/chat/providers.py
  - backend/chat/service.py
  - backend/chat/settings.py
  - backend/devcenter/session/proposals.py
  - backend/process_guard.py
  - change_guard/workspace/candidate.py
  - docs/AGENT_GUIDE.md
  - docs/SECURITY_BOUNDARIES.md
---

## Decided
- The user's boundary: an agent must answer model questions from PBIBrain's graph quickly, never wander into TMDL/report files or its own tools. So: `brain_dependencies` (name or ID -> object, formula, upstream via DEPENDS_ON/REFERENCES/SOURCES_FROM, downstream plus USES to visuals, pages) answers dependency questions in one call; the chat resolves names in the question before the model starts and adds a `<graph>` block, so "what does X depend on" often needs no tool call; one set of grounding rules (`backend/agent_rules.py`) goes into the MCP instructions, the chat system prompt and the editor files.
- `brain agent-setup` writes `.vscode/mcp.json`, `.mcp.json`, `.github/agents/pbibrain.agent.md` (`tools: ['pbibrain/*']`, the hard boundary in Copilot) and Antigravity's `.agents/mcp_config.json` + `.agents/rules/pbibrain.md` (`trigger: always_on`).
- Only Copilot and Antigravity are subscription chat providers (the user dropped the Claude CLI). The CLI stays a text model: PBIBrain owns the tool loop and its limits (now 5 rounds, 15 calls, 6 per turn).
- Name resolution is exact (casefolded name index per graph revision); a single plain lowercase word never counts as an object, so "sales" in prose does not pull in the Sales table.

## Tried and ruled out
- An Antigravity custom agent with a `tools` list: its docs say an unknown tool name can hang the subagent and MCP tool naming there is undocumented, so Antigravity gets an always-on rule instead.
- Letting the CLI run its own agent loop with the PBIBrain MCP server: the per-answer limits would not apply.

## Watch out
- Measures read columns through REFERENCES, not DEPENDS_ON (that is measure to measure); a dependency walk on DEPENDS_ON alone misses every column.
- Antigravity's stream ends with `{"event":"result","result":{"status","response","error"}}`, not a string `result`; Copilot reads a piped prompt only without `-p`.
- The sample project has a "Gross Margin %" measure; pick another name for NOT_FOUND tests.

In the code: backend/api/dependencies.py, backend/agent_rules.py, backend/agent_setup.py, backend/chat/cli_providers.py, backend/chat/service.py (_grounding), backend/tool_registry.py (brain_dependencies), backend/mcp_snapshot.py (SNAPSHOT_GET_ROUTES), tests/test_graph_grounding.py, tests/test_agent_guardrails.py.
