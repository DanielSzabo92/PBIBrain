"""Phase 3 semantic inference over canonical nodes and Phase 2 results."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import inspect
import json
import logging
import re
from collections.abc import Iterable, Mapping
from typing import Any

from backend.graph.schema import Edge, Node, edge_from_dict, node_from_dict

from .confidence import confidence_breakdown, confidence_from_evidence
from .semantics import (
    SemanticCandidate,
    SemanticConflict,
    detect_conflicts,
    edge_for,
    infer_candidates,
    make_candidate,
    make_evidence,
    semantic_node_for,
)

LOGGER = logging.getLogger(__name__)


def _safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_safe(item) for item in value]
    return str(value)


def _json(value: Any) -> str:
    return json.dumps(_safe(value), ensure_ascii=False, sort_keys=True, default=str)


def _get(value: Any, *keys: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        for key in keys:
            if key in value and value[key] is not None:
                return value[key]
        return default
    for key in keys:
        candidate = getattr(value, key, None)
        if candidate is not None:
            return candidate
    return default


def _hash(*parts: Any) -> str:
    return hashlib.sha256("|".join(_json(part) for part in parts).encode("utf-8")).hexdigest()[:32]


def _node_values(nodes: Iterable[Node] | Mapping[str, Node]) -> list[Node]:
    values = nodes.values() if isinstance(nodes, Mapping) else nodes
    return sorted(
        (value if isinstance(value, Node) else node_from_dict(value) for value in values),
        key=lambda item: str(item.id),
    )


def _analysis_values(analysis: Any) -> dict[str, Any]:
    if analysis is None:
        return {}
    values = _get(analysis, "analyses", default=analysis)
    if not isinstance(values, Mapping):
        return {}
    return {str(key): value for key, value in values.items()}


def _edge_values(value: Any) -> list[Edge]:
    if value is None:
        return []
    values = _get(value, "edges", "facts", "observations", default=value)
    if isinstance(values, Mapping):
        values = values.values()
    if not isinstance(values, (list, tuple, set, frozenset)):
        values = [values]
    result: list[Edge] = []
    for item in values:
        result.append(item if isinstance(item, Edge) else edge_from_dict(item))
    return result


def _candidate_values(value: Any) -> list[Any]:
    if value is None:
        return []
    values = _get(value, "candidates", "semantic_candidates", "assertions", default=value)
    if isinstance(values, Mapping):
        values = values.values()
    if not isinstance(values, (list, tuple, set, frozenset)):
        values = [values]
    return list(values)


def _as_candidate(value: Any, nodes: Mapping[str, Node]) -> SemanticCandidate | None:
    if isinstance(value, SemanticCandidate):
        return value
    target = _get(value, "target", "target_id", "object", "object_id", "source_object")
    if target is None:
        return None
    assertion_type = _get(value, "type", "assertion_type", "assertion", "kind", default="BUSINESS_CONCEPT")
    semantic_value = _get(value, "value", "meaning", "concept", "role", "behavior", "alias")
    if semantic_value is None:
        target_node = nodes.get(str(target))
        semantic_value = target_node.name if target_node else str(target)
    source = str(_get(value, "source", "origin", default="inference"))
    evidence = _get(value, "evidence", "provenance", default=[])
    if isinstance(evidence, Mapping):
        evidence = [evidence]
    if not isinstance(evidence, (list, tuple)):
        evidence = [evidence]
    status = str(_get(value, "status", default="candidate"))
    edge_type = str(_get(value, "edge_type", "relationship", default="SEMANTICALLY_MAPS_TO"))
    props = _get(value, "properties", default={})
    if not isinstance(props, Mapping):
        props = {}
    props = dict(props)
    for key in ("selector_id", "column_ids", "measure_ids", "table_id", "consumer_ids", "options"):
        candidate_value = _get(value, key)
        if candidate_value is not None:
            props.setdefault(key, candidate_value)
    confidence = _get(value, "confidence", default=None)
    return make_candidate(
        str(target),
        assertion_type=str(assertion_type),
        value=semantic_value,
        source=source,
        evidence=evidence,
        confidence=float(confidence) if confidence is not None else None,
        edge_type=edge_type,
        status=status,
        properties=props,
    )


def _reference_target_ids(analysis: Any) -> list[str]:
    refs = _get(analysis, "references", default=[])
    if not isinstance(refs, (list, tuple)):
        return []
    return [str(target) for item in refs if (target := _get(item, "target", "target_id"))]


def _behavior_list(analysis: Any, node: Node) -> list[Mapping[str, Any]]:
    values = _get(analysis, "behaviors", default=node.properties.get("dax_behaviors", []))
    if not isinstance(values, (list, tuple)):
        return []
    return [item for item in values if isinstance(item, Mapping)]


def _disconnected_tables(nodes: list[Node], edges: list[Edge]) -> dict[str, Node]:
    tables = {node.id: node for node in nodes if node.type == "TABLE"}
    columns = {node.id: node for node in nodes if node.type == "COLUMN"}
    related: set[str] = set()
    for edge in edges:
        if edge.type != "RELATES_TO":
            continue
        for endpoint in (edge.from_id, edge.to_id):
            column = columns.get(endpoint)
            if column:
                table_id = column.properties.get("table_id")
                if table_id:
                    related.add(str(table_id))
    return {table_id: table for table_id, table in tables.items() if table_id not in related}


def _column_table(nodes: Mapping[str, Node], column: Node) -> Node | None:
    table_id = column.properties.get("table_id")
    table = nodes.get(str(table_id)) if table_id else None
    return table if table and table.type == "TABLE" else None


def _column_values(column: Node) -> list[Any]:
    for key in ("values", "distinct_values", "distinctValues", "options", "allowed_values", "allowedValues"):
        value = column.properties.get(key)
        if isinstance(value, (list, tuple, set, frozenset)):
            return sorted(list(value), key=lambda item: _json(item))
    for key in ("cardinality", "distinct_count", "distinctCount"):
        value = column.properties.get(key)
        if isinstance(value, (list, tuple, set, frozenset)):
            return sorted(list(value), key=lambda item: _json(item))
    return []


def _fallback_selector_candidates(
    nodes: list[Node], analyses: Mapping[str, Any], edges: list[Edge]
) -> list[SemanticCandidate]:
    """Behavior + structure selector heuristic used when no adapter helper exists."""

    by_id = {node.id: node for node in nodes}
    disconnected = _disconnected_tables(nodes, edges)
    hits: dict[str, set[str]] = {}
    columns_by_table: dict[str, set[str]] = {}
    evidence_by_table: dict[str, list[Any]] = {}
    for source_id, analysis in sorted(analyses.items()):
        source = by_id.get(source_id)
        if source is None or source.type not in {"MEASURE", "CALCULATION_ITEM", "COLUMN"}:
            continue
        behaviors = _behavior_list(analysis, source)
        selector_behaviors = [
            behavior
            for behavior in behaviors
            if str(_get(behavior, "function", "type", default="")).upper()
            in {"SELECTEDVALUE", "VALUES", "HASONEVALUE", "ISFILTERED", "ISCROSSFILTERED", "FILTERS", "SELECTOR_CONSTRUCT"}
        ]
        if not selector_behaviors:
            continue
        for behavior in selector_behaviors:
            target_ids = _get(behavior, "target_ids", "targetIds", "targets", default=[])
            if isinstance(target_ids, Mapping):
                target_ids = _get(target_ids, "id", "target", "target_id", default=[])
            if not isinstance(target_ids, (list, tuple, set, frozenset)):
                target_ids = [target_ids]
            target_ids = [str(value) for value in target_ids if value]
            if not target_ids:
                target_ids = _reference_target_ids(analysis)
            for target_id in target_ids:
                target = by_id.get(target_id)
                table = _column_table(by_id, target) if target and target.type == "COLUMN" else target if target and target.type == "TABLE" else None
                if table is None or table.id not in disconnected:
                    continue
                hits.setdefault(table.id, set()).add(source.id)
                if target.type == "COLUMN":
                    columns_by_table.setdefault(table.id, set()).add(target.id)
                function = str(_get(behavior, "function", "type", default="SELECTOR_CONSTRUCT")).upper()
                evidence_by_table.setdefault(table.id, []).append(
                    make_evidence(
                        "dax_analysis",
                        extractor=str(_get(behavior, "extractor", default="selector_behavior")),
                        evidence=f"{function} references {target.name if target else target_id}",
                        target=table.id,
                        ast_location=_get(behavior, "ast_location"),
                    )
                )
    result: list[SemanticCandidate] = []
    for table_id in sorted(hits):
        table = disconnected[table_id]
        source_count = len(hits[table_id])
        structural = make_evidence(
            "structural",
            extractor="disconnected_table",
            evidence="table has no physical relationship",
            target=table_id,
        )
        usage = make_evidence(
            "dax_analysis",
            extractor="selector_measure_usage",
            evidence=f"referenced by {source_count} expression object(s)",
            target=table_id,
        )
        evidence = [structural, usage, *evidence_by_table.get(table_id, [])]
        result.append(
            make_candidate(
                table_id,
                assertion_type="SELECTOR",
                value=table.name,
                source="dax_analysis",
                evidence=evidence,
                edge_type="CONTROLLED_BY",
                properties={
                    "table_id": table_id,
                    "column_ids": sorted(columns_by_table.get(table_id, set())),
                    "consumer_ids": sorted(hits[table_id]),
                    "selector_id": f"semantic:selector:{_hash(table_id)}",
                    "selector_node_id": f"semantic:selector:{_hash(table_id)}",
                    "priority": 2,
                },
            )
        )
    return result


def _invoke(function: Any, nodes: list[Node], analyses: Mapping[str, Any], edges: list[Edge]) -> Any:
    """Call a helper while accepting the small public API variants used by workers."""

    attempts = (
        ((nodes,), {"analyses": analyses, "edges": edges}),
        ((nodes,), {"dax_analysis": analyses, "edges": edges}),
        ((nodes, analyses, edges), {}),
        ((nodes, edges), {}),
        ((nodes,), {}),
    )
    try:
        signature = inspect.signature(function)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"Cannot inspect inference helper {function!r}") from exc
    for args, kwargs in attempts:
        try:
            signature.bind(*args, **kwargs)
        except TypeError:
            continue
        # Do not catch TypeError here.  A helper's internal TypeError is a
        # real implementation failure and must reach the caller.
        return function(*args, **kwargs)
    raise TypeError(f"Inference helper {function!r} has no supported signature")


def _module_candidates(module: Any, nodes: list[Node], analyses: Mapping[str, Any], edges: list[Edge]) -> tuple[list[Any], list[Edge]]:
    for name in (
        "discover_selector_candidates",
        "discover_selectors",
        "infer_selectors",
        "selector_candidates",
        "analyze_selectors",
    ):
        function = getattr(module, name, None)
        if not callable(function):
            continue
        result = _invoke(function, nodes, analyses, edges)
        return _candidate_values(result), _edge_values(result)
    return [], []


def _module_observations(module: Any, nodes: list[Node], analyses: Mapping[str, Any], edges: list[Edge]) -> tuple[list[Any], list[Edge]]:
    for name in (
        "analyze_report_usage",
        "report_usage",
        "discover_report_usage",
        "observed_usage",
        "usage_observations",
    ):
        function = getattr(module, name, None)
        if not callable(function):
            continue
        result = _invoke(function, nodes, analyses, edges)
        return _candidate_values(result), _edge_values(result)
    return [], []


def _module_options(module: Any, selector_values: list[Any], nodes: list[Node]) -> list[Any]:
    for name in ("discover_selector_options", "selector_options", "infer_selector_options"):
        function = getattr(module, name, None)
        if not callable(function):
            continue
        attempts = (
            ((selector_values, nodes), {}),
            ((selector_values,), {"nodes": nodes}),
            ((selector_values,), {}),
        )
        try:
            signature = inspect.signature(function)
        except (TypeError, ValueError) as exc:
            raise TypeError(f"Cannot inspect selector option helper {function!r}") from exc
        for args, kwargs in attempts:
            try:
                signature.bind(*args, **kwargs)
            except TypeError:
                continue
            return _candidate_values(function(*args, **kwargs))
        raise TypeError(f"Selector option helper {function!r} has no supported signature")
    return []


def _module_defaults(module: Any, analyses: Mapping[str, Any]) -> list[Any]:
    for name in ("infer_selector_defaults", "discover_selector_defaults", "selector_defaults"):
        function = getattr(module, name, None)
        if not callable(function):
            continue
        return _candidate_values(function(analyses))
    return []


def _coerce_observation(value: Any, nodes: Mapping[str, Node]) -> Edge | None:
    if isinstance(value, Edge):
        if value.type != "OBSERVED_WITH":
            return None
        return value
    edge_type = str(_get(value, "type", "edge_type", default="OBSERVED_WITH")).upper()
    if edge_type != "OBSERVED_WITH":
        return None
    from_id = _get(value, "from_id", "from", "source_object", "left")
    to_id = _get(value, "to_id", "to", "target", "right")
    if from_id is None or to_id is None or str(from_id) not in nodes or str(to_id) not in nodes:
        return None
    evidence = _get(value, "evidence", default=[])
    if isinstance(evidence, Mapping):
        evidence = [evidence]
    if not isinstance(evidence, (list, tuple)):
        evidence = [evidence]
    evidence = [
        dict(item, status="candidate", evidence_class="OBSERVED") if isinstance(item, Mapping) else item
        for item in evidence
    ]
    confidence = float(_get(value, "confidence", default=0.0) or 0.0)
    marker = _hash("OBSERVED_WITH", from_id, to_id)
    return Edge(
        id=f"edge:observed:{marker}",
        type="OBSERVED_WITH",
        from_id=str(from_id),
        to_id=str(to_id),
        source=str(_get(value, "source", default="report_usage")),
        confidence=max(0.0, min(1.0, confidence)),
        status="candidate",
        evidence=evidence,
        evidence_class="OBSERVED",
        properties={"observation": True},
    )


def _with_ast_location(evidence: Any, fallback: Any = None) -> Any:
    if not isinstance(evidence, Mapping):
        return evidence
    result = dict(evidence)
    if result.get("ast_location") or result.get("location"):
        return result
    nested = result.get("behavior")
    if isinstance(nested, Mapping):
        nested = [nested]
    if isinstance(nested, (list, tuple)):
        for item in nested:
            if isinstance(item, Mapping):
                location = item.get("ast_location") or item.get("location")
                if location:
                    result["ast_location"] = _safe(location)
                    break
    if not result.get("ast_location") and fallback:
        result["ast_location"] = _safe(fallback)
    return result


def _normalize_candidate_evidence(candidate: SemanticCandidate, fallback: Any = None) -> None:
    fallback = candidate.properties.get("ast_location") or fallback
    candidate.evidence = [
        _with_ast_location(item, fallback)
        if isinstance(item, Mapping) and str(item.get("source", "")).casefold() in {"dax_ast", "dax_analysis"}
        else item
        for item in candidate.evidence
    ]


def _normalize_edge_evidence(edge: Edge, fallback: Any = None) -> Edge:
    evidence = []
    for item in edge.evidence:
        if isinstance(item, Mapping) and str(item.get("source", "")).casefold() in {"dax_ast", "dax_analysis"}:
            evidence.append(_with_ast_location(item, fallback))
        else:
            evidence.append(item)
    edge.evidence = evidence
    return edge


def _first_ast_location(value: Any) -> Any:
    if isinstance(value, Mapping):
        for key in ("ast_location", "location"):
            if value.get(key):
                return value[key]
        for child in value.values():
            location = _first_ast_location(child)
            if location:
                return location
    elif isinstance(value, (list, tuple, set, frozenset)):
        for child in value:
            location = _first_ast_location(child)
            if location:
                return location
    return None


def _scope_for_candidate(
    candidate: SemanticCandidate,
    source_nodes: Mapping[str, Node],
    selector_scopes: Mapping[str, tuple[str | None, str | None]],
) -> tuple[str | None, str | None]:
    target = source_nodes.get(candidate.target)
    if target is not None:
        return target.model_id, target.report_id
    for key in ("table_id", "column_id", "selector_id", "selector_node_id"):
        value = candidate.properties.get(key)
        if value is None:
            continue
        scoped = selector_scopes.get(str(value))
        if scoped is not None:
            return scoped
        source = source_nodes.get(str(value))
        if source is not None:
            return source.model_id, source.report_id
    return candidate.properties.get("model_id"), candidate.properties.get("report_id")


@dataclass(slots=True)
class InferenceResult:
    """Semantic output kept separate from the factual graph input."""

    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    candidates: list[SemanticCandidate] = field(default_factory=list)
    observations: list[Edge] = field(default_factory=list)
    conflicts: list[SemanticConflict] = field(default_factory=list)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)

    @property
    def semantic_candidates(self) -> list[SemanticCandidate]:
        return self.candidates

    @property
    def assertions(self) -> list[SemanticCandidate]:
        return self.candidates

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [node.to_dict() for node in sorted(self.nodes, key=lambda item: item.id)],
            "edges": [edge.to_dict() for edge in sorted(self.edges, key=lambda item: item.id)],
            "candidates": [item.to_dict() for item in sorted(self.candidates, key=lambda item: item.id)],
            "semantic_candidates": [item.to_dict() for item in sorted(self.candidates, key=lambda item: item.id)],
            "observations": [item.to_dict() for item in sorted(self.observations, key=lambda item: item.id)],
            "conflicts": [item.to_dict() for item in sorted(self.conflicts, key=lambda item: item.id)],
            "diagnostics": sorted(self.diagnostics, key=lambda item: _json(item)),
        }

    as_dict = to_dict

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.to_dict().get(key, default)


class InferenceEngine:
    """Run Phase 3 inference using existing DAX analysis output."""

    def __init__(
        self,
        nodes: Iterable[Node] | Mapping[str, Node],
        *,
        dax_analysis: Any = None,
        analyses: Any = None,
        edges: Iterable[Edge] | None = None,
        report_edges: Iterable[Edge] | None = None,
    ) -> None:
        self.nodes = _node_values(nodes)
        self._node_map = {node.id: node for node in self.nodes}
        self.analysis_source = dax_analysis if dax_analysis is not None else analyses
        raw_diagnostics = _get(self.analysis_source, "diagnostics", default=[])
        if isinstance(raw_diagnostics, Mapping):
            raw_diagnostics = [raw_diagnostics]
        elif not isinstance(raw_diagnostics, (list, tuple, set, frozenset)):
            raw_diagnostics = [] if raw_diagnostics is None else [raw_diagnostics]
        self.analysis_diagnostics = [_safe(item) for item in raw_diagnostics]
        self.analyses = _analysis_values(self.analysis_source)
        self.edges = _edge_values(list(edges or []) + list(report_edges or []))

    def infer(self) -> InferenceResult:
        candidates = infer_candidates(self.nodes, self.analyses)

        # Selector/report modules are optional seams.  The deterministic local
        # fallback keeps the Brain useful while an adapter is absent.
        selector_values: list[Any] = []
        selector_edges: list[Edge] = []
        from . import selectors

        selector_values, selector_edges = _module_candidates(selectors, self.nodes, self.analyses, self.edges)
        for value in selector_values:
            candidate = _as_candidate(value, self._node_map)
            if candidate is not None:
                candidates.append(candidate)
        known_selector_targets = {
            candidate.target
            for candidate in candidates
            if candidate.type == "SELECTOR"
        }
        fallback_candidates = [
            candidate
            for candidate in _fallback_selector_candidates(self.nodes, self.analyses, self.edges)
            if candidate.target not in known_selector_targets
        ]
        candidates.extend(fallback_candidates)

        selector_options: list[Any] = []
        selector_defaults: list[Any] = []
        option_inputs = [*selector_values, *[candidate.to_dict() for candidate in fallback_candidates]]
        selector_options = _module_options(selectors, option_inputs, self.nodes)
        selector_defaults = _module_defaults(selectors, self.analyses)

        observation_values: list[Any] = []
        observed_edges: list[Edge] = []
        from . import report_usage

        observation_values, observed_edges = _module_observations(
            report_usage, self.nodes, self.analyses, self.edges
        )
        observations: list[Edge] = []
        for edge in [*observed_edges, *(_coerce_observation(item, self._node_map) for item in observation_values)]:
            if edge is None or edge.type != "OBSERVED_WITH":
                continue
            if not any(existing.id == edge.id for existing in observations):
                observations.append(edge)

        # Stable candidate de-duplication.  Equal assertions from description
        # and a helper retain the first (strongest-priority) source ordering.
        unique: dict[str, SemanticCandidate] = {}
        for candidate in sorted(candidates, key=lambda item: (item.target, item.type, _json(item.value), item.source, item.id)):
            location = None
            if candidate.source == "dax_analysis":
                for analysis in self.analyses.values():
                    for behavior in _behavior_list(analysis, self._node_map.get(candidate.target, Node(id="x", type="UNKNOWN"))):
                        location = _get(behavior, "ast_location", "location")
                        if location:
                            break
                    if location:
                        break
            _normalize_candidate_evidence(candidate, location)
            unique.setdefault(candidate.id, candidate)
        candidates = sorted(unique.values(), key=lambda item: item.id)
        conflicts = detect_conflicts(self.nodes, candidates, self.analyses)

        semantic_nodes: dict[str, Node] = {}
        semantic_edges: dict[str, Edge] = {}
        selector_node_ids: dict[str, str] = {}
        selector_scopes: dict[str, tuple[str | None, str | None]] = {}
        for candidate in candidates:
            if candidate.type != "SELECTOR":
                continue
            scope = _scope_for_candidate(candidate, self._node_map, {})
            for key in (
                candidate.target,
                candidate.properties.get("selector_id"),
                candidate.properties.get("selector_node_id"),
            ):
                if key is not None:
                    selector_scopes[str(key)] = scope
        for candidate in candidates:
            model_id, report_id = _scope_for_candidate(candidate, self._node_map, selector_scopes)
            semantic_node = semantic_node_for(candidate, model_id=model_id, report_id=report_id)
            if candidate.type == "SELECTOR":
                selector_node_ids[candidate.target] = semantic_node.id
                if candidate.properties.get("selector_id"):
                    selector_node_ids[str(candidate.properties["selector_id"])] = semantic_node.id
                if candidate.properties.get("selector_node_id"):
                    selector_node_ids[str(candidate.properties["selector_node_id"])] = semantic_node.id
                for column_id in candidate.properties.get("column_ids", []):
                    selector_node_ids[str(column_id)] = semantic_node.id
            current = semantic_nodes.get(semantic_node.id)
            if current is None:
                semantic_nodes[semantic_node.id] = semantic_node
            else:
                previous = current.properties.setdefault("candidate_evidence", [])
                for evidence in candidate.evidence:
                    if evidence not in previous:
                        previous.append(evidence)
                current.properties.setdefault("candidate_ids", []).append(candidate.id)
                if current.status != semantic_node.status:
                    current.status = "candidate"
            edge = edge_for(candidate, semantic_node)
            semantic_edges.setdefault(edge.id, edge)

        # Known option metadata is a mechanical fact.  It remains FACT and
        # does not become a semantic approval merely because a selector was
        # inferred.
        option_node_ids: dict[tuple[str, str], str] = {}
        for record in selector_options:
            selector_id = _get(record, "selector_id", "selector", "target_id", "target")
            value = _get(record, "value", "name", "option")
            if selector_id is None or value is None:
                continue
            selector_graph_id = selector_node_ids.get(str(selector_id), str(selector_id))
            option_id = str(_get(record, "id", "option_id", default=f"semantic:selector-option:{_hash(selector_graph_id, value)}"))
            evidence = _get(record, "evidence", default=[])
            if isinstance(evidence, Mapping):
                evidence = [evidence]
            if not isinstance(evidence, (list, tuple)):
                evidence = [evidence]
            option_node = Node(
                id=option_id,
                type="SELECTOR_OPTION",
                name=str(value),
                description=str(value),
                model_id=selector_scopes.get(str(selector_id), (None, None))[0],
                report_id=selector_scopes.get(str(selector_id), (None, None))[1],
                source_id=option_id.rsplit(":", 1)[-1],
                status=str(_get(record, "status", default="factual")),
                properties={
                    "selector_id": selector_graph_id,
                    "value": _safe(value),
                    "ordinal": _get(record, "ordinal"),
                    "confidence": float(_get(record, "confidence", default=1.0) or 1.0),
                    "evidence": _safe(evidence),
                    "source_record": _safe(record),
                },
                source=str(_get(record, "source", default="model_metadata")),
            )
            semantic_nodes.setdefault(option_node.id, option_node)
            option_node_ids[(selector_graph_id, _json(value))] = option_node.id
            marker = _hash("HAS_OPTION", selector_graph_id, option_id)
            semantic_edges.setdefault(
                f"edge:option:{marker}",
                Edge(
                    id=f"edge:option:{marker}",
                    type="HAS_OPTION",
                    from_id=selector_graph_id,
                    to_id=option_id,
                    source=option_node.source,
                    confidence=float(_get(record, "confidence", default=1.0) or 1.0),
                    status=option_node.status,
                    evidence=list(evidence),
                    evidence_class=str(_get(record, "evidence_class", default="FACT")).upper(),
                    properties={"value": _safe(value), "selector_id": selector_graph_id},
                ),
            )

        for record in selector_defaults:
            target_id = _get(record, "target_id", "target", "target_ids")
            target_ids = target_id if isinstance(target_id, (list, tuple, set, frozenset)) else [target_id]
            selector_graph_id = next(
                (
                    selector_node_ids.get(str(item))
                    for item in target_ids
                    if item is not None and selector_node_ids.get(str(item))
                ),
                None,
            )
            if selector_graph_id is None:
                continue
            value = _get(record, "value", "default")
            if value is None:
                continue
            option_id = option_node_ids.get((selector_graph_id, _json(value)))
            if option_id is None:
                option_id = f"semantic:selector-option:{_hash(selector_graph_id, value)}"
                evidence = _get(record, "evidence", default=[])
                if isinstance(evidence, Mapping):
                    evidence = [evidence]
                if not isinstance(evidence, (list, tuple)):
                    evidence = [evidence]
                semantic_nodes.setdefault(
                    option_id,
                    Node(
                        id=option_id,
                        type="SELECTOR_OPTION",
                        name=str(value),
                        description=str(value),
                        model_id=(semantic_nodes.get(selector_graph_id).model_id if semantic_nodes.get(selector_graph_id) else None),
                        report_id=(semantic_nodes.get(selector_graph_id).report_id if semantic_nodes.get(selector_graph_id) else None),
                        source_id=option_id.rsplit(":", 1)[-1],
                        status="candidate",
                        properties={"selector_id": selector_graph_id, "value": _safe(value), "confidence": 1.0, "evidence": _safe(evidence)},
                        source="dax_ast",
                    ),
                )
            evidence = _get(record, "evidence", default=[])
            if isinstance(evidence, Mapping):
                evidence = [evidence]
            if not isinstance(evidence, (list, tuple)):
                evidence = [evidence]
            record_map = _safe(record)
            evidence = [record_map, *list(evidence)]
            confidence = float(_get(record, "confidence", default=1.0) or 1.0)
            marker = _hash("DEFAULTS_TO", selector_graph_id, option_id)
            semantic_edges.setdefault(
                f"edge:default:{marker}",
                Edge(
                    id=f"edge:default:{marker}",
                    type="DEFAULTS_TO",
                    from_id=selector_graph_id,
                    to_id=option_id,
                    source="semantic_inference",
                    confidence=max(0.0, min(1.0, confidence)),
                    status="candidate",
                    evidence=evidence,
                    evidence_class="INFERRED",
                    properties={"value": _safe(value), "function": "SELECTEDVALUE", "target_id": target_id},
                ),
            )

        for conflict in conflicts:
            conflict_node = Node(
                id=conflict.id,
                type="CONFLICT",
                name=conflict.reason,
                description=conflict.reason,
                model_id=self._node_map.get(conflict.target).model_id if self._node_map.get(conflict.target) else None,
                report_id=self._node_map.get(conflict.target).report_id if self._node_map.get(conflict.target) else None,
                source_id=conflict.id.rsplit(":", 1)[-1],
                status=conflict.status,
                properties=conflict.to_dict(),
                source="semantic_conflict",
            )
            semantic_nodes[conflict_node.id] = conflict_node
            marker = _hash("CONFLICTS_WITH", conflict.target, conflict.id)
            semantic_edges[f"edge:conflict:{marker}"] = Edge(
                id=f"edge:conflict:{marker}",
                type="CONFLICTS_WITH",
                from_id=conflict.target,
                to_id=conflict.id,
                source="semantic_conflict",
                confidence=conflict.confidence,
                status="candidate",
                evidence=conflict.evidence,
                evidence_class="INFERRED",
                properties={
                    "conflict": "description conflicts with DAX behavior",
                    "reason": conflict.reason,
                    "description_candidate": conflict.description_candidate,
                },
            )

        for edge in selector_edges:
            if edge.type in {"HAS_OPTION", "DEFAULTS_TO", "CONTROLLED_BY"}:
                _normalize_edge_evidence(edge, _first_ast_location(edge.evidence))
                if edge.source in {"dax_ast", "dax_analysis"}:
                    edge.source = "semantic_inference"
                semantic_edges.setdefault(edge.id, edge)
        for edge in observations:
            semantic_edges.setdefault(edge.id, edge)

        diagnostics: list[dict[str, Any]] = list(self.analysis_diagnostics)
        for candidate in candidates:
            if not candidate.evidence:
                diagnostics.append(
                    {
                        "code": "candidate_without_evidence",
                        "target": candidate.target,
                        "candidate": candidate.id,
                        "status": "candidate",
                    }
                )
            candidate.properties.setdefault("confidence_breakdown", confidence_breakdown(candidate.evidence))
        return InferenceResult(
            nodes=sorted(semantic_nodes.values(), key=lambda item: item.id),
            edges=sorted(semantic_edges.values(), key=lambda item: item.id),
            candidates=candidates,
            observations=sorted(observations, key=lambda item: item.id),
            conflicts=conflicts,
            diagnostics=diagnostics,
        )

    run = infer
    analyze = infer
    analyse = infer


SemanticInferenceEngine = InferenceEngine
Engine = InferenceEngine


def infer_semantics(
    nodes: Iterable[Node] | Mapping[str, Node],
    *,
    dax_analysis: Any = None,
    analyses: Any = None,
    edges: Iterable[Edge] | None = None,
) -> InferenceResult:
    return InferenceEngine(nodes, dax_analysis=dax_analysis, analyses=analyses, edges=edges).infer()


infer = infer_semantics
analyze_semantics = infer_semantics


__all__ = [
    "Engine",
    "InferenceEngine",
    "InferenceResult",
    "SemanticInferenceEngine",
    "analyze_semantics",
    "infer",
    "infer_semantics",
]
