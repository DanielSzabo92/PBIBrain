"""One safety assessment for every change to project sources (issue #17).

The same function judges three kinds of change:

- an agent edit in a guarded candidate copy (change guard, with or without a container),
- a Development Center apply (the merge guard),
- a file that changed outside the app (the file watcher, ``brain_pending_changes``).

It compares the graph before and after the change, object by object, and says:

- ``changes``: objects created, deleted, renamed, or changed;
- ``breaks``: objects that are still there but used an object that is now deleted, or that
  still use the old name of a renamed object;
- ``needs``: created or changed DAX that refers to a measure, column or table the model does
  not have.

Graphs are plain ``{"nodes": [...], "edges": [...]}`` mappings: the snapshot analysis graph
of the guard and the agent snapshot graph of the project use the same node shape.
"""

from __future__ import annotations

import json
import re
from typing import Any
from collections.abc import Iterable, Mapping

from backend.impact.analyzer import CONSUMER_EDGES

SAFETY_VERSION = 1

# Objects a person or an agent edits. Inferred nodes (business concepts, conflicts) are not.
TRACKED_TYPES = frozenset({
    "MODEL", "TABLE", "COLUMN", "MEASURE", "RELATIONSHIP", "CALCULATION_GROUP", "CALCULATION_ITEM", "HIERARCHY", "LEVEL",
    "PARTITION", "SHARED_EXPRESSION", "USER_DEFINED_FUNCTION", "FIELD_PARAMETER", "SECURITY_ROLE", "ROLE_FILTER",
    "OLS_PERMISSION", "REPORT", "PAGE", "VISUAL", "REPORT_MEASURE", "VISUAL_CALCULATION", "BOOKMARK", "PAGE_FILTER",
    "REPORT_FILTER", "VISUAL_FILTER",
})
# Edges whose source object stops working when the target goes away.
BREAK_EDGES = frozenset(CONSUMER_EDGES | {"RELATES_TO", "FORMATS_BY", "DRILLS_THROUGH_TO", "TOOLTIP_PAGE"})
# Properties that change with every parse, not with the object (``dax_*`` parser output too).
_VOLATILE = frozenset({"dax_ast", "dax_behaviors", "dax_evidence", "raw_source", "raw_metadata", "ast_location",
                       "source_fingerprint", "source_location", "evidence", "review_status"})
_DAX_TYPES = frozenset({"MEASURE", "COLUMN", "TABLE", "CALCULATION_ITEM", "USER_DEFINED_FUNCTION", "ROLE_FILTER",
                        "REPORT_MEASURE", "VISUAL_CALCULATION"})
# 'Table'[Name], Table[Name] or [Name]; strings and comments are removed first.
_REFERENCE = re.compile(r"(?:'((?:[^']|'')+)'|([A-Za-z_][A-Za-z0-9_.]*))?\[([^\[\]]+)\]")
_STRIP = re.compile(r'"(?:[^"]|"")*"|//[^\n]*|--[^\n]*|/\*.*?\*/', re.S)
MAX_LISTED = 200


def _nodes(graph: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in (graph or {}).get("nodes", []) if isinstance(item, Mapping) and item.get("id")}


