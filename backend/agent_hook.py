"""The PBIBrain workspace boundary: a pre-tool hook for Claude Code, GitHub Copilot (VS Code,
Copilot CLI), Codex and Antigravity.

``brain agent-setup`` registers this script in each editor's hook file of the Power BI project
folder. The editor runs it before every tool call of its agent and obeys the answer, so the
boundary does not depend on the model reading or following instructions:

- A **PBIBrain tool** (the ``pbibrain`` MCP server: reads, the dry-run check, proposals) is
  approved without a prompt. Everything an agent may do to the model goes through these tools,
  and every change they make is a proposal the user accepts or rejects in PBIBrain.
- A **harmless editor tool** (a to-do list, asking the user a question, loading tool schemas) is
  allowed.
- **Everything else is denied**: reading, searching or editing files, terminal commands, web
  access, subagents and other MCP servers. The deny reason tells the agent which PBIBrain tool to
  use instead, so it goes back to the graph in one step instead of trying another way around.

The same script also answers each client's session-start hook (``--event session``): it puts the
grounding rules that ``agent-setup`` saved in ``.pbibrain/agent-context.md`` into the agent's
context, so the rules arrive with every new session and do not depend on the agent opening an
instructions file.

An error inside the hook denies the call (fail closed). The user can switch the boundary off for a
while with ``.pbibrain/agent-policy.json`` = ``{"mode": "off"}``; an agent cannot, because it
cannot write files here. Each decision is appended to ``.pbibrain/agent-hook.log``.

The script uses the standard library only and imports nothing from PBIBrain, so it starts fast
and runs as ``python agent_hook.py`` as well as ``PBIBrain-Agent.exe agent-hook``. Editors treat a
hook that times out as "no decision" (fail open), so speed matters.

Vendor contracts (checked 2026-11-16):

- Claude Code and Codex: stdin ``{hook_event_name, tool_name, tool_input}``; allow with
  ``hookSpecificOutput.permissionDecision``; deny with exit code 2 and the reason on stderr.
  ``PermissionRequest`` answers ``hookSpecificOutput.decision.behavior``.
- Copilot (``.github/hooks``, camelCase ``preToolUse``): stdin ``{toolName, toolArgs}``; stdout
  ``{permissionDecision, permissionDecisionReason}``; exit code 2 also denies.
- Antigravity (``.agents/hooks.json``): stdin ``{toolCall: {name, args}}``; stdout
  ``{decision: auto_approve | deny, reason}``.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

# Every tool of the pbibrain MCP server (backend/tool_registry.py; a test keeps the lists equal).
PBIBRAIN_TOOLS = frozenset({
    "brain_dependencies", "brain_overview", "brain_search", "brain_object", "brain_context", "brain_graph",
    "brain_impact", "brain_compare", "brain_commonality", "brain_pending_changes", "brain_guide",
    "session_get", "compare_rows_list", "impact_get", "naming_rules_get", "name_propose", "proposal_check",
    "proposal_submit", "question_ask", "plan_validate",
})

# Editor tools with no reach outside the conversation, by the names each vendor uses.
HARMLESS_TOOLS = frozenset({
    # Claude Code
    "TodoWrite", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet", "AskUserQuestion", "ExitPlanMode", "EnterPlanMode",
    "ToolSearch", "ListMcpResourcesTool",
    # Copilot
    "update_todo", "ask_user", "report_intent", "think", "tool_search",
    # Codex
    "update_plan", "request_user_input",
    # Antigravity
    "ask_question", "list_permissions",
})

SERVER = "pbibrain"
LOG_LIMIT = 1_000_000

GUIDANCE = (
    "This Power BI project is answered and changed through PBIBrain only; files, terminal, web, subagents and "
    "other servers are switched off here by the project's hook. Use the pbibrain tools: brain_dependencies "
    "(what X depends on, what uses X, where it is shown), brain_search and brain_object (find and read objects, "
    "formulas included), brain_impact (what a change breaks), brain_guide (DAX, M and function syntax and rules). "
    "To change the model: session_get, then proposal_check, then proposal_submit; the user accepts or rejects "
    "each proposal in PBIBrain."
)


def _pbibrain_tool(name: str) -> bool:
    """``mcp__pbibrain__brain_search``, ``pbibrain-brain_search``, ``pbibrain/brain_search`` and the like."""

    lowered = name.lower()
    head, found, rest = lowered.partition(SERVER)
    if not found or (head and not re.fullmatch(r"(mcp)?[_\-/.:]*", head)):
        return False
    return rest.lstrip("_-/.:") in PBIBRAIN_TOOLS


def classify(name: str, args: Any) -> tuple[str, str]:
    """(allow_pbibrain | allow | deny, reason)."""

    if _pbibrain_tool(name):
        return "allow_pbibrain", "PBIBrain tool"
    if name in HARMLESS_TOOLS:
        return "allow", "editor tool with no outside reach"
    if name == "ReadMcpResourceTool" and isinstance(args, dict) and str(args.get("server", "")).lower() == SERVER:
        return "allow_pbibrain", "PBIBrain resource"
    return "deny", f"Blocked by the PBIBrain boundary: {name or 'this tool'} is not available in this project. {GUIDANCE}"


# Input ---------------------------------------------------------------------------------------


def read_call(payload: dict[str, Any]) -> tuple[str, Any, str]:
    """(tool name, arguments, event) from any of the four payload shapes."""

    call = payload.get("toolCall")
    if isinstance(call, dict):
        return str(call.get("name") or ""), call.get("args"), "PreToolUse"
    if "toolName" in payload:
        args = payload.get("toolArgs")
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except ValueError:
                pass
        return str(payload.get("toolName") or ""), args, "preToolUse"
    return str(payload.get("tool_name") or ""), payload.get("tool_input"), str(payload.get("hook_event_name") or "PreToolUse")


# Output --------------------------------------------------------------------------------------


def answer(client: str, event: str, decision: str, reason: str) -> tuple[str, str, int]:
    """(stdout, stderr, exit code) in the client's format."""

    allowed = decision != "deny"
    if client == "antigravity":
        value = "auto_approve" if decision == "allow_pbibrain" else ("allow" if allowed else "deny")
        return json.dumps({"decision": value, "reason": reason}), "", 0
    if client == "copilot":
        body = {"permissionDecision": "allow" if allowed else "deny", "permissionDecisionReason": reason}
        return json.dumps(body), ("" if allowed else reason), 0 if allowed else 2
    # Claude Code and Codex (the same hook contract).
    if event == "PermissionRequest":
        behavior = {"behavior": "allow"} if allowed else {"behavior": "deny", "message": reason}
        return json.dumps({"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": behavior}}), "", 0
    if not allowed:
        # Exit 2 denies in Claude Code, Codex and Copilot alike; the reason goes to the model on stderr.
        # Copilot also reads .claude/settings.json, so it gets its own JSON shape on stdout.
        return json.dumps({"permissionDecision": "deny", "permissionDecisionReason": reason}), reason, 2
    if client == "codex":
        return "", "", 0  # no objection; Codex approves the pbibrain server by its config (default_tools_approval_mode)
    output = {"hookEventName": "PreToolUse", "permissionDecision": "allow", "permissionDecisionReason": reason}
    return json.dumps({"hookSpecificOutput": output}), "", 0


