---
title: "Subscription chat providers drive the vendor CLI as a text model with its own tools off, and PBIBrain runs every tool call under fixed run limits"
author: Claude
date: 2026-11-15
branch: claude/charming-dirac-kg461o
cost: { minutes: 11, tokens: 247518 }
id: l-0e72dd00
scope: repo
status: active
src: agent
touches:
  - backend/process_guard.py
  - backend/chat/cli_providers.py
  - tests/test_agent_guardrails.py
  - frontend/test/aiSettingsSubscription.test.js
  - backend/chat/service.py
  - backend/devcenter/session/proposals.py
---

## Decided
- The Claude, GitHub Copilot (VS Code plan) and Antigravity subscriptions are chat providers that start the vendor's signed-in CLI (`claude`, `copilot`, `agy`) as a plain text model. The CLI's own tools are turned off by flags; the model asks for PBIBrain tools with `<tool_call>{json}</tool_call>` blocks and the chat service runs them through the same registry, `TOOL_ROUTES` allowlist and run limits as API providers. This keeps every guardrail in PBIBrain whatever each CLI's permission flags really do.
- The CLI runs in a new empty temp folder (never the project), with API keys/tokens scrubbed from its environment except the one sign-in variable its vendor documents (so `ANTHROPIC_API_KEY` is dropped and Claude bills the plan). The prompt goes on stdin; argv holds only fixed flags and a regex-checked model name.
- Run limits per chat answer (8 calls per turn, 40 per answer, 10 proposals/questions, same call twice, 20k chars of args, 10 min) live in the chat service; a server-side cap of 200 open agent proposals / 20 open questions per merge session covers MCP clients too, reusing `action_not_allowed` with a reason (no new error code).
- One helper, `run_bounded`, starts every outside program (guard local tier and CLIs): own process group, kill the group on timeout/Stop/output cap.

## Tried and ruled out
- Giving the CLI the PBIBrain MCP server and letting it run its own agent loop: our per-answer limits would not apply, and Copilot/Antigravity have no reliable per-run allowlist flag.
- Passing the prompt as an argument: on Windows the npm `.cmd` shims go through cmd.exe, which cuts at the first newline and treats `"`/`&` in project text as syntax.

## Watch out
- The vendor flags could not be checked against live docs from the build session (docs.github.com and antigravity.google were blocked): Copilot uses piped stdin without `-p` plus `--deny-tool shell/write/url`; agy uses `--input-format stream-json --output-format stream-json --mode plan` with `{"event":"user","message":{"content":...}}`. Test connection sends a multi-line probe; fix the preset when a CLI version changes.
- The CLI provider prompt mentions `<tool_result>` in its instructions, so a fake CLI must look for `<tool_result id=` to detect results.

In the code: backend/chat/cli_providers.py (PRESETS, render_prompt, parse_reply, SubscriptionCLIProvider), backend/process_guard.py, backend/chat/service.py (MAX_* limits, ChatRun.should_stop), backend/devcenter/session/proposals.py (MAX_OPEN_AGENT_*), tests/test_agent_guardrails.py.
