"""Evidence-derived confidence scoring for semantic candidates."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


# Fixed weights keep inference reproducible and make the score explainable.
SOURCE_WEIGHTS = {
    "description": 0.96,
    "model_metadata": 0.82,
    "structural": 0.82,
    "dax_ast": 0.86,
    "dax_analysis": 0.86,
    "report_usage": 0.48,
    "report_metadata": 0.42,
    "object_name": 0.30,
    "name": 0.30,
    "manual": 1.0,
    "llm": 0.20,
}


def _source(value: Any) -> str:
    if isinstance(value, Mapping):
        return str(value.get("source") or value.get("origin") or "").casefold()
    return ""


def evidence_weight(value: Any) -> float:
    """Return the fixed contribution for one provenance item."""

    source = _source(value)
    if not source and isinstance(value, str):
        source = value.casefold()
    for key, weight in sorted(SOURCE_WEIGHTS.items(), key=lambda item: len(item[0]), reverse=True):
        if source == key or source.startswith(key + "_") or key in source:
            return weight
    # Unknown evidence is useful, but never allowed to look authoritative.
    return 0.15


def confidence_breakdown(evidence: Iterable[Any]) -> list[dict[str, Any]]:
    """Return stable, inspectable score components."""

    result: list[dict[str, Any]] = []
    for item in evidence:
        weight = evidence_weight(item)
        source = _source(item) or (str(item) if isinstance(item, str) else "unknown")
        result.append({"source": source, "weight": weight, "evidence": item})
    return result


def confidence_from_evidence(evidence: Iterable[Any]) -> float:
    """Combine independent evidence with a bounded deterministic union."""

    weights = [evidence_weight(item) for item in evidence]
    if not weights:
        return 0.0
    score = 1.0
    for weight in weights:
        score *= 1.0 - weight
    return round(max(0.0, min(1.0, 1.0 - score)), 6)


def score_evidence(evidence: Iterable[Any]) -> float:
    return confidence_from_evidence(evidence)


def calculate_confidence(evidence: Iterable[Any]) -> float:
    return confidence_from_evidence(evidence)


def evidence_confidence(evidence: Iterable[Any]) -> float:
    return confidence_from_evidence(evidence)


def combine_confidence(*values: float) -> float:
    """Combine numeric evidence scores without trusting a self-rating."""

    score = 1.0
    for value in values:
        score *= 1.0 - max(0.0, min(1.0, float(value)))
    return round(max(0.0, min(1.0, 1.0 - score)), 6)


__all__ = [
    "SOURCE_WEIGHTS",
    "calculate_confidence",
    "combine_confidence",
    "confidence_breakdown",
    "confidence_from_evidence",
    "evidence_confidence",
    "evidence_weight",
    "score_evidence",
]
