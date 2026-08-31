"""Structural, reference, and DAX dependency validation."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping, Sequence

from backend.graph.schema import EDGE_TYPES, OBJECT_TYPES, STATUS_VALUES, EVIDENCE_CLASSES

from . import ValidationIssue, ValidationResult, graph_values, item_dict, properties


_MODEL_TYPES = frozenset(
    {
        "TABLE",
        "COLUMN",
        "MEASURE",
        "RELATIONSHIP",
        "FIELD_PARAMETER",
        "SHARED_EXPRESSION",
        "USER_DEFINED_FUNCTION",
        "CALCULATION_GROUP",
        "CALCULATION_ITEM",
    }
)
_REPORT_TYPES = frozenset({"PAGE", "VISUAL", "VISUAL_FILTER", "PAGE_FILTER", "REPORT_FILTER"})
_DAX_SOURCE_TYPES = frozenset({"MEASURE", "CALCULATION_ITEM", "SHARED_EXPRESSION", "USER_DEFINED_FUNCTION", "COLUMN"})


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _id(value: Any) -> str | None:
    text = _text(value).strip()
    return text or None


def _add(
    result: ValidationResult,
    code: str,
    severity: str,
    message: str,
    *,
    category: str = "graph_integrity",
    object_id: str | None = None,
    edge_id: str | None = None,
    evidence: list[Any] | None = None,
    **details: Any,
) -> None:
    result.add(
        ValidationIssue(
            code,
            severity,
            message,
            category=category,
            object_id=object_id,
            edge_id=edge_id,
            evidence=evidence or [],
            details=details,
        )
    )


def _records(value: Any, edges: Any = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes, edge_values = graph_values(value, edges)
    return [item_dict(item) for item in nodes], [item_dict(item) for item in edge_values]


def _duplicate_ids(records: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for record in records:
        value = _id(record.get("id"))
        if value:
            counts[value] += 1
    return {key: count for key, count in counts.items() if count > 1}


def _edge_type(edge: Mapping[str, Any]) -> str:
    return _text(edge.get("type")).upper()


def _node_type(node: Mapping[str, Any]) -> str:
    return _text(node.get("type")).upper()


def _walk_cycles(adjacency: Mapping[str, set[str]]) -> list[list[str]]:
    cycles: list[list[str]] = []
    states: dict[str, int] = {}
    stack: list[str] = []

    def visit(node_id: str) -> None:
        states[node_id] = 1
        stack.append(node_id)
        for child in sorted(adjacency.get(node_id, set())):
            if states.get(child, 0) == 0:
                visit(child)
            elif states.get(child) == 1 and child in stack:
                start = stack.index(child)
                cycle = stack[start:] + [child]
                if cycle not in cycles:
                    cycles.append(cycle)
        stack.pop()
        states[node_id] = 2

    for node_id in sorted(adjacency):
        if states.get(node_id, 0) == 0:
            visit(node_id)
    return cycles


def validate_graph_integrity(value: Any, edges: Any = None) -> ValidationResult:
    """Check universal graph contracts and structural relationships.

    The function is deliberately read-only and accepts either a repository,
    ``FactGraph``, canonical mapping, or explicit node/edge iterables.
    """

    nodes, edge_records = _records(value, edges)
    result = ValidationResult()
    node_ids = {_id(node.get("id")) for node in nodes} - {None}

    for node_id, count in sorted(_duplicate_ids(nodes).items()):
        _add(result, "duplicate_node_id", "BLOCKING", f"Node id occurs {count} times: {node_id}", object_id=node_id)
    for edge_id, count in sorted(_duplicate_ids(edge_records).items()):
        _add(result, "duplicate_edge_id", "BLOCKING", f"Edge id occurs {count} times: {edge_id}", edge_id=edge_id)

    for index, node in enumerate(nodes):
        node_id = _id(node.get("id"))
        type_name = _node_type(node)
        if node_id is None:
            _add(result, "missing_node_id", "BLOCKING", f"Node at index {index} has no stable id")
        if not type_name:
            _add(result, "missing_node_type", "BLOCKING", f"Node {node_id or index} has no object type", object_id=node_id)
        elif type_name not in OBJECT_TYPES:
            # The ontology is extensible.  Unknown types are visible, not fatal.
            _add(result, "unknown_node_type", "INFO", f"Node uses extensible object type {type_name}", object_id=node_id)
        status = _text(node.get("status", "factual")).lower()
        if status not in STATUS_VALUES:
            _add(result, "invalid_node_status", "ERROR", f"Unsupported node status {status!r}", object_id=node_id)

    for index, edge in enumerate(edge_records):
        edge_id = _id(edge.get("id"))
        edge_type = _edge_type(edge)
        from_id = _id(edge.get("from_id", edge.get("from")))
        to_id = _id(edge.get("to_id", edge.get("to")))
        if edge_id is None:
            _add(result, "missing_edge_id", "BLOCKING", f"Edge at index {index} has no stable id")
        if not edge_type:
            _add(result, "missing_edge_type", "BLOCKING", f"Edge {edge_id or index} has no type", edge_id=edge_id)
        elif edge_type not in EDGE_TYPES:
            _add(result, "unknown_edge_type", "INFO", f"Edge uses extensible edge type {edge_type}", edge_id=edge_id)
        for role, endpoint in (("from", from_id), ("to", to_id)):
            if endpoint is None:
                _add(result, "missing_edge_endpoint", "BLOCKING", f"Edge {edge_id or index} has no {role} endpoint", edge_id=edge_id)
            elif endpoint not in node_ids:
                _add(
                    result,
                    "dangling_edge_endpoint",
                    "ERROR",
                    f"Edge {edge_id or index} points to missing {role} node {endpoint}",
                    edge_id=edge_id,
                    evidence=[{"edge_id": edge_id, "endpoint": role, "target": endpoint}],
                )
        status = _text(edge.get("status", "factual")).lower()
        if status not in STATUS_VALUES:
            _add(result, "invalid_edge_status", "ERROR", f"Unsupported edge status {status!r}", edge_id=edge_id)
        evidence_class = _text(edge.get("evidence_class", "FACT")).upper()
        if evidence_class not in EVIDENCE_CLASSES:
            _add(result, "invalid_evidence_class", "ERROR", f"Unsupported evidence class {evidence_class!r}", edge_id=edge_id)
        try:
            confidence = float(edge.get("confidence", 1.0))
            if not 0 <= confidence <= 1:
                raise ValueError
        except (TypeError, ValueError):
            _add(result, "invalid_edge_confidence", "ERROR", "Edge confidence must be between 0 and 1", edge_id=edge_id)
        if "source" not in edge or not _text(edge.get("source")).strip():
            _add(result, "missing_edge_provenance", "ERROR", "Edge has no provenance source", edge_id=edge_id)
        if "evidence" not in edge or not edge.get("evidence"):
            _add(result, "missing_edge_evidence", "WARNING", "Edge has no evidence payload", edge_id=edge_id)
        if evidence_class == "FACT" and status != "factual":
            _add(result, "fact_status_mismatch", "ERROR", "FACT edge must remain factual", edge_id=edge_id)
        if evidence_class == "INFERRED" and status == "factual":
            _add(result, "inference_status_mismatch", "ERROR", "INFERRED edge cannot masquerade as factual", edge_id=edge_id)
        if evidence_class == "OBSERVED" and edge_type != "OBSERVED_WITH":
            _add(result, "observed_type_mismatch", "ERROR", "OBSERVED evidence must use OBSERVED_WITH", edge_id=edge_id)
        if from_id and to_id and from_id == to_id and edge_type not in {"SIMILAR_TO", "OBSERVED_WITH"}:
            _add(result, "self_referential_edge", "WARNING", f"Edge {edge_id or index} points to itself", edge_id=edge_id)

    by_id = {_id(node.get("id")): node for node in nodes if _id(node.get("id"))}
    _validate_relationships(result, by_id, edge_records)
    _validate_containment(result, by_id, edge_records)
    _validate_orphans(result, by_id, edge_records)
    return result


def _validate_relationships(
    result: ValidationResult,
    by_id: Mapping[str, Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
) -> None:
    for node_id, node in sorted(by_id.items()):
        type_name = _node_type(node)
        props = properties(node)
        model_id = _id(node.get("model_id"))
        report_id = _id(node.get("report_id"))
        if type_name in _MODEL_TYPES and model_id and model_id not in by_id:
            _add(result, "missing_model_reference", "ERROR", f"Object references missing model {model_id}", object_id=node_id, model_id=model_id)
        if type_name in _MODEL_TYPES and model_id and _node_type(by_id[model_id]) != "MODEL":
            _add(result, "invalid_model_reference", "ERROR", f"Object model_id is not a MODEL: {model_id}", object_id=node_id, model_id=model_id)
        if type_name in _REPORT_TYPES and report_id and report_id not in by_id:
            _add(result, "missing_report_reference", "ERROR", f"Report object references missing report {report_id}", object_id=node_id, report_id=report_id)
        if type_name in _REPORT_TYPES and report_id and _node_type(by_id[report_id]) != "REPORT":
            _add(result, "invalid_report_reference", "ERROR", f"Object report_id is not a REPORT: {report_id}", object_id=node_id, report_id=report_id)

        table_id = _id(props.get("table_id", props.get("tableId")))
        if type_name in {"COLUMN", "MEASURE"} and table_id:
            if table_id not in by_id:
                _add(result, "missing_table_reference", "ERROR", f"Object references missing table {table_id}", object_id=node_id, table_id=table_id)
            elif _node_type(by_id[table_id]) != "TABLE":
                _add(result, "invalid_table_reference", "ERROR", f"Object table_id is not a TABLE: {table_id}", object_id=node_id, table_id=table_id)
            elif model_id and _id(by_id[table_id].get("model_id")) not in {None, model_id}:
                _add(result, "cross_model_table_reference", "ERROR", f"Object table and model scopes differ", object_id=node_id, table_id=table_id)

        parent_id = _id(props.get("parent_id", props.get("parentId")))
        if type_name in _REPORT_TYPES and parent_id and parent_id not in by_id:
            _add(result, "missing_parent_reference", "ERROR", f"Report object references missing parent {parent_id}", object_id=node_id, parent_id=parent_id)

        if type_name == "RELATIONSHIP":
            endpoint_values = [
                ("from_column_id", props.get("from_column_id", props.get("fromColumnId"))),
                ("to_column_id", props.get("to_column_id", props.get("toColumnId"))),
            ]
            for key, raw_endpoint in endpoint_values:
                endpoint = _id(raw_endpoint)
                if endpoint is None or endpoint not in by_id:
                    _add(result, "missing_relationship_endpoint", "ERROR", f"Relationship endpoint is missing: {endpoint or key}", object_id=node_id, endpoint=endpoint)
                elif _node_type(by_id[endpoint]) != "COLUMN":
                    _add(result, "invalid_relationship_endpoint", "ERROR", f"Relationship endpoint is not a COLUMN: {endpoint}", object_id=node_id, endpoint=endpoint)

        for key in ("referenced_object_ids", "referencedObjectIds", "field_ids", "fieldIds", "measure_ids", "measureIds", "column_ids", "columnIds"):
            values = props.get(key)
            if values is None:
                continue
            if not isinstance(values, (list, tuple, set, frozenset)):
                values = [values]
            for target in values:
                target_id = _id(target.get("id") if isinstance(target, Mapping) else target)
                if target_id and target_id not in by_id:
                    _add(result, "missing_object_reference", "ERROR", f"Object references missing object {target_id}", object_id=node_id, target_id=target_id, property=key)

        if type_name == "VISUAL":
            unresolved = props.get("unresolved_field_refs", [])
            if not isinstance(unresolved, (list, tuple)):
                unresolved = [unresolved]
            for reference in unresolved:
                ref = reference.get("reference") if isinstance(reference, Mapping) else reference
                _add(
                    result,
                    "missing_object_reference",
                    "ERROR",
                    f"Visual binding could not resolve object reference {ref!r}",
                    object_id=node_id,
                    evidence=[reference],
                    target_ref=ref,
                )

        if type_name in {"VISUAL_FILTER", "PAGE_FILTER", "REPORT_FILTER"}:
            unresolved = props.get("unresolved_target")
            target_id = _id(props.get("target_id"))
            target_ref = props.get("target_ref")
            if unresolved is not None or (target_ref is not None and target_id is None):
                _add(
                    result,
                    "missing_object_reference",
                    "ERROR",
                    f"Filter target could not resolve object reference {target_ref!r}",
                    object_id=node_id,
                    evidence=[unresolved or {"reference": target_ref}],
                    target_ref=target_ref,
                )

    for edge in edges:
        edge_id = _id(edge.get("id"))
        edge_type = _edge_type(edge)
        from_id = _id(edge.get("from_id", edge.get("from")))
        to_id = _id(edge.get("to_id", edge.get("to")))
        source = by_id.get(from_id or "")
        target = by_id.get(to_id or "")
        if source is None or target is None:
            continue
        source_type = _node_type(source)
        target_type = _node_type(target)
        if edge_type == "CONTAINS":
            _validate_contains_pair(result, source_type, target_type, edge_id, from_id, to_id)
        elif edge_type == "USES_MODEL" and (source_type != "REPORT" or target_type != "MODEL"):
            _add(result, "invalid_model_binding", "ERROR", "USES_MODEL must connect REPORT to MODEL", edge_id=edge_id)
        elif edge_type == "USES" and source_type == "VISUAL" and target_type not in _MODEL_TYPES:
            _add(result, "invalid_visual_binding", "ERROR", "Visual USES edge must target a model object", edge_id=edge_id)
        elif edge_type == "FILTERS" and source_type not in {"VISUAL_FILTER", "PAGE_FILTER", "REPORT_FILTER"}:
            _add(result, "invalid_filter_binding", "ERROR", "FILTERS edge must originate from a filter object", edge_id=edge_id)
        elif edge_type == "RELATES_TO" and source_type != "RELATIONSHIP" and target_type != "RELATIONSHIP":
            _add(result, "invalid_relationship_edge", "ERROR", "RELATES_TO edge must include a RELATIONSHIP node", edge_id=edge_id)


def _validate_contains_pair(
    result: ValidationResult,
    source_type: str,
    target_type: str,
    edge_id: str | None,
    from_id: str | None,
    to_id: str | None,
) -> None:
    allowed = {
        "MODEL": _MODEL_TYPES | {"TABLE"},
        "TABLE": {"COLUMN", "MEASURE"},
        "CALCULATION_GROUP": {"CALCULATION_ITEM"},
        "REPORT": {"PAGE"},
        "PAGE": {"VISUAL", "PAGE_FILTER"},
        "VISUAL": {"VISUAL_FILTER"},
    }
    if source_type in allowed and target_type not in allowed[source_type]:
        _add(result, "invalid_containment", "ERROR", f"{source_type} cannot contain {target_type}", edge_id=edge_id, from_id=from_id, to_id=to_id)


def _validate_containment(result: ValidationResult, by_id: Mapping[str, Mapping[str, Any]], edges: Sequence[Mapping[str, Any]]) -> None:
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        if _edge_type(edge) != "CONTAINS":
            continue
        from_id = _id(edge.get("from_id", edge.get("from")))
        to_id = _id(edge.get("to_id", edge.get("to")))
        if from_id and to_id:
            adjacency[from_id].add(to_id)
    for cycle in _walk_cycles(adjacency):
        _add(result, "containment_cycle", "BLOCKING", "Containment graph contains a cycle", object_id=cycle[0], path=cycle)


def _validate_orphans(
    result: ValidationResult,
    by_id: Mapping[str, Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
) -> None:
    """Report canonical objects that lost their structural parent."""

    incoming: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for edge in edges:
        to_id = _id(edge.get("to_id", edge.get("to")))
        if to_id:
            incoming[to_id].append(edge)
    expected_parent = {
        "TABLE": {"MODEL"},
        "RELATIONSHIP": {"MODEL"},
        "FIELD_PARAMETER": {"MODEL"},
        "SHARED_EXPRESSION": {"MODEL"},
        "USER_DEFINED_FUNCTION": {"MODEL"},
        "CALCULATION_GROUP": {"MODEL"},
        "COLUMN": {"TABLE"},
        "MEASURE": {"TABLE", "MODEL"},
        "CALCULATION_ITEM": {"CALCULATION_GROUP"},
        "PAGE": {"REPORT"},
        "VISUAL": {"PAGE"},
        "VISUAL_FILTER": {"VISUAL"},
        "PAGE_FILTER": {"PAGE"},
        "REPORT_FILTER": {"REPORT"},
    }
    for node_id, node in sorted(by_id.items()):
        type_name = _node_type(node)
        if type_name not in expected_parent:
            continue
        parents = {
            _node_type(by_id.get(_id(edge.get("from_id", edge.get("from"))) or {}))
            for edge in incoming.get(node_id, [])
            if _edge_type(edge) == "CONTAINS"
        }
        if parents.isdisjoint(expected_parent[type_name]):
            _add(
                result,
                "orphan_object",
                "WARNING",
                f"{type_name} has no expected CONTAINS parent",
                object_id=node_id,
                object_type=type_name,
            )


def validate_reference_integrity(value: Any, edges: Any = None) -> ValidationResult:
    """Validate model/report references and bindings without DAX parsing."""

    full = validate_graph_integrity(value, edges)
    result = ValidationResult([issue for issue in full.issues if issue.code in {
        "missing_model_reference", "invalid_model_reference", "missing_report_reference", "invalid_report_reference",
        "missing_table_reference", "invalid_table_reference", "cross_model_table_reference", "missing_parent_reference",
        "missing_relationship_endpoint", "invalid_relationship_endpoint", "missing_object_reference", "invalid_model_binding",
        "invalid_visual_binding", "invalid_filter_binding", "invalid_relationship_edge", "invalid_containment",
    }])
    return result


def validate_dax_dependencies(value: Any, edges: Any = None, *, analyses: Any = None) -> ValidationResult:
    """Validate dependency edges and existing analyzer output.

    Analyzer results are consumed as supplied.  This function never reparses
    DAX expressions.
    """

    nodes, edge_records = _records(value, edges)
    result = ValidationResult()
    by_id = {_id(node.get("id")): node for node in nodes if _id(node.get("id"))}
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in edge_records:
        if _edge_type(edge) != "DEPENDS_ON":
            continue
        edge_id = _id(edge.get("id"))
        from_id = _id(edge.get("from_id", edge.get("from")))
        to_id = _id(edge.get("to_id", edge.get("to")))
        if from_id and to_id:
            adjacency[from_id].add(to_id)
        if from_id not in by_id or to_id not in by_id:
            _add(result, "broken_dax_dependency", "ERROR", "DEPENDS_ON points to a missing object", edge_id=edge_id, from_id=from_id, to_id=to_id)
            continue
        if _node_type(by_id[from_id]) not in _DAX_SOURCE_TYPES:
            _add(result, "invalid_dax_dependency_source", "ERROR", "DEPENDS_ON source is not an expression object", edge_id=edge_id, from_id=from_id)
    for cycle in _walk_cycles(adjacency):
        _add(result, "dax_dependency_cycle", "BLOCKING", "DAX dependency graph contains a cycle", object_id=cycle[0], path=cycle)

    if analyses is not None:
        analysis_values = analyses.get("analyses", analyses) if isinstance(analyses, Mapping) else getattr(analyses, "analyses", {})
        if isinstance(analysis_values, Mapping):
            for source_id, analysis in sorted(analysis_values.items(), key=lambda item: str(item[0])):
                records = analysis.get("references", []) if isinstance(analysis, Mapping) else getattr(analysis, "references", [])
                for reference in records or []:
                    if not isinstance(reference, Mapping):
                        continue
                    target = reference.get("target") or reference.get("target_id")
                    if target:
                        continue
                    if str(reference.get("scope", "")).casefold() == "variable":
                        continue
                    _add(
                        result,
                        "unresolved_dax_reference",
                        "ERROR",
                        f"Analyzer could not resolve DAX reference in {source_id}",
                        object_id=str(source_id),
                        evidence=[reference],
                    )
                diagnostics = analysis.get("diagnostics", []) if isinstance(analysis, Mapping) else getattr(analysis, "diagnostics", [])
                for diagnostic in diagnostics or []:
                    code = str(diagnostic.get("code", "")) if isinstance(diagnostic, Mapping) else str(getattr(diagnostic, "code", ""))
                    if code in {"parse_error", "parser_unavailable"}:
                        _add(result, "dax_parse_failure", "ERROR", f"DAX analysis failed for {source_id}", object_id=str(source_id), evidence=[diagnostic])
    else:
        # Scanner persistence keeps analyzer diagnostics on the canonical
        # expression node.  Consume those records directly; do not reparse
        # the stored expression.
        for source_id, node in sorted(by_id.items()):
            diagnostics = properties(node).get("dax_diagnostics", [])
            if not isinstance(diagnostics, (list, tuple)):
                diagnostics = [diagnostics]
            for diagnostic in diagnostics:
                if not isinstance(diagnostic, Mapping):
                    continue
                code = _text(diagnostic.get("code")).lower()
                if code == "unresolved_reference":
                    _add(result, "unresolved_dax_reference", "ERROR", f"Analyzer could not resolve DAX reference in {source_id}", object_id=source_id, evidence=[diagnostic])
                elif code in {"parse_error", "parser_unavailable"}:
                    _add(result, "dax_parse_failure", "ERROR", f"DAX analysis failed for {source_id}", object_id=source_id, evidence=[diagnostic])
    return result


def validate_source_disappearance(
    previous: Any,
    current: Any = None,
    *,
    changes: Any = None,
    previous_edges: Any = None,
) -> ValidationResult:
    """Report stable source objects that disappeared between scans."""

    old_nodes, old_edges = graph_values(previous)
    if current is not None:
        new_nodes, _ = graph_values(current)
    else:
        new_nodes = []
    old_records = [item_dict(item) for item in old_nodes]
    new_records = [item_dict(item) for item in new_nodes]
    old_ids = {_id(item.get("id")) for item in old_records} - {None}
    new_ids = {_id(item.get("id")) for item in new_records} - {None}
    deleted_ids = old_ids - new_ids if current is not None else set()
    deleted_records: list[Mapping[str, Any]] = []

    # A SyncResult/ChangeSet can carry deletion records even when the caller
    # does not retain the previous graph object.
    change_value = changes
    if change_value is None:
        change_value = getattr(previous, "changes", None)
    if change_value is None and isinstance(previous, Mapping):
        change_value = previous.get("changes") or previous.get("change_records")
    if change_value is not None:
        raw_changes = getattr(change_value, "records", change_value)
        if isinstance(raw_changes, Mapping):
            raw_changes = raw_changes.get("DELETED", raw_changes.get("deleted", []))
        if not isinstance(raw_changes, (list, tuple, set, frozenset)):
            raw_changes = [raw_changes]
        for raw in raw_changes:
            record = item_dict(raw) if not isinstance(raw, Mapping) else dict(raw)
            status = _text(record.get("status", record.get("state", ""))).upper()
            if status != "DELETED":
                continue
            identifier = _id(record.get("id", record.get("object_id")))
            if identifier:
                deleted_ids.add(identifier)
                deleted_records.append(record)

    previous_edge_values = previous_edges if previous_edges is not None else old_edges
    previous_edge_records = [item_dict(item) for item in previous_edge_values]
    result = ValidationResult()
    for identifier in sorted(deleted_ids):
        record = next((item for item in old_records if _id(item.get("id")) == identifier), None)
        source_id = (record or {}).get("source_id")
        dependents = sorted(
            {
                _id(edge.get("from_id", edge.get("from")))
                for edge in previous_edge_records
                if _id(edge.get("to_id", edge.get("to"))) == identifier
                and _id(edge.get("from_id", edge.get("from")))
            }
        )
        evidence: list[Any] = [{"source": "source_metadata", "object_id": identifier, "source_id": source_id}]
        if dependents:
            evidence.append({"source": "graph_integrity", "dependent_ids": dependents})
        result.add(
            ValidationIssue(
                "source_disappearance",
                "WARNING",
                f"Source object disappeared: {identifier}",
                category="source_integrity",
                object_id=identifier,
                evidence=evidence,
                details={"source_id": source_id, "dependent_ids": dependents, "status": "DELETED"},
            )
        )
    return result


validate_graph = validate_graph_integrity
validate_references = validate_reference_integrity
validate_dependencies = validate_dax_dependencies
validate_source_disappearances = validate_source_disappearance


__all__ = [
    "validate_dax_dependencies",
    "validate_dependencies",
    "validate_graph",
    "validate_graph_integrity",
    "validate_reference_integrity",
    "validate_references",
    "validate_source_disappearance",
    "validate_source_disappearances",
]
