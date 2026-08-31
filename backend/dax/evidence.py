"""Evidence contracts for deterministic DAX analysis.

The analyzer emits plain dictionaries so evidence survives JSON and LadybugDB
round trips without a custom serializer.  This module only formats locations;
it does not interpret DAX or infer business meaning.
"""

from __future__ import annotations

from dataclasses import dataclass, field, is_dataclass, asdict
from typing import Any, Mapping


def _json_value(value: Any) -> Any:
    """Return a JSON-safe value while retaining useful parser locations."""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if is_dataclass(value):
        return _json_value(asdict(value))
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            return _json_value(to_dict())
        except Exception:  # pragma: no cover - defensive for third-party ASTs
            pass
    return str(value)


def ast_location(node: Any) -> dict[str, Any] | str | None:
    """Extract a stable, serialisable source location from an AST node."""

    if node is None:
        return None
    candidates: list[Any] = []
    if isinstance(node, Mapping):
        for key in ("ast_location", "location", "span", "source_span", "range"):
            if key in node:
                candidates.append(node[key])
        candidates.extend(
            [
                {key: node[key] for key in ("start", "end") if key in node},
                {key: node[key] for key in ("start_offset", "end_offset") if key in node},
            ]
        )
    else:
        for key in ("ast_location", "location", "span", "source_span", "range"):
            value = getattr(node, key, None)
            if value is not None:
                candidates.append(value)
        start = getattr(node, "start", None)
        end = getattr(node, "end", None)
        if start is not None or end is not None:
            candidates.append({"start": start, "end": end})
        start = getattr(node, "start_offset", None)
        end = getattr(node, "end_offset", None)
        if start is not None or end is not None:
            candidates.append({"start": start, "end": end})
    for value in candidates:
        if value in (None, {}, ""):
            continue
        if isinstance(value, Mapping):
            result = {str(key): _json_value(item) for key, item in value.items()}
            if result:
                return result
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            return {"start": _json_value(value[0]), "end": _json_value(value[1])}
        return _json_value(value)
    return None


@dataclass(slots=True)
class DaxEvidence:
    """Canonical evidence payload for one extracted DAX assertion."""

    source_object: str
    type: str
    target: str | None = None
    ast_location: Any = None
    extractor: str = ""
    source: str = "dax_ast"
    confidence: float = 1.0
    status: str = "factual"
    evidence_class: str = "FACT"
    evidence: list[Any] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        result = {
            "source_object": str(self.source_object),
            "type": str(self.type).upper(),
            "target": str(self.target) if self.target is not None else None,
            "ast_location": _json_value(self.ast_location),
            "extractor": self.extractor,
            "source": self.source,
            "confidence": float(self.confidence),
            "status": self.status,
            "evidence_class": self.evidence_class,
            "evidence": _json_value(self.evidence),
        }
        return result

    as_dict = to_dict

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.to_dict().get(key, default)


def make_evidence(
    source_object: str,
    edge_type: str,
    target: str | None,
    *,
    node: Any = None,
    extractor: str,
    source: str = "dax_ast",
    evidence: Any = None,
    confidence: float = 1.0,
    status: str = "factual",
    evidence_class: str = "FACT",
) -> dict[str, Any]:
    """Build one JSON-safe evidence dictionary.

    ``evidence`` is deliberately explicit: a parser span alone says where an
    assertion came from, while this short value says what was observed there.
    """

    if evidence is None:
        values: list[Any] = []
    elif isinstance(evidence, list):
        values = evidence
    else:
        values = [evidence]
    return DaxEvidence(
        source_object=str(source_object),
        type=edge_type,
        target=target,
        ast_location=ast_location(node),
        extractor=extractor,
        source=source,
        confidence=confidence,
        status=status,
        evidence_class=evidence_class,
        evidence=values,
    ).to_dict()


Evidence = DaxEvidence


__all__ = ["DaxEvidence", "Evidence", "ast_location", "make_evidence"]
