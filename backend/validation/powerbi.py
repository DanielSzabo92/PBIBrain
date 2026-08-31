"""Small, read-only hooks for targeted Power BI validation queries.

Adapters are intentionally duck-typed.  The Brain records the query and
returned value as evidence, while the adapter remains responsible for the
Power BI connection and authentication.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Callable, Mapping


def _safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_safe(item) for item in value]
    return str(value)


@dataclass(frozen=True, slots=True)
class ValidationQuery:
    """One small query allowed at the validation boundary."""

    query: str
    target_id: str
    purpose: str = ""
    name: str = "targeted_validation"
    params: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not str(self.query).strip():
            raise ValueError("validation query is required")
        if not str(self.target_id).strip():
            raise ValueError("validation query target_id is required")
        if len(str(self.query)) > 100_000:
            raise ValueError("validation query is too large")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": str(self.name),
            "target_id": str(self.target_id),
            "purpose": str(self.purpose),
            "query": str(self.query),
            "params": _safe(self.params),
            "read_only": True,
        }

    @property
    def target(self) -> str:
        return self.target_id


@dataclass(frozen=True, slots=True)
class ValidationEvidence:
    """Traceable result from one read-only validation query."""

    query: ValidationQuery
    result: Any
    source: str = "validation_query"
    status: str = "factual"
    evidence_class: str = "FACT"

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "source": self.source,
            "extractor": "targeted_read_only_query",
            "status": self.status,
            "evidence_class": self.evidence_class,
            "target": self.query.target_id,
            "query": self.query.to_dict(),
            "result": _safe(self.result),
        }
        payload["evidence"] = [{
            "source": self.source,
            "target": self.query.target_id,
            "purpose": self.query.purpose,
            "query": self.query.query,
            "result": _safe(self.result),
            "read_only": True,
        }]
        return payload


class ReadOnlyValidationAdapter:
    """Constructible adapter seam for one read-only executor."""

    def __init__(self, executor: Callable[..., Any]) -> None:
        if not callable(executor):
            raise TypeError("read-only validation executor must be callable")
        self.executor = executor

    def execute_readonly(self, query: str, params: Mapping[str, Any] | None = None) -> Any:
        return self.executor(query, params or {})

    query_readonly = execute_readonly


def _call_adapter(adapter: Any, request: ValidationQuery) -> Any:
    # Do not accept generic ``execute``/``run`` methods.  A validation query
    # must have an explicitly read-only adapter seam.
    for method_name in ("execute_readonly", "query_readonly", "execute_dax_readonly", "query_dax", "read_query"):
        method = getattr(adapter, method_name, None)
        if not callable(method):
            continue
        params = dict(request.params)
        try:
            return method(request.query, params)
        except TypeError:
            if params:
                raise
            return method(request.query)
    raise TypeError(
        "validation adapter must expose execute_readonly/query_readonly/execute_dax_readonly/query_dax/read_query"
    )


def _assert_read_only(query: str) -> None:
    if re.search(r"\b(?:INSERT|UPDATE|DELETE|ALTER|CREATE|DROP|MERGE|TRUNCATE|GRANT|REVOKE)\b", query, re.I):
        raise ValueError("validation query must be read-only")


def run_validation_query(
    adapter: Any,
    query: ValidationQuery | str,
    target_id: str | None = None,
    *,
    target: str | None = None,
    purpose: str = "",
    name: str = "targeted_validation",
    params: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute one bounded read-only query and return provenance evidence."""

    request = query if isinstance(query, ValidationQuery) else ValidationQuery(
        str(query), str(target_id or target or ""), purpose=purpose, name=name, params=params or {}
    )
    _assert_read_only(request.query)
    value = _call_adapter(adapter, request)
    return ValidationEvidence(request, value).to_dict()


class PowerBIValidationHook:
    """Convenience wrapper that keeps adapter calls read-only and traceable."""

    def __init__(self, adapter: Any, *, max_queries: int = 10) -> None:
        if max_queries < 1:
            raise ValueError("max_queries must be positive")
        self.adapter = adapter
        self.max_queries = int(max_queries)
        self.evidence: list[dict[str, Any]] = []

    def run(self, query: ValidationQuery | str, target_id: str | None = None, **kwargs: Any) -> dict[str, Any]:
        if len(self.evidence) >= self.max_queries:
            raise RuntimeError("validation query limit reached")
        evidence = run_validation_query(self.adapter, query, target_id, **kwargs)
        self.evidence.append(evidence)
        return evidence

    execute = run
    validate = run


def selector_values_query(table_name: str, column_name: str, *, target_id: str) -> ValidationQuery:
    """Build a small VALUES query for selector option validation."""

    def quote(value: str) -> str:
        return "'" + str(value).replace("'", "''") + "'"

    return ValidationQuery(
        f"EVALUATE VALUES({quote(table_name)}[{str(column_name).replace(']', ']]')}])",
        target_id,
        purpose="selector_option_discovery",
        name="selector_values",
    )


def validation_query_evidence(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return run_validation_query(*args, **kwargs)


__all__ = [
    "PowerBIValidationHook",
    "ReadOnlyValidationAdapter",
    "ValidationEvidence",
    "ValidationQuery",
    "run_validation_query",
    "selector_values_query",
    "validation_query_evidence",
]
