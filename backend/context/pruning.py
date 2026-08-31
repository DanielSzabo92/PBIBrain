"""Deterministic context cleanup after relevance traversal."""

from __future__ import annotations

import json
from typing import Any, Mapping

from .schema import CONTEXT_KEYS, empty_context


def _safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _safe(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_safe(item) for item in value]
    return str(value)


def _key(value: Any) -> str:
    return json.dumps(_safe(value), ensure_ascii=False, sort_keys=True, default=str)


def _dedupe(values: Any) -> list[Any]:
    if not isinstance(values, list):
        return []
    unique = {_key(item): _safe(item) for item in values}
    return [unique[key] for key in sorted(unique)]


def prune_context(
    context: Mapping[str, Any],
    task: str | Mapping[str, Any] | None = None,
    *,
    max_evidence: int | None = None,
) -> dict[str, Any]:
    """Normalize ordering and remove duplicate records without losing facts.

    Relevance traversal happens in :mod:`builder`; this function deliberately
    does not apply a token budget by default.  Correct interpretation wins.
    """

    result = empty_context()
    for key in CONTEXT_KEYS:
        if key in context:
            result[key] = _safe(context[key])
    if not isinstance(result["target"], Mapping):
        result["target"] = {}
    scope = result["scope"] if isinstance(result["scope"], Mapping) else {}
    result["scope"] = {
        "model_ids": sorted({str(item) for item in scope.get("model_ids", []) if item is not None}),
        "report_ids": sorted({str(item) for item in scope.get("report_ids", []) if item is not None}),
    }
    for key in CONTEXT_KEYS[2:]:
        if key == "confidence":
            value = result[key]
            result[key] = {
                str(name): float(score)
                for name, score in sorted(value.items(), key=lambda item: str(item[0]))
                if isinstance(score, (int, float)) and not isinstance(score, bool)
            } if isinstance(value, Mapping) else {}
        else:
            result[key] = _dedupe(result[key])
    if max_evidence is not None:
        if max_evidence < 0:
            raise ValueError("max_evidence must be non-negative")
        # Explicit caller budget.  The default remains lossless.
        result["evidence"] = result["evidence"][:max_evidence]
    return result


prune = prune_context


__all__ = ["prune", "prune_context"]
