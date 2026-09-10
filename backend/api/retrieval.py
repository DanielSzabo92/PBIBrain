"""Deterministic, evidence-bearing object retrieval for agent consumers."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from backend.graph.repository import GraphRepository
from backend.graph.schema import Node

from .review import OverrideStore, apply_overrides_to_dict


DEFAULT_LIMIT = 20
MAX_LIMIT = 100
_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


@dataclass(frozen=True, slots=True)
class _Field:
    path: str
    value: str
    weight: int
    identity: bool = False


@dataclass(frozen=True, slots=True)
class _Hit:
    node: Node
    score: int
    kind: str
    evidence: tuple[dict[str, Any], ...]


def _text(value: Any) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).casefold().strip()


def _lexical(value: Any) -> str:
    return " ".join(_TOKEN_RE.findall(_text(value)))


def _tokens(value: Any) -> tuple[str, ...]:
    return tuple(dict.fromkeys(_TOKEN_RE.findall(_text(value))))


def _scope_values(
    value: str | Sequence[str] | None,
    *,
    upper: bool = False,
    lower: bool = False,
) -> frozenset[str] | None:
    if value is None:
        return None
    values: Iterable[Any]
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        values = value
    else:
        raise TypeError("scope values must be a string or sequence of strings")
    normalized = {str(item).strip() for item in values if str(item).strip()}
    if not normalized:
        raise ValueError("scope values cannot be empty")
    if upper:
        return frozenset(item.upper() for item in normalized)
    if lower:
        return frozenset(item.lower() for item in normalized)
    return frozenset(normalized)


def _validate_page(limit: int, offset: int) -> tuple[int, int]:
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise TypeError("limit must be an integer")
    if isinstance(offset, bool) or not isinstance(offset, int):
        raise TypeError("offset must be an integer")
    if not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_LIMIT}")
    if offset < 0:
        raise ValueError("offset must be non-negative")
    return limit, offset


def _property_fields(properties: Mapping[str, Any]) -> list[_Field]:
    """Return the small set of metadata that is useful for lexical retrieval."""

    result: list[_Field] = []
    direct = {
        "display_name": 880,
        "qualified_name": 870,
        "alias": 850,
        "aliases": 850,
        "synonym": 850,
        "synonyms": 850,
        "meaning": 760,
        "business_concept": 760,
        "expression": 520,
        "formula": 520,
    }

    def add(path: str, value: Any, weight: int) -> None:
        if isinstance(value, str) and value.strip():
            result.append(_Field(path, value, weight))
        elif isinstance(value, (list, tuple, set, frozenset)):
            for index, item in enumerate(value):
                if isinstance(item, str) and item.strip():
                    result.append(_Field(f"{path}[{index}]", item, weight))

    for key, weight in direct.items():
        add(f"properties.{key}", properties.get(key), weight)
    raw = properties.get("raw_source")
    if isinstance(raw, Mapping):
        add("properties.raw_source.name", raw.get("name"), 890)
        add("properties.raw_source.description", raw.get("description"), 680)
        add("properties.raw_source.id", raw.get("id"), 830)
        add("properties.raw_source.expression", raw.get("expression"), 510)
    return result


def _fields(node: Node) -> list[_Field]:
    fields = [
        _Field("id", node.id, 1000, True),
        _Field("source_id", node.source_id or "", 960, True),
        _Field("name", node.name, 920, True),
        _Field("description", node.description or "", 700),
    ]
    fields.extend(_property_fields(node.properties if isinstance(node.properties, Mapping) else {}))
    return [field for field in fields if field.value]


def _match_field(field: _Field, query_text: str, query_lexical: str, query_tokens: tuple[str, ...]) -> tuple[int, str] | None:
    raw = _text(field.value)
    lexical = _lexical(field.value)
    words = set(_tokens(field.value))
    if field.path in {"id", "source_id"} and raw == query_text:
        return field.weight, f"exact_{field.path}"
    if lexical == query_lexical:
        return field.weight, f"exact_{field.path.replace('.', '_')}"
    if query_lexical and lexical.startswith(query_lexical):
        return field.weight - 60, f"prefix_{field.path.replace('.', '_')}"
    if query_lexical and query_lexical in lexical:
        return field.weight - 90, f"phrase_{field.path.replace('.', '_')}"
    if query_tokens and all(token in words for token in query_tokens):
        return field.weight - 120, f"tokens_{field.path.replace('.', '_')}"
    return None


def _node_in_scope(
    node: Node,
    *,
    object_types: frozenset[str] | None,
    model_ids: frozenset[str] | None,
    report_ids: frozenset[str] | None,
    statuses: frozenset[str] | None,
) -> bool:
    node_model = node.id if node.type == "MODEL" else node.model_id
    node_report = node.id if node.type == "REPORT" else node.report_id
    return (
        (object_types is None or node.type.upper() in object_types)
        and (model_ids is None or node_model in model_ids)
        and (report_ids is None or node_report in report_ids)
        and (statuses is None or node.status in statuses)
    )


def _ranked_hits(
    repository: GraphRepository,
    query: str,
    *,
    object_type: str | Sequence[str] | None = None,
    model_id: str | Sequence[str] | None = None,
    report_id: str | Sequence[str] | None = None,
    status: str | Sequence[str] | None = None,
) -> tuple[list[_Hit], dict[str, list[str]]]:
    query = str(query or "").strip()
    query_text = _text(query)
    query_lexical = _lexical(query)
    query_tokens = _tokens(query)
    object_types = _scope_values(object_type, upper=True)
    model_ids = _scope_values(model_id)
    report_ids = _scope_values(report_id)
    statuses = _scope_values(status, lower=True)
    scope = {
        "object_types": sorted(object_types or ()),
        "model_ids": sorted(model_ids or ()),
        "report_ids": sorted(report_ids or ()),
        "statuses": sorted(statuses or ()),
    }
    hits: list[_Hit] = []
    for node in repository.all_nodes():
        if not _node_in_scope(
            node,
            object_types=object_types,
            model_ids=model_ids,
            report_ids=report_ids,
            statuses=statuses,
        ):
            continue
        if not query:
            hits.append(_Hit(node, 0, "browse", ()))
            continue
        matches: list[tuple[int, str, _Field]] = []
        for field in _fields(node):
            match = _match_field(field, query_text, query_lexical, query_tokens)
            if match is not None:
                matches.append((match[0], match[1], field))
        if not matches:
            continue
        matches.sort(key=lambda item: (-item[0], item[2].path, _text(item[2].value)))
        best_score, best_kind, _ = matches[0]
        evidence = tuple(
            {
                "field": field.path,
                "match": kind,
                "value": field.value,
            }
            for _, kind, field in matches[:3]
        )
        hits.append(_Hit(node, best_score, best_kind, evidence))
    hits.sort(
        key=lambda hit: (
            -hit.score,
            hit.node.type,
            _lexical(hit.node.name),
            hit.node.model_id or "",
            hit.node.report_id or "",
            hit.node.id,
        )
    )
    return hits, scope


def _ambiguity(hits: Sequence[_Hit], query: str) -> dict[str, Any]:
    if not query or not hits:
        return {"ambiguous": False, "reason": None, "candidate_ids": []}
    top_score = hits[0].score
    top = [hit for hit in hits if hit.score == top_score]
    exact_name = [hit for hit in hits if _lexical(hit.node.name) == _lexical(query)]
    candidates = exact_name if len(exact_name) > 1 else top
    ambiguous = len(candidates) > 1
    reason = None
    if len(exact_name) > 1:
        reason = "duplicate_exact_name_across_scopes"
    elif len(top) > 1:
        reason = "multiple_top_matches"
    return {
        "ambiguous": ambiguous,
        "reason": reason,
        "candidate_ids": [hit.node.id for hit in candidates] if ambiguous else [],
    }


def _excerpt(value: str, query: str, limit: int = 240) -> str:
    value = " ".join(str(value).split())
    if len(value) <= limit:
        return value
    position = value.casefold().find(str(query).casefold())
    start = max(0, position - limit // 3) if position >= 0 else 0
    end = min(len(value), start + limit)
    start = max(0, end - limit)
    return f"{'…' if start else ''}{value[start:end]}{'…' if end < len(value) else ''}"


def _hit_payload(hit: _Hit, store: OverrideStore | None) -> dict[str, Any]:
    full = apply_overrides_to_dict(hit.node.to_dict(), store)
    payload = {
        key: full.get(key)
        for key in ("id", "type", "name", "description", "model_id", "report_id", "source_id", "status", "source")
    }
    payload["match"] = {
        "score": hit.score,
        "kind": hit.kind,
        "evidence": [
            {**item, "value": _excerpt(str(item["value"]), hit.node.name)}
            for item in hit.evidence
        ],
    }
    return payload


def retrieve_objects(
    repository: GraphRepository,
    query: str = "",
    *,
    object_type: str | Sequence[str] | None = None,
    model_id: str | Sequence[str] | None = None,
    report_id: str | Sequence[str] | None = None,
    status: str | Sequence[str] | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    store: OverrideStore | None = None,
) -> dict[str, Any]:
    """Return one exact, bounded result page with ranking evidence."""

    limit, offset = _validate_page(limit, offset)
    hits, scope = _ranked_hits(
        repository,
        query,
        object_type=object_type,
        model_id=model_id,
        report_id=report_id,
        status=status,
    )
    total = len(hits)
    page = hits[offset : offset + limit]
    next_offset = offset + len(page)
    has_more = next_offset < total
    return {
        "query": str(query or "").strip(),
        "scope": scope,
        "items": [_hit_payload(hit, store) for hit in page],
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": has_more,
        "next_offset": next_offset if has_more else None,
        "pagination": {
            "offset": offset,
            "limit": limit,
            "returned": len(page),
            "total": total,
            "total_is_exact": True,
            "has_more": has_more,
            "next_offset": next_offset if has_more else None,
        },
        "ambiguity": _ambiguity(hits, str(query or "").strip()),
    }


def resolve_object(
    repository: GraphRepository,
    reference: str,
    *,
    object_type: str | Sequence[str] | None = None,
    model_id: str | Sequence[str] | None = None,
    report_id: str | Sequence[str] | None = None,
    status: str | Sequence[str] | None = None,
    store: OverrideStore | None = None,
) -> dict[str, Any]:
    """Resolve a canonical ID or unique exact source/name reference.

    Ranked partial matches are returned as candidates and never silently
    promoted to a resolved identity.
    """

    reference = str(reference or "").strip()
    if not reference:
        raise ValueError("reference is required")
    hits, scope = _ranked_hits(
        repository,
        reference,
        object_type=object_type,
        model_id=model_id,
        report_id=report_id,
        status=status,
    )
    canonical = [hit for hit in hits if hit.kind == "exact_id"]
    exact = canonical or [
        hit
        for hit in hits
        if hit.kind in {"exact_source_id", "exact_name", "exact_properties_raw_source_name", "exact_properties_raw_source_id"}
    ]
    if len(exact) == 1:
        return {
            "status": "resolved",
            "reference": reference,
            "scope": scope,
            "object": apply_overrides_to_dict(exact[0].node.to_dict(), store),
            "match": _hit_payload(exact[0], store)["match"],
            "candidates": [],
        }
    candidates = exact if exact else hits[:5]
    return {
        "status": "ambiguous" if len(candidates) > 1 or hits else "not_found",
        "reference": reference,
        "scope": scope,
        "object": None,
        "match": None,
        "candidates": [_hit_payload(hit, store) for hit in candidates],
    }


def ranked_object_list(
    repository: GraphRepository,
    query: str = "",
    *,
    object_type: str | Sequence[str] | None = None,
    model_id: str | Sequence[str] | None = None,
    report_id: str | Sequence[str] | None = None,
    store: OverrideStore | None = None,
) -> list[dict[str, Any]]:
    """Compatibility shape for the original unpaginated search operation."""

    hits, _ = _ranked_hits(
        repository,
        query,
        object_type=object_type,
        model_id=model_id,
        report_id=report_id,
    )
    return [apply_overrides_to_dict(hit.node.to_dict(), store) for hit in hits]


__all__ = [
    "DEFAULT_LIMIT",
    "MAX_LIMIT",
    "ranked_object_list",
    "resolve_object",
    "retrieve_objects",
]