def _edges(graph: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    return [item for item in (graph or {}).get("edges", []) if isinstance(item, Mapping)]


def _props(node: Mapping[str, Any]) -> dict[str, Any]:
    return dict(node.get("properties") or {})


def _fingerprint(node: Mapping[str, Any]) -> Any:
    return (node.get("type"), node.get("name"), node.get("description"),
            sorted((key, json.dumps(value, sort_keys=True, default=str)) for key, value in _props(node).items() if key not in _VOLATILE and not key.startswith("dax_")))


def _label(node: Mapping[str, Any], nodes: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    props = _props(node)
    table = nodes.get(props.get("table_id") or "", {})
    item = {"object_id": node["id"], "object_type": node.get("type"), "name": node.get("name") or ""}
    if table.get("name"):
        item["table"] = table["name"]
    for key in ("model_id", "report_id"):
        if node.get(key):
            item[key] = node[key]
    return item


def object_changes(before: Mapping[str, Any] | None, after: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """Objects created, deleted, renamed or changed between two graphs.

    Node IDs come from lineage tags where the source has them, so a rename keeps its ID and
    shows as ``renamed`` with ``old_name``. Without a lineage tag a rename is a delete and a create.
    """

    old, new = _nodes(before), _nodes(after)
    changes = []
    for object_id in sorted(set(old) | set(new)):
        a, b = old.get(object_id), new.get(object_id)
        node = b or a
        if node.get("type") not in TRACKED_TYPES:
            continue
        if a is None:
            changes.append({**_label(b, new), "change": "created"})
        elif b is None:
            changes.append({**_label(a, old), "change": "deleted"})
        elif (a.get("name") or "") != (b.get("name") or ""):
            changes.append({**_label(b, new), "change": "renamed", "old_name": a.get("name") or ""})
        elif _fingerprint(a) != _fingerprint(b):
            changes.append({**_label(b, new), "change": "changed"})
    return changes


def find_breaks(before: Mapping[str, Any] | None, after: Mapping[str, Any] | None,
                changes: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Objects that remain but used a deleted object, or still use the old name of a renamed one."""

    old, new = _nodes(before), _nodes(after)
    changes = list(changes)
    deleted = {item["object_id"] for item in changes if item["change"] == "deleted"}
    renamed = {item["object_id"]: item for item in changes if item["change"] == "renamed"}
    resolved = {(edge.get("from_id"), edge.get("to_id")) for edge in _edges(after) if edge.get("type") in BREAK_EDGES}
    found: dict[tuple[str, str], dict[str, Any]] = {}
    for edge in _edges(before):
        if edge.get("type") not in BREAK_EDGES:
            continue
        user, used = edge.get("from_id"), edge.get("to_id")
        if user in deleted or user not in new or user == used:
            continue  # removed together, or not there any more
        if used in deleted:
            reason = "uses_deleted"
        elif used in renamed and (user, used) not in resolved:
            reason = "uses_old_name"
        else:
            continue
        key = (user, used)
        if key in found:
            continue
        target = old[used]
        item = {**_label(new[user], new), "reason": reason, "uses": {**_label(target, old)}, "edge_type": edge.get("type")}
        if reason == "uses_old_name":
            item["uses"]["new_name"] = renamed[used].get("name")
        found[key] = item
    return sorted(found.values(), key=lambda item: (item["object_type"] or "", item["name"], item["uses"]["name"]))


def _dax_references(expression: str) -> list[tuple[str | None, str]]:
    text = _STRIP.sub(" ", expression)
    return [((match[1].replace("''", "'") if match[1] is not None else match[2]), match[3].strip()) for match in _REFERENCE.finditer(text)]


def find_needs(after: Mapping[str, Any] | None, changes: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Created or changed DAX that names a measure, column or table its model does not have."""

    new = _nodes(after)
    by_model: dict[Any, dict[str, Any]] = {}
    for node in new.values():
        model = by_model.setdefault(node.get("model_id"), {"tables": {}, "measures": set(), "columns": set()})
        kind, name = node.get("type"), (node.get("name") or "").casefold()
        if kind == "TABLE":
            model["tables"].setdefault(name, set())
        elif kind == "MEASURE":
            model["measures"].add(name)
    for node in new.values():
        if node.get("type") == "COLUMN":
            model = by_model.setdefault(node.get("model_id"), {"tables": {}, "measures": set(), "columns": set()})
            table = new.get(_props(node).get("table_id") or "", {})
            name = (node.get("name") or "").casefold()
            model["columns"].add(name)
            model["tables"].setdefault((table.get("name") or "").casefold(), set()).add(name)
    needs = []
    for change in changes:
        if change["change"] not in {"created", "changed", "renamed"} or change.get("object_type") not in _DAX_TYPES:
            continue
        node = new.get(change["object_id"])
        expression = _props(node or {}).get("expression")
        if not isinstance(expression, str) or not node or not node.get("model_id"):
            continue  # report-level objects are bound by field, not by DAX text
        model = by_model.get(node.get("model_id"), {"tables": {}, "measures": set(), "columns": set()})
        missing = []
        for table, name in _dax_references(expression):
            folded = name.casefold()
            if table is None:
                if folded not in model["measures"] and folded not in model["columns"]:
                    missing.append({"kind": "measure_or_column", "name": name})
            elif table.casefold() not in model["tables"]:
                missing.append({"kind": "table", "name": table})
            elif folded not in model["tables"][table.casefold()] and folded not in model["measures"]:
                missing.append({"kind": "column", "table": table, "name": name})
        unique = []
        for item in missing:
            if item not in unique:
                unique.append(item)
        if unique:
            needs.append({**_label(node, new), "missing": unique})
    return needs


def assess_change(before: Mapping[str, Any] | None, after: Mapping[str, Any] | None) -> dict[str, Any]:
    """The shared safety report: changes, breaks and needs, with exact counts and bounded lists."""

    changes = object_changes(before, after)
    breaks = find_breaks(before, after, changes)
    needs = find_needs(after, changes)
    counts: dict[str, int] = {}
    for item in changes:
        counts[item["change"]] = counts.get(item["change"], 0) + 1
    return {
        "safety_version": SAFETY_VERSION,
        "status": "BREAKS" if breaks else "NEEDS" if needs else "CHANGED" if changes else "UNCHANGED",
        "summary": {"changes": len(changes), **counts, "breaks": len(breaks), "needs": len(needs)},
        "changes": changes[:MAX_LISTED],
        "breaks": breaks[:MAX_LISTED],
        "needs": needs[:MAX_LISTED],
        "truncated": any(len(values) > MAX_LISTED for values in (changes, breaks, needs)),
    }
