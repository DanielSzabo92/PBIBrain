"""Scoped graph payloads for React Flow."""

from __future__ import annotations

from collections import deque
from typing import Any, Sequence

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
    allowed = {
        key for key, node in all_nodes.items()
        if (model_id is None or node.model_id == model_id or key == model_id)
        and (report_id is None or node.report_id == report_id or key == report_id)
    }
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
        nodes = sorted(nodes, key=lambda node: (node.type not in {"MODEL", "REPORT"}, node.type, node.name.casefold(), node.id))
    payloads = [apply_overrides_to_dict(node.to_dict(), store) for node in nodes]
    for payload in payloads:
        payload["artifact_group"] = artifact_group(payload)
    payloads = [payload for payload in payloads
                if (artifact is None or payload["artifact_group"] == artifact)
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


__all__ = ["connected_graph", "find_path", "get_graph", "graph", "graph_data"]
