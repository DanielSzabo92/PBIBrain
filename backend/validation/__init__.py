"""Deterministic validation contracts for the Power BI Brain.

Validation is read-only.  It reports defects in the canonical graph, source
references, semantic assertions, and human overrides; it never edits graph
facts or Power BI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


SEVERITIES = ("INFO", "WARNING", "ERROR", "BLOCKING")
_SEVERITY_RANK = {name: index for index, name in enumerate(SEVERITIES)}


def normalize_severity(value: Any) -> str:
    text = str(value or "WARNING").upper()
    aliases = {"WARN": "WARNING", "CRITICAL": "BLOCKING", "FATAL": "BLOCKING"}
    return aliases.get(text, text if text in _SEVERITY_RANK else "WARNING")


@dataclass(slots=True)
class ValidationIssue:
    """One traceable validation finding."""

    code: str
    severity: str
    message: str
    category: str = "integrity"
    object_id: str | None = None
    edge_id: str | None = None
    evidence: list[Any] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    source: str = "validation"

    def __post_init__(self) -> None:
        self.code = str(self.code)
        self.severity = normalize_severity(self.severity)
        self.message = str(self.message)
        self.category = str(self.category)
        self.object_id = str(self.object_id) if self.object_id is not None else None
        self.edge_id = str(self.edge_id) if self.edge_id is not None else None
        self.evidence = list(self.evidence or [])
        self.details = dict(self.details or {})
        self.source = str(self.source)

    @property
    def issue_type(self) -> str:
        return self.code

    @property
    def level(self) -> str:
        return self.severity

    @property
    def is_blocking(self) -> bool:
        return self.severity == "BLOCKING"

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "code": self.code,
            "issue_type": self.code,
            "severity": self.severity,
            "message": self.message,
            "category": self.category,
            "object_id": self.object_id,
            "edge_id": self.edge_id,
            "evidence": list(self.evidence),
            "source": self.source,
        }
        result.update(self.details)
        return result

    as_dict = to_dict

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]


@dataclass(slots=True)
class ValidationResult:
    """Stable result envelope returned by every validation operation."""

    issues: list[ValidationIssue] = field(default_factory=list)
    checked: bool = True
    evidence: list[Any] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.issues = [coerce_issue(item) for item in self.issues]
        self.evidence = list(self.evidence or [])

    def add(self, issue: ValidationIssue | Mapping[str, Any], **kwargs: Any) -> ValidationIssue:
        if not isinstance(issue, ValidationIssue):
            issue = coerce_issue(issue, **kwargs)
        self.issues.append(issue)
        return issue

    def extend(self, other: "ValidationResult | Iterable[ValidationIssue | Mapping[str, Any]]") -> "ValidationResult":
        values = other.issues if isinstance(other, ValidationResult) else other
        self.issues.extend(coerce_issue(item) for item in values)
        if isinstance(other, ValidationResult):
            self.evidence.extend(other.evidence)
            self.checked = self.checked and other.checked
        return self

    @property
    def state(self) -> str:
        if not self.checked:
            return "not_run"
        if any(issue.severity in {"ERROR", "BLOCKING"} for issue in self.issues):
            return "invalid"
        if any(issue.severity == "WARNING" for issue in self.issues):
            return "warning"
        return "valid"

    @property
    def status(self) -> str:
        return self.state

    @property
    def valid(self) -> bool:
        return self.checked and not any(issue.severity in {"ERROR", "BLOCKING"} for issue in self.issues)

    @property
    def is_valid(self) -> bool:
        return self.valid

    @property
    def blocking(self) -> list[ValidationIssue]:
        return [issue for issue in self.issues if issue.severity == "BLOCKING"]

    @property
    def errors(self) -> list[ValidationIssue]:
        return [issue for issue in self.issues if issue.severity == "ERROR"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [issue for issue in self.issues if issue.severity == "WARNING"]

    @property
    def infos(self) -> list[ValidationIssue]:
        return [issue for issue in self.issues if issue.severity == "INFO"]

    @property
    def counts(self) -> dict[str, int]:
        return {severity.lower(): sum(issue.severity == severity for issue in self.issues) for severity in SEVERITIES}

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "status": self.status,
            "valid": self.valid,
            "checked": self.checked,
            "counts": self.counts,
            "issues": [issue.to_dict() for issue in sorted(self.issues, key=issue_sort_key)],
            "evidence": list(self.evidence),
        }

    as_dict = to_dict

    def __bool__(self) -> bool:
        return self.valid


def issue_sort_key(issue: ValidationIssue) -> tuple[Any, ...]:
    return (
        -_SEVERITY_RANK.get(issue.severity, 0),
        issue.category,
        issue.code,
        issue.object_id or "",
        issue.edge_id or "",
        issue.message,
    )


def coerce_issue(value: ValidationIssue | Mapping[str, Any], **overrides: Any) -> ValidationIssue:
    if isinstance(value, ValidationIssue):
        return value
    data = dict(value)
    code = data.pop("code", data.pop("issue_type", data.pop("type", "validation_issue")))
    severity = data.pop("severity", data.pop("level", "WARNING"))
    message = data.pop("message", str(code))
    known = {
        "category": data.pop("category", "integrity"),
        "object_id": data.pop("object_id", data.pop("target_id", None)),
        "edge_id": data.pop("edge_id", None),
        "evidence": data.pop("evidence", []),
        "source": data.pop("source", "validation"),
        "details": data.pop("details", data),
    }
    known.update(overrides)
    return ValidationIssue(code, severity, message, **known)


def graph_values(value: Any, edges: Any = None) -> tuple[list[Any], list[Any]]:
    """Accept a repository, FactGraph, mapping, or explicit node/edge lists."""

    if hasattr(value, "all_nodes") and callable(value.all_nodes):
        nodes = list(value.all_nodes())
        graph_edges = list(value.all_edges()) if hasattr(value, "all_edges") else []
        return nodes, list(edges) if edges is not None else graph_edges
    if hasattr(value, "nodes") and hasattr(value, "edges"):
        return list(value.nodes.values()) if isinstance(value.nodes, Mapping) else list(value.nodes), list(edges) if edges is not None else list(value.edges)
    if isinstance(value, Mapping):
        nodes = value.get("nodes", value.get("objects", []))
        graph_edges = value.get("edges", value.get("relationships", []))
        if isinstance(nodes, Mapping):
            nodes = list(nodes.values())
        if isinstance(graph_edges, Mapping):
            graph_edges = list(graph_edges.values())
        return list(nodes or []), list(edges) if edges is not None else list(graph_edges or [])
    return list(value or []), list(edges or [])


def item_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return dict(to_dict())
    return dict(vars(value))


def properties(value: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = value.get("properties")
    return raw if isinstance(raw, Mapping) else {}


from .graph import (  # noqa: E402  (exports after shared contracts)
    validate_dax_dependencies,
    validate_graph,
    validate_graph_integrity,
    validate_reference_integrity,
    validate_source_disappearance,
    validate_source_disappearances,
)
from .integrity import ValidationEngine, validate, validate_integrity
from .overrides import validate_override_integrity, validate_overrides
from .semantics import (
    validate_invalid_selector_semantics,
    validate_semantic_integrity,
    validate_selector_semantics,
    validate_semantics,
)
from .powerbi import (
    PowerBIValidationHook,
    ReadOnlyValidationAdapter,
    ValidationEvidence,
    ValidationQuery,
    run_validation_query,
)


__all__ = [
    "SEVERITIES",
    "ValidationIssue",
    "ValidationResult",
    "ValidationEngine",
    "ValidationEvidence",
    "ValidationQuery",
    "PowerBIValidationHook",
    "ReadOnlyValidationAdapter",
    "validate",
    "validate_dax_dependencies",
    "validate_graph",
    "validate_graph_integrity",
    "validate_integrity",
    "validate_override_integrity",
    "validate_overrides",
    "validate_reference_integrity",
    "validate_source_disappearance",
    "validate_source_disappearances",
    "validate_invalid_selector_semantics",
    "validate_semantic_integrity",
    "validate_selector_semantics",
    "validate_semantics",
    "run_validation_query",
]
