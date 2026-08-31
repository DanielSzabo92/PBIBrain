"""Validation for separately stored human overrides."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

from . import ValidationIssue, ValidationResult, graph_values, item_dict


_OVERRIDE_STATUSES = frozenset({"candidate", "approved", "rejected", "overridden"})
_IMMUTABLE_PROPERTIES = frozenset(
    {
        "id",
        "type",
        "name",
        "model_id",
        "report_id",
        "source_id",
        "source",
        "evidence",
        "evidence_class",
        "from_id",
        "to_id",
        "status",
    }
)


def _records(overrides: Any) -> list[dict[str, Any]]:
    if overrides is None:
        return []
    if hasattr(overrides, "records") and callable(overrides.records):
        return [item_dict(value) for value in overrides.records()]
    if isinstance(overrides, (str, Path)):
        from backend.api.review import OverrideStore

        return [item_dict(value) for value in OverrideStore(overrides).records()]
    if isinstance(overrides, Mapping):
        value = overrides.get("overrides", [overrides])
        if isinstance(value, Mapping):
            value = [value]
        return [item_dict(item) for item in value] if isinstance(value, (list, tuple)) else []
    if isinstance(overrides, Iterable) and not isinstance(overrides, (str, bytes)):
        return [item_dict(item) for item in overrides]
    return []


def _matches(record: Mapping[str, Any], node: Mapping[str, Any], edge: Mapping[str, Any]) -> bool:
    target = str(record.get("target", ""))
    if not target:
        return False
    for item in (node, edge):
        if str(item.get("id", "")) == target:
            return True
        props = item.get("properties") if isinstance(item.get("properties"), Mapping) else {}
        if any(str(props.get(key, "")) == target for key in ("candidate_id", "candidateId", "target", "target_id", "object_id")):
            return True
    return False


def validate_overrides(value: Any, overrides: Any = None) -> ValidationResult:
    """Check override shape, stable targets, and source-fact protection."""

    # Accept ``validate_overrides(repository, store)`` and
    # ``validate_overrides(store, repository)`` for small integration callers.
    repository = value if hasattr(value, "all_nodes") else overrides if hasattr(overrides, "all_nodes") else None
    store = overrides if repository is value else value if repository is not None else overrides
    nodes, edges = graph_values(repository) if repository is not None else ([], [])
    node_records = [item_dict(item) for item in nodes]
    edge_records = [item_dict(item) for item in edges]
    records = _records(store)
    result = ValidationResult()
    seen: set[tuple[str, str]] = set()
    for index, record in enumerate(records):
        target = str(record.get("target", "")).strip()
        property_name = str(record.get("property", "")).strip()
        status = str(record.get("status", "overridden")).lower()
        if not target:
            result.add(
                ValidationIssue(
                    "override_missing_target",
                    "ERROR",
                    f"Override at index {index} has no stable target",
                    category="override_integrity",
                    evidence=[record],
                )
            )
            continue
        if not property_name:
            result.add(
                ValidationIssue(
                    "override_missing_property",
                    "ERROR",
                    f"Override for {target} has no property",
                    category="override_integrity",
                    object_id=target,
                    evidence=[record],
                )
            )
        if status not in _OVERRIDE_STATUSES:
            result.add(
                ValidationIssue(
                    "override_invalid_status",
                    "ERROR",
                    f"Override for {target} has unsupported status {status!r}",
                    category="override_integrity",
                    object_id=target,
                    evidence=[record],
                )
            )
        marker = (target, property_name)
        if marker in seen:
            result.add(
                ValidationIssue(
                    "duplicate_override",
                    "WARNING",
                    f"Override is duplicated for {target}.{property_name}",
                    category="override_integrity",
                    object_id=target,
                    evidence=[record],
                )
            )
        seen.add(marker)
        if property_name.casefold() in _IMMUTABLE_PROPERTIES:
            result.add(
                ValidationIssue(
                    "override_mutates_generated_fact",
                    "BLOCKING",
                    f"Override cannot replace generated field {property_name}",
                    category="override_integrity",
                    object_id=target,
                    evidence=[record],
                )
            )
        if repository is not None and not any(_matches(record, node, edge) for node, edge in [*[(node, {}) for node in node_records], *[({}, edge) for edge in edge_records]]):
            result.add(
                ValidationIssue(
                    "stale_override",
                    "WARNING",
                    f"Override target no longer exists: {target}",
                    category="override_integrity",
                    object_id=target,
                    evidence=[record],
                    details={"target_id": target, "property": property_name},
                )
            )
    return result


def validate_override_integrity(value: Any, overrides: Any = None) -> ValidationResult:
    return validate_overrides(value, overrides)


def stale_overrides(value: Any, overrides: Any = None) -> list[dict[str, Any]]:
    result = validate_overrides(value, overrides)
    return [issue.to_dict() for issue in result.issues if issue.code == "stale_override"]


__all__ = ["stale_overrides", "validate_override_integrity", "validate_overrides"]
