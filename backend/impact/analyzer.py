"""Conservative analytical traversal of the existing canonical graph.

Results are evidence records, never speculative edges in LadybugDB.
Output limits are applied after closure, and cannot certify completeness.
"""
from __future__ import annotations

from collections import defaultdict, deque
from copy import deepcopy
from time import perf_counter
from typing import Any, Mapping

from backend.snapshots.manifest import content_hash
from backend.validation import graph_values, item_dict

CALCULATIONS = {"MEASURE", "CALCULATION_ITEM", "COLUMN", "TABLE", "SHARED_EXPRESSION", "USER_DEFINED_FUNCTION", "VISUAL_CALCULATION"}
CONSUMER_EDGES = {"DEPENDS_ON", "REFERENCES", "USES", "USES_MODEL", "FILTERS", "MODIFIES_FILTER", "ACTIVATES_RELATIONSHIP", "MODIFIES_RELATIONSHIP"}
RELATIONSHIP_PROPERTIES = {"from_column_id", "to_column_id", "active", "cross_filter_direction", "cardinality", "from_cardinality", "to_cardinality", "security_filter_behavior"}
REPORT_TYPES = {"VISUAL", "PAGE", "REPORT", "VISUAL_FILTER", "PAGE_FILTER", "REPORT_FILTER", "VISUAL_CALCULATION"}


def properties(node: Mapping[str, Any]) -> dict[str, Any]:
    return dict(node.get("properties", {}))


def relationship_paths(nodes: Mapping[str, Any], changes: list[dict[str, Any]]) -> tuple[dict[str, list[tuple[str, str]]], list[str]]:
    """Possible filter influence, including inactive paths with explicit conditions.

    Both directions are retained conservatively for expanded tables, DAX
    overrides and security. This intentionally over-approximates actual flow.
    """
    adjacency: dict[str, list[tuple[str, str]]] = defaultdict(list)
    unknown = []
    for node in nodes.values():
        if node["type"] != "RELATIONSHIP":
            continue
        prop = properties(node)
        for change in changes:
            if change["object_id"] == node["id"]:
                prop[change["property"]] = change["new_value"]
        endpoints = [nodes.get(prop.get(key, "")) for key in ("from_column_id", "to_column_id")]
        if any(endpoint is None or endpoint["type"] != "COLUMN" for endpoint in endpoints):
            unknown.append("UNRESOLVED_RELATIONSHIP:" + node["id"])
            continue
        tables = [properties(endpoint).get("table_id") for endpoint in endpoints]
        if any(table not in nodes for table in tables):
            unknown.append("MISSING_ENDPOINT_TABLE:" + node["id"])
            continue
        for left, right in ((tables[0], tables[1]), (tables[1], tables[0])):
            adjacency[left].append((right, node["id"]))
    return {key: sorted(set(value)) for key, value in adjacency.items()}, sorted(set(unknown))


