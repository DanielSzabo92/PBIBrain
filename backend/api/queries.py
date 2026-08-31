"""Stable read/query operations exposed by the Brain API facade."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from backend.graph.repository import GraphRepository
from backend.validation import validate_reference_integrity

from .graph import find_path
from .objects import (
    _payload,
    get_dependencies,
    get_dependents,
    get_neighbors,
    get_semantics,
    get_usage,
    search_objects,
)
from .review import OverrideStore


def _selection_ids(value: Any) -> list[str]:
    """Normalize the small set of selection shapes accepted by the API."""

    if isinstance(value, Mapping):
        value = value.get("object_ids", value.get("ids", value.get("objects", [])))
    if isinstance(value, str):
        value = [value]
    if value is None:
        return []
    if not isinstance(value, Iterable) or isinstance(value, (bytes, bytearray)):
        raise TypeError("object_ids must be a sequence of stable ids")
    return sorted({str(item) for item in value if str(item)})


def _issue_dict(issue: Any) -> dict[str, Any]:
    if isinstance(issue, Mapping):
        return dict(issue)
    to_dict = getattr(issue, "to_dict", None)
    if callable(to_dict):
        return dict(to_dict())
    return dict(vars(issue))


def validate_selection(
    repository: GraphRepository,
    object_ids: Sequence[str] | str | Mapping[str, Any] | None,
    *,
    store: OverrideStore | None = None,
) -> dict[str, Any]:
    """Validate a requested object selection without changing graph state.

    Missing ids are errors.  Existing validation findings are limited to the
    selected objects or their incident edges, so unrelated graph warnings do
    not make an otherwise usable selection fail.
    """

    selected_ids = _selection_ids(object_ids)
    nodes = {node.id: node for node in repository.all_nodes()}
    selected_nodes = [nodes[item] for item in selected_ids if item in nodes]
    issues: list[dict[str, Any]] = []
    for object_id in selected_ids:
        if object_id not in nodes:
            issues.append(
                {
                    "code": "missing_object",
                    "issue_type": "missing_object",
                    "severity": "ERROR",
                    "message": f"Selection object does not exist: {object_id}",
                    "category": "selection",
                    "object_id": object_id,
                    "edge_id": None,
                    "evidence": [{"object_id": object_id}],
                    "source": "brain_api",
                }
            )

    selected_set = set(selected_ids)
    incident_edges = {
        edge.id: edge
        for edge in repository.all_edges()
        if edge.from_id in selected_set or edge.to_id in selected_set
    }
    for issue in validate_reference_integrity(repository).issues:
        record = _issue_dict(issue)
        object_id = record.get("object_id")
        edge_id = record.get("edge_id")
        details = record
        touches_selection = str(object_id) in selected_set if object_id is not None else False
        if edge_id is not None and str(edge_id) in incident_edges:
            touches_selection = True
        if not touches_selection:
            for key in ("from_id", "to_id", "target_id", "source_id"):
                if str(details.get(key)) in selected_set:
                    touches_selection = True
                    break
        if touches_selection:
            issues.append(record)

    # Keep issue order stable and avoid duplicate reports from overlapping
    # validation passes.
    unique: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for issue in issues:
        marker = (
            str(issue.get("code", issue.get("issue_type", "validation_issue"))),
            str(issue.get("object_id", "")),
            str(issue.get("edge_id", "")),
            str(issue.get("message", "")),
        )
        unique.setdefault(marker, issue)
    issues = sorted(
        unique.values(),
        key=lambda item: (
            str(item.get("severity", "WARNING")),
            str(item.get("code", item.get("issue_type", ""))),
            str(item.get("object_id", "")),
            str(item.get("edge_id", "")),
        ),
    )
    has_error = any(str(item.get("severity", "")).upper() in {"ERROR", "BLOCKING"} for item in issues)
    has_warning = any(str(item.get("severity", "")).upper() == "WARNING" for item in issues)
    state = "invalid" if has_error else "warning" if has_warning else "valid"
    return {
        "selected_ids": selected_ids,
        "objects": [_payload(node, store) for node in selected_nodes],
        "issues": issues,
        "valid": not has_error,
        "state": state,
        "status": state,
    }


__all__ = [
    "find_path",
    "get_dependencies",
    "get_dependents",
    "get_neighbors",
    "get_semantics",
    "get_usage",
    "search_objects",
    "validate_selection",
]
