"""Build compact, provenance-aware context from the canonical graph."""

from __future__ import annotations

import json
from collections import deque
from typing import Any, Iterable, Mapping, Sequence

from backend.graph.schema import Edge, Node, edge_from_dict, node_from_dict

from .pruning import prune_context
from .schema import empty_context


_DEPENDENCY_EDGES = frozenset({"DEPENDS_ON", "REFERENCES"})
_SEMANTIC_EDGES = frozenset(
    {
        "SEMANTICALLY_MAPS_TO",
        "SIMILAR_TO",
        "ALIAS_OF",
        "HAS_ROLE",
        "HAS_BEHAVIOR",
        "CONFLICTS_WITH",
    }
)
_STRUCTURAL_EDGES = frozenset({"CONTAINS", "BELONGS_TO", "RELATES_TO", "USES_MODEL"})
_CONSTRAINT_EDGES = frozenset(
    {"FILTERS", "MODIFIES_FILTER", "MODIFIES_RELATIONSHIP", "ACTIVATES_RELATIONSHIP"}
)
_EXPANDABLE_TYPES = frozenset({"MODEL", "TABLE", "REPORT", "PAGE", "CALCULATION_GROUP"})
_SEMANTIC_NODE_TYPES = frozenset(
    {"BUSINESS_CONCEPT", "SELECTOR", "SELECTOR_OPTION", "CONFLICT", "SEMANTIC_ASSERTION"}
)


def _safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _safe(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_safe(item) for item in value]
    return str(value)


def _json(value: Any) -> str:
    return json.dumps(_safe(value), ensure_ascii=False, sort_keys=True, default=str)


def _values(repository: Any, name: str, converter: Any) -> list[Any]:
    method = getattr(repository, name, None)
    values = method() if callable(method) else []
    if isinstance(values, Mapping):
        values = values.values()
    if not isinstance(values, Iterable) or isinstance(values, (str, bytes)):
        values = []
    result: list[Any] = []
    for value in values:
        try:
            result.append(converter(value))
        except (TypeError, KeyError, ValueError):
            continue
    return result


def _node_values(repository: Any) -> list[Node]:
    if isinstance(repository, Mapping):
        values = repository.get("nodes", [])
        if isinstance(values, Mapping):
            values = values.values()
        return [node_from_dict(value) for value in values]
    return _values(repository, "all_nodes", node_from_dict)


def _edge_values(repository: Any) -> list[Edge]:
    if isinstance(repository, Mapping):
        values = repository.get("edges", [])
        if isinstance(values, Mapping):
            values = values.values()
        return [edge_from_dict(value) for value in values]
    return _values(repository, "all_edges", edge_from_dict)


def _record_matches(item: Mapping[str, Any], target: str) -> bool:
    target = str(target)
    if str(item.get("id", "")) == target:
        return True
    if target in {str(item.get("from_id", "")), str(item.get("to_id", ""))}:
        return True
    properties = item.get("properties")
    if isinstance(properties, Mapping):
        if properties.get("candidate_ids"):
            return False
        return any(str(properties.get(key, "")) == target for key in ("candidate_id", "target", "target_id"))
    return False


def _apply_overrides(value: Mapping[str, Any], store: Any) -> dict[str, Any]:
    """Apply human decisions to a response copy; generated graph stays intact."""

    result = dict(_safe(value))
    properties = dict(result.get("properties") or {}) if isinstance(result.get("properties"), Mapping) else {}
    records = store.records() if store is not None and callable(getattr(store, "records", None)) else []
    applied: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, Mapping) or not _record_matches(result, str(record.get("target", ""))):
            continue
        property_name = str(record.get("property", "")).strip()
        if not property_name:
            continue
        value = _safe(record.get("value"))
        if property_name == "status":
            result["status"] = str(value).lower()
        else:
            result[property_name] = value
            properties[property_name] = value
            if property_name in {"business_concept", "concept", "meaning", "value", "role", "behavior", "alias"}:
                result["value"] = value
                result["meaning"] = value
                properties["meaning"] = value
        applied.append(dict(_safe(record)))
    if applied:
        result["properties"] = properties
        result["overrides"] = applied
        if any(str(item.get("status", "")).lower() == "overridden" for item in applied):
            result["status"] = "overridden"
    return result


