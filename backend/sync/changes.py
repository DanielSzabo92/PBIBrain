"""Deterministic source change and review-state helpers.

The graph remains authoritative.  This module only compares canonical records
and carries human review state across a source rebuild.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Iterable, Mapping

from backend.graph.schema import Edge, Node


UNCHANGED = "UNCHANGED"
CHANGED = "CHANGED"
NEW = "NEW"
DELETED = "DELETED"
CHANGE_STATES = frozenset({UNCHANGED, CHANGED, NEW, DELETED})


_GENERATED_NODE_KEYS = frozenset(
    {
        "source_hash",
        "source_fingerprint",
        "dax_ast",
        "dax_asts",
        "dax_behaviors",
        "dax_evidence",
        "dax_diagnostics",
        "confidence_breakdown",
        "candidate_evidence",
        "candidate_ids",
    }
)


def _safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_safe(item) for item in value]
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _safe(value.to_dict())
    return str(value)


def _digest(value: Any) -> str:
    payload = json.dumps(_safe(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _node_payload(node: Node | Mapping[str, Any]) -> dict[str, Any]:
    value = node.to_dict() if isinstance(node, Node) else dict(node)
    properties = value.get("properties")
    if isinstance(properties, Mapping):
        properties = {
            str(key): item
            for key, item in properties.items()
            if str(key) not in _GENERATED_NODE_KEYS
        }
    else:
        properties = {}
    return {
        "id": value.get("id"),
        "type": value.get("type"),
        "name": value.get("name"),
        "description": value.get("description"),
        "model_id": value.get("model_id"),
        "report_id": value.get("report_id"),
        "source_id": value.get("source_id"),
        "source": value.get("source"),
        "properties": properties,
    }


def _edge_payload(edge: Edge | Mapping[str, Any]) -> dict[str, Any]:
    value = edge.to_dict() if isinstance(edge, Edge) else dict(edge)
    return {
        "id": value.get("id"),
        "type": value.get("type"),
        "from_id": value.get("from_id"),
        "to_id": value.get("to_id"),
        "source": value.get("source"),
        "confidence": value.get("confidence"),
        "evidence": value.get("evidence", []),
        "evidence_class": value.get("evidence_class"),
        "properties": value.get("properties", {}),
    }


def node_fingerprint(node: Node | Mapping[str, Any]) -> str:
    """Hash source-bearing canonical metadata, ignoring generated analysis."""

    return _digest(_node_payload(node))


def edge_fingerprint(edge: Edge | Mapping[str, Any]) -> str:
    """Hash an edge without treating human lifecycle status as source data."""

    return _digest(_edge_payload(edge))


@dataclass(frozen=True, slots=True)
class Change:
    """One canonical record transition."""

    id: str
    status: str
    object_type: str | None = None
    source_id: str | None = None
    old_hash: str | None = None
    new_hash: str | None = None

    @property
    def kind(self) -> str:
        return self.status

    @property
    def state(self) -> str:
        return self.status

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "kind": self.status,
            "object_type": self.object_type,
            "source_id": self.source_id,
            "old_hash": self.old_hash,
            "new_hash": self.new_hash,
        }


@dataclass(slots=True)
class ChangeSet:
    """Mapping-like view grouped by ``UNCHANGED``/``CHANGED``/``NEW``/``DELETED``."""

    records: list[Change] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.records = sorted(self.records, key=lambda item: (item.status, item.id))

    @property
    def statuses(self) -> dict[str, str]:
        return {item.id: item.status for item in sorted(self.records, key=lambda value: value.id)}

    @property
    def by_status(self) -> dict[str, list[str]]:
        result = {state: [] for state in (UNCHANGED, CHANGED, NEW, DELETED)}
        for item in self.records:
            result.setdefault(item.status, []).append(item.id)
        return result

    def __getitem__(self, key: str) -> list[str]:
        wanted = str(key).upper()
        if wanted not in CHANGE_STATES:
            raise KeyError(key)
        return list(self.by_status[wanted])

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key: object) -> bool:
        return str(key).upper() in CHANGE_STATES

    def __iter__(self):
        return iter((UNCHANGED, CHANGED, NEW, DELETED))

    def __len__(self) -> int:
        return len(CHANGE_STATES)

    @property
    def unchanged(self) -> list[str]:
        return self[UNCHANGED]

    @property
    def changed(self) -> list[str]:
        return self[CHANGED]

    @property
    def new(self) -> list[str]:
        return self[NEW]

    @property
    def deleted(self) -> list[str]:
        return self[DELETED]

    def to_dict(self) -> dict[str, list[str]]:
        return self.by_status


def _record_map(values: Iterable[Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for value in values:
        identifier = getattr(value, "id", None)
        if identifier is None and isinstance(value, Mapping):
            identifier = value.get("id")
        if identifier is not None:
            result[str(identifier)] = value
    return result


def classify_changes(
    previous: Iterable[Node | Edge | Mapping[str, Any]],
    current: Iterable[Node | Edge | Mapping[str, Any]],
    *,
    fingerprints: Mapping[str, str] | None = None,
) -> ChangeSet:
    """Classify canonical records by stable ID and deterministic fingerprint."""

    old = _record_map(previous)
    new = _record_map(current)
    records: list[Change] = []
    for identifier in sorted(set(old) | set(new)):
        before = old.get(identifier)
        after = new.get(identifier)
        if before is None:
            status = NEW
        elif after is None:
            status = DELETED
        else:
            old_hash = node_fingerprint(before) if isinstance(before, Node) or _looks_like_node(before) else edge_fingerprint(before)
            new_hash = node_fingerprint(after) if isinstance(after, Node) or _looks_like_node(after) else edge_fingerprint(after)
            status = UNCHANGED if old_hash == new_hash else CHANGED
        old_hash = None if before is None else _fingerprint(before)
        new_hash = None if after is None else _fingerprint(after)
        object_type = None
        candidate = after if after is not None else before
        if isinstance(candidate, Node):
            object_type = candidate.type
        elif isinstance(candidate, Mapping):
            object_type = candidate.get("type")
        source_id = None
        if isinstance(candidate, Node):
            source_id = candidate.source_id
        elif isinstance(candidate, Mapping):
            source_id = candidate.get("source_id")
        records.append(Change(identifier, status, object_type, source_id, old_hash, new_hash))
    return ChangeSet(records)


def _looks_like_node(value: Any) -> bool:
    if isinstance(value, Node):
        return True
    return isinstance(value, Mapping) and "from_id" not in value and "to_id" not in value


def _fingerprint(value: Any) -> str:
    return node_fingerprint(value) if _looks_like_node(value) else edge_fingerprint(value)


def preserve_review_statuses(
    current_nodes: Iterable[Node],
    current_edges: Iterable[Edge],
    previous_nodes: Iterable[Node],
    previous_edges: Iterable[Edge],
) -> None:
    """Carry approved/rejected/overridden generated state by stable ID only."""

    old_nodes = {item.id: item for item in previous_nodes}
    old_edges = {item.id: item for item in previous_edges}
    for node in current_nodes:
        previous = old_nodes.get(node.id)
        if previous is not None and previous.status != "factual" and node.status != "factual":
            node.status = previous.status
    for edge in current_edges:
        previous = old_edges.get(edge.id)
        if previous is not None and previous.status != "factual" and edge.status != "factual":
            edge.status = previous.status


@dataclass(slots=True)
class SyncResult:
    """Result returned by an incremental scanner operation."""

    graph: Any
    changes: ChangeSet
    edge_changes: ChangeSet = field(default_factory=ChangeSet)
    stale_overrides: list[dict[str, Any]] = field(default_factory=list)
    override_conflicts: list[dict[str, Any]] = field(default_factory=list)
    affected_ids: list[str] = field(default_factory=list)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)

    @property
    def status(self) -> ChangeSet:
        return self.changes

    @property
    def nodes(self):
        return self.graph.nodes

    @property
    def edges(self):
        return self.graph.edges

    def to_dict(self) -> dict[str, Any]:
        result = self.graph.to_dict()
        result.update(
            {
                "changes": self.changes.to_dict(),
                "edge_changes": self.edge_changes.to_dict(),
                "change_records": [item.to_dict() for item in self.changes.records],
                "affected_ids": list(self.affected_ids),
                "stale_overrides": list(self.stale_overrides),
                "override_conflicts": list(self.override_conflicts),
            }
        )
        return result

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]


__all__ = [
    "CHANGED",
    "CHANGE_STATES",
    "DELETED",
    "NEW",
    "UNCHANGED",
    "Change",
    "ChangeSet",
    "SyncResult",
    "classify_changes",
    "edge_fingerprint",
    "node_fingerprint",
    "preserve_review_statuses",
]
