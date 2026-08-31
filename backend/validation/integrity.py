"""Single validation entry point used by scanners and local tooling."""

from __future__ import annotations

from typing import Any

from . import ValidationResult, graph_values
from .graph import (
    validate_dax_dependencies,
    validate_graph_integrity,
    validate_reference_integrity,
    validate_source_disappearance,
)
from .overrides import validate_overrides
from .semantics import validate_semantic_integrity, validate_semantics


class ValidationEngine:
    """Run deterministic validation passes against one graph snapshot."""

    def __init__(self, repository_or_graph: Any, *, overrides: Any = None, analyses: Any = None) -> None:
        self.value = repository_or_graph
        self.overrides = overrides
        self.analyses = analyses

    def validate(self) -> ValidationResult:
        return validate_integrity(self.value, overrides=self.overrides, analyses=self.analyses)

    run = validate


def validate_integrity(
    value: Any,
    edges: Any = None,
    *,
    overrides: Any = None,
    analyses: Any = None,
    previous: Any = None,
    current: Any = None,
    changes: Any = None,
    previous_edges: Any = None,
) -> ValidationResult:
    """Run all Phase 5 validation passes without changing the graph."""

    result = ValidationResult()
    result.extend(validate_graph_integrity(value, edges))
    result.extend(validate_reference_integrity(value, edges))
    result.extend(validate_dax_dependencies(value, edges, analyses=analyses))
    result.extend(validate_semantic_integrity(value, edges, analyses=analyses))
    if overrides is not None:
        result.extend(validate_overrides(value, overrides))
    if previous is not None or changes is not None:
        result.extend(
            validate_source_disappearance(
                previous if previous is not None else value,
                current if current is not None else value,
                changes=changes,
                previous_edges=previous_edges,
            )
        )
    # Same logical issue can arise from the broad graph pass and a specialised
    # pass.  Keep one deterministic record for the Inspector/review queue.
    unique: dict[tuple[str, str | None, str | None, str], Any] = {}
    for issue in result.issues:
        marker = (issue.code, issue.object_id, issue.edge_id, issue.message)
        unique.setdefault(marker, issue)
    result.issues = sorted(unique.values(), key=lambda item: (-{"INFO": 0, "WARNING": 1, "ERROR": 2, "BLOCKING": 3}.get(item.severity, 0), item.code, item.object_id or "", item.edge_id or "", item.message))
    return result


def validate(value: Any, edges: Any = None, **kwargs: Any) -> ValidationResult:
    return validate_integrity(value, edges, **kwargs)


validate_repository = validate_integrity
validate_graph = validate_graph_integrity


__all__ = ["ValidationEngine", "validate", "validate_graph", "validate_integrity", "validate_repository"]
