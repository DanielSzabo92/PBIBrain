"""Scoped graph payloads for React Flow."""

from __future__ import annotations

import hashlib
import json
from collections import deque
from typing import Any
from collections.abc import Sequence

from backend.graph.repository import GraphRepository
from backend.graph.artifacts import artifact_group
from backend.graph.schema import STATUS_VALUES

from .review import OverrideStore, apply_overrides_to_dict


def _values(value: str | Sequence[str] | None) -> set[str] | None:
    if value is None:
        return None
    values = value if isinstance(value, (list, tuple, set, frozenset)) else [value]
    return {str(item).upper() for item in values}


def get_graph(
    repository: GraphRepository,
    *,
    query: str = "",
    object_types: str | Sequence[str] | None = None,
    edge_types: str | Sequence[str] | None = None,
    center_id: str | None = None,
    depth: int = 1,
    limit: int | None = None,
    model_id: str | None = None,
    report_id: str | None = None,
    artifact: str | None = None,
    status: str | None = None,
    store: OverrideStore | None = None,
) -> dict[str, Any]:
    """Return only the requested graph slice.

    React Flow receives this payload; the repository remains the source of
    truth and no visual coordinates or UI state are persisted here.
    """

    if isinstance(depth, bool) or not isinstance(depth, int) or not 0 <= depth <= 8:
        raise ValueError("graph depth must be an integer between 0 and 8")
    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000):
        raise ValueError("graph limit must be an integer between 1 and 1000")
    wanted_nodes = _values(object_types)
    wanted_edges = _values(edge_types)
    if artifact is not None and (not isinstance(artifact, str) or artifact not in {"report", "model", "other"}):
        raise ValueError("artifact must be report, model, or other")
    if status is not None and (not isinstance(status, str) or status not in STATUS_VALUES):
        raise ValueError("Unsupported graph status")
    all_nodes = {node.id: node for node in repository.all_nodes()}
    all_edges = repository.all_edges()
    # A report slice includes its source model and the fields actually used by
    # its visuals/filters. Ownership metadata on those fields remains model.
    report_context = {key for key, node in all_nodes.items()
                      if node.report_id and (report_id is None or node.report_id == report_id)}
    report_roots = set(report_context)
    report_context.update(edge.to_id for edge in all_edges
                          if edge.from_id in report_roots and edge.type in {"USES", "FILTERS", "USES_MODEL"})
    allowed = {
        key for key, node in all_nodes.items()
        if (model_id is None or node.model_id == model_id or key == model_id)
        and (report_id is None or key in report_context or key == report_id)
    }
    if model_id is not None:
        # A data source has no model (issue #10): a model slice keeps the sources its queries read.
        allowed.update(edge.to_id for edge in all_edges if edge.type == "SOURCES_FROM" and edge.from_id in allowed)
    adjacency: dict[str, set[str]] = {}
    for edge in all_edges:
        if edge.from_id not in allowed or edge.to_id not in allowed or (wanted_edges and edge.type not in wanted_edges):
            continue
        adjacency.setdefault(edge.from_id, set()).add(edge.to_id)
        adjacency.setdefault(edge.to_id, set()).add(edge.from_id)

    if center_id is not None:
        center = str(center_id)
        if center not in allowed:
            raise KeyError(f"object not found: {center_id}")
        selected: set[str] = {center}
        frontier = deque([(center, 0)])
        ordered = [center]
        while frontier:
            current, distance = frontier.popleft()
            if distance >= depth:
                continue
            for other in sorted(adjacency.get(current, ())):
                if other not in selected:
                    selected.add(other)
                    ordered.append(other)
                    frontier.append((other, distance + 1))
        nodes = [all_nodes[item] for item in ordered]
    elif query:
        nodes = repository.search_objects(query)
    else:
        nodes = repository.all_nodes()
    nodes = [node for node in nodes if node.id in allowed]
    if query and center_id is not None:
        matches = {node.id for node in repository.search_objects(query)}
        nodes = [node for node in nodes if node.id in matches]
    if wanted_nodes:
        nodes = [node for node in nodes if node.type in wanted_nodes or node.id == center_id]
    if center_id is None:
        # Visit report branches before unrelated model objects so a limited
        # overview still contains pages, visuals and their immediate bindings.
        order = {kind: index for index, kind in enumerate(("MODEL", "REPORT", "REPORT_FILTER", "PAGE", "PAGE_FILTER", "VISUAL", "VISUAL_FILTER", "VISUAL_CALCULATION"))}
        children: dict[str, list[str]] = {}
        for edge in all_edges:
            if edge.type == "USES_MODEL":
                # Display report branches beside their model without inventing containment.
                children.setdefault(edge.to_id, []).append(edge.from_id)
            if edge.type in {"CONTAINS", "USES", "FILTERS"}:
                children.setdefault(edge.from_id, []).append(edge.to_id)
        available = {node.id: node for node in nodes}
        key = lambda item: (order.get(available[item].type, 99), available[item].name.casefold(), item)
        ordered_ids: list[str] = []
        visited: set[str] = set()

        def visit(item: str) -> None:
            if item in visited:
                return
            visited.add(item)
            ordered_ids.append(item)
            for child in sorted((value for value in children.get(item, []) if value in available), key=key):
                visit(child)

        for item in sorted(available, key=key):
            visit(item)
        nodes = [available[item] for item in ordered_ids]
    payloads = [apply_overrides_to_dict(node.to_dict(), store) for node in nodes]
    for payload in payloads:
        payload["artifact_group"] = artifact_group(payload)
    payloads = [payload for payload in payloads
                if (artifact is None or payload["artifact_group"] == artifact or artifact == "report" and payload["id"] in report_context)
                and (status is None or payload.get("status") == status)]
    total_nodes = len(payloads)
    if limit is not None:
        payloads = payloads[:limit]
    node_ids = {node["id"] for node in payloads}
    edges = [
        edge
        for edge in all_edges
        if edge.from_id in node_ids and edge.to_id in node_ids and (not wanted_edges or edge.type in wanted_edges)
    ]
    return {
        "nodes": payloads,
        "edges": [apply_overrides_to_dict(edge.to_dict(), store) for edge in edges],
        "total_nodes": total_nodes,
        "truncated": len(payloads) < total_nodes,
        "scope": {
            "center_id": str(center_id) if center_id is not None else None,
            "depth": depth,
            "query": query,
            "model_id": model_id,
            "report_id": report_id,
            "artifact": artifact,
            "status": status,
            "limit": limit,
            "object_types": sorted(wanted_nodes) if wanted_nodes else [],
            "edge_types": sorted(wanted_edges) if wanted_edges else [],
        },
    }


