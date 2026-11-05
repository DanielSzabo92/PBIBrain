---
title: "Agent tool modules must not use postponed annotations, and the session proposal schema keeps the payload loose"
author: Daniel
date: 2026-11-05
branch: dc/21-s10-agent-mcp-tools
cost: { minutes: 1, tokens: 1648 }
id: l-a6f588ed
scope: repo
status: active
touches:
  - backend/devcenter/agent_tools.py
  - backend/devcenter/contracts/agent.json
---

## Decided
- The module with the FastMCP agent tools does not use postponed annotations. FastMCP reads the real annotation types to find the Context parameter. With postponed annotations, the tool registration fails with "issubclass() arg 1 must be a class".
- The proposal item of the GET session reply keeps "payload" as a free object. Only the proposal submit request checks the payload for each kind. The UI mock fixtures use a different merge-choice payload shape, and a strict view schema breaks the UI contract tests.

## Tried and ruled out
- A strict payload check (by kind) in the proposal view schema: 12 UI contract tests failed on the mock fixtures.

## Watch out
- The other failures of that run were test faults (a revision that moved while the test filled a dict, a wrong count). They were not code faults.

In the code:
- backend/devcenter/agent_tools.py: no "from __future__ import annotations"; tools take "ctx: Context".
- backend/devcenter/contracts/agent.json: "$defs/proposal" has no allOf on "payload"; http/proposals.request.json has the per-kind allOf.
- tests/fixtures/devcenter_ui/*/session.json use the payload choice "take_from" with the key "source".
