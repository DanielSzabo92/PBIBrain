"""Read-only object payloads for the Brain Inspector."""

from __future__ import annotations

from typing import Any
from collections.abc import Mapping, Sequence

from backend.graph.repository import GraphRepository
from backend.graph.schema import Edge, Node

from .review import OverrideStore, apply_overrides_to_dict
from .retrieval import ranked_object_list


def _payload(value: Any, store: OverrideStore | None = None) -> dict[str, Any]:
    if isinstance(value, Mapping):
        result = dict(value)
    else:
        result = value.to_dict()
    return apply_overrides_to_dict(result, store)


def search_objects(
    repository: GraphRepository,
    query: str = "",
    *,
    object_type: str | Sequence[str] | None = None,
    model_id: str | None = None,
    report_id: str | None = None,
    store: OverrideStore | None = None,
) -> list[dict[str, Any]]:
    return ranked_object_list(
        repository,
        query,
        object_type=object_type,
        model_id=model_id,
        report_id=report_id,
        store=store,
    )


def get_object(
    repository: GraphRepository,
    object_id: str,
    *,
    store: OverrideStore | None = None,
) -> dict[str, Any] | None:
    value = repository.get_object(str(object_id))
    return _payload(value, store) if value is not None else None


def get_neighbors(
    repository: GraphRepository,
    object_id: str,
    edge_types: Sequence[str] | None = None,
    *,
    direction: str = "both",
    store: OverrideStore | None = None,
) -> list[dict[str, Any]]:
    return [_payload(value, store) for value in repository.get_neighbors(object_id, edge_types, direction=direction)]


def get_dependencies(
    repository: GraphRepository,
    object_id: str,
    *,
    store: OverrideStore | None = None,
) -> list[dict[str, Any]]:
    """Return expression dependencies as canonical object payloads."""

    return [_payload(value, store) for value in repository.get_dependencies(str(object_id))]


def get_dependents(
    repository: GraphRepository,
    object_id: str,
    *,
    store: OverrideStore | None = None,
) -> list[dict[str, Any]]:
    """Return objects that depend on the selected expression object."""

    return [_payload(value, store) for value in repository.get_dependents(str(object_id))]


def get_usage(
    repository: GraphRepository,
    object_id: str,
    *,
    store: OverrideStore | None = None,
) -> list[dict[str, Any]]:
    """Return report visuals and other objects using the selected object."""

    return [_payload(value, store) for value in repository.get_usage(str(object_id))]


def _edge_payload(edge: Edge, store: OverrideStore | None = None) -> dict[str, Any]:
    return _payload(edge, store)


def _semantic_records(repository: GraphRepository, object_id: str, store: OverrideStore | None) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for edge in repository.all_edges():
        if edge.from_id != str(object_id) and edge.to_id != str(object_id):
            continue
        if edge.evidence_class not in {"INFERRED", "OBSERVED"} and edge.type not in {
            "CONTROLLED_BY",
            "HAS_OPTION",
            "DEFAULTS_TO",
            "SEMANTICALLY_MAPS_TO",
            "SIMILAR_TO",
            "OBSERVED_WITH",
            "CONFLICTS_WITH",
        }:
            continue
        values.append(_edge_payload(edge, store))
        other_id = edge.to_id if edge.from_id == str(object_id) else edge.from_id
        other = repository.get_object(other_id)
        if other is not None and (other.type in {"BUSINESS_CONCEPT", "SELECTOR", "SELECTOR_OPTION", "CONFLICT", "SEMANTIC_ASSERTION"}):
            payload = other.to_dict()
            if other.properties.get("candidate_ids") and edge.properties.get("candidate_id"):
                # Render the meaning in this assertion's context, not another target's decision.
                payload["properties"] = {**other.properties, **edge.properties, "candidate_ids": []}
                payload.update(status=edge.status, confidence=edge.confidence, evidence=edge.evidence)
            values.append(_payload(payload, store))
    direct = repository.get_object(str(object_id))
    if direct is not None and not direct.properties.get("candidate_ids") and direct.type in {"BUSINESS_CONCEPT", "SELECTOR", "SELECTOR_OPTION", "CONFLICT", "SEMANTIC_ASSERTION"}:
        values.insert(0, _payload(direct, store))
    unique: dict[str, dict[str, Any]] = {}
    for value in values:
        marker = f"{value.get('id')}|{value.get('type')}|{value.get('from_id', '')}|{value.get('to_id', '')}|{value.get('properties', {}).get('candidate_id', '')}"
        unique[marker] = value
    return [unique[key] for key in sorted(unique)]