# Structural links that lineage and the impact matrix read. Semantic, similarity and
# co-occurrence links are context, not lineage, and are left out of this payload.
LINEAGE_EDGES = frozenset({
    "CONTAINS", "BELONGS_TO", "HAS_OPTION", "DEPENDS_ON", "REFERENCES", "USES", "USES_MODEL", "FILTERS",
    "MODIFIES_FILTER", "CONTROLLED_BY", "ACTIVATES_RELATIONSHIP", "MODIFIES_RELATIONSHIP", "SOURCES_FROM",
})
_LINEAGE_FIELDS = ("model_id", "report_id", "table_id", "page_id", "parent_id", "display_name", "source_id", "source_hash", "visual_type", "evidence_class",
                  "origin", "workspace_name", "check_status", "not_checked_reason", "not_checked_detail",
                  # Issue #10: data source kind and location, and whether a query's M was read.
                  "kind", "location", "source_status")


def _definition_hash(payload: dict[str, Any]) -> str | None:
    """Hash of what the source file says about the object, without the scan's ids: equal for identical copies."""

    raw = payload.get("raw_source")
    if not isinstance(raw, dict) or not raw:
        return None
    text = json.dumps(raw, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def _lineage_tag(payload: dict[str, Any]) -> str | None:
    raw = payload.get("raw_source") if isinstance(payload.get("raw_source"), dict) else {}
    tag = payload.get("lineage_tag") or payload.get("lineageTag") or raw.get("lineageTag") or raw.get("lineage_tag")
    return str(tag) if tag else None


def get_lineage(
    repository: GraphRepository,
    *,
    model_id: str | None = None,
    report_id: str | None = None,
    store: OverrideStore | None = None,
) -> dict[str, Any]:
    """The whole factual structure of a scope, in compact form and without an object limit.

    Each node carries only what lineage, the impact matrix and version grouping need (a few
    ids, names and the source hash), so a project of tens of thousands of objects stays a few
    megabytes; the full object is read on selection with ``get_object``.
    """

    scoped = get_graph(repository, model_id=model_id, report_id=report_id, status="factual", store=store,
                       edge_types=sorted(LINEAGE_EDGES))
    nodes = []
    for payload in scoped["nodes"]:
        compact = {"id": payload["id"], "type": payload["type"], "name": payload.get("name") or "", "status": payload.get("status")}
        compact.update({key: payload[key] for key in _LINEAGE_FIELDS if payload.get(key) not in (None, "")})
        definition = _definition_hash(payload)
        if definition:
            compact["definition_hash"] = definition
        tag = _lineage_tag(payload)
        if tag:
            compact["lineage_tag"] = tag
        nodes.append(compact)
    edges = [{"id": edge["id"], "type": edge["type"], "from_id": edge["from_id"], "to_id": edge["to_id"], "status": edge.get("status"),
              # The usage role (value, category, slicer_field...) of a report binding.
              **({"role": edge["properties"]["role"]} if isinstance(edge.get("properties"), dict) and edge["properties"].get("role") else {})}
             for edge in scoped["edges"] if edge.get("status", "factual") == "factual"]
    return {"nodes": nodes, "edges": edges, "total_nodes": len(nodes), "truncated": False,
            "scope": {"model_id": model_id, "report_id": report_id}}


def find_path(
    repository: GraphRepository,
    from_id: str,
    to_id: str,
    *,
    store: OverrideStore | None = None,
) -> list[dict[str, Any]]:
    """Return the shortest repository path as canonical node payloads."""

    return [
        apply_overrides_to_dict(node.to_dict(), store)
        for node in repository.find_path(str(from_id), str(to_id))
    ]


graph = get_graph
graph_data = get_graph
connected_graph = get_graph


__all__ = ["connected_graph", "find_path", "get_graph", "get_lineage", "graph", "graph_data"]