def analyze_impact(graph: Any, target_ids: list[str], proposed_changes: list[dict[str, Any]] | None = None, *,
                   baseline_snapshot_id: str | None = None, completeness: Mapping[str, Any] | None = None,
                   include_report_usage: bool = True, output_limit: int | None = None) -> dict[str, Any]:
    started = perf_counter()
    raw_nodes, raw_edges = graph_values(graph)
    nodes = {item["id"]: item for item in map(item_dict, raw_nodes)}
    edges = sorted(map(item_dict, raw_edges), key=lambda item: item["id"])
    target_ids = sorted(set(target_ids))
    if not target_ids or any(target not in nodes for target in target_ids):
        raise KeyError("Impact requires exact resolved object IDs")
    changes = []
    for value in proposed_changes or []:
        change = dict(value)
        change.setdefault("object_id", target_ids[0] if len(target_ids) == 1 else None)
        if change["object_id"] not in target_ids or not isinstance(change.get("property"), str) or "new_value" not in change:
            raise ValueError("Invalid proposed property change")
        if change["property"] in {"from_column_id", "to_column_id"} and (
            change["new_value"] not in nodes or nodes[change["new_value"]]["type"] != "COLUMN"
            or nodes[change["new_value"]].get("model_id") != nodes[change["object_id"]].get("model_id")
        ):
            raise ValueError("Relationship endpoint must resolve to a column in the same model")
        changes.append(change)
    changes.sort(key=content_hash)
    incoming, outgoing, parents, children = defaultdict(list), defaultdict(list), defaultdict(list), defaultdict(list)
    for edge in edges:
        outgoing[edge["from_id"]].append(edge)
        if edge["type"] in CONSUMER_EDGES:
            incoming[edge["to_id"]].append(edge)
        if edge["type"] == "CONTAINS":
            parents[edge["to_id"]].append(edge)
            children[edge["from_id"]].append(edge)
    records: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    unknowns, warnings = [], []
    initial_complete = deepcopy(dict(completeness or {"status": "UNKNOWN", "blocking": ["SCANNER_COVERAGE_UNKNOWN"]}))

    def add(object_id: str, root: str, trigger: str, category: str, path: list[dict[str, Any]], reason: str, *, rule: str,
            conditions: list[str] | None = None) -> None:
        if object_id not in nodes:
            unknowns.append("DANGLING_GRAPH_ENDPOINT:" + object_id)
            return
        key = (object_id, root, trigger, rule)
        record = {"object_id": object_id, "object_type": nodes[object_id]["type"], "name": nodes[object_id].get("name", ""),
                  "model_id": nodes[object_id].get("model_id"), "report_id": nodes[object_id].get("report_id"),
                  "impact_category": category, "root_modified_object": root, "triggering_property": trigger,
                  "path": path, "evidence": [item for step in path for item in step.get("evidence", [])],
                  "analyzer_rule_id": rule, "completeness_status": initial_complete.get("status", "UNKNOWN"),
                  "reason": reason, "conditions": conditions or [], "runtime_verification_required": category != "DIRECT",
                  "evidence_class": "INFERRED" if category in {"POTENTIAL_BEHAVIORAL", "CONDITIONAL", "UNKNOWN"}
                  or any(step.get("direction") == "analytical" or step.get("evidence_class", "FACT") != "FACT" for step in path) else "FACT"}
        # One shortest path per rule/root/property; distinct causes remain separate.
        if key not in records or (len(path), content_hash(path)) < (len(records[key]["path"]), content_hash(records[key]["path"])):
            records[key] = record

    for target in target_ids:
        node = nodes[target]
        triggers = sorted({item["property"] for item in changes if item["object_id"] == target}) or ["unspecified"]
        for trigger in triggers:
            add(target, target, trigger, "DIRECT", [], "Explicit modification target", rule="seed")
            seeds = [(target, [])]
            if node["type"] == "RELATIONSHIP":
                before_paths, before_unknown = relationship_paths(nodes, [])
                after_paths, after_unknown = relationship_paths(nodes, changes)
                unknowns.extend(before_unknown + after_unknown)
                relevant_changes = [item for item in changes if item["object_id"] == target]
                endpoint_ids = {properties(node).get(key) for key in ("from_column_id", "to_column_id")}
                endpoint_ids.update(item["new_value"] for item in relevant_changes if item["property"] in {"from_column_id", "to_column_id"})
                table_queue, visited = deque(), set()
                for endpoint in sorted(item for item in endpoint_ids if item):
                    step = {"from_id": target, "to_id": endpoint, "edge_type": "RELATES_TO", "direction": "out", "evidence": node.get("properties", {}).get("evidence", [])}
                    add(endpoint, target, trigger, "STRUCTURAL", [step], "Original or proposed relationship endpoint", rule="relationship_endpoint")
                    table = properties(nodes.get(endpoint, {})).get("table_id")
                    if table:
                        table_queue.append((table, [step]))
                while table_queue:
                    table, path = table_queue.popleft()
                    if table in visited:
                        continue
                    visited.add(table)
                    add(table, target, trigger, "POTENTIAL_BEHAVIORAL", path, "Relationship may change reachable filter context", rule="filter_influence",
                        conditions=["Filter context, active paths, cardinality, expanded tables and DAX overrides determine actual results"])
                    for other, relationship in sorted(set(before_paths.get(table, []) + after_paths.get(table, []))):
                        table_queue.append((other, path + [{"from_id": table, "to_id": other, "edge_type": "POSSIBLE_FILTER_PATH", "direction": "analytical", "relationship_id": relationship,
                                                         "evidence": [properties(nodes[relationship])]}]))
                for expression in sorted(nodes.values(), key=lambda item: item["id"]):
                    if expression["type"] not in CALCULATIONS or expression.get("model_id") != node.get("model_id"):
                        continue
                    prop = properties(expression)
                    # Calculation groups/UDFs and expressions without resolvable
                    # literal references can influence any calculation in scope.
                    depends = [edge for edge in outgoing.get(expression["id"], []) if edge["type"] in CONSUMER_EDGES]
                    operates = prop.get("table_id") in visited or any(
                        edge["to_id"] in visited or properties(nodes.get(edge["to_id"], {})).get("table_id") in visited for edge in depends)
                    if not operates and depends and expression["type"] not in {"CALCULATION_ITEM", "USER_DEFINED_FUNCTION", "SHARED_EXPRESSION"}:
                        continue
                    if expression["type"] in {"COLUMN", "TABLE"} and not prop.get("expression"):
                        if expression["id"] not in visited and prop.get("table_id") not in visited:
                            continue
                    implicit_path = [{"from_id": target, "to_id": expression["id"], "edge_type": "FILTER_CONTEXT_INFLUENCE", "direction": "analytical", "evidence": [{"tables": sorted(visited)}]}]
                    add(expression["id"], target, trigger, "POTENTIAL_BEHAVIORAL", implicit_path,
                        "Evaluation context may change despite unchanged expression text", rule="calculation_context")
                    seeds.append((expression["id"], implicit_path))
                    for behavior in prop.get("dax_behaviors", prop.get("behaviors", [])):
                        function = behavior.get("function", "") if isinstance(behavior, dict) else ""
                        if function in {"USERELATIONSHIP", "CROSSFILTER", "ALL", "REMOVEFILTERS", "TREATAS"}:
                            add(expression["id"], target, trigger, "CONDITIONAL", implicit_path,
                                "Explicit DAX relationship/filter override requires a specialized test", rule="dax_override:" + function,
                                conditions=[function, "Override endpoint validity and selected context must be evaluated"])
                if any(item["type"] in {"ROLE", "TABLE_PERMISSION", "ROW_LEVEL_SECURITY", "OBJECT_LEVEL_SECURITY"} or properties(item).get("roles") or properties(item).get("raw_source", {}).get("roles") for item in nodes.values()):
                    warnings.append("RLS_REQUIRES_EXTENDED_VERIFICATION")
            elif node["type"] in {"MODEL", "TABLE", "COLUMN", "USER_DEFINED_FUNCTION", "FIELD_PARAMETER", "CALCULATION_GROUP", "CALCULATION_ITEM", "ROLE", "TABLE_PERMISSION", "ROW_LEVEL_SECURITY", "OBJECT_LEVEL_SECURITY", "SHARED_EXPRESSION"}:
                for calculation in sorted(nodes.values(), key=lambda item: item["id"]):
                    if calculation.get("model_id") == node.get("model_id") and calculation["type"] in CALCULATIONS:
                        path = [{"from_id": target, "to_id": calculation["id"], "edge_type": "MODEL_CONTEXT_INFLUENCE", "direction": "analytical", "evidence": ["Calculation/security/source context may affect evaluation"]}]
                        add(calculation["id"], target, trigger, "POTENTIAL_BEHAVIORAL", path, "Model-wide evaluation context may change", rule="model_context")
                        seeds.append((calculation["id"], path))
                if "SECURITY" in node["type"] or node["type"] in {"ROLE", "TABLE_PERMISSION"}:
                    warnings.append("RLS_REQUIRES_EXTENDED_VERIFICATION")
            queue, seen = deque(seeds), set()
            while queue:
                current, path = queue.popleft()
                if current in seen:
                    continue
                seen.add(current)
                if nodes.get(current, {}).get("type") in {"MODEL", "TABLE", "CALCULATION_GROUP"}:
                    for edge in children.get(current, []):
                        child = edge["to_id"]
                        path_to_child = path + [{"from_id": current, "to_id": child, "edge_type": "CONTAINS", "direction": "out", "evidence_class": edge.get("evidence_class", "FACT"), "evidence": edge.get("evidence", [])}]
                        add(child, target, trigger, "STRUCTURAL", path_to_child, "Contained definitions may be affected", rule="contained_scope")
                        queue.append((child, path_to_child))
                for edge in incoming.get(current, []):
                    consumer = edge["from_id"]
                    if not include_report_usage and nodes.get(consumer, {}).get("type") in REPORT_TYPES:
                        continue
                    next_path = path + [{"from_id": current, "to_id": consumer, "edge_type": edge["type"], "direction": "in", "edge_id": edge["id"], "evidence": edge.get("evidence", []), "evidence_class": edge.get("evidence_class", "FACT")}]
                    category = "STRUCTURAL" if node["type"] != "RELATIONSHIP" else "POTENTIAL_BEHAVIORAL"
                    add(consumer, target, trigger, category, next_path, "Consumes potentially affected object", rule="consumer_closure")
                    queue.append((consumer, next_path))
                for edge in parents.get(current, []):
                    parent = edge["from_id"]
                    if include_report_usage and nodes.get(current, {}).get("type") in REPORT_TYPES:
                        next_path = path + [{"from_id": current, "to_id": parent, "edge_type": "CONTAINS", "direction": "in", "evidence": edge.get("evidence", [])}]
                        add(parent, target, trigger, "STRUCTURAL", next_path, "Contains affected report object", rule="report_ancestry")
                        queue.append((parent, next_path))

    models = sorted({nodes[target].get("model_id") or (target if nodes[target]["type"] == "MODEL" else "") for target in target_ids} - {""})
    for node in nodes.values():
        if node.get("model_id") not in models and node["type"] != "REPORT":
            continue
        prop = properties(node)
        for key in ("unresolved_references", "unresolved_fields", "unresolved_bindings", "dax_diagnostics", "diagnostics"):
            if prop.get(key):
                unknowns.append(key.upper() + ":" + node["id"])
        if node["type"] == "REPORT" and not node.get("model_id"):
            unknowns.append("UNRESOLVED_REPORT_MODEL:" + node["id"])
        if node["type"] == "VISUAL" and prop.get("fields") and not prop.get("field_ids"):
            unknowns.append("UNRESOLVED_VISUAL_BINDING:" + node["id"])
    unknowns.extend(str(item) for item in initial_complete.get("blocking", []))
    complete = initial_complete.get("status") == "COMPLETE" and not unknowns
    ordered = sorted(records.values(), key=lambda item: (item["object_id"], item["root_modified_object"], item["triggering_property"], item["analyzer_rule_id"]))
    impacted = sorted({item["object_id"] for item in ordered})
    required_tests = []
    categories = ["unfiltered_total", "grouped_dimension_total", "affected_measure", "dependent_measure", "alternate_relationship", "blank_unmatched_keys", "slicer_filter_context", "time_intelligence", "report_bound_calculation"]
    if "RLS_REQUIRES_EXTENDED_VERIFICATION" in warnings:
        categories.append("security_role")
    for category in categories:
        selected = [item for item in impacted if nodes[item]["type"] in {"MEASURE", "CALCULATION_ITEM", "VISUAL", "USER_DEFINED_FUNCTION"}]
        if selected:
            required_tests.append({"test_id": "impact:" + category, "category": category, "target_objects": selected, "required": True,
                                   "status": "QUERY_REQUIRED", "reason": "Trusted explicit query/context assertions must be supplied"})
    truncated = output_limit is not None and len(ordered) > output_limit
    if output_limit is not None and (isinstance(output_limit, bool) or output_limit < 1):
        raise ValueError("Output limit must be positive")
    shown = ordered[:output_limit] if output_limit else ordered
    report = {"impact_report_version": 1, "baseline_snapshot_id": baseline_snapshot_id or content_hash({"nodes": list(nodes.values()), "edges": edges}),
              "target_ids": target_ids, "changed_properties": changes, "direct_impacts": [item for item in shown if item["impact_category"] == "DIRECT"],
              "potential_impacts": [item for item in shown if item["impact_category"] in {"STRUCTURAL", "POTENTIAL_BEHAVIORAL"}],
              "conditional_impacts": [item for item in shown if item["impact_category"] == "CONDITIONAL"],
              "unknown_impacts": [{"impact_category": "UNKNOWN", "reason": item, "runtime_verification_required": True} for item in sorted(set(unknowns))],
              "affected_model_ids": models, "affected_report_ids": sorted({nodes[item].get("report_id") or item for item in impacted if nodes[item]["type"] == "REPORT" or nodes[item].get("report_id")}),
              "impacted_objects": impacted, "impact_paths": [{"object_id": item["object_id"], "object_type": item["object_type"], "impact_category": item["impact_category"], "runtime_verification_required": item["runtime_verification_required"], "path_id": content_hash(item), "category": item["analyzer_rule_id"]} for item in ordered],
              "required_tests": required_tests, "warnings": sorted(set(warnings)), "evidence": [item["path"] for item in shown],
              "completeness": {**initial_complete, "status": "COMPLETE" if complete else "INCOMPLETE", "analysis_truncated": False,
                               "output_truncated": truncated, "total_impact_records": len(ordered), "nodes_analyzed": len(nodes), "edges_analyzed": len(edges),
                               "missing_execution_evidence": True, "filter_analysis": "CONSERVATIVE_SUPERSET"}}
    report["impact_report_id"] = content_hash(report)
    report["metrics"] = {"traversal_seconds": perf_counter() - started, "nodes_examined": len(nodes), "edges_examined": len(edges), "impacted_objects": len(impacted), "selected_tests": len(required_tests), "llm_calls": 0}
    return report