def get_semantics(
    repository: GraphRepository,
    object_id: str,
    *,
    store: OverrideStore | None = None,
) -> list[dict[str, Any]]:
    """Return semantic assertions and their linked semantic nodes.

    Both sides are returned because the edge carries provenance while the
    semantic node carries the canonical meaning/value.  Facts and inferred or
    observed records retain their original evidence class and status.
    """

    return _semantic_records(repository, str(object_id), store)


def visual_bindings(repository: GraphRepository, node: Node, edges: list[Edge], store: OverrideStore | None) -> dict[str, list[dict[str, Any]]]:
    """Use canonical edges for fields, calculations and inherited filters."""
    groups: dict[str, list[dict[str, Any]]] = {key: [] for key in ("columns", "measures", "calculations", "visual_filters", "page_filters", "report_filters")}
    owners = {node.id}
    frontier = [node.id]
    while frontier:
        current = frontier.pop()
        for edge in edges:
            if edge.type == "CONTAINS" and edge.to_id == current and edge.from_id not in owners:
                owners.add(edge.from_id)
                frontier.append(edge.from_id)
    group_types = {"COLUMN": "columns", "MEASURE": "measures", "VISUAL_CALCULATION": "calculations", "VISUAL_FILTER": "visual_filters", "PAGE_FILTER": "page_filters", "REPORT_FILTER": "report_filters"}
    seen: set[str] = set()
    for edge in edges:
        if not (edge.from_id == node.id and edge.type in {"USES", "CONTAINS"}
                or edge.from_id in owners and edge.type == "CONTAINS"):
            continue
        target = repository.get_object(edge.to_id)
        if target is None or target.id in seen or target.type not in group_types:
            continue
        if target.type in {"COLUMN", "MEASURE", "VISUAL_CALCULATION"} and edge.from_id != node.id:
            continue
        seen.add(target.id)
        groups[group_types[target.type]].append(_payload(target, store))
    for values in groups.values():
        values.sort(key=lambda value: (value["name"].casefold(), value["id"]))
    return groups


_WELL_NAMES = {"category": "Axis", "value": "Values", "legend": "Legend", "tooltip": "Tooltips", "rows": "Rows", "columns": "Columns",
               "small_multiples": "Small multiples", "details": "Details", "size": "Size", "play_axis": "Play axis", "target": "Target",
               "trend": "Trend", "range": "Range", "location": "Location", "slicer_field": "Slicer field"}


def field_wells(repository: GraphRepository, node: Node, store: OverrideStore | None) -> list[dict[str, Any]]:
    """The fields of a visual by the well they sit in (Axis, Values, Legend), in the order of the report file.

    Sort and conditional-formatting uses are not wells and are left out. Empty when the source
    did not record roles; the caller then shows the plain column and measure lists.
    """

    wells: dict[str, dict[str, Any]] = {}
    for item in node.properties.get("field_roles") or []:
        if not isinstance(item, dict) or item.get("usage") != "projection" or item.get("hidden") is True:
            continue
        target = repository.get_object(str(item.get("object_id") or ""))
        if target is None:
            continue
        role = str(item.get("role") or "field")
        well = wells.setdefault(role, {"role": role, "label": _WELL_NAMES.get(role) or role.replace("_", " ").capitalize(), "fields": []})
        if any(field["id"] == target.id for field in well["fields"]):
            continue
        field = _payload(target, store)
        if item.get("aggregation"):
            field["aggregation"] = item["aggregation"]
        if item.get("display_name"):
            field["shown_as"] = item["display_name"]
        well["fields"].append(field)
    return list(wells.values())


_CONTAINERS = {"MODEL", "TABLE", "REPORT", "PAGE"}
_CONTENT_ORDER = ["TABLE", "MEASURE", "COLUMN", "HIERARCHY", "RELATIONSHIP", "PAGE", "VISUAL"]
MAX_CONTENT_ROWS = 300


