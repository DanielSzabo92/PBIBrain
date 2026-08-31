"""Inspector review operations.

The graph remains the source of generated facts.  Human edits are kept in a
small, separate override file and applied only when an API payload is built.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from backend.graph.repository import GraphRepository
from backend.graph.schema import Edge, Node


_SEMANTIC_TYPES = frozenset({"BUSINESS_CONCEPT", "SELECTOR", "SELECTOR_OPTION", "CONFLICT", "SEMANTIC_ASSERTION"})
_ALLOWED_STATUSES = frozenset({"candidate", "approved", "rejected", "overridden"})


def _dict(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return dict(to_dict())
    return dict(vars(value))


def _properties(item: Mapping[str, Any]) -> Mapping[str, Any]:
    value = item.get("properties")
    return value if isinstance(value, Mapping) else {}


def _item_matches(item: Mapping[str, Any], target: str) -> bool:
    target = str(target)
    if str(item.get("id", "")) == target:
        return True
    properties = _properties(item)
    return any(
        str(properties.get(key, "")) == target
        for key in ("candidate_id", "candidateId", "target", "target_id", "object_id")
    )


class OverrideStore:
    """Separate, JSON-backed human decision store.

    ``path=None`` is an in-memory store, useful for an embedded Inspector and
    tests.  The API can pass ``config/overrides.json`` for durable decisions.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else None
        self._records: list[dict[str, Any]] = self._read()

    def _read(self) -> list[dict[str, Any]]:
        if self.path is None or not self.path.is_file():
            return []
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid overrides file: {self.path}") from exc
        if isinstance(value, Mapping):
            value = value.get("overrides", [value])
        if not isinstance(value, list):
            raise ValueError("overrides file must contain a list or an overrides object")
        return [dict(item) for item in value if isinstance(item, Mapping) and item.get("target")]

    def records(self) -> list[dict[str, Any]]:
        return [dict(record) for record in self._records]

    def _write(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = sorted(self._records, key=lambda item: (str(item.get("target", "")), str(item.get("property", ""))))
        self.path.write_text(
            json.dumps({"version": 1, "overrides": payload}, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def record_id(record: Mapping[str, Any]) -> str:
        return f"override:{record.get('target', '')}:{record.get('property', '')}"

    def put(
        self,
        target: str,
        property: str,
        value: Any,
        *,
        status: str = "overridden",
        source: str = "manual",
        evidence: Iterable[Any] | None = None,
    ) -> dict[str, Any]:
        target = str(target).strip()
        property = str(property).strip()
        status = str(status).lower()
        if not target:
            raise ValueError("override target is required")
        if not property:
            raise ValueError("override property is required")
        if status not in _ALLOWED_STATUSES:
            raise ValueError(f"unsupported override status: {status}")
        record: dict[str, Any] = {
            "target": target,
            "property": property,
            "value": value,
            "status": status,
            "source": str(source),
        }
        if evidence is not None:
            record["evidence"] = list(evidence)
        self._records = [
            item
            for item in self._records
            if not (str(item.get("target")) == target and str(item.get("property")) == property)
        ]
        self._records.append(record)
        self._write()
        return dict(record)

    def remove(self, identifier: str, property: str | None = None) -> list[dict[str, Any]]:
        """Remove only the explicitly selected human override record(s)."""

        identifier = str(identifier).strip()
        property_name = str(property).strip() if property is not None else None
        removed: list[dict[str, Any]] = []
        retained: list[dict[str, Any]] = []
        for record in self._records:
            matches_id = self.record_id(record) == identifier
            matches_target = str(record.get("target", "")) == identifier and (
                property_name is None or str(record.get("property", "")) == property_name
            )
            if matches_id or matches_target:
                removed.append(dict(record))
            else:
                retained.append(record)
        if not removed:
            raise KeyError(f"override not found: {identifier}")
        self._records = retained
        self._write()
        return removed

    def patch(
        self,
        target: str,
        values: Mapping[str, Any],
        *,
        status: str = "overridden",
        source: str = "manual",
    ) -> list[dict[str, Any]]:
        if not isinstance(values, Mapping) or not values:
            raise ValueError("override patch must contain at least one property")
        return [self.put(target, key, value, status=status, source=source) for key, value in values.items()]


def _override_records(store: OverrideStore | None) -> list[dict[str, Any]]:
    return store.records() if store is not None else []


def apply_overrides_to_dict(item: Mapping[str, Any], store: OverrideStore | None = None) -> dict[str, Any]:
    """Return an effective payload without modifying the generated record."""

    result = dict(item)
    properties = dict(_properties(item))
    applied: list[dict[str, Any]] = []
    for record in _override_records(store):
        if not _item_matches(item, str(record.get("target", ""))):
            continue
        property_name = str(record.get("property", "")).strip()
        if not property_name:
            continue
        value = record.get("value")
        if property_name == "status":
            result["status"] = str(value).lower()
        else:
            result[property_name] = value
            properties[property_name] = value
            if property_name in {"business_concept", "concept", "meaning", "value", "role", "behavior", "alias"}:
                result["value"] = value
                result["meaning"] = value
                properties["meaning"] = value
        applied.append(dict(record))
    if applied:
        result["properties"] = properties
        result["overrides"] = applied
        result.setdefault("status", "overridden")
        if any(str(record.get("status", "")).lower() == "overridden" for record in applied):
            result["status"] = "overridden"
    return result


def _all_items(repository: GraphRepository) -> tuple[list[Node], list[Edge]]:
    return repository.all_nodes(), repository.all_edges()


def _candidate_target(item: Mapping[str, Any], edges: Sequence[Edge]) -> str | None:
    properties = _properties(item)
    for key in ("target", "target_id", "object_id"):
        if properties.get(key):
            return str(properties[key])
    if item.get("from_id"):
        return str(item["from_id"])
    item_id = str(item.get("id", ""))
    incoming = [edge for edge in edges if edge.to_id == item_id and edge.evidence_class == "INFERRED"]
    if incoming:
        return sorted(incoming, key=lambda edge: edge.id)[0].from_id
    conflict_target = properties.get("target_id")
    return str(conflict_target) if conflict_target else None


def _impact(item: Mapping[str, Any], target: Mapping[str, Any] | None) -> str:
    if str(item.get("type", "")).upper() in {"CONFLICT", "CONFLICTS_WITH"}:
        return "high"
    if target and str(target.get("type", "")).upper() in {"MEASURE", "TABLE", "MODEL"}:
        return "high"
    try:
        return "high" if float(item.get("confidence", 0.0)) < 0.5 else "normal"
    except (TypeError, ValueError):
        return "normal"


def _queue_item(
    item: Mapping[str, Any],
    *,
    edges: Sequence[Edge],
    target: Mapping[str, Any] | None,
    store: OverrideStore | None,
) -> dict[str, Any]:
    value = apply_overrides_to_dict(item, store)
    item_type = str(value.get("type", "")).upper()
    properties = _properties(value)
    assertion_type = str(value.get("assertion_type") or properties.get("assertion_type") or "").upper()
    issue_type = "conflict" if (
        item_type in {"CONFLICT", "CONFLICTS_WITH"}
        or assertion_type == "CONFLICT"
        or bool(properties.get("conflict"))
    ) else "candidate"
    target_id = _candidate_target(value, edges)
    target_model_id = target.get("model_id") if target else value.get("model_id")
    target_report_id = target.get("report_id") if target else value.get("report_id")
    result = {
        "id": str(value.get("id", "")),
        "review_id": str(value.get("id", "")),
        "target_id": target_id,
        "object_id": target_id,
        "model_id": target_model_id,
        "report_id": target_report_id,
        "object_type": target.get("type") if target else None,
        "type": item_type,
        "issue_type": issue_type,
        "value": value.get("value", value.get("meaning")),
        "confidence": float(value.get("confidence", _properties(value).get("confidence", 0.0)) or 0.0),
        "status": value.get("status", "candidate"),
        "evidence_class": value.get("evidence_class", "INFERRED"),
        "source": value.get("source", "semantic_inference"),
        "evidence": value.get("evidence", _properties(value).get("evidence", [])),
        "impact": _impact(value, target),
        "item": value,
    }
    return result


def get_review_queue(
    repository: GraphRepository,
    store: OverrideStore | None = None,
    *,
    object_type: str | Sequence[str] | None = None,
    model_id: str | None = None,
    report_id: str | None = None,
    issue_type: str | None = None,
    min_confidence: float | None = None,
    max_confidence: float | None = None,
    sort_by: str = "confidence",
    descending: bool = False,
) -> list[dict[str, Any]]:
    """Return unresolved semantic candidates and conflicts for the Inspector."""

    nodes, edges = _all_items(repository)
    by_id = {node.id: node for node in nodes}
    records: list[dict[str, Any]] = []
    seen_candidates: set[str] = set()
    for node in nodes:
        if node.type not in _SEMANTIC_TYPES and node.status == "factual":
            continue
        effective = apply_overrides_to_dict(node.to_dict(), store)
        if str(effective.get("status", node.status)).lower() != "candidate":
            continue
        properties = _properties(effective)
        candidate_keys = {
            str(value)
            for value in [properties.get("candidate_id"), *properties.get("candidate_ids", [])]
            if value
        }
        if node.type == "CONFLICT":
            candidate_keys.add(node.id)
        if candidate_keys and candidate_keys <= seen_candidates:
            continue
        target_id = _candidate_target(effective, edges)
        records.append(_queue_item(effective, edges=edges, target=by_id.get(target_id or ""), store=None))
        seen_candidates.update(candidate_keys or {str(effective.get("id", ""))})
    for edge in edges:
        if edge.evidence_class != "INFERRED" and edge.type not in {"CONFLICTS_WITH"}:
            continue
        effective = apply_overrides_to_dict(edge.to_dict(), store)
        if str(effective.get("status", edge.status)).lower() != "candidate":
            continue
        properties = _properties(effective)
        candidate_key = str(properties.get("candidate_id") or effective.get("id", ""))
        if edge.type == "CONFLICTS_WITH":
            conflict_endpoint = next(
                (
                    endpoint
                    for endpoint in (edge.from_id, edge.to_id)
                    if by_id.get(endpoint) is not None and by_id[endpoint].type == "CONFLICT"
                ),
                None,
            )
            candidate_key = conflict_endpoint or candidate_key
        if candidate_key in seen_candidates:
            continue
        target_id = _candidate_target(effective, edges)
        records.append(_queue_item(effective, edges=edges, target=by_id.get(target_id or ""), store=None))
        seen_candidates.add(candidate_key)

    # A missing override target is actionable Inspector state.  Detection is
    # read-only here; source reconciliation remains a later sync concern.
    if store is not None:
        for override_record in store.records():
            target = str(override_record.get("target", ""))
            if not target or any(_item_matches(item.to_dict(), target) for item in [*nodes, *edges]):
                continue
            records.append(
                {
                    "id": f"override:{target}:{override_record.get('property', '')}",
                    "review_id": f"override:{target}:{override_record.get('property', '')}",
                    "target_id": target,
                    "object_id": target,
                    "target": target,
                    "override_target": target,
                    "override_property": override_record.get("property"),
                    "override_id": OverrideStore.record_id(override_record),
                    "type": "OVERRIDE",
                    "issue_type": "stale",
                    "value": override_record.get("value"),
                    "confidence": 0.0,
                    "status": "candidate",
                    "evidence_class": "INFERRED",
                    "source": "manual",
                    "evidence": [override_record],
                    "impact": "high",
                    "item": dict(override_record),
                }
            )

    wanted_types = None
    if object_type:
        values = object_type if isinstance(object_type, (list, tuple, set, frozenset)) else [object_type]
        wanted_types = {str(value).upper() for value in values}
    filtered: list[dict[str, Any]] = []
    for record in records:
        target = by_id.get(str(record.get("target_id")))
        if wanted_types and record["type"] not in wanted_types and (target is None or target.type not in wanted_types):
            continue
        if model_id and (target is None or target.model_id != str(model_id)):
            continue
        if report_id and (target is None or target.report_id != str(report_id)):
            continue
        if issue_type and record["issue_type"] != str(issue_type).casefold():
            continue
        confidence = float(record["confidence"])
        if min_confidence is not None and confidence < float(min_confidence):
            continue
        if max_confidence is not None and confidence > float(max_confidence):
            continue
        filtered.append(record)

    sort_key = str(sort_by).casefold()
    if sort_key not in {"confidence", "impact", "type", "id", "object_type"}:
        raise ValueError("unsupported review sort field")
    impact_rank = {"high": 0, "normal": 1}
    filtered.sort(
        key=lambda record: (
            float(record["confidence"]) if sort_key == "confidence" else
            impact_rank.get(str(record["impact"]), 2) if sort_key == "impact" else
            record["type"] if sort_key in {"type", "object_type"} else record["id"],
            record["id"],
        ),
        reverse=bool(descending),
    )
    return filtered


review_queue = get_review_queue


def _set_status(repository: GraphRepository, item_id: str, status: str) -> dict[str, Any]:
    status = str(status).lower()
    if status not in _ALLOWED_STATUSES:
        raise ValueError(f"unsupported review status: {status}")
    nodes, edges = _all_items(repository)
    target = str(item_id)
    changed_nodes: list[Node] = []
    changed_edges: list[Edge] = []
    for node in nodes:
        if _item_matches(node.to_dict(), target) and node.status != "factual":
            node.status = status
            changed_nodes.append(node)
    for edge in edges:
        if _item_matches(edge.to_dict(), target) and edge.evidence_class == "INFERRED":
            edge.status = status
            changed_edges.append(edge)
    if not changed_nodes and not changed_edges:
        raise KeyError(f"review item not found: {item_id}")
    repository.replace(nodes, edges)
    return {
        "item_id": target,
        "status": status,
        "nodes": [node.to_dict() for node in changed_nodes],
        "edges": [edge.to_dict() for edge in changed_edges],
    }


def approve(repository: GraphRepository, item_id: str) -> dict[str, Any]:
    return _set_status(repository, item_id, "approved")


def reject(repository: GraphRepository, item_id: str) -> dict[str, Any]:
    return _set_status(repository, item_id, "rejected")


def edit(
    repository: GraphRepository,
    item_id: str,
    changes: Mapping[str, Any] | None = None,
    *,
    property: str | None = None,
    value: Any = None,
    store: OverrideStore | None = None,
) -> dict[str, Any]:
    """Store a human edit separately and return its effective records."""

    if store is None:
        store = OverrideStore()
    if changes is None:
        if property is None:
            raise ValueError("edit requires changes or property")
        changes = {property: value}
    records = store.patch(str(item_id), changes)
    return {"item_id": str(item_id), "status": "overridden", "overrides": records}


def override(
    repository: GraphRepository,
    item_id: str,
    property: str | None = None,
    value: Any = None,
    *,
    patch: Mapping[str, Any] | None = None,
    store: OverrideStore | None = None,
) -> dict[str, Any]:
    if store is None:
        store = OverrideStore()
    if patch is not None:
        records = store.patch(str(item_id), patch)
    elif property is not None:
        records = [store.put(str(item_id), property, value)]
    else:
        raise ValueError("override requires property/value or patch")
    return {"item_id": str(item_id), "status": "overridden", "overrides": records}


apply_override = override


def remove_override(
    repository: GraphRepository,
    item_id: str,
    *,
    property: str | None = None,
    store: OverrideStore | None = None,
) -> dict[str, Any]:
    """Remove a selected human override; generated graph records stay intact."""

    if store is None:
        store = OverrideStore()
    removed = store.remove(str(item_id), property)
    return {"item_id": str(item_id), "status": "removed", "overrides": removed}


__all__ = [
    "OverrideStore",
    "apply_overrides_to_dict",
    "approve",
    "edit",
    "get_review_queue",
    "override",
    "remove_override",
    "reject",
    "review_queue",
]
