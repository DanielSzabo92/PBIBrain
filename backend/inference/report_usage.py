"""Observed report co-occurrence evidence.

Co-occurrence is an observation about report layout.  This module deliberately
emits only ``OBSERVED_WITH`` edges; it never turns usage into compatibility or
another semantic assertion.
"""

from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from typing import Any, Iterable, Mapping

from backend.graph.schema import Edge, Node, edge_from_dict, node_from_dict


_MODEL_OBJECT_TYPES = frozenset(
    {
        "TABLE",
        "COLUMN",
        "MEASURE",
        "FIELD_PARAMETER",
        "SHARED_EXPRESSION",
        "USER_DEFINED_FUNCTION",
        "CALCULATION_GROUP",
        "CALCULATION_ITEM",
    }
)


def _norm(value: Any) -> str:
    return "".join(char for char in str(value).casefold() if char.isalnum())


def _get(value: Any, *keys: str, default: Any = None) -> Any:
    for key in keys:
        if isinstance(value, Mapping):
            if key in value and value[key] is not None:
                return value[key]
            wanted = _norm(key)
            for actual, candidate in value.items():
                if _norm(actual) == wanted and candidate is not None:
                    return candidate
        else:
            candidate = getattr(value, key, None)
            if candidate is not None:
                return candidate
    return default


def _nodes(values: Iterable[Node] | Mapping[str, Node]) -> list[Node]:
    source = values.values() if isinstance(values, Mapping) else values
    result: dict[str, Node] = {}
    for value in source:
        try:
            node = value if isinstance(value, Node) else node_from_dict(value)
        except (TypeError, ValueError):
            continue
        result[node.id] = node
    return [result[key] for key in sorted(result)]


def _edges(values: Iterable[Edge] | Mapping[str, Edge] | None) -> list[Edge]:
    if values is None:
        return []
    source = values.values() if isinstance(values, Mapping) else values
    result: list[Edge] = []
    for value in source:
        try:
            result.append(value if isinstance(value, Edge) else edge_from_dict(value))
        except (TypeError, ValueError, KeyError):
            continue
    return sorted(result, key=lambda item: item.id)


def _as_ids(value: Any) -> list[str]:
    if value is None:
        return []
    values = value if isinstance(value, (list, tuple, set, frozenset)) else [value]
    result: list[str] = []
    for item in values:
        if isinstance(item, Mapping):
            item = _get(item, "id", "object_id", "objectId", "target", "target_id", "targetId")
        if item is not None and str(item) not in result:
            result.append(str(item))
    return result


def _visual_objects(visual: Node, uses: Mapping[str, set[str]], by_id: Mapping[str, Node]) -> list[str]:
    object_ids: set[str] = set(uses.get(visual.id, set()))
    properties = visual.properties
    for key in (
        "field_ids",
        "fieldIds",
        "measure_ids",
        "measureIds",
        "column_ids",
        "columnIds",
        "object_ids",
        "objectIds",
    ):
        object_ids.update(_as_ids(properties.get(key)))
    return sorted(
        item
        for item in object_ids
        if item in by_id and by_id[item].type in _MODEL_OBJECT_TYPES
    )


def analyze_report_usage(
    nodes: Iterable[Node] | Mapping[str, Node],
    edges: Iterable[Edge] | Mapping[str, Edge] | None = None,
    *,
    min_occurrences: int = 1,
) -> list[Edge]:
    """Build deterministic observed co-occurrence edges from report visuals."""

    if min_occurrences < 1:
        raise ValueError("min_occurrences must be at least 1")
    canonical_nodes = _nodes(nodes)
    by_id = {item.id: item for item in canonical_nodes}
    uses: dict[str, set[str]] = defaultdict(set)
    for edge in _edges(edges):
        if edge.type == "USES" and edge.from_id in by_id and edge.to_id in by_id:
            uses[edge.from_id].add(edge.to_id)

    observations: dict[tuple[str, str], dict[str, Any]] = {}
    visuals = [item for item in canonical_nodes if item.type == "VISUAL"]
    for visual in visuals:
        object_ids = _visual_objects(visual, uses, by_id)
        for index, left in enumerate(object_ids):
            for right in object_ids[index + 1 :]:
                pair = (left, right)
                record = observations.setdefault(pair, {"count": 0, "visual_ids": set(), "report_ids": set()})
                record["count"] += 1
                record["visual_ids"].add(visual.id)
                if visual.report_id:
                    record["report_ids"].add(str(visual.report_id))

    result: list[Edge] = []
    for (left, right), record in sorted(observations.items()):
        if record["count"] < min_occurrences:
            continue
        visual_ids = sorted(record["visual_ids"])
        report_ids = sorted(record["report_ids"])
        evidence = [
            {
                "source_object": visual_id,
                "type": "OBSERVED_WITH",
                "target": right,
                "source": "report_usage",
                "confidence": 1.0,
                "status": "factual",
                "evidence_class": "OBSERVED",
                "extractor": "visual_cooccurrence",
                "evidence": f"visual contains both {left} and {right}",
            }
            for visual_id in visual_ids
        ]
        marker = "|".join(("OBSERVED_WITH", left, right, "report_usage"))
        edge_id = "edge:" + hashlib.sha256(marker.encode("utf-8")).hexdigest()[:32]
        result.append(
            Edge(
                id=edge_id,
                type="OBSERVED_WITH",
                from_id=left,
                to_id=right,
                source="report_usage",
                confidence=1.0,
                status="factual",
                evidence=evidence,
                evidence_class="OBSERVED",
                properties={
                    "occurrences": int(record["count"]),
                    "visual_ids": visual_ids,
                    "report_ids": report_ids,
                    "symmetric": True,
                },
            )
        )
    return sorted(result, key=lambda item: item.id)


def discover_report_usage(*args: Any, **kwargs: Any) -> list[Edge]:
    return analyze_report_usage(*args, **kwargs)


def build_observed_usage_edges(*args: Any, **kwargs: Any) -> list[Edge]:
    return analyze_report_usage(*args, **kwargs)


def report_usage_edges(*args: Any, **kwargs: Any) -> list[Edge]:
    return analyze_report_usage(*args, **kwargs)


__all__ = [
    "analyze_report_usage",
    "discover_report_usage",
    "build_observed_usage_edges",
    "report_usage_edges",
]