def _task_kind(task: str | Mapping[str, Any] | None) -> str:
    if task is None:
        return "all"
    if isinstance(task, Mapping):
        value = task.get("kind", task.get("task", task.get("name", "all")))
    else:
        value = task
    return str(value or "all").casefold()


def _include_usage(task: str | Mapping[str, Any] | None) -> bool:
    kind = _task_kind(task)
    return not any(token in kind for token in ("lineage", "dependency", "semantic", "meaning"))


def _edge_record(edge: Edge, nodes: Mapping[str, Node], store: Any = None) -> dict[str, Any]:
    # Endpoint IDs are already canonical.  Embedding full endpoint nodes here
    # repeats raw metadata and defeats compact context retrieval.
    return _safe(edge.to_dict())


def _object_record(node: Node, edge: Edge | None, store: Any = None) -> dict[str, Any]:
    record = _apply_overrides(node.to_dict(), store)
    if edge is not None:
        record.update(
            {
                "edge_id": edge.id,
                "edge_type": edge.type,
                "edge_source": edge.source,
                "edge_confidence": edge.confidence,
                "edge_status": edge.status,
                "edge_evidence_class": edge.evidence_class,
                "edge_evidence": _safe(edge.evidence),
            }
        )
    return record


def _semantic_record(edge: Edge, nodes: Mapping[str, Node], store: Any = None) -> dict[str, Any]:
    record = _apply_overrides(_edge_record(edge, nodes, store), store)
    properties = record.get("properties", {})
    target_id = edge.from_id
    record.update(
        {
            "target": target_id,
            "target_id": target_id,
            "assertion_type": properties.get("assertion_type", edge.type),
            "value": _safe(record.get("value", properties.get("value", properties.get("meaning")))),
            "meaning": _safe(record.get("meaning", properties.get("meaning", properties.get("value")))),
        }
    )
    semantic_node = nodes.get(edge.to_id)
    if semantic_node is not None and semantic_node.type in _SEMANTIC_NODE_TYPES:
        payload = semantic_node.to_dict()
        if semantic_node.properties.get("candidate_ids") and edge.properties.get("candidate_id"):
            payload["properties"] = {**semantic_node.properties, **edge.properties, "candidate_ids": []}
            payload.update(status=edge.status, confidence=edge.confidence, evidence=edge.evidence)
        record["semantic_node"] = _apply_overrides(payload, store)
    return record


def _validation_payload(repository: Any) -> list[Any]:
    value = getattr(repository, "validation_result", None)
    if value is None and callable(getattr(repository, "get_validation_result", None)):
        value = repository.get_validation_result()
    if value is None:
        return []
    if hasattr(value, "to_dict") and callable(value.to_dict):
        value = value.to_dict()
    if isinstance(value, Mapping):
        issues = value.get("issues", value.get("findings", []))
    else:
        issues = getattr(value, "issues", [])
    if not isinstance(issues, (list, tuple, set, frozenset)):
        return []
    return [_safe(item.to_dict() if hasattr(item, "to_dict") and callable(item.to_dict) else item) for item in issues]


