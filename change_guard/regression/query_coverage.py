"""Query AST coverage; a target label alone cannot certify evaluation."""
import re
from backend.dax.analyzer import DaxAnalyzer
from backend.graph.schema import Node, node_from_dict


def query_targets(query: str, target_ids: tuple[str, ...], graph: dict | None) -> dict:
    if not graph:
        return {"status": "NOT_RUN", "reason": "QUERY_TARGET_GRAPH_UNAVAILABLE", "resolved_ids": []}
    nodes = [node_from_dict(item) for item in graph.get("nodes", [])]
    indexed = {node.id: node for node in nodes}
    models = {indexed[target].model_id for target in target_ids if target in indexed}
    if len(models) != 1 or None in models:
        return {"status": "INCONCLUSIVE", "reason": "QUERY_MODEL_SCOPE_UNRESOLVED", "resolved_ids": []}
    match = re.fullmatch(r"\s*EVALUATE\s+(.+?)\s*", query, re.IGNORECASE | re.DOTALL)
    if not match:
        return {"status": "INCONCLUSIVE", "reason": "QUERY_STATEMENT_NOT_SUPPORTED_BY_COVERAGE_PARSER", "resolved_ids": []}
    source = Node(id="regression:query", name="Regression query", type="MEASURE", model_id=next(iter(models)))
    analysis = DaxAnalyzer(nodes).analyze_object(source, expression=match.group(1))
    resolved = {item["target"] for item in analysis.references if item.get("target")}
    # Calculations referenced by the query also execute their dependencies.
    adjacency = {}
    for edge in graph.get("edges", []):
        if edge["type"] in {"DEPENDS_ON", "REFERENCES"} and edge.get("evidence_class", "FACT") == "FACT":
            adjacency.setdefault(edge["from_id"], []).append(edge["to_id"])
    queue = list(resolved)
    while queue:
        current = queue.pop()
        for target in adjacency.get(current, []):
            if target not in resolved:
                resolved.add(target); queue.append(target)
    # Table contexts are evaluated through their referenced fields/calculations.
    resolved.update(indexed[target].properties["table_id"] for target in list(resolved) if target in indexed and indexed[target].properties.get("table_id"))
    children, uses = {}, {}
    for edge in graph.get("edges", []):
        if edge.get("evidence_class", "FACT") != "FACT": continue
        if edge["type"] == "CONTAINS": children.setdefault(edge["from_id"], []).append(edge["to_id"])
        if edge["type"] in {"USES", "FILTERS"}: uses.setdefault(edge["from_id"], set()).add(edge["to_id"])
    report_contexts = []
    for target in target_ids:
        if target not in indexed or indexed[target].type not in {"VISUAL", "PAGE", "REPORT"}: continue
        descendants, pending = set(), [target]
        while pending:
            item = pending.pop()
            if item in descendants: continue
            descendants.add(item); pending.extend(children.get(item, []))
        visuals = [item for item in descendants if indexed.get(item) and indexed[item].type == "VISUAL"]
        fields = set().union(*(uses.get(item, set()) for item in visuals)) if visuals else set()
        # Filtered/bookmarked/dynamic visual contexts need a separate compiler.
        # A matching field label cannot certify those unimplemented contexts.
        unsupported = False
        for item in descendants:
            raw = indexed[item].properties.get("raw_source", {})
            if raw.get("filters") or raw.get("filterConfig", {}).get("filters") or raw.get("visualInteractions") or raw.get("pageBinding"):
                unsupported = True
        if fields and fields.issubset(resolved) and not unsupported:
            resolved.add(target)
            report_contexts.append({"object_id": target, "field_ids": sorted(fields), "verification_scope": "BOUND_DATA_ONLY"})
    missing = sorted(set(target_ids) - resolved)
    return {"status": "PASSED" if not missing and not analysis.diagnostics else "INCONCLUSIVE", "resolved_ids": sorted(resolved),
            "missing_ids": missing, "diagnostics": analysis.diagnostics, "report_contexts": report_contexts}
