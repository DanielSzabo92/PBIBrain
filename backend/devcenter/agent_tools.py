"""The eight agent tools of the "PBIBrain" MCP server (technical design section 12, build step S10).

Each tool maps to exactly one HTTP route of ``TOOL_ROUTES``. That table is the
fixed endpoint allowlist of the MCP adapter: it holds only read routes and the
two proposal routes. No tool can call an accepted-state write or Apply,
because these exist only in the pywebview JS API (ADR 0003).

The tools act only on the session that is open in the app. A tool gives the
reply of the route, or the error shape ``{error: {code, message, details}}``.
"""

# No "from __future__ import annotations": FastMCP reads the real annotation types to find the Context parameter.

from typing import Any
from collections.abc import Callable, Mapping

# Tool name -> (HTTP method, path below /api/devcenter/). Do not add a route that changes accepted state.
TOOL_ROUTES: dict[str, tuple[str, str]] = {
    "session_get": ("GET", "session"),
    "compare_rows_list": ("GET", "compare-rows"),
    "impact_get": ("GET", "impact"),
    "naming_rules_get": ("GET", "naming-rules"),
    "name_propose": ("POST", "name-propose"),
    "proposal_submit": ("POST", "proposals"),
    "question_ask": ("POST", "questions"),
    "plan_validate": ("POST", "plan-validate"),
}

# send(method, path, query, body) -> reply or error shape.
Send = Callable[[str, str, Mapping[str, Any] | None, Mapping[str, Any] | None], dict[str, Any]]

DEFAULT_CLIENT = "MCP client"


def _query(**values: Any) -> dict[str, Any]:
    result = {}
    for key, value in values.items():
        if value is None:
            continue
        result[key] = ("true" if value else "false") if isinstance(value, bool) else value
    return result


class AgentTools:
    """The tool bodies. ``send`` is the transport (HTTP in the MCP server, in-process in the tests)."""

    def __init__(self, send: Send) -> None:
        self._send = send

    def _call(self, tool: str, query: Mapping[str, Any] | None = None, body: Mapping[str, Any] | None = None) -> dict[str, Any]:
        method, path = TOOL_ROUTES[tool]
        return self._send(method, path, query if method == "GET" else None, body if method == "POST" else None)

    def session_get(self) -> dict[str, Any]:
        return self._call("session_get")

    def compare_rows_list(self, *, type: str | None = None, table: str | None = None, state: str | None = None,
                          source: str | None = None, changed: bool | None = None, marks: bool | None = None,
                          q: str | None = None, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        return self._call("compare_rows_list", _query(type=type, table=table, state=state, source=source, changed=changed,
                                                      marks=marks, q=q, limit=limit, offset=offset))

    def impact_get(self, *, target: str = "plan", include_proposals: bool | str = True, direction: str | None = None,
                   blocking: bool | None = None, severity: str | None = None, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        return self._call("impact_get", _query(target=target, include_proposals=include_proposals, direction=direction,
                                               blocking=blocking, severity=severity, limit=limit, offset=offset))

    def naming_rules_get(self) -> dict[str, Any]:
        return self._call("naming_rules_get")

    def name_propose(self, *, name: str, object_type: str, table: str | None = None, display_folder: str | None = None,
                     source_id: str | None = None, candidate: str | None = None) -> dict[str, Any]:
        body = {"name": name, "object_type": object_type, "table": table, "display_folder": display_folder, "source_id": source_id}
        if candidate is not None:
            body["candidate"] = candidate
        return self._call("name_propose", body=body)

    def proposal_submit(self, *, kind: str, target: str, payload: Mapping[str, Any], confidence: float, reason: str,
                        base_revision: int, target_name: str | None = None, client: str | None = None) -> dict[str, Any]:
        body = {"kind": kind, "target": target, "payload": dict(payload), "confidence": confidence, "reason": reason,
                "base_revision": base_revision, "mcp_client": client or DEFAULT_CLIENT}
        if target_name:
            body["target_name"] = target_name
        return self._call("proposal_submit", body=body)

    def question_ask(self, *, target: str, text: str, options: list[Mapping[str, Any]], recommended_option: str, reason: str,
                     base_revision: int, target_name: str | None = None, client: str | None = None) -> dict[str, Any]:
        body = {"target": target, "text": text, "options": [dict(item) for item in options], "recommended_option": recommended_option,
                "reason": reason, "base_revision": base_revision, "mcp_client": client or DEFAULT_CLIENT}
        if target_name:
            body["target_name"] = target_name
        return self._call("question_ask", body=body)

    def plan_validate(self, *, mode: str = "quick", include_proposals: bool | str = True) -> dict[str, Any]:
        return self._call("plan_validate", body={"mode": mode, "include_proposals": include_proposals})


def client_name(ctx: Any) -> str:
    """The name that the MCP client gave at the start of the MCP session."""

    try:
        name = ctx.session.client_params.clientInfo.name
    except AttributeError:
        return DEFAULT_CLIENT
    text = str(name or "").strip()[:100]
    return text or DEFAULT_CLIENT


# The MCP server and the in-app chat expose these tools from one registry: backend/tool_registry.py.