def contents(repository: GraphRepository, node: Node, edges: list[Edge]) -> list[dict[str, Any]] | None:
    """What a model, table, report or page holds, by kind: the page of a container is its table of contents.

    Each row is small (name, kind, data type, hidden, how many objects it holds itself); a kind
    with more than ``MAX_CONTENT_ROWS`` objects is cut and says how many there are.
    """

    if node.type not in _CONTAINERS:
        return None
    held: dict[str, int] = {}
    children: list[str] = []
    for edge in edges:
        if edge.type != "CONTAINS":
            continue
        held[edge.from_id] = held.get(edge.from_id, 0) + 1
        if edge.from_id == node.id:
            children.append(edge.to_id)
    groups: dict[str, list[dict[str, Any]]] = {}
    for child_id in dict.fromkeys(children):
        child = repository.get_object(child_id)
        if child is None or child.status == "candidate":
            continue
        row = {"id": child.id, "name": child.name, "type": child.type, "holds": held.get(child.id, 0)}
        for key in ("data_type", "visual_type"):
            if child.properties.get(key):
                row[key] = child.properties[key]
        if child.properties.get("is_hidden") or child.properties.get("hidden"):
            row["hidden"] = True
        groups.setdefault(child.type, []).append(row)
    order = {kind: index for index, kind in enumerate(_CONTENT_ORDER)}
    result = []
    for kind in sorted(groups, key=lambda value: (order.get(value, len(order)), value)):
        rows = sorted(groups[kind], key=lambda row: (str(row["name"]).casefold(), row["id"]))
        result.append({"type": kind, "count": len(rows), "items": rows[:MAX_CONTENT_ROWS]})
    return result


def _usage_roles(repository: GraphRepository, node: Node, edges: list[Edge]) -> dict[str, Any] | None:
    from backend.inference.usage_roles import usage_profile

    return usage_profile({item.id: item for item in repository.all_nodes()}, edges, node.id)


def inspect_object(
    repository: GraphRepository,
    object_id: str,
    *,
    store: OverrideStore | None = None,
) -> dict[str, Any] | None:
    """Build the complete local Inspector view for one canonical object."""

    node = repository.get_object(str(object_id))
    if node is None:
        return None
    object_payload = _payload(node, store)
    all_edges = repository.all_edges()
    connected = [edge for edge in all_edges if edge.from_id == node.id or edge.to_id == node.id]
    related = {
        edge.to_id if edge.from_id == node.id else edge.from_id
        for edge in connected
        if edge.type in {"RELATES_TO", "CONTAINS", "USES_MODEL", "FILTERS"}
    }
    relationship_nodes = [repository.get_object(item) for item in sorted(related)]
    relationship_nodes = [item for item in relationship_nodes if item is not None]
    evidence: list[Any] = []
    for item in [object_payload, *(_edge_payload(edge, store) for edge in connected)]:
        value = item.get("evidence")
        if isinstance(value, list):
            evidence.extend(value)
        properties = item.get("properties")
        if isinstance(properties, Mapping) and isinstance(properties.get("evidence"), list):
            evidence.extend(properties["evidence"])
    warnings: list[Any] = []
    properties = object_payload.get("properties")
    if isinstance(properties, Mapping):
        for key in ("warnings", "warning", "conflicts", "conflict"):
            value = properties.get(key)
            if value:
                warnings.extend(value if isinstance(value, list) else [value])
    for edge in connected:
        if edge.type == "CONFLICTS_WITH" or edge.status == "candidate" and "conflict" in str(edge.properties).casefold():
            warnings.append(_edge_payload(edge, store))

    return {
        "object": object_payload,
        "visual_bindings": visual_bindings(repository, node, all_edges, store) if node.type == "VISUAL" else None,
        "field_wells": field_wells(repository, node, store) if node.type == "VISUAL" else None,
        "contents": contents(repository, node, all_edges),
        "identity": {
            key: object_payload.get(key)
            for key in ("id", "type", "name", "model_id", "report_id", "source_id", "status")
        },
        "raw_metadata": object_payload.get("raw_source", object_payload.get("properties", {}).get("raw_source") if isinstance(object_payload.get("properties"), Mapping) else None),
        "description": object_payload.get("description"),
        "dependencies": [_payload(item, store) for item in repository.get_dependencies(node.id)],
        "dependents": [_payload(item, store) for item in repository.get_dependents(node.id)],
        "relationships": {
            "nodes": [_payload(item, store) for item in relationship_nodes],
            "edges": [_edge_payload(edge, store) for edge in connected if edge.type in {"RELATES_TO", "CONTAINS", "USES_MODEL", "FILTERS"}],
        },
        "usage": [_payload(item, store) for item in repository.get_usage(node.id)],
        "usage_roles": _usage_roles(repository, node, all_edges),
        "semantics": _semantic_records(repository, node.id, store),
        "evidence": evidence,
        "confidence": object_payload.get("confidence", object_payload.get("properties", {}).get("confidence") if isinstance(object_payload.get("properties"), Mapping) else None),
        "approval_state": object_payload.get("status"),
        "warnings": warnings,
        "edges": [_edge_payload(edge, store) for edge in connected],
    }


object_details = inspect_object
get_object_inspector = inspect_object


__all__ = [
    "get_dependencies",
    "get_dependents",
    "get_neighbors",
    "get_object",
    "get_object_inspector",
    "get_semantics",
    "get_usage",
    "inspect_object",
    "object_details",
    "search_objects",
]
