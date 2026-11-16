---
title: Editor hooks are the agent boundary; agents change the model only as checked proposals
author: Claude
date: 2026-11-16
branch: claude/charming-dirac-kg461o
cost: { minutes: 42, tokens: 577169 }
id: l-380d4852
scope: repo
status: active
src: agent
touches:
  - README.md
  - backend/chat/cli_providers.py
  - docs/AGENT_GUIDE.md
  - docs/SECURITY_BOUNDARIES.md
  - tests/test_agent_guardrails.py
  - backend/agent.py
  - backend/agent_rules.py
  - backend/agent_setup.py
  - backend/api/app.py
  - backend/api/dependencies.py
---

## Decided
- The boundary for editor agents (Claude Code, Copilot, Codex, Antigravity) is a pre-tool hook the editor runs and obeys, not instructions: PBIBrain MCP tools are approved without a prompt, a short list of harmless editor tools is allowed, everything else (files, shell, web, subagents, other MCP servers) is denied with a pointer to the PBIBrain tool to use. The user asked for this because agents skip AGENTS.md-style rules. Errors fail closed; the user (not the agent) can switch it off in .pbibrain/agent-policy.json.
- Inside the app nothing is refused that the user may want: agents propose merge choices and edits to measures, columns, tables, DAX functions, calculation items, shared M and partition M. The user accepts or rejects; accept/apply stay JS-API only (ADR 0003).
- Every object edit gets advisory change rules (result type change, function signature/result, dropped source column, shared query users, calc item without SELECTEDMEASURE). A "breaks" rule forces needs_review; rules never refuse. Only clear syntax errors refuse (DAX parse, broken M brackets/text, let without in).
- proposal_check is a READ POST dry run of proposal_submit; brain_guide is static authoring notes (no route, no scan).

## Tried and ruled out
- Antigravity --mode plan for the chat CLI: it waits for a plan review and never answers headless.
- Feeding a whole UDF text to the DAX lexer: it fails on "(x : T) =>", so the compiler translates only the body and keeps the signature as written.
- Calling the dry-run's failure key "error": the test harness and clients read any "error" key as the error shape; it is "refusal".

## Watch out
- Hooks that time out fail open in every editor; keep the hook stdlib-only and fast.
- Codex runs project hooks only after the user trusts them (/hooks); Codex web search cannot be hooked, so agent-setup sets web_search = "disabled".
- VS Code reads .claude/settings.json hooks too, workspace-wide.
- The DAX type inference is coarse: unknown means no rule, so absence of a rule is not proof of safety.

In the code: backend/agent_hook.py, backend/agent_setup.py, backend/devcenter/session/change_rules.py, backend/devcenter/session/proposals.py (proposal_check, _change_rules), backend/devcenter/plan/compiler.py (EDITABLE_PROPERTIES, M_KINDS, FUNCTION_SIGNATURE), ModelWriter.cs ApplyRewriteExpression partition case, backend/agent_knowledge.py.
