"""Deterministic selector evidence from canonical nodes and DAX analyses.

This module does not parse DAX.  It consumes the AST/analysis objects produced
by :mod:`backend.dax.analyzer`; that keeps semantic inference separate from
syntax and makes a second parse impossible on this path.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
import hashlib
import json
import re
from typing import Any, Iterable, Mapping, Sequence

from backend.graph.schema import Edge, Node, edge_from_dict, node_from_dict


SELECTOR_FUNCTIONS = frozenset(
    {
        "SELECTEDVALUE",
        "VALUES",
        "HASONEVALUE",
        "ISFILTERED",
        "ISCROSSFILTERED",
        "FILTERS",
    }
)

_MODEL_TYPES = frozenset({"TABLE", "COLUMN", "MEASURE"})
_VALUE_KEYS = (
    "known_values",
    "knownValues",
    "distinct_values",
    "distinctValues",
    "allowed_values",
    "allowedValues",
    "selector_options",
    "selectorOptions",
    "values",
    "options",
    "items",
)
_CARDINALITY_KEYS = ("cardinality", "distinct_count", "distinctCount", "value_count", "valueCount")
_SCOPED_VALUE_KEYS = (
    "values_by_column",
    "valuesByColumn",
    "column_values",
    "columnValues",
    "distinct_values_by_column",
    "distinctValuesByColumn",
    "cardinality_by_column",
    "cardinalityByColumn",
)
_UNSAFE_VALUE = object()


class SelectorDiscovery(list):
    """List-shaped selector result with optional engine side channels.

    Direct callers see selector candidates as a normal list.  The inference
    engine can also read option/default candidates and relationship edges from
    the attributes without requiring a second analysis pass.
    """

    def __init__(
        self,
        selectors: Iterable[dict[str, Any]] = (),
        *,
        candidates: Iterable[dict[str, Any]] = (),
        edges: Iterable[Edge] = (),
    ) -> None:
        super().__init__(selectors)
        self.candidates = list(candidates)
        self.edges = list(edges)


def _norm(value: Any) -> str:
    return "".join(char for char in str(value).casefold() if char.isalnum())


_VALUE_KEY_NAMES = frozenset(_norm(item) for item in _VALUE_KEYS)
_SCOPED_VALUE_KEY_NAMES = frozenset(_norm(item) for item in _SCOPED_VALUE_KEYS)


def _json(value: Any) -> Any:
    """Convert duck-typed analysis values to deterministic JSON data."""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json(item) for item in value]
    if is_dataclass(value):
        return _json(asdict(value))
    for method_name in ("to_dict", "as_dict"):
        method = getattr(value, method_name, None)
        if callable(method):
            try:
                return _json(method())
            except Exception:  # pragma: no cover - defensive duck typing
                pass
    try:
        values = vars(value)
    except TypeError:
        values = None
    if isinstance(values, Mapping):
        return {str(key): _json(item) for key, item in values.items()}
    return str(value)


def _get(value: Any, *keys: str, default: Any = None) -> Any:
    """Read mapping keys/attributes with snake/camel-case tolerance."""

    for key in keys:
        if isinstance(value, Mapping):
            if key in value and value[key] is not None:
                return value[key]
            wanted = _norm(key)
            for actual, candidate in value.items():
                if _norm(actual) == wanted and candidate is not None:
                    return candidate
        else:
            candidate = getattr(value, key, None)
            if candidate is not None:
                return candidate
    return default


def _node(value: Any) -> Node:
    return value if isinstance(value, Node) else node_from_dict(value)


def _nodes(values: Iterable[Node] | Mapping[str, Node] | None) -> list[Node]:
    if values is None:
        return []
    source = values.values() if isinstance(values, Mapping) else values
    result: dict[str, Node] = {}
    for value in source:
        try:
            item = _node(value)
        except (TypeError, ValueError):
            continue
        result[item.id] = item
    return [result[key] for key in sorted(result)]


def _analysis_items(analyses: Any, nodes: Sequence[Node]) -> list[tuple[str, Any]]:
    """Return ``(source_id, analysis)`` without reparsing expressions."""

    if analyses is None:
        result: list[tuple[str, Any]] = []
        for item in nodes:
            payload = item.properties.get("dax_analysis")
            if payload is not None:
                result.append((item.id, payload))
            # Phase 2 stores behavior facts on the canonical node.  Keep this
            # fallback useful when callers do not retain the batch object.
            behaviors = item.properties.get("dax_behaviors")
            if behaviors:
                result.append((item.id, {"source_object_id": item.id, "behaviors": behaviors}))
        return result

    batch = getattr(analyses, "analyses", None)
    if batch is not None:
        analyses = batch
    if isinstance(analyses, Mapping):
        return [(str(key), value) for key, value in sorted(analyses.items(), key=lambda pair: str(pair[0]))]

    result = []
    for value in analyses:
        source_id = _get(value, "source_object_id", "source_object", "object_id", "objectId")
        if source_id is not None:
            result.append((str(source_id), value))
    return sorted(result, key=lambda pair: pair[0])


def _analysis_value(analysis: Any, *keys: str, default: Any = None) -> Any:
    return _get(analysis, *keys, default=default)


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set, frozenset)):
        return list(value)
    return [value]


def _type(value: Any) -> str:
    return str(_get(value, "type", "object_type", "objectType", default="")).upper()


def _target_ids(record: Any) -> list[str]:
    values = _get(
        record,
        "target_ids",
        "targetIds",
        "targets",
        "target",
        "column_id",
        "columnId",
        "field_id",
        "fieldId",
        "object_id",
        "objectId",
        default=[],
    )
    result: list[str] = []
    for value in _list(values):
        if isinstance(value, Mapping):
            value = _get(value, "id", "target", "target_id", "targetId")
        if value is not None and str(value) not in result:
            result.append(str(value))
    return result


def _functions(analysis: Any) -> list[tuple[str, Any]]:
    """Get selector function records from existing analyzer output."""

    records: list[tuple[str, Any]] = []
    behaviors = _analysis_value(analysis, "behaviors", default=[])
    for behavior in _list(behaviors):
        function = _get(behavior, "function", "function_name", "functionName")
        kind = _type(behavior)
        if function is None and kind == "SELECTOR_CONSTRUCT":
            function = "SELECTOR_CONSTRUCT"
        if function is None:
            continue
        function_name = str(function).upper()
        if function_name in SELECTOR_FUNCTIONS or kind == "SELECTOR_CONSTRUCT":
            records.append((function_name, behavior))
    # A caller may pass a compact analysis containing only function records.
    for function in _list(_analysis_value(analysis, "functions", default=[])):
        name = _get(function, "function", "name", "function_name", "functionName")
        if name is not None and str(name).upper() in SELECTOR_FUNCTIONS:
            records.append((str(name).upper(), function))
    return records


def _relationship_columns(nodes: Sequence[Node], edges: Sequence[Edge]) -> set[str]:
    connected: set[str] = set()
    for node in nodes:
        if node.type != "RELATIONSHIP":
            continue
        for key in (
            "from_column_id",
            "fromColumnId",
            "to_column_id",
            "toColumnId",
            "from_column",
            "fromColumn",
            "to_column",
            "toColumn",
        ):
            value = _get(node.properties, key)
            if value is not None:
                connected.add(str(value))
    for edge in edges:
        if edge.type != "RELATES_TO":
            continue
        # RELATES_TO is relationship -> column in the canonical graph.
        connected.add(edge.to_id)
    return connected


def _table_columns(table: Node, nodes: Sequence[Node]) -> list[Node]:
    return [
        item
        for item in nodes
        if item.type == "COLUMN"
        and str(_get(item.properties, "table_id", "tableId", default="")) == table.id
    ]


def _table_measures(table: Node, nodes: Sequence[Node]) -> list[Node]:
    return [
        item
        for item in nodes
        if item.type == "MEASURE"
        and (
            str(_get(item.properties, "table_id", "tableId", default="")) == table.id
            or (item.model_id == table.model_id and not _get(item.properties, "table_id", "tableId"))
        )
    ]


def _source_id(analysis: Any, fallback: str = "") -> str:
    return str(_analysis_value(analysis, "source_object_id", "source_object", "object_id", "objectId", default=fallback))


def _behavior_targets(analysis: Any) -> dict[str, list[tuple[str, Any]]]:
    """Map resolved target IDs to selector behaviors and their evidence."""

    result: dict[str, list[tuple[str, Any]]] = {}
    for function, behavior in _functions(analysis):
        target_ids = _target_ids(behavior)
        for target in target_ids:
            result.setdefault(target, []).append((function, behavior))
        if target_ids:
            continue
        # Some lightweight callers expose references but no target_ids on the
        # behavior.  The analyzer's references already contain resolved IDs.
        refs = _analysis_value(analysis, "references", default=[])
        for reference in _list(refs):
            target = _get(reference, "target", "target_id", "targetId")
            if target is not None:
                result.setdefault(str(target), []).append((function, behavior))
    for target, values in list(result.items()):
        unique: dict[str, tuple[str, Any]] = {}
        for function, behavior in values:
            marker = json.dumps([function, _json(behavior)], sort_keys=True, default=str)
            unique.setdefault(marker, (function, behavior))
        result[target] = [unique[key] for key in sorted(unique)]
    return result


def _consumer_map(
    nodes: Sequence[Node],
    analyses: Any,
) -> dict[str, list[str]]:
    consumers: dict[str, set[str]] = {}
    for source_id, analysis in _analysis_items(analyses, nodes):
        source = next((item for item in nodes if item.id == source_id), None)
        if source is not None and source.type != "MEASURE":
            continue
        for reference in _list(_analysis_value(analysis, "references", default=[])):
            target = _get(reference, "target", "target_id", "targetId")
            if target is not None:
                consumers.setdefault(str(target), set()).add(source_id)
        for behavior in _list(_analysis_value(analysis, "behaviors", default=[])):
            for target in _target_ids(behavior):
                consumers.setdefault(target, set()).add(source_id)
    return {key: sorted(value) for key, value in sorted(consumers.items())}


def _normalize_value(value: Any, *, unwrap_literal: bool = False) -> Any:
    """Return a scalar metadata value or reject an ambiguous row."""

    if value is None:
        return _UNSAFE_VALUE
    if isinstance(value, (str, int, float, bool)):
        if unwrap_literal and isinstance(value, str):
            text = value.strip()
            if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
                return text[1:-1].replace(text[0] * 2, text[0])
        return value
    if isinstance(value, Mapping):
        # Query rows are often {"Value": ...} or {"Literal": {"Value": ...}}.
        # A row with multiple fields is not safe to flatten into one option.
        if len(value) != 1:
            return _UNSAFE_VALUE
        key, child = next(iter(value.items()))
        return _normalize_value(child, unwrap_literal=unwrap_literal or _norm(key) == "literal")
    return _UNSAFE_VALUE


def _value_items(value: Any) -> list[Any]:
    """Normalize explicit scalar values while rejecting composite rows."""

    if isinstance(value, (list, tuple, set, frozenset)):
        result: list[Any] = []
        for item in value:
            normalized = _normalize_value(item)
            if normalized is not _UNSAFE_VALUE:
                result.append(normalized)
        return result
    normalized = _normalize_value(value)
    return [] if normalized is _UNSAFE_VALUE else [normalized]


def _raw_values(value: Any, *, depth: int = 0) -> list[Any]:
    """Find explicit scalar values only; never infer from names or rows."""

    if depth > 5 or value is None:
        return []
    if isinstance(value, Mapping):
        result: list[Any] = []
        for key, candidate in value.items():
            if _norm(key) in _VALUE_KEY_NAMES:
                result.extend(_value_items(candidate))
        # Raw metadata commonly nests values below data/rows.  Do not descend
        # into an explicit value payload after rejecting a composite row.
        for key, child in value.items():
            if _norm(key) in _VALUE_KEY_NAMES:
                continue
            if isinstance(child, (Mapping, list, tuple, set, frozenset)):
                result.extend(_raw_values(child, depth=depth + 1))
        return result
    if isinstance(value, (list, tuple, set, frozenset)):
        result: list[Any] = []
        for child in value:
            normalized = _normalize_value(child)
            if normalized is not _UNSAFE_VALUE:
                result.append(normalized)
            elif isinstance(child, (Mapping, list, tuple, set, frozenset)):
                result.extend(_raw_values(child, depth=depth + 1))
        return result
    return []


def _scoped_values(owner: Any, column: Node) -> list[Any]:
    """Read table metadata only when it explicitly names this column."""

    if not isinstance(owner, Mapping):
        return []
    identifiers = {
        str(value)
        for value in (column.id, column.source_id, column.name)
        if value is not None and str(value)
    }
    normalized_identifiers = {_norm(value) for value in identifiers}
    result: list[Any] = []
    for key, payload in owner.items():
        if _norm(key) not in _SCOPED_VALUE_KEY_NAMES or not isinstance(payload, Mapping):
            continue
        for candidate_key, candidate_value in payload.items():
            if str(candidate_key) in identifiers or _norm(candidate_key) in normalized_identifiers:
                result.extend(_value_items(candidate_value))
    for key in ("columns", "fields"):
        payload = _get(owner, key)
        if not isinstance(payload, (list, tuple)):
            continue
        for candidate in payload:
            if not isinstance(candidate, Mapping):
                continue
            candidate_id = _get(candidate, "id", "source_id", "sourceId", "name", "displayName")
            if candidate_id is not None and (
                str(candidate_id) in identifiers or _norm(candidate_id) in normalized_identifiers
            ):
                result.extend(_raw_values(candidate))
    return result


def _known_values(table: Node, column: Node) -> list[Any]:
    values: list[Any] = []
    # Column metadata is already scoped.  Table metadata is read only through
    # explicit column-keyed containers, preventing sibling values leaking in
    # from the duplicated raw source snapshot.
    values.extend(_raw_values(column.properties))
    values.extend(_raw_values(column.properties.get("raw_source")))
    values.extend(_scoped_values(table.properties, column))
    values.extend(_scoped_values(table.properties.get("raw_source"), column))
    # Preserve order from source, then deduplicate by canonical JSON value.
    unique: dict[str, Any] = {}
    for value in values:
        normalized = _normalize_value(value)
        if normalized is _UNSAFE_VALUE:
            continue
        marker = json.dumps(_json(normalized), sort_keys=True, default=str)
        unique.setdefault(marker, _json(normalized))
    return [unique[key] for key in sorted(unique)]


def _cardinality(table: Node, column: Node, values: Sequence[Any]) -> int | None:
    for key in _CARDINALITY_KEYS:
        value = _get(column.properties, key)
        if isinstance(value, bool):
            continue
        try:
            if value is not None:
                return int(value)
        except (TypeError, ValueError):
            continue
    return len(values) if values else None


def _evidence_item(text: str, *, source: str, target: str | None = None, **extra: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "source": source,
        "status": "candidate",
        "evidence_class": "INFERRED",
        "evidence": text,
    }
    if target is not None:
        item["target"] = target
    item.update(extra)
    return item


def _semantic_selector_id(table_id: str) -> str:
    """Build a selector identity from stable canonical source identity only."""

    marker = json.dumps(str(table_id), ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(marker.encode("utf-8")).hexdigest()[:32]
    return f"semantic:selector:{digest}"


def discover_selectors(
    nodes: Iterable[Node] | Mapping[str, Node],
    analyses: Any = None,
    edges: Iterable[Edge] | Mapping[str, Edge] | None = None,
    *,
    max_cardinality: int = 100,
) -> list[dict[str, Any]]:
    """Return reviewable selector candidates from behavior and structure.

    A table name never participates in this decision.  The minimum signal is
    a disconnected table, selector-like DAX use, and consumption by a
    measure.  Explicit small cardinality raises confidence and is retained as
    evidence, but missing value metadata does not force a query or a guess.
    """

    canonical_nodes = _nodes(nodes)
    canonical_edges = []
    if edges is not None:
        values = edges.values() if isinstance(edges, Mapping) else edges
        for value in values:
            try:
                canonical_edges.append(value if isinstance(value, Edge) else edge_from_dict(value))
            except (TypeError, ValueError, KeyError):
                continue
    by_id = {item.id: item for item in canonical_nodes}
    connected_columns = _relationship_columns(canonical_nodes, canonical_edges)
    consumers = _consumer_map(canonical_nodes, analyses)
    behavior_by_column: dict[str, list[tuple[str, Any, str]]] = {}
    for source_id, analysis in _analysis_items(analyses, canonical_nodes):
        for target_id, values in _behavior_targets(analysis).items():
            target = by_id.get(target_id)
            if target is None or target.type != "COLUMN":
                continue
            for function, behavior in values:
                behavior_by_column.setdefault(target.id, []).append((function, behavior, source_id))

    candidates: list[dict[str, Any]] = []
    for table in canonical_nodes:
        if table.type != "TABLE":
            continue
        all_columns = _table_columns(table, canonical_nodes)
        # Only columns directly named by selector behavior can supply options
        # or be advertised as selector controls.  Other columns on the same
        # disconnected table are unrelated metadata.
        columns = [column for column in all_columns if column.id in behavior_by_column]
        table_behavior = [item for column in columns for item in behavior_by_column.get(column.id, [])]
        if not table_behavior:
            continue
        consumer_ids = sorted(
            {
                source_id
                for column in columns
                for source_id in consumers.get(column.id, [])
                if source_id in by_id and by_id[source_id].type == "MEASURE"
            }
        )
        if not consumer_ids:
            continue
        disconnected = bool(all_columns) and not any(column.id in connected_columns for column in all_columns)
        if not disconnected:
            continue

        value_columns: list[dict[str, Any]] = []
        options: list[Any] = []
        for column in columns:
            values = _known_values(table, column)
            count = _cardinality(table, column, values)
            if count is not None and count <= max_cardinality:
                value_columns.append({"column_id": column.id, "cardinality": count, "values": values})
                options.extend(values)
        unique_options: dict[str, Any] = {}
        for value in options:
            unique_options.setdefault(json.dumps(value, sort_keys=True, default=str), value)
        small_cardinality = bool(value_columns) and all(
            item["cardinality"] is not None and item["cardinality"] <= max_cardinality for item in value_columns
        )
        functions = sorted({function for function, _, _ in table_behavior})
        behavior_records = [
            {
                "function": function,
                "source_object": source_id,
                "ast_location": _get(behavior, "ast_location", "astLocation"),
                "extractor": _get(behavior, "extractor"),
                "evidence": _json(_get(behavior, "evidence")),
            }
            for function, behavior, source_id in table_behavior
        ]
        evidence: list[dict[str, Any]] = [
            _evidence_item(
                "table has no physical relationship to model columns",
                source="model_metadata",
                target=table.id,
                extractor="disconnected_table",
            ),
            _evidence_item(
                "referenced through " + ", ".join(functions),
                source="dax_analysis",
                target=table.id,
                extractor="selector_behavior",
                ast_location=next(
                    (
                        _get(behavior, "ast_location", "astLocation")
                        for _, behavior, _ in table_behavior
                        if _get(behavior, "ast_location", "astLocation") is not None
                    ),
                    None,
                ),
                behavior=behavior_records,
            ),
            _evidence_item(
                f"column referenced by {len(consumer_ids)} measure(s)",
                source="dax_analysis",
                target=table.id,
                extractor="measure_consumption",
                measure_ids=consumer_ids,
            ),
        ]
        if small_cardinality:
            evidence.append(
                _evidence_item(
                    f"selector column has {min(item['cardinality'] for item in value_columns)} distinct value(s)",
                    source="model_metadata",
                    target=table.id,
                    extractor="known_cardinality",
                )
            )
        score = 0.25 + 0.40 + 0.25 + (0.10 if small_cardinality else 0.0)
        selector_name = table.name or "Selector"
        selector_node_id = _semantic_selector_id(table.id)
        selector_id = selector_node_id
        candidate = {
            "id": selector_id,
            "candidate": "selector",
            "type": "SELECTOR",
            "value": selector_name,
            "meaning": selector_name,
            "target": table.id,
            "target_id": table.id,
            "selector_id": selector_id,
            "selector_node_id": selector_node_id,
            "name": selector_name,
            "model_id": table.model_id,
            "column_ids": [column.id for column in columns],
            "measure_ids": consumer_ids,
            "behavior_functions": functions,
            "options": [unique_options[key] for key in sorted(unique_options)],
            "source": "dax_analysis",
            "confidence": min(0.99, round(score, 2)),
            "status": "candidate",
            "evidence_class": "INFERRED",
            "edge_type": "SEMANTICALLY_MAPS_TO",
            "evidence": evidence,
            "properties": {
                "table_id": table.id,
                "column_ids": [column.id for column in columns],
                "consumer_ids": consumer_ids,
                "selector_id": selector_id,
                "selector_node_id": selector_node_id,
                "priority": 2,
            },
            "confidence_factors": {
                "disconnected_table": 0.25,
                "selector_behavior": 0.40,
                "measure_consumption": 0.25,
                "small_cardinality": 0.10 if small_cardinality else 0.0,
            },
        }
        candidates.append(candidate)
    selectors = sorted(candidates, key=lambda item: (str(item.get("target_id", "")), str(item.get("id", ""))))

    control_edges: list[Edge] = []
    for selector in selectors:
        selector_node_id = str(selector["selector_node_id"])
        for consumer_id in selector.get("measure_ids", []):
            marker = "|".join(("CONTROLLED_BY", str(consumer_id), selector_node_id, "dax_analysis"))
            edge_id = "edge:" + hashlib.sha256(marker.encode("utf-8")).hexdigest()[:32]
            control_edges.append(
                Edge(
                    id=edge_id,
                    type="CONTROLLED_BY",
                    from_id=str(consumer_id),
                    to_id=selector_node_id,
                    source="dax_analysis",
                    confidence=float(selector["confidence"]),
                    status="candidate",
                    evidence=selector["evidence"],
                    evidence_class="INFERRED",
                    properties={
                        "selector_id": selector_node_id,
                        "table_id": selector["target_id"],
                    },
                )
            )
    return SelectorDiscovery(selectors, candidates=selectors, edges=control_edges)


def discover_selector_candidates(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
    """Compatibility alias for the public selector-discovery operation."""

    return discover_selectors(*args, **kwargs)


def _candidate_table(candidate: Any, by_id: Mapping[str, Node]) -> tuple[Node | None, list[Node]]:
    properties = _get(candidate, "properties", default={})

    def candidate_value(*keys: str, default: Any = None) -> Any:
        value = _get(candidate, *keys, default=None)
        if value is not None:
            return value
        return _get(properties, *keys, default=default)

    table_hint = candidate_value("table_id", "tableId")
    target = table_hint or _get(candidate, "target_id", "target", "selector_id")
    target_node = by_id.get(str(target)) if target is not None else None
    if target_node is not None and target_node.type == "TABLE":
        columns: list[Node] = []
        for value in _list(candidate_value("column_ids", "columnIds", default=[])):
            column = by_id.get(str(value))
            if column is None or column.type != "COLUMN":
                continue
            table_id = _get(column.properties, "table_id", "tableId")
            if table_id is not None and str(table_id) == target_node.id:
                columns.append(column)
        return target_node, columns
    columns: list[Node] = []
    for value in _list(candidate_value("column_ids", "columnIds", default=[])):
        column = by_id.get(str(value))
        if column is not None and column.type == "COLUMN":
            columns.append(column)
    if columns:
        table_ids = {
            str(table_id)
            for column in columns
            if (table_id := _get(column.properties, "table_id", "tableId")) is not None
        }
        if len(table_ids) != 1:
            return None, []
        table_id = next(iter(table_ids))
        table = by_id.get(str(table_id)) if table_id is not None else None
        return table, [column for column in columns if str(_get(column.properties, "table_id", "tableId")) == str(table_id)]
    return None, []


def discover_selector_options(
    selectors: Iterable[Any] | Mapping[str, Any],
    nodes: Iterable[Node] | Mapping[str, Node],
    *,
    max_values: int = 100,
) -> list[dict[str, Any]]:
    """Return explicit selector values as factual option records.

    This reads metadata already present in the canonical graph.  It does not
    issue validation queries; a future adapter can pass validated values into
    the same record shape.
    """

    canonical_nodes = _nodes(nodes)
    by_id = {item.id: item for item in canonical_nodes}
    candidates = selectors.values() if isinstance(selectors, Mapping) else selectors
    result: list[dict[str, Any]] = []
    for candidate in candidates:
        table, candidate_columns = _candidate_table(candidate, by_id)
        if table is None:
            continue
        properties = _get(candidate, "properties", default={})
        scoped_columns = _get(candidate, "column_ids", "columnIds", default=None)
        if scoped_columns is None:
            scoped_columns = _get(properties, "column_ids", "columnIds", default=None)
        has_scoped_columns = scoped_columns is not None
        columns = candidate_columns if has_scoped_columns else _table_columns(table, canonical_nodes)
        values: list[tuple[str, Any]] = []
        for column in columns:
            for value in _known_values(table, column):
                values.append((column.id, value))
        unique: dict[str, tuple[str, Any]] = {}
        for column_id, value in values:
            marker = json.dumps(value, sort_keys=True, default=str)
            unique.setdefault(marker, (column_id, value))
        if len(unique) > max_values:
            continue
        # The graph endpoint is always derived from the resolved canonical
        # table ID.  Display names or caller-provided labels are not identity.
        selector_id = _semantic_selector_id(table.id)
        for ordinal, marker in enumerate(sorted(unique)):
            column_id, value = unique[marker]
            value_text = str(value)
            option_digest = hashlib.sha256(
                "|".join(
                    json.dumps(_json(part), ensure_ascii=False, sort_keys=True, default=str)
                    for part in (selector_id, value)
                ).encode("utf-8")
            ).hexdigest()[:32]
            option_id = f"semantic:selector-option:{option_digest}"
            result.append(
                {
                    "id": option_id,
                    "type": "SELECTOR_OPTION",
                    "name": value_text,
                    "value": value,
                    "selector_id": selector_id,
                    "target": selector_id,
                    "column_id": column_id,
                    "ordinal": ordinal,
                    "source": "model_metadata",
                    "confidence": 1.0,
                    "status": "factual",
                    "evidence_class": "FACT",
                    "evidence": [
                        {
                            "source": "model_metadata",
                            "status": "factual",
                            "evidence_class": "FACT",
                            "extractor": "known_selector_value",
                            "column_id": column_id,
                            "value": value,
                        }
                    ],
                }
            )
    return sorted(result, key=lambda item: (str(item["selector_id"]), int(item["ordinal"]), str(item["id"])))


def selector_options(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
    return discover_selector_options(*args, **kwargs)


def _ast_children(value: Any) -> list[Any]:
    if value is None or isinstance(value, (str, bytes, int, float, bool)):
        return []
    arguments = _get(value, "arguments", "args")
    if arguments is not None:
        return _list(arguments)
    children = _get(value, "children")
    if children is not None:
        return _list(children)
    if isinstance(value, Mapping):
        result = []
        for key, child in value.items():
            if _norm(key) in {"location", "span", "text", "value", "name", "kind", "nodetype"}:
                continue
            if isinstance(child, (Mapping, list, tuple)):
                result.extend(_list(child))
        return result
    return []


def _walk_ast(root: Any) -> Iterable[Any]:
    seen: set[int] = set()
    stack = [root]
    while stack:
        value = stack.pop()
        if value is None or isinstance(value, (str, bytes, int, float, bool)):
            continue
        marker = id(value)
        if marker in seen:
            continue
        seen.add(marker)
        yield value
        children = _ast_children(value)
        stack.extend(reversed(children))


def _ast_function_name(value: Any) -> str | None:
    name = _get(value, "function", "function_name", "functionName")
    kind = str(_get(value, "kind", "node_type", "nodeType", default="")).upper()
    if name is None and ("FUNCTION" in kind or "CALL" in kind):
        name = _get(value, "name", "identifier")
    return str(name).upper() if name is not None else None


def _literal(value: Any) -> tuple[bool, Any]:
    kind = str(_get(value, "kind", "node_type", "nodeType", default="")).upper()
    if "LITERAL" not in kind and _get(value, "literal_type", "literalType") is None:
        return False, None
    literal = _get(value, "value", "text")
    if isinstance(literal, Mapping):
        literal = _get(literal, "value", "text", default=literal)
    if isinstance(literal, str):
        text = literal.strip()
        if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
            literal = text[1:-1].replace(text[0] * 2, text[0])
    return True, literal


def _default_records(analysis: Any) -> list[dict[str, Any]]:
    ast = _analysis_value(analysis, "ast", "dax_ast")
    if ast is None:
        return []
    source_id = _source_id(analysis)
    result: list[dict[str, Any]] = []
    # Import the established visitor only as an AST walker.  It never parses.
    try:
        from backend.dax.evidence import ast_location
        from backend.dax.visitors import attr, function_name, walk_ast  # type: ignore
    except ImportError:  # pragma: no cover - fallback for lightweight callers
        attr = function_name = ast_location = walk_ast = None
    if walk_ast is not None:
        function_nodes = []
        for visit in walk_ast(ast):
            name = function_name(visit.node)
            if name and str(name).upper() == "SELECTEDVALUE":
                args = attr(visit.node, "arguments", "args", default=())
                function_nodes.append((visit.node, _list(args)))
    else:
        function_nodes = []
        for item in _walk_ast(ast):
            if _ast_function_name(item) == "SELECTEDVALUE":
                function_nodes.append((item, _ast_children(item)))
    selected_behaviors = [behavior for function, behavior in _functions(analysis) if function == "SELECTEDVALUE"]
    for function_index, (function_node, args) in enumerate(function_nodes):
        if len(args) < 2:
            continue
        is_literal, value = _literal(args[1])
        if not is_literal:
            continue
        location = ast_location(args[1]) if ast_location is not None else _get(args[1], "location", "span", "ast_location")
        function_location = ast_location(function_node) if ast_location is not None else _get(function_node, "location", "span")
        target_text = _get(args[0], "qualified_name", "qualification", "text", "name")
        behavior = selected_behaviors[function_index] if function_index < len(selected_behaviors) else None
        target_ids = _target_ids(behavior) if behavior is not None else []
        result.append(
            {
                "source_object": source_id,
                "target_id": target_ids[0] if target_ids else None,
                "target_ids": target_ids,
                "target_reference": target_text,
                "value": value,
                "default": value,
                "source": "dax_ast",
                "confidence": 1.0,
                "status": "candidate",
                "evidence_class": "INFERRED",
                "extractor": "selectedvalue_default",
                "ast_location": location,
                "function_ast_location": function_location,
                "evidence": [f"SELECTEDVALUE fallback literal: {value!r}"],
            }
        )
    return result


def infer_selector_defaults(analyses: Any) -> list[dict[str, Any]]:
    """Extract SELECTEDVALUE fallback literals from an existing AST batch."""

    values = analyses.values() if isinstance(analyses, Mapping) else getattr(analyses, "analyses", analyses)
    if values is None:
        return []
    if isinstance(values, Mapping):
        values = values.values()
    result: list[dict[str, Any]] = []
    for analysis in values:
        result.extend(_default_records(analysis))
    unique: dict[str, dict[str, Any]] = {}
    for value in result:
        marker = json.dumps(value, sort_keys=True, default=str)
        unique.setdefault(marker, value)
    return [unique[key] for key in sorted(unique)]


def discover_selector_defaults(analyses: Any) -> list[dict[str, Any]]:
    return infer_selector_defaults(analyses)


def selector_defaults(analyses: Any) -> list[dict[str, Any]]:
    return infer_selector_defaults(analyses)


__all__ = [
    "SELECTOR_FUNCTIONS",
    "SelectorDiscovery",
    "discover_selectors",
    "discover_selector_candidates",
    "discover_selector_options",
    "selector_options",
    "infer_selector_defaults",
    "discover_selector_defaults",
    "selector_defaults",
]
