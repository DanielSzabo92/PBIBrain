"""The one tool registry shared by the MCP server and the in-app chat (issue #7).

``build_tools`` returns the 17 tools as plain Python functions: their names, docstrings and
annotated signatures are the tool contract. ``backend/mcp_server.py`` adds each one to the
FastMCP server; ``backend/chat`` calls the same functions in process and derives the JSON
schema it sends to the AI provider from the same signatures (``tool_schema``). The two
surfaces therefore cannot drift apart.

Each tool reaches PBIBrain through a ``client`` with ``get``, ``post``, ``devcenter`` and
``freshness``. The Merge models tools go through ``client.devcenter``, which allows only the
read routes and the proposal routes of ``TOOL_ROUTES``. No tool can accept or apply (ADR 0003).
"""

# No "from __future__ import annotations": FastMCP and tool_schema read the real annotation types.

import inspect
import typing
from typing import Any, Callable
from urllib.parse import quote

from backend.devcenter.agent_tools import DEFAULT_CLIENT, AgentTools
from backend.mcp_budget import META_RESERVE, budget_for, fit_reply, size

Tool = Callable[..., dict[str, Any]]


def brain_tools(client: Any, freshness: Callable[[], dict[str, Any]]) -> list[Tool]:
    """The nine read-only project tools. Every reply is cut to its budget (``TOOL_BUDGETS``)."""

    def reply(tool: str, detail: str, call: Any) -> dict[str, Any]:
        budget_for(tool, detail)  # refuse an unknown detail before any work
        payload = call()
        return fit_reply(payload, tool=tool, detail=detail, meta={"freshness": freshness()})

    def brain_overview(detail: str = "compact") -> dict[str, Any]:
        """List project model/report IDs, object counts, and known scan status. detail: compact|full."""
        return reply("brain_overview", detail, lambda: client.get("overview"))

    def brain_search(query: str, model_id: str | None = None, report_id: str | None = None,
                     object_type: str | None = None, limit: int = 20, offset: int = 0,
                     detail: str = "compact") -> dict[str, Any]:
        """Rank objects with exact matching evidence. Page all results (next_offset) before claiming completeness."""
        return reply("brain_search", detail, lambda: client.get(
            "search", q=query, model_id=model_id, report_id=report_id, object_type=object_type, limit=limit, offset=offset))

    def brain_object(object_id: str, detail: str = "compact") -> dict[str, Any]:
        """Inspect an exact stable ID, its expression, dependencies, usage, and evidence."""
        return reply("brain_object", detail, lambda: client.get("objects/" + quote(object_id, safe="")))

    def brain_context(target: str, task: str | None = None, detail: str = "compact") -> dict[str, Any]:
        """Retrieve a task-scoped evidence package for an exact object ID."""
        return reply("brain_context", detail, lambda: client.get("context", target=target, task=task))

    def brain_graph(center_id: str, depth: int = 1, limit: int = 100,
                    model_id: str | None = None, report_id: str | None = None,
                    detail: str = "compact") -> dict[str, Any]:
        """Read a bounded neighborhood. Truncation means this is not the whole graph."""
        return reply("brain_graph", detail, lambda: client.get(
            "graph", center_id=center_id, depth=depth, limit=limit, model_id=model_id, report_id=report_id))

    def brain_impact(target_id: str, proposed_changes: list[dict[str, Any]] | None = None, include_report_usage: bool = True,
                     detail: str = "compact") -> dict[str, Any]:
        """Read conservative impact; unknown coverage never proves no effects."""
        return reply("brain_impact", detail, lambda: client.post(
            "impact", {"target_id": target_id, "proposed_changes": proposed_changes or [], "include_report_usage": include_report_usage}))

    def brain_compare(before: str, after: str, detail: str = "compact") -> dict[str, Any]:
        """Compare two previously prepared immutable snapshot IDs (app only). No paths/writes."""
        return reply("brain_compare", detail, lambda: client.post("compare", {"before": before, "after": after}))

    def brain_commonality(type: str | None = None, scope: str | None = None, bucket: str | None = None,
                          group_id: str | None = None, limit: int = 25, offset: int = 0,
                          detail: str = "compact") -> dict[str, Any]:
        """Across all models/reports: identical, differs (which properties), renamed, unique objects, and duplicate DAX logic.

        type: object type (MEASURE, COLUMN, TABLE, PAGE, VISUAL...). scope: "models", "reports" or model/report
        ids or refs (m1,r2). bucket: identical|differs|renamed|unique. Sources are referenced by ref (m1, r1).
        Compact replies stay under about 3,000 tokens; page with next_offset while has_more. group_id gives one
        group with its object IDs."""
        # The commonality route pages to fit by itself; it gets the room the reply budget leaves.
        room = budget_for("brain_commonality", detail) - META_RESERVE
        return reply("brain_commonality", detail, lambda: client.get(
            "commonality", type=type, scope=scope, bucket=bucket, group_id=group_id, limit=limit, offset=offset,
            compact="true" if detail == "compact" else "false", max_chars=room))

    def brain_pending_changes(detail: str = "compact") -> dict[str, Any]:
        """Project files changed outside PBIBrain since the last scan (by an agent, a person or another tool).

        Lists the changed files and the objects created, deleted, renamed or changed, with
        Breaks (objects that still use a deleted or renamed object) and Needs (DAX that names a
        missing measure, column or table). Check it after editing project files. Read-only;
        status UNCHANGED means the files match the last scan."""
        return reply("brain_pending_changes", detail, lambda: client.get("pending-changes"))

    return [brain_overview, brain_search, brain_object, brain_context, brain_graph, brain_impact, brain_compare,
            brain_commonality, brain_pending_changes]