# Policy and log ------------------------------------------------------------------------------


def policy_mode(project: Path | None) -> str:
    if project is None:
        return "strict"
    try:
        data = json.loads((project / ".pbibrain" / "agent-policy.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "strict"
    return "off" if isinstance(data, dict) and data.get("mode") == "off" else "strict"


def log(project: Path | None, record: dict[str, Any]) -> None:
    if project is None:
        return
    path = project / ".pbibrain" / "agent-hook.log"
    try:
        if path.exists() and path.stat().st_size > LOG_LIMIT:
            os.replace(path, path.with_suffix(".log.1"))
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


def decide(client: str, payload: dict[str, Any], project: Path | None) -> tuple[str, str, int]:
    name, args, event = read_call(payload)
    if policy_mode(project) == "off":
        decision, reason = "allow", "PBIBrain boundary switched off in .pbibrain/agent-policy.json"
        if _pbibrain_tool(name):
            decision = "allow_pbibrain"
    else:
        decision, reason = classify(name, args)
    log(project, {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "client": client, "event": event, "tool": name[:200],
                  "decision": "deny" if decision == "deny" else "allow"})
    return answer(client, event, decision, reason)


CONTEXT_LIMIT = 20_000


def session_context(client: str, project: Path | None) -> str:
    """The client's session-start output: the saved grounding rules as added context."""

    text = ""
    if project is not None:
        try:
            text = (project / ".pbibrain" / "agent-context.md").read_text(encoding="utf-8")[:CONTEXT_LIMIT]
        except OSError:
            text = ""
    text = text or GUIDANCE
    if client == "antigravity":
        return json.dumps({"injectSteps": [{"systemMessage": {"systemMessage": text, "metadata": {"source": "pbibrain"}}}]})
    if client == "copilot":
        return json.dumps({"additionalContext": text})
    return json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}})


def _arguments(argv: list[str]) -> tuple[str, Path | None, str]:
    client, project, event = "claude", None, "tool"
    items = iter(argv)
    for item in items:
        if item == "--client":
            client = next(items, client)
        elif item == "--project":
            value = next(items, "")
            project = Path(value) if value else None
        elif item == "--event":
            event = next(items, event)
    return client, project, event


def main(argv: list[str] | None = None) -> int:
    client, project, event = _arguments(list(sys.argv[1:] if argv is None else argv))
    if event == "session":
        try:
            sys.stdin.buffer.read()
        except OSError:
            pass
        sys.stdout.write(session_context(client, project) + "\n")
        sys.stdout.flush()
        return 0
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", "replace")
        payload = json.loads(raw or "{}")
        if not isinstance(payload, dict):
            raise ValueError("the hook input is not a JSON object")
        out, err, code = decide(client, payload, project)
    except Exception as exc:  # fail closed: an error denies the call
        reason = f"Blocked by the PBIBrain boundary: the hook could not read the call ({exc}). {GUIDANCE}"
        out, err, code = answer(client, "PreToolUse", "deny", reason)
        if client == "antigravity":
            code = 0
    if out:
        sys.stdout.write(out + "\n")
    if err:
        sys.stderr.write(err + "\n")
    sys.stdout.flush()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