class ContextBuilder:
    """Compile a relevant graph slice into the canonical context schema."""

    def __init__(self, repository: Any, *, store: Any = None) -> None:
        self.repository = repository
        self.store = store

    def build(
        self,
        target: str | Node | Mapping[str, Any],
        task: str | Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        nodes = {node.id: node for node in _node_values(self.repository)}
        edges = sorted(_edge_values(self.repository), key=lambda item: item.id)
        target_id = target.id if isinstance(target, Node) else target.get("id") if isinstance(target, Mapping) else target
        target_id = str(target_id)
        target_node = nodes.get(target_id)
        if target_node is None:
            raise KeyError(f"object not found: {target_id}")

        outgoing: dict[str, list[Edge]] = {}
        incident: dict[str, list[Edge]] = {}
        for edge in edges:
            outgoing.setdefault(edge.from_id, []).append(edge)
            incident.setdefault(edge.from_id, []).append(edge)
            incident.setdefault(edge.to_id, []).append(edge)

        relevant: set[str] = {target_id}
        queue: deque[str] = deque([target_id])
        expanded_structural: set[str] = {target_id} if target_node.type in _EXPANDABLE_TYPES else set()
        selected: dict[str, dict[str, Edge]] = {
            "dependencies": {},
            "relationships": {},
            "controls": {},
            "usage": {},
            "constraints": {},
            "semantics": {},
        }
        include_usage = _include_usage(task)
        # A visual's field bindings are part of its meaning even for a
        # lineage request.  Other leaf targets still omit report usage from
        # lineage/semantic contexts.

        def add(edge: Edge, category: str, other_id: str | None = None, *, expand: bool = False) -> None:
            selected[category][edge.id] = edge
            endpoint = other_id or (edge.to_id if edge.from_id == current_id else edge.from_id)
            if endpoint and endpoint in nodes and endpoint not in relevant:
                relevant.add(endpoint)
                queue.append(endpoint)
            if endpoint and expand:
                expanded_structural.add(endpoint)

        while queue:
            current_id = queue.popleft()
            current = nodes[current_id]
            for edge in incident.get(current_id, []):
                edge_type = edge.type
                if edge_type in _DEPENDENCY_EDGES and edge.from_id == current_id:
                    add(edge, "dependencies", edge.to_id)
                    continue
                if edge_type in _SEMANTIC_EDGES:
                    # CONFLICTS_WITH is also surfaced under warnings later.
                    add(edge, "semantics")
                    continue
                if edge_type in {"CONTROLLED_BY", "HAS_OPTION", "DEFAULTS_TO"}:
                    if edge.from_id == current_id or edge.to_id == current_id:
                        add(edge, "controls")
                    continue
                if edge_type == "USES":
                    if (include_usage or (current_id == target_id and target_node.type == "VISUAL")) and (
                        edge.from_id == current_id or edge.to_id == current_id
                    ):
                        add(edge, "usage")
                    continue
                if edge_type == "OBSERVED_WITH":
                    if include_usage and (edge.from_id == current_id or edge.to_id == current_id):
                        add(edge, "usage")
                    continue
                if edge_type in _CONSTRAINT_EDGES:
                    if edge.from_id == current_id or edge.to_id == current_id:
                        add(edge, "constraints")
                    continue
                if edge_type == "USES_MODEL":
                    # A report needs its model; a model's incoming reports are
                    # usage and are intentionally not pulled into model context.
                    if edge.from_id == current_id:
                        add(edge, "relationships", edge.to_id)
                    elif include_usage and edge.to_id == current_id:
                        add(edge, "usage", edge.from_id)
                    continue
                if edge_type not in _STRUCTURAL_EDGES:
                    continue
                if edge_type == "RELATES_TO":
                    add(edge, "relationships")
                    continue
                if edge.to_id == current_id:
                    # Always retain the parent chain.  Do not expand a parent
                    # container's other children into a leaf context.
                    add(edge, "relationships", edge.from_id)
                    continue
                if current_id not in expanded_structural:
                    continue
                if edge.from_id == current_id:
                    expand = current.type in _EXPANDABLE_TYPES
                    add(edge, "relationships", edge.to_id, expand=expand)
                elif edge.to_id == current_id:
                    # Parent containment is useful, but its other children
                    # are unrelated to a leaf target and stay pruned.
                    add(edge, "relationships", edge.from_id)

            # A column/measure/table can have report usage through a child
            # object.  Add incoming uses for already selected model objects.
            if include_usage and current.type in {"COLUMN", "MEASURE", "TABLE", "MODEL"}:
                for edge in incident.get(current_id, []):
                    if edge.type == "USES" and edge.to_id == current_id:
                        add(edge, "usage", edge.from_id)

        # Relationship endpoint edges may introduce a relation node after the
        # initial walk; one short closure captures the endpoint columns.
        for relation_id in list(relevant):
            if nodes.get(relation_id, Node("", "UNKNOWN")).type != "RELATIONSHIP":
                continue
            for edge in incident.get(relation_id, []):
                if edge.type == "RELATES_TO":
                    selected["relationships"][edge.id] = edge
                    endpoint = edge.to_id if edge.from_id == relation_id else edge.from_id
                    if endpoint in nodes:
                        relevant.add(endpoint)

        context = empty_context()
        context["target"] = _apply_overrides(target_node.to_dict(), self.store)
        context["scope"] = {
            "model_ids": sorted(
                {
                    str(nodes[item].id if nodes[item].type == "MODEL" else nodes[item].model_id)
                    for item in relevant
                    if nodes[item].type == "MODEL" or nodes[item].model_id is not None
                }
            ),
            "report_ids": sorted(
                {
                    str(nodes[item].id if nodes[item].type == "REPORT" else nodes[item].report_id)
                    for item in relevant
                    if nodes[item].type == "REPORT" or nodes[item].report_id is not None
                }
            ),
        }

        for category in ("relationships", "controls", "usage", "constraints"):
            context[category] = [
                _edge_record(edge, nodes, self.store)
                for edge in sorted(selected[category].values(), key=lambda item: item.id)
            ]
        context["dependencies"] = [
            _object_record(nodes[edge.to_id], edge, self.store)
            for edge in sorted(selected["dependencies"].values(), key=lambda item: item.id)
            if edge.to_id in nodes
        ]

        semantic_records = [
            _semantic_record(edge, nodes, self.store)
            for edge in sorted(selected["semantics"].values(), key=lambda item: item.id)
            if edge.type != "CONFLICTS_WITH"
        ]
        if target_node.type in _SEMANTIC_NODE_TYPES and not target_node.properties.get("candidate_ids"):
            semantic_records.insert(0, _apply_overrides(target_node.to_dict(), self.store))
        context["semantics"] = semantic_records

        evidence: list[Any] = []
        for node_id in sorted(relevant):
            properties = nodes[node_id].properties
            if isinstance(properties, Mapping):
                evidence_properties: list[str] = []
                evidence_count = 0
                scalar_values: list[Any] = []
                for key in ("evidence", "candidate_evidence"):
                    value = properties.get(key)
                    if isinstance(value, (list, tuple, set, frozenset)):
                        evidence_properties.append(key)
                        evidence_count += len(value)
                        scalar_values.extend(item for item in value if not isinstance(item, Mapping))
                if evidence_count:
                    record: dict[str, Any] = {
                        "subject_id": node_id,
                        "subject_kind": "node",
                        "properties": evidence_properties,
                        "evidence_count": evidence_count,
                    }
                    if len(scalar_values) == 1:
                        record["value"] = _safe(scalar_values[0])
                    evidence.append(record)
        for category in selected.values():
            for edge in category.values():
                if not edge.evidence:
                    continue
                record = {
                    "subject_id": edge.id,
                    "subject_kind": "edge",
                    "edge_type": edge.type,
                    "source": edge.source,
                    "evidence_class": edge.evidence_class,
                    "evidence_count": len(edge.evidence),
                }
                if len(edge.evidence) == 1 and not isinstance(edge.evidence[0], Mapping):
                    record["value"] = _safe(edge.evidence[0])
                evidence.append(record)
        context["evidence"] = evidence

        confidence: dict[str, float] = {}

        def score(identifier: str, value: Any) -> None:
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                confidence[str(identifier)] = max(0.0, min(1.0, float(value)))

        for node_id in sorted(relevant):
            properties = nodes[node_id].properties
            if isinstance(properties, Mapping):
                score(node_id, properties.get("confidence", properties.get("candidate_confidence")))
                score(str(properties.get("candidate_id")), properties.get("candidate_confidence"))
        for category in selected.values():
            for edge in category.values():
                score(edge.id, edge.confidence)
                candidate_id = edge.properties.get("candidate_id") if isinstance(edge.properties, Mapping) else None
                if candidate_id:
                    score(str(candidate_id), edge.confidence)
        context["confidence"] = confidence

        warnings: list[Any] = []
        for node_id in sorted(relevant):
            node = nodes[node_id]
            if node.type == "CONFLICT":
                warnings.append(_apply_overrides(node.to_dict(), self.store))
            properties = node.properties if isinstance(node.properties, Mapping) else {}
            for key in ("warnings", "warning", "conflicts", "conflict"):
                value = properties.get(key)
                if value:
                    warnings.extend(value if isinstance(value, list) else [value])
        for edge in selected["semantics"].values():
            if edge.type == "CONFLICTS_WITH":
                warnings.append(_edge_record(edge, nodes, self.store))
        for issue in _validation_payload(self.repository):
            if not isinstance(issue, Mapping):
                warnings.append(issue)
                continue
            issue_target = next(
                (issue.get(key) for key in ("object_id", "target_id", "node_id", "id") if issue.get(key)),
                None,
            )
            if issue_target is None or str(issue_target) in relevant:
                warnings.append(issue)
        context["warnings"] = warnings
        result = prune_context(context, task)
        task_name = task if isinstance(task, str) else task.get("task", task.get("type", "")) if isinstance(task, Mapping) else ""
        if task_name in {"impact", "change_preflight", "regression_planning", "post_change_review"}:
            from backend.impact import analyze_impact
            proposal = list(task.get("proposed_changes", [])) if isinstance(task, Mapping) else []
            impact = analyze_impact(self.repository, [target_id], proposal,
                                    completeness=getattr(self.repository, "impact_completeness", None))
            dependency_queue, dependency_seen, dependency_records = deque([(target_id, 0)]), set(), []
            while dependency_queue:
                current, distance = dependency_queue.popleft()
                if current in dependency_seen:
                    continue
                dependency_seen.add(current)
                for edge in outgoing.get(current, []):
                    if edge.type in {"DEPENDS_ON", "REFERENCES"}:
                        dependency_records.append({**_edge_record(edge, nodes, self.store), "distance": distance + 1})
                        dependency_queue.append((edge.to_id, distance + 1))
            result.update(impact=impact, impact_report_id=impact["impact_report_id"], baseline_snapshot_id=impact["baseline_snapshot_id"],
                          requested_mutation=proposal, current_properties=dict(target_node.properties),
                          direct_dependencies=[item for item in dependency_records if item["distance"] == 1],
                          transitive_dependencies=[item for item in dependency_records if item["distance"] > 1],
                          constraints=[*result.get("constraints", []), {"code": "EXACT_TARGET_REQUIRED", "target_id": target_id}, {"code": "CONTEXT_DOES_NOT_AUTHORIZE_MUTATION"},
                                       {"code": "UNKNOWN_COVERAGE_BLOCKS_CERTIFICATION", "status": impact["completeness"]["status"]}],
                          relationship_paths=[item["path"] for item in impact["potential_impacts"]],
                          potentially_affected_measures=[item for item in impact["potential_impacts"] if item["object_type"] == "MEASURE"],
                          potentially_affected_visuals=[item for item in impact["potential_impacts"] if item["object_type"] == "VISUAL"],
                          security_implications=impact["warnings"], unknowns=impact["unknown_impacts"], completeness=impact["completeness"], omitted_optional_context=[])
            result["current_validation_failures"] = [item for item in _validation_payload(self.repository) if isinstance(item, Mapping) and item.get("severity") in {"ERROR", "BLOCKING"}]
        return result

    get_context = build
    compile = build
    build_context = build


ContextCompiler = ContextBuilder


def build_context(
    repository: Any,
    target: str | Node | Mapping[str, Any],
    task: str | Mapping[str, Any] | None = None,
    *,
    store: Any = None,
) -> dict[str, Any]:
    return ContextBuilder(repository, store=store).build(target, task)


get_context = build_context


__all__ = ["ContextBuilder", "ContextCompiler", "build_context", "get_context"]
