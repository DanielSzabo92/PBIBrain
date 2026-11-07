"""DATA_SOURCE nodes and SOURCES_FROM links read from the M of partitions and shared expressions (issue #10).

A data source node stands for one source object (a SQL table, a lakehouse table, a dataflow
entity, a file, a URL). Its id is a hash of the connector kind and the location, and it has no
model, so two models that read the same object link to the same node. A query whose M cannot
be read is marked ``check_status: not_checked`` (reason ``m_not_read``) instead of guessed.
"""

from __future__ import annotations

from typing import Any, Mapping, MutableMapping

from .m_sources import (
    REASON_M_NOT_READ, STATUS_NOT_CHECKED, STATUS_READ, data_source_id, entity_source, parameter_value,
    read_m_sources, source_name,
)
from .schema import Node

_SOURCE_FIELDS = ("kind", "connector", "server", "database", "schema", "object", "path", "url", "format",
                  "workspace_id", "lakehouse_id", "dataflow_id", "warehouse_id", "native_query", "query")


def _is_m(node: Node) -> bool:
    if node.type == "SHARED_EXPRESSION":
        raw = node.properties.get("raw_source")
        kind = raw.get("kind") if isinstance(raw, Mapping) else None
        return str(kind or "m").casefold() == "m"
    if node.type == "PARTITION":
        return str(node.properties.get("expression_language") or "").upper() != "DAX"
    return False


def _partition_source(node: Node) -> Mapping[str, Any]:
    raw = node.properties.get("raw_source")
    source = raw.get("source") if isinstance(raw, Mapping) else None
    return source if isinstance(source, Mapping) else {}


def _location(source: Mapping[str, Any]) -> str | None:
    parts = [source.get("server"), source.get("database")] if source.get("server") else [source.get("path") or source.get("url")]
    text = "/".join(str(part) for part in parts if part)
    return text or None


def link_data_sources(nodes: MutableMapping[str, Node]) -> list[tuple[str, str, str, str, dict[str, Any]]]:
    """Add DATA_SOURCE nodes to ``nodes``, mark each M query, and return the links to add.

    Each link is ``(edge type, from id, to id, evidence, properties)``.
    """

    queries = [node for node in nodes.values() if node.type in {"PARTITION", "SHARED_EXPRESSION"} and _is_m(node)]
    parameters: dict[str | None, dict[str, str]] = {}
    expressions: dict[tuple[str | None, str], Node] = {}
    for node in queries:
        if node.type != "SHARED_EXPRESSION":
            continue
        expressions[(node.model_id, node.name)] = node
        value = parameter_value(node.properties.get("expression"))
        if value is not None:
            parameters.setdefault(node.model_id, {})[node.name] = value
            node.properties["parameter_value"] = value
    links: list[tuple[str, str, str, str, dict[str, Any]]] = []
    results: dict[str, Any] = {}

    def result_of(node: Node) -> Any:
        if node.id not in results:
            results[node.id] = read_m_sources(node.properties.get("expression"), parameters.get(node.model_id, {}))
        return results[node.id]

    for node in sorted(queries, key=lambda item: item.id):
        if node.type == "SHARED_EXPRESSION" and "parameter_value" in node.properties:
            continue
        partition_source = _partition_source(node) if node.type == "PARTITION" else {}
        if str(node.properties.get("source_type") or partition_source.get("type") or "").casefold() == "entity":
            # Direct Lake: the table is read through a shared expression that names the lakehouse or warehouse.
            name = partition_source.get("expressionSource") or partition_source.get("expression_source")
            expression = expressions.get((node.model_id, str(name))) if name else None
            if expression is None:
                status, sources, reasons, used = STATUS_NOT_CHECKED, [], ["the expression source of the entity partition is not in the model"], []
            else:
                links.append(("REFERENCES", node.id, expression.id, "entity partition expression source", {}))
                base = result_of(expression)
                status, reasons, used = base.status, list(base.reasons), list(base.parameters)
                sources = entity_source(base.sources, schema=partition_source.get("schemaName"), entity=partition_source.get("entityName"))
                status = STATUS_NOT_CHECKED if reasons else STATUS_READ if sources else STATUS_NOT_CHECKED
                if not sources and not reasons:
                    reasons = ["the expression source of the entity partition names no data source"]
        elif not node.properties.get("expression"):
            continue
        else:
            result = result_of(node)
            status, sources, reasons, used = result.status, result.sources, result.reasons, result.parameters
        node.properties["source_status"] = status
        if used:
            node.properties["source_parameters"] = list(used)
        if status == STATUS_NOT_CHECKED:
            node.properties.update(check_status=STATUS_NOT_CHECKED, not_checked_reason=REASON_M_NOT_READ,
                                   not_checked_detail="; ".join(reasons))
        for source in sources:
            source_id = data_source_id(source)
            current = nodes.get(source_id)
            if current is None:
                properties = {key: source[key] for key in _SOURCE_FIELDS if source.get(key) not in (None, "")}
                location = _location(source)
                if location:
                    properties["location"] = location
                properties["model_ids"] = []
                current = nodes[source_id] = Node(id=source_id, type="DATA_SOURCE", name=source_name(source),
                                                  source="model_metadata", properties=properties)
            if node.model_id and node.model_id not in current.properties["model_ids"]:
                current.properties["model_ids"] = sorted([*current.properties["model_ids"], node.model_id])
            links.append(("SOURCES_FROM", node.id, source_id, f"M connector call {source.get('connector') or source.get('kind')}",
                          {"connector": source.get("connector"), **({"parameters": list(used)} if used else {})}))
    return links
