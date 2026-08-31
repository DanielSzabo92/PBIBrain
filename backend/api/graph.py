"""Scoped graph payloads for React Flow."""

from __future__ import annotations

from collections import deque
from typing import Any, Sequence

from backend.graph.repository import GraphRepository

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
    store: OverrideStore | None = None,
) -> dict[str, Any]:
    """Return only the requested graph slice.

    React Flow receives this payload; the repository remains the source of
    truth and no visual coordinates or UI state are persisted here.
    """

    if depth < 0:
        raise ValueError("graph depth must be non-negative")
    if limit is not None and limit < 1:
        raise ValueError("graph limit must be positive")
    wanted_nodes = _values(object_types)
    wanted_edges = _values(edge_types)
    all_nodes = {node.id: node for node in repository.all_nodes()}
    all_edges = repository.all_edges()

    if center_id is not None:
        center = str(center_id)
        if center not in all_nodes:
            raise KeyError(f"object not found: {center_id}")
        selected: set[str] = {center}
        frontier = deque([(center, 0)])
        while frontier:
            current, distance = frontier.popleft()
            if distance >= depth:
                continue
            for edge in all_edges:
                if wanted_edges and edge.type not in wanted_edges:
                    continue
                if edge.from_id == current:
                    other = edge.to_id
                elif edge.to_id == current:
                    other = edge.from_id
                else:
                    continue
                if other not in selected:
                    selected.add(other)
                    frontier.append((other, distance + 1))
        nodes = [all_nodes[item] for item in sorted(selected) if item in all_nodes]
    elif query:
        nodes = repository.search_objects(query)
    else:
        nodes = repository.all_nodes()
    if wanted_nodes:
        nodes = [node for node in nodes if node.type in wanted_nodes]
    if limit is not None:
        nodes = nodes[:limit]
    node_ids = {node.id for node in nodes}
    edges = [
        edge
        for edge in all_edges
        if edge.from_id in node_ids and edge.to_id in node_ids and (not wanted_edges or edge.type in wanted_edges)
    ]
    return {
        "nodes": [apply_overrides_to_dict(node.to_dict(), store) for node in nodes],
        "edges": [apply_overrides_to_dict(edge.to_dict(), store) for edge in edges],
        "scope": {
            "center_id": str(center_id) if center_id is not None else None,
            "depth": depth,
            "query": query,
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
