"""Semantic trust-boundary and contradiction validation."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Mapping, Sequence

from . import ValidationIssue, ValidationResult, graph_values, item_dict, properties


_SEMANTIC_EDGE_TYPES = frozenset(
    {
        "CONTROLLED_BY",
        "HAS_OPTION",
        "DEFAULTS_TO",
        "SEMANTICALLY_MAPS_TO",
        "SIMILAR_TO",
        "CONFLICTS_WITH",
    }
)
_SEMANTIC_NODE_TYPES = frozenset(
    {"BUSINESS_CONCEPT", "SELECTOR", "SELECTOR_OPTION", "SEMANTIC_ASSERTION", "CONFLICT"}
)


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _value(record: Mapping[str, Any]) -> Any:
    props = properties(record)
    for key in ("value", "meaning", "concept", "role", "behavior", "alias"):
        if record.get(key) is not None:
            return record.get(key)
        if props.get(key) is not None:
            return props.get(key)
    return None


def _assertion_type(record: Mapping[str, Any]) -> str:
    props = properties(record)
    return _text(record.get("assertion_type") or props.get("assertion_type") or record.get("type")).upper()


def _target(record: Mapping[str, Any]) -> str | None:
    props = properties(record)
    for key in ("target", "target_id", "object_id", "source_object_id"):
        value = record.get(key, props.get(key))
        if value:
            return str(value)
    return None


def _is_truthy_conflict(record: Mapping[str, Any]) -> bool:
    props = properties(record)
    if _text(record.get("type")).upper() in {"CONFLICT", "CONFLICTS_WITH"}:
        return True
    if _assertion_type(record) == "CONFLICT":
        return True
    return bool(props.get("conflict") or props.get("contradiction"))


def _safe_marker(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _analysis_values(analyses: Any) -> Mapping[str, Any]:
    if analyses is None:
        return {}
    if isinstance(analyses, Mapping):
        values = analyses.get("analyses", analyses)
        return values if isinstance(values, Mapping) else {}
    values = getattr(analyses, "analyses", {})
    return values if isinstance(values, Mapping) else {}


def validate_semantics(value: Any, edges: Any = None, *, analyses: Any = None) -> ValidationResult:
    """Find contradictions and evidence-class violations.

    Semantic ambiguity is reported as a warning for human review.  A semantic
    assertion never upgrades itself into a factual graph edge here.
    """

    node_values, edge_values = graph_values(value, edges)
    nodes = [item_dict(item) for item in node_values]
    edge_records = [item_dict(item) for item in edge_values]
    result = ValidationResult()
    by_id = {str(node.get("id")): node for node in nodes if node.get("id") is not None}

    # Explicit conflict nodes/edges are reviewable semantic warnings.
    for node in nodes:
        node_id = str(node.get("id", ""))
        if _text(node.get("type")).upper() == "CONFLICT" or _is_truthy_conflict(node):
            _add_conflict(result, node, object_id=node_id)
        status = _text(node.get("status", "factual")).lower()
        if _text(node.get("evidence_class")).upper() == "OBSERVED":
            _add(result, "observed_node_class", "ERROR", "OBSERVED evidence belongs on an OBSERVED_WITH edge", object_id=node_id, evidence=[node])
        if _text(node.get("type")).upper() in _SEMANTIC_NODE_TYPES and status == "factual" and _assertion_type(node) == "CONFLICT":
            _add_conflict(result, node, object_id=node_id)

    for edge in edge_records:
        edge_id = str(edge.get("id", ""))
        edge_type = _text(edge.get("type")).upper()
        evidence_class = _text(edge.get("evidence_class", "FACT")).upper()
        if edge_type == "CONFLICTS_WITH" or _is_truthy_conflict(edge):
            _add_conflict(result, edge, edge_id=edge_id, object_id=_target(edge))
        if edge_type == "OBSERVED_WITH" and evidence_class != "OBSERVED":
            _add(result, "observed_evidence_mismatch", "ERROR", "OBSERVED_WITH must carry OBSERVED evidence", edge_id=edge_id, evidence=[edge])
        if evidence_class == "OBSERVED" and edge_type != "OBSERVED_WITH":
            _add(result, "observed_evidence_mismatch", "ERROR", "OBSERVED evidence cannot become semantic fact", edge_id=edge_id, evidence=[edge])
        if edge_type in _SEMANTIC_EDGE_TYPES and edge_type != "HAS_OPTION" and evidence_class == "FACT":
            _add(result, "semantic_fact_mismatch", "ERROR", f"Semantic edge {edge_type} cannot be labelled FACT", edge_id=edge_id, evidence=[edge])
        if edge_type in _SEMANTIC_EDGE_TYPES and evidence_class == "INFERRED" and _text(edge.get("status", "factual")).lower() == "factual":
            _add(result, "semantic_status_mismatch", "ERROR", "Inferred semantic edge cannot be factual", edge_id=edge_id, evidence=[edge])

    # Approved/candidate semantic meanings for one target must not silently
    # disagree.  Group edges and assertion nodes by stable target/type.
    assertions: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for node in nodes:
        type_name = _text(node.get("type")).upper()
        if type_name not in _SEMANTIC_NODE_TYPES or type_name == "CONFLICT":
            continue
        target = _target(node)
        if target:
            assertions[(target, _assertion_type(node))].append(node)
    for edge in edge_records:
        if _text(edge.get("type")).upper() not in _SEMANTIC_EDGE_TYPES:
            continue
        target = str(edge.get("from_id")) if edge.get("from_id") else _target(edge)
        assertion_type = _assertion_type(edge)
        if target and assertion_type:
            assertions[(target, assertion_type)].append(edge)
    for (target, assertion_type), records in sorted(assertions.items()):
        approved = [record for record in records if _text(record.get("status", "factual")).lower() == "approved"]
        candidates = [record for record in records if _text(record.get("status", "factual")).lower() == "candidate"]
        for group, code, severity in ((approved, "approved_semantic_contradiction", "WARNING"), (candidates, "candidate_semantic_ambiguity", "INFO")):
            values = {_safe_marker(_value(record)) for record in group if _value(record) is not None}
            if len(values) > 1:
                _add(result, code, severity, f"{assertion_type} has multiple meanings for {target}", object_id=target, evidence=list(group), assertion_type=assertion_type)

    # Optional existing analyzer output can surface unresolved semantic
    # evidence, but this pass still does not parse raw DAX.
    for source_id, analysis in sorted(_analysis_values(analyses).items(), key=lambda item: str(item[0])):
        diagnostics = analysis.get("diagnostics", []) if isinstance(analysis, Mapping) else getattr(analysis, "diagnostics", [])
        for diagnostic in diagnostics or []:
            if not isinstance(diagnostic, Mapping):
                continue
            code = _text(diagnostic.get("code")).lower()
            if code in {"semantic_conflict", "contradiction", "conflict"}:
                _add(result, "semantic_contradiction", "WARNING", f"Analyzer reported semantic contradiction for {source_id}", object_id=str(source_id), evidence=[diagnostic])
    return result


def validate_selector_semantics(value: Any, edges: Any = None) -> ValidationResult:
    """Validate selector/option/default edge shape and ownership."""

    node_values, edge_values = graph_values(value, edges)
    nodes = [item_dict(item) for item in node_values]
    edge_records = [item_dict(item) for item in edge_values]
    by_id = {str(node.get("id")): node for node in nodes if node.get("id") is not None}
    result = ValidationResult()
    options_by_selector: dict[str, set[str]] = defaultdict(set)
    selectors = {identifier for identifier, node in by_id.items() if _text(node.get("type")).upper() == "SELECTOR"}
    options = {identifier for identifier, node in by_id.items() if _text(node.get("type")).upper() == "SELECTOR_OPTION"}
    for edge in edge_records:
        edge_type = _text(edge.get("type")).upper()
        from_id = str(edge.get("from_id", ""))
        to_id = str(edge.get("to_id", ""))
        if edge_type == "HAS_OPTION":
            if from_id not in selectors or to_id not in options:
                _selector_issue(result, edge, "HAS_OPTION must connect SELECTOR to SELECTOR_OPTION", severity="ERROR")
            else:
                options_by_selector[from_id].add(to_id)
        elif edge_type == "DEFAULTS_TO":
            if from_id not in selectors or to_id not in options:
                _selector_issue(result, edge, "DEFAULTS_TO must connect SELECTOR to SELECTOR_OPTION", severity="ERROR")
            elif to_id not in options_by_selector.get(from_id, set()):
                _selector_issue(result, edge, "Selector default is not one of its options", severity="ERROR")

    for option_id in sorted(options):
        node = by_id[option_id]
        props = properties(node)
        selector_id = _text(props.get("selector_id") or props.get("selectorId"))
        owned = any(option_id in option_ids for option_ids in options_by_selector.values())
        if selector_id and selector_id in by_id and selector_id not in selectors:
            _selector_issue(result, node, "SELECTOR_OPTION selector_id is not a SELECTOR", severity="ERROR")
        elif not selector_id and not owned:
            _selector_issue(result, node, "SELECTOR_OPTION has no owning selector", severity="WARNING")
        elif selector_id and selector_id in selectors and not owned:
            _selector_issue(result, node, "SELECTOR_OPTION is not linked by HAS_OPTION", severity="WARNING")

    # Known selectors should have at least one option edge when option data is
    # claimed.  A selector without discovered values is uncertainty, not a
    # graph failure, so keep this warning-level.
    for selector_id in sorted(selectors):
        node = by_id[selector_id]
        props = properties(node)
        claimed_options = props.get("options") or props.get("option_ids") or props.get("optionIds")
        if claimed_options and not options_by_selector.get(selector_id):
            _selector_issue(result, node, "Selector claims options but has no HAS_OPTION edge", severity="ERROR")
    return result


def _selector_issue(result: ValidationResult, record: Mapping[str, Any], message: str, *, severity: str) -> None:
    is_edge = "from_id" in record or "to_id" in record
    result.add(
        ValidationIssue(
            "invalid_selector_semantics",
            severity,
            message,
            category="semantic_integrity",
            object_id=None if is_edge else str(record.get("id", "")),
            edge_id=str(record.get("id", "")) if is_edge else None,
            evidence=[record],
        )
    )


def _add_conflict(result: ValidationResult, record: Mapping[str, Any], *, object_id: str | None = None, edge_id: str | None = None) -> None:
    evidence = record.get("evidence", [])
    if not isinstance(evidence, list):
        evidence = [evidence]
    _add(result, "semantic_contradiction", "WARNING", _text(record.get("reason") or record.get("message") or "Semantic conflict requires review"), object_id=object_id, edge_id=edge_id, evidence=evidence)


def _add(result: ValidationResult, code: str, severity: str, message: str, *, object_id: str | None = None, edge_id: str | None = None, evidence: list[Any] | None = None, **details: Any) -> None:
    result.add(ValidationIssue(code, severity, message, category="semantic_integrity", object_id=object_id, edge_id=edge_id, evidence=evidence or [], details=details))


def validate_semantic_integrity(value: Any, edges: Any = None, *, analyses: Any = None) -> ValidationResult:
    result = validate_semantics(value, edges, analyses=analyses)
    result.extend(validate_selector_semantics(value, edges))
    unique: dict[tuple[str, str | None, str | None, str], ValidationIssue] = {}
    for issue in result.issues:
        unique.setdefault((issue.code, issue.object_id, issue.edge_id, issue.message), issue)
    result.issues = list(unique.values())
    return result


validate_semantic_contradictions = validate_semantics
validate_invalid_selector_semantics = validate_selector_semantics


__all__ = [
    "validate_invalid_selector_semantics",
    "validate_semantic_contradictions",
    "validate_semantic_integrity",
    "validate_selector_semantics",
    "validate_semantics",
]