def merge_tools(client: Any, client_label: Callable[[], str]) -> list[Tool]:
    """The eight Merge models (Development Center) agent tools: reads and proposals only."""

    def send(method: str, path: str, query: Any, body: Any) -> dict[str, Any]:
        payload = client.devcenter(method, path, query, body)
        # The agent tool replies have fixed schemas; only an oversized reply gets the budget block.
        return payload if size(payload) <= budget_for("devcenter") else fit_reply(payload, tool="devcenter")

    tools = AgentTools(send)

    def label() -> str:
        try:
            return client_label() or DEFAULT_CLIENT
        except Exception:  # noqa: BLE001 - a client name is only a log label
            return DEFAULT_CLIENT

    def session_get() -> dict[str, Any]:
        """Read the open merge session: revision, sources, target, plan status, open proposals and questions."""
        return tools.session_get()

    def compare_rows_list(type: str | None = None, table: str | None = None, state: str | None = None, source: str | None = None,
                          changed: bool | None = None, marks: bool | None = None, q: str | None = None,
                          limit: int = 50, offset: int = 0) -> dict[str, Any]:
        """List compare rows with filters. Read has_more and page all rows before you claim completeness."""
        return tools.compare_rows_list(type=type, table=table, state=state, source=source, changed=changed, marks=marks, q=q,
                                       limit=limit, offset=offset)

    def impact_get(target: str = "plan", include_proposals: bool = True, direction: str | None = None,
                   blocking: bool | None = None, severity: str | None = None, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        """Read impact items for the plan or one row ID. include_proposals adds the open agent proposals."""
        return tools.impact_get(target=target, include_proposals=include_proposals, direction=direction, blocking=blocking,
                                severity=severity, limit=limit, offset=offset)

    def naming_rules_get() -> dict[str, Any]:
        """Read the naming rules with status, origin, support, and break counts."""
        return tools.naming_rules_get()

    def name_propose(name: str, object_type: str, table: str | None = None, display_folder: str | None = None,
                     source_id: str | None = None, candidate: str | None = None) -> dict[str, Any]:
        """Calculate a name that obeys the confirmed naming rules. This changes nothing."""
        return tools.name_propose(name=name, object_type=object_type, table=table, display_folder=display_folder,
                                  source_id=source_id, candidate=candidate)

    def proposal_submit(kind: str, target: str, payload: dict[str, Any], confidence: float, reason: str, base_revision: int,
                        target_name: str | None = None) -> dict[str, Any]:
        """Propose a change for the user to accept. The user decides. Confidence must be 0.9 or more and the reason must not be empty.

        kind: merge_choice, alignment, removal_policy, impact_action, need_mapping, name, or the object kinds
        object_edit {set: {expression, format_string, description, display_folder, is_hidden, ...}},
        object_rename {new_name}, object_delete {}, object_create {object_type, table, name, properties}.
        An object proposal is checked on submit: the reply's proposal.check has the plan blocking items and the
        Breaks/Needs impact; a DAX error or a missing name is refused with details.reason proposal_not_valid.
        """
        return tools.proposal_submit(kind=kind, target=target, payload=payload, confidence=confidence, reason=reason,
                                     base_revision=base_revision, target_name=target_name, client=label())

    def question_ask(target: str, text: str, options: list[dict[str, Any]], recommended_option: str, reason: str,
                     base_revision: int, target_name: str | None = None) -> dict[str, Any]:
        """Ask the user a question with 2 to 5 options. Each option has id, label, and an optional proposal {kind, payload}."""
        return tools.question_ask(target=target, text=text, options=options, recommended_option=recommended_option, reason=reason,
                                  base_revision=base_revision, target_name=target_name, client=label())

    def plan_validate(mode: str = "quick", include_proposals: bool = True) -> dict[str, Any]:
        """Validate the Change Plan. mode is quick or full. include_proposals adds the open agent proposals."""
        return tools.plan_validate(mode=mode, include_proposals=include_proposals)

    return [session_get, compare_rows_list, impact_get, naming_rules_get, name_propose, proposal_submit, question_ask,
            plan_validate]


def pbi_tools(client: Any) -> list[Tool]:
    """The six typed Power BI domain tools for lineage, impact, and bindings."""

    def pbi_find_object(query: str = "", model_id: str | None = None, object_type: str | None = None,
                        name: str | None = None) -> dict[str, Any]:
        """Find Power BI objects (table, column, measure, visual, page) by query or exact name."""
        q = name if name else query
        return client.get("search", q=q, model_id=model_id, object_type=object_type)

    def pbi_lineage(object_id: str, direction: str = "both") -> dict[str, Any]:
        """Trace lineage dependencies (upstream and downstream) with exact source file spans."""
        return client.get("objects/" + quote(object_id, safe=""))

    def pbi_impact(target_id: str, include_report_usage: bool = True) -> dict[str, Any]:
        """Evaluate downstream impact on measures, columns, partitions, and visuals."""
        return client.post("impact", {"target_id": target_id, "include_report_usage": include_report_usage})

    def pbi_visual_bindings(target_id: str) -> dict[str, Any]:
        """Get model columns, measures, and roles bound to a visual or page."""
        return client.get("objects/" + quote(target_id, safe=""))

    def pbi_rls_for(table_id_or_name: str, role_name: str | None = None) -> dict[str, Any]:
        """Find Row-Level Security (RLS) filter expressions and affected tables/roles."""
        return client.get("search", q=table_id_or_name, object_type="ROLE_FILTER")

    def pbi_context(target: str, task: str | None = None) -> dict[str, Any]:
        """Retrieve task-scoped context and code spans for an exact object ID."""
        return client.get("context", target=target, task=task)

    return [pbi_find_object, pbi_lineage, pbi_impact, pbi_visual_bindings, pbi_rls_for, pbi_context]


def build_tools(client: Any, *, freshness: Callable[[], dict[str, Any]] | None = None,
                client_label: Callable[[], str] = lambda: DEFAULT_CLIENT,
                include_pbi_tools: bool = False) -> dict[str, Tool]:
    """Every tool, by name, in a fixed order (the order is part of the provider prompt cache prefix)."""

    fresh = freshness if freshness is not None else client.freshness
    tools = brain_tools(client, fresh) + merge_tools(client, client_label)
    if include_pbi_tools:
        tools.extend(pbi_tools(client))
    return {tool.__name__: tool for tool in tools}


def build_pbi_tools(client: Any) -> dict[str, Tool]:
    """Typed Power BI domain tools by name."""
    return {tool.__name__: tool for tool in pbi_tools(client)}


# JSON schema of a tool, derived from its signature ------------------------------------------

_SCALARS = {str: "string", int: "integer", float: "number", bool: "boolean"}


def _type_schema(annotation: Any) -> tuple[dict[str, Any], bool]:
    """(schema, optional) for one parameter annotation."""

    args = typing.get_args(annotation)
    if type(None) in args:  # X | None
        inner = [item for item in args if item is not type(None)]
        schema, _ = _type_schema(inner[0] if len(inner) == 1 else Any)
        return schema, True
    origin = typing.get_origin(annotation) or annotation
    if origin in _SCALARS:
        return {"type": _SCALARS[origin]}, False
    if origin is dict:
        return {"type": "object"}, False
    if origin is list:
        item = args[0] if args else Any
        return {"type": "array", "items": _type_schema(item)[0] if item is not Any else {}}, False
    return {}, False


def tool_schema(tool: Tool) -> dict[str, Any]:
    """{name, description, input_schema} for one registry tool."""

    hints = typing.get_type_hints(tool)
    properties: dict[str, Any] = {}
    required: list[str] = []
    for name, parameter in inspect.signature(tool).parameters.items():
        schema, optional = _type_schema(hints.get(name, Any))
        if parameter.default is not inspect.Parameter.empty and parameter.default is not None:
            schema = {**schema, "default": parameter.default}
        properties[name] = schema
        if parameter.default is inspect.Parameter.empty and not optional:
            required.append(name)
    description = inspect.cleandoc(tool.__doc__ or "")
    return {"name": tool.__name__, "description": description,
            "input_schema": {"type": "object", "properties": properties, "required": required, "additionalProperties": False}}
