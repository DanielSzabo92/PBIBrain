---
title: "Chat providers keep one profile each, favourites narrow the chat's model picker, and effort is checked against the model before it reaches any provider"
author: Claude
date: 2026-11-16
branch: claude/charming-dirac-kg461o
cost: { minutes: 19, tokens: 318574 }
id: l-f30dd0da
scope: repo
status: active
src: agent
touches:
  - README.md
  - backend/adapters/tabular_metadata/dotnet/ModelWriter.cs
  - backend/agent.py
  - backend/agent_hook.py
  - backend/agent_knowledge.py
  - backend/agent_rules.py
  - backend/agent_setup.py
  - backend/cli/main.py
  - backend/devcenter/agent_tools.py
  - backend/devcenter/contracts/agent.json
---

## Decided
- Each chat provider keeps its own profile (model, URL or program, default effort). The one saved last is the default. The chat picks provider, model and effort per message, but only from providers the user saved once. A provider never set up is refused, so an unexpected network destination is never opened.
- Favourites ({model, effort} per provider, at most 50) narrow the chat's model picker. With none, the picker shows the provider's whole list. A favourite's effort beats the profile's effort for the same model.
- Effort is a whitelist per provider and model (backend/chat/models.py). It is validated on save and on every chat start before it becomes an API field or a CLI argument. An empty effort sends nothing, so the provider or the user's own CLI config decides. A shell CLAUDE_CODE_EFFORT_LEVEL stays in force when no effort is picked.
- Effort mapping: Anthropic output_config.effort; OpenAI-compatible reasoning_effort (o-series and gpt-5 only); Claude Code --effort plus CLAUDE_CODE_EFFORT_LEVEL (the variable wins over the flag, so both are set); Codex -c model_reasoning_effort="x"; Copilot --reasoning-effort=x. Antigravity and local endpoints take none.

## Tried and ruled out
- Listing models of the subscription CLIs: none of claude, codex, copilot or agy has a documented headless list command. Claude Code gets a built-in catalog; the others offer only "Default of your plan" and the user adds names as favourites.
- Spaces in model names: allowed only for Antigravity, whose model names carry the effort ("Gemini 3.1 Pro (High)").

## Watch out
- The live list (GET /api/chat/models) is cached for 10 minutes per provider, URL and key presence. It falls back to the catalog with an error string when the SDK is missing or the call fails.
- The Anthropic catalog in models.py was cached on 2026-11-03. Update it when new models ship. Unknown ids get efforts by name pattern.

In the code: backend/chat/models.py, backend/chat/settings.py (ChatSettings.selection, save, _clean_favourites), backend/chat/cli_providers.py (effort flags), frontend/src/chat.js (pickerModels, pickerProvider), tests/test_chat_models.py, frontend/test/chatPickers.test.js.
