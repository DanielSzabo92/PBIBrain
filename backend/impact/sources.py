"""Upstream data sources of an impact target (issue #10).

The walk goes against the data flow: a visual to the fields it uses, a column to its table,
a table to its partitions, a query to the shared expressions it references and to the
DATA_SOURCE nodes it reads. Queries whose M was not read are listed as not checked, because
a source behind them cannot be named.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any
from collections.abc import Mapping, Sequence

# USES_MODEL is left out: a report reaches the sources its visuals use, not every source of its model.
UPSTREAM_EDGES = {"DEPENDS_ON", "REFERENCES", "USES", "FILTERS", "SOURCES_FROM"}
_CONTAINERS = {"MODEL", "TABLE", "REPORT", "PAGE", "VISUAL"}
_SOURCE_FIELDS = ("kind", "connector", "server", "database", "schema", "object", "path", "url", "location",
                  "workspace_id", "lakehouse_id", "dataflow_id", "warehouse_id", "native_query")


def _properties(node: Mapping[str, Any]) -> Mapping[str, Any]:
    value = node.get("properties")
    return value if isinstance(value, Mapping) else {}


def not_checked_query(node: Mapping[str, Any]) -> dict[str, Any]:
    properties = _properties(node)
    return {"area": "m_query", "object_id": node["id"], "object_type": node.get("type"), "name": node.get("name", ""),
            "model_id": node.get("model_id"), "reason": properties.get("not_checked_reason") or "m_not_read",
            "detail": properties.get("not_checked_detail") or ""}


def is_not_checked_query(node: Mapping[str, Any]) -> bool:
    return node.get("type") in {"PARTITION", "SHARED_EXPRESSION"} and _properties(node).get("check_status") == "not_checked"


def upstream_sources(nodes: Mapping[str, Mapping[str, Any]], edges: Sequence[Mapping[str, Any]],
                     target_ids: Sequence[str]) -> dict[str, list[dict[str, Any]]]:
    """The DATA_SOURCE nodes that feed the targets, each with one shortest path, and the unread queries on the way."""

    outgoing: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        kind = edge.get("type")
        if kind in UPSTREAM_EDGES:
            outgoing[edge["from_id"]].append(edge["to_id"])
        elif kind == "CONTAINS" and nodes.get(edge["from_id"], {}).get("type") in _CONTAINERS:
            child = nodes.get(edge["to_id"], {}).get("type")
            parent = nodes[edge["from_id"]]["type"]
            # A table feeds its columns from its partitions; a model and a report reach their parts.
            if parent != "TABLE" or child == "PARTITION":
                outgoing[edge["from_id"]].append(edge["to_id"])
    sources: dict[str, dict[str, Any]] = {}
    unread: dict[str, dict[str, Any]] = {}
    queue = deque((target, [target]) for target in sorted(target_ids) if target in nodes)
    seen = set(target_ids)
    while queue:
        current, path = queue.popleft()
        node = nodes[current]
        if node.get("type") == "DATA_SOURCE":
            properties = _properties(node)
            sources[current] = {"id": current, "name": node.get("name", ""), "path": path,
                                **{key: properties[key] for key in _SOURCE_FIELDS if properties.get(key) not in (None, "")}}
            continue
        if is_not_checked_query(node):
            unread[current] = not_checked_query(node)
        following = list(outgoing.get(current, []))
        table_id = _properties(node).get("table_id")
        if node.get("type") == "COLUMN" and table_id:
            following.append(str(table_id))
        for other in sorted(set(following)):
            if other in nodes and other not in seen:
                seen.add(other)
                queue.append((other, [*path, other]))
    return {"sources": [sources[key] for key in sorted(sources)], "not_checked": [unread[key] for key in sorted(unread)]}
