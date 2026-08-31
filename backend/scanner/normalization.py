"""Mechanical Power BI metadata normalization.

This module assigns canonical identities and turns source-specific mappings into
plain :class:`~backend.graph.schema.Node` objects.  It intentionally creates no
semantic assertions; semantic inference starts in a later phase.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from backend.graph.schema import Node

from .metadata_reader import collection, description, display_name, expression, pick, source_id
from .model_reader import ModelReader
from .report_reader import ReportReader


def _norm(value: Any) -> str:
    return "".join(char for char in str(value).casefold() if char.isalnum())


def _present(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


def _bool(value: Any, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.casefold().strip()
        if lowered in {"true", "yes", "1"}:
            return True
        if lowered in {"false", "no", "0"}:
            return False
    return bool(value)


def _safe_value(value: Any) -> Any:
    """Make source references JSON-safe without changing ordinary metadata."""

    if isinstance(value, Mapping):
        return {str(key): _safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _raw_properties(
    raw: Mapping[str, Any], *, exclude: Iterable[str] = (), **values: Any
) -> dict[str, Any]:
    excluded = {_norm(key) for key in exclude}
    result = {key: _safe_value(value) for key, value in values.items() if value is not None}
    result["raw_source"] = _safe_value(
        {key: value for key, value in raw.items() if _norm(key) not in excluded}
    )
    return result


def _decode_json_field(value: Any) -> Any:
    """Decode only report fields whose API contract permits JSON strings."""

    if not isinstance(value, str):
        return value
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        return value
    return decoded if isinstance(decoded, (Mapping, list)) else value


def _prepare_visual(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Expose legacy and PBIR visual definitions without changing source data."""

    prepared = dict(raw)
    for key in ("config", "query", "filters"):
        value = pick(prepared, key)
        decoded = _decode_json_field(value)
        if decoded is not value:
            prepared[key] = decoded

    # PBIR keeps the definition under visual; legacy report JSON keeps it in
    # config.singleVisual. Flatten known mechanical fields for one extractor.
    for candidate in (pick(prepared, "visual"), pick(prepared, "config")):
        if not isinstance(candidate, Mapping):
            continue
        for key, value in candidate.items():
            prepared.setdefault(key, value)
        single = pick(candidate, "singleVisual")
        if isinstance(single, Mapping):
            prepared.setdefault("singleVisual", single)
            for key, value in single.items():
                prepared.setdefault(key, value)
    return prepared


def _literal_text(value: Any) -> str | None:
    if isinstance(value, Mapping):
        nested = pick(value, "value", "text", "expr", "literal")
        return _literal_text(nested) if nested is not None else None
    if value is None:
        return None
    text = str(value)
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        quote = text[0]
        text = text[1:-1]
        text = text.replace(quote * 2, quote)
    return text or None


def _visual_parts(raw: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    parts: list[Mapping[str, Any]] = [raw]
    for key in ("visual", "config", "singleVisual"):
        value = pick(raw, key)
        if isinstance(value, Mapping):
            parts.append(value)
            nested = pick(value, "singleVisual")
            if isinstance(nested, Mapping):
                parts.append(nested)
    return parts


def _visual_type(raw: Mapping[str, Any]) -> Any:
    for part in _visual_parts(raw):
        value = pick(part, "visualType", "visual_type", "type")
        if value is not None and not isinstance(value, Mapping):
            return value
    return None


def _visual_title(raw: Mapping[str, Any]) -> str | None:
    for part in _visual_parts(raw):
        value = pick(part, "title", "displayTitle", "display_title")
        if value is not None and not isinstance(value, Mapping):
            return _literal_text(value)
        for key in ("vcObjects", "objects"):
            objects = pick(part, key)
            if not isinstance(objects, Mapping):
                continue
            title = pick(objects, "title")
            entries = title if isinstance(title, list) else [title]
            for entry in entries:
                if not isinstance(entry, Mapping):
                    continue
                properties = pick(entry, "properties")
                text = pick(properties, "text") if isinstance(properties, Mapping) else None
                candidate = _literal_text(text)
                if candidate:
                    return candidate
    return None


def _source_entities(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    raw_from = pick(value, "from")
    entries = raw_from if isinstance(raw_from, list) else [raw_from]
    result: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        alias = pick(entry, "name", "source", "alias")
        entity = pick(entry, "entity", "table", "tableName")
        if alias is not None and entity is not None:
            result[_norm(alias)] = str(entity)
    return result


def _semantic_binding(value: Any, entities: Mapping[str, str]) -> tuple[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    column = pick(value, "column")
    if isinstance(column, Mapping):
        expression_value = pick(column, "expression")
        source_ref = pick(expression_value, "sourceRef") if isinstance(expression_value, Mapping) else None
        alias = pick(source_ref, "source", "name") if isinstance(source_ref, Mapping) else None
        table = entities.get(_norm(alias)) if alias is not None else None
        table = table or (pick(source_ref, "entity", "table") if isinstance(source_ref, Mapping) else None)
        property_name = pick(column, "property", "name", "column")
        if property_name is not None:
            if table is not None:
                return "COLUMN", {"table": table, "column": property_name}
            return "COLUMN", property_name
    measure = pick(value, "measure")
    if isinstance(measure, Mapping):
        property_name = pick(measure, "property", "name", "measure")
        if property_name is not None:
            text = str(property_name).strip()
            if len(text) >= 2 and text[0] == "[" and text[-1] == "]":
                text = text[1:-1]
            return "MEASURE", text
    aggregation = pick(value, "aggregation")
    if isinstance(aggregation, Mapping):
        return _semantic_binding(aggregation, entities)
    field = pick(value, "field")
    if isinstance(field, Mapping):
        return _semantic_binding(field, entities)
    expression_value = pick(value, "expression")
    if isinstance(expression_value, Mapping):
        return _semantic_binding(expression_value, entities)
    return None


def _collect_semantic_bindings(raw: Mapping[str, Any]) -> tuple[list[tuple[str, Any]], dict[str, tuple[str, Any]], dict[str, str]]:
    found: list[tuple[str, Any]] = []
    query_refs: dict[str, tuple[str, Any]] = {}
    entities: dict[str, str] = {}

    def visit(value: Any, inherited: Mapping[str, str]) -> None:
        if isinstance(value, Mapping):
            local = dict(inherited)
            local.update(_source_entities(value))
            entities.update(local)
            direct = _semantic_binding(value, local)
            if direct:
                found.append(direct)
                reference = pick(value, "name", "queryRef", "query_ref")
                if reference is not None:
                    query_refs[_norm(reference)] = direct
            selected = pick(value, "select")
            entries = selected if isinstance(selected, list) else [selected]
            for entry in entries:
                if not isinstance(entry, Mapping):
                    continue
                binding = _semantic_binding(entry, local)
                if binding:
                    found.append(binding)
                    reference = pick(entry, "name", "queryRef", "query_ref")
                    if reference is not None:
                        query_refs[_norm(reference)] = binding
            for child in value.values():
                visit(child, local)
        elif isinstance(value, (list, tuple)):
            for child in value:
                visit(child, inherited)

    visit(raw, {})
    unique: list[tuple[str, Any]] = []
    seen: set[str] = set()
    for item in found:
        marker = json.dumps([item[0], _safe_value(item[1])], sort_keys=True, default=str)
        if marker not in seen:
            seen.add(marker)
            unique.append(item)
    return unique, query_refs, entities


class StableIdentity:
    """Canonical IDs backed by source IDs and a persisted generated map."""

    def __init__(self, mapping_path: str | Path | None = None) -> None:
        self.mapping_path = Path(mapping_path) if mapping_path is not None else None
        self.mapping: dict[str, str] = {}
        if self.mapping_path and self.mapping_path.is_file():
            try:
                payload = json.loads(self.mapping_path.read_text(encoding="utf-8"))
                values = payload.get("mappings", payload) if isinstance(payload, Mapping) else {}
                if isinstance(values, Mapping):
                    self.mapping = {str(key): str(value) for key, value in values.items()}
            except (OSError, ValueError, TypeError):
                self.mapping = {}

    def token(self, scope: str, object_type: str, source: Any = None, fallback: str = "object") -> str:
        if _present(source):
            return str(source).strip()
        key = f"{scope}|{object_type.upper()}|{fallback}"
        token = self.mapping.get(key)
        if token is None:
            token = uuid.uuid5(uuid.NAMESPACE_URL, f"powerbi-brain:{key}").hex
            self.mapping[key] = token
        return token

    def object_id(
        self,
        object_type: str,
        source: Any = None,
        *,
        parent_id: str | None = None,
        fallback: str = "object",
    ) -> tuple[str, str]:
        kind = str(object_type).upper()
        token = self.token(parent_id or "root", kind, source, fallback)
        prefix = kind.casefold()
        return (f"{parent_id}/{prefix}:{token}" if parent_id else f"{prefix}:{token}", token)

    def save(self) -> None:
        if self.mapping_path is None:
            return
        self.mapping_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "mappings": {key: self.mapping[key] for key in sorted(self.mapping)}}
        self.mapping_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


@dataclass(slots=True)
class NormalizationResult:
    nodes: list[Node]
    model_ids: list[str] = field(default_factory=list)
    report_ids: list[str] = field(default_factory=list)

    def __iter__(self):
        return iter(self.nodes)

    def __len__(self) -> int:
        return len(self.nodes)


class Normalizer:
    """Normalize one or more model/report payloads into canonical nodes."""

    def __init__(self, identity: StableIdentity | None = None, identity_path: str | Path | None = None) -> None:
        self.identity = identity or StableIdentity(identity_path)
        self.nodes: dict[str, Node] = {}
        self._lookup: dict[tuple[str, str, str], str] = {}
        self._model_refs: dict[str, str] = {}
        self._model_ids: list[str] = []
        self._report_ids: list[str] = []

    @property
    def model_ids(self) -> list[str]:
        return list(self._model_ids)

    @property
    def report_ids(self) -> list[str]:
        return list(self._report_ids)

    def _add(self, node: Node, *, aliases: Iterable[Any] = ()) -> Node:
        existing = self.nodes.get(node.id)
        if existing is not None:
            return existing
        self.nodes[node.id] = node
        model_scope = node.model_id or "global"
        values = [node.source_id, node.name, *aliases]
        for value in values:
            if not _present(value):
                continue
            key = _norm(value)
            self._lookup.setdefault((model_scope, node.type, key), node.id)
            self._lookup.setdefault(("global", node.type, key), node.id)
            if node.type == "COLUMN" and node.properties.get("table_id"):
                table_id = str(node.properties["table_id"])
                self._lookup.setdefault((model_scope, node.type, f"{_norm(table_id)}|{key}"), node.id)
                self._lookup.setdefault(("global", node.type, f"{_norm(table_id)}|{key}"), node.id)
        return node

    def _new_node(
        self,
        object_type: str,
        raw: Mapping[str, Any],
        *,
        parent_id: str | None = None,
        model_id: str | None = None,
        report_id: str | None = None,
        fallback: str,
        properties: Mapping[str, Any] | None = None,
        aliases: Iterable[Any] = (),
        source: str = "model_metadata",
    ) -> Node:
        raw_source = source_id(raw)
        object_id, effective_source = self.identity.object_id(
            object_type, raw_source, parent_id=parent_id, fallback=fallback
        )
        node = Node(
            id=object_id,
            type=object_type,
            name=display_name(raw, default=effective_source),
            description=description(raw),
            model_id=model_id,
            report_id=report_id,
            source_id=effective_source,
            properties=dict(properties or {}),
            source=source,
        )
        return self._add(node, aliases=aliases)

    def _remember_model(self, raw: Mapping[str, Any], node: Node) -> None:
        for value in (node.source_id, node.name, source_id(raw), pick(raw, "modelId", "datasetId")):
            if _present(value):
                self._model_refs[_norm(value)] = node.id

    def _resolve_model(self, ref: Any) -> str | None:
        if isinstance(ref, Mapping):
            ref = source_id(ref) or display_name(ref)
        if _present(ref):
            text = str(ref)
            if text in self.nodes and self.nodes[text].type == "MODEL":
                return text
            found = self._model_refs.get(_norm(text))
            if found:
                return found
            # A report may be normalized by itself.  A native Power BI model
            # ID still gives it a deterministic canonical reference even when
            # the model payload is loaded in a separate scan.
            return text if text.startswith("model:") else f"model:{text}"
        if len(self._model_ids) == 1:
            return self._model_ids[0]
        return None

    def _resolve_ref(self, ref: Any, expected: Sequence[str] | None = None, model_id: str | None = None) -> str | None:
        expected_types = [str(item).upper() for item in (expected or ("MEASURE", "COLUMN", "TABLE", "FIELD_PARAMETER"))]
        scope = model_id or (self._model_ids[0] if len(self._model_ids) == 1 else "global")
        if isinstance(ref, Node):
            return ref.id
        if isinstance(ref, Mapping):
            direct = pick(ref, "canonical_id", "canonicalId")
            if _present(direct) and str(direct) in self.nodes:
                return str(direct)
            explicit_type = pick(ref, "type", "object_type", "objectType")
            if explicit_type:
                expected_types = [str(explicit_type).upper()]
            table_ref = pick(ref, "table", "table_id", "tableId", "entity")
            column_ref = pick(ref, "column", "column_id", "columnId", "field", "property")
            measure_ref = pick(ref, "measure", "measure_id", "measureId")
            if measure_ref is not None:
                return self._resolve_ref(measure_ref, ["MEASURE"], model_id)
            if column_ref is not None:
                if isinstance(column_ref, Mapping):
                    column_ref = source_id(column_ref) or display_name(column_ref)
                if table_ref is not None:
                    table_id = self._resolve_ref(table_ref, ["TABLE"], model_id)
                    if table_id:
                        found = self._lookup.get((scope, "COLUMN", f"{_norm(table_id)}|{_norm(column_ref)}"))
                        if found:
                            return found
                return self._resolve_ref(column_ref, ["COLUMN"], model_id)
            value = source_id(ref) or pick(ref, "name", "queryRef", "query_ref", "ref", "value")
            if value is not None and value is not ref:
                return self._resolve_ref(value, expected_types, model_id)
            return None
        if not _present(ref):
            return None
        text = str(ref).strip()
        if text in self.nodes and (not expected_types or self.nodes[text].type in expected_types):
            return text
        # Common report binding spelling: 'Table'[Column], Table[Column], or Table.Column.
        bracket = re.match(r"^'?([^']+?)'?\[([^]]+)\]$", text)
        if bracket:
            table_name, column_name = bracket.groups()
            return self._resolve_ref({"table": table_name, "column": column_name}, ["COLUMN"], model_id)
        if "." in text and "COLUMN" in expected_types:
            table_name, column_name = text.rsplit(".", 1)
            found = self._resolve_ref({"table": table_name, "column": column_name}, ["COLUMN"], model_id)
            if found:
                return found
        for object_type in expected_types:
            found = self._lookup.get((scope, object_type, _norm(text)))
            if found:
                return found
            found = self._lookup.get(("global", object_type, _norm(text)))
            if found:
                return found
        return None

    def normalize_model(self, source: Any, *, source_key: Any = 0) -> NormalizationResult:
        raw = ModelReader().read(source)
        name = display_name(raw, default="model")
        model_source = source_id(raw)
        model_id, model_effective_source = self.identity.object_id(
            "MODEL", model_source, fallback=f"model:{model_source or source_key}"
        )
        model = Node(
            id=model_id,
            type="MODEL",
            name=name or model_effective_source,
            description=description(raw),
            source_id=model_effective_source,
            properties=_raw_properties(
                raw,
                exclude=("tables", "entities", "relationships", "measures"),
                workspace_id=pick(raw, "workspace_id", "workspaceId"),
                compatibility_level=pick(raw, "compatibility_level", "compatibilityLevel"),
            ),
            source="model_metadata",
        )
        self._add(model, aliases=(model_source,))
        if model_id not in self._model_ids:
            self._model_ids.append(model_id)
        self._remember_model(raw, model)

        tables = collection(raw, "tables", "entities")
        for table_index, table_raw in enumerate(tables):
            if not isinstance(table_raw, Mapping):
                continue
            table_source = source_id(table_raw)
            table_name = display_name(table_raw, default=f"table_{table_index}")
            table = self._new_node(
                "TABLE",
                table_raw,
                parent_id=model_id,
                model_id=model_id,
                fallback=f"table:{table_source or table_index}",
                properties=_raw_properties(
                    table_raw,
                    exclude=("columns", "fields", "measures", "calculations"),
                    hidden=_bool(pick(table_raw, "hidden", "isHidden")),
                    table_type=pick(table_raw, "type", "tableType"),
                    storage_mode=pick(table_raw, "storageMode", "storage_mode"),
                ),
                aliases=(table_source, table_name),
            )
            table_id = table.id
            for column_index, column_raw in enumerate(collection(table_raw, "columns", "fields")):
                if not isinstance(column_raw, Mapping):
                    continue
                column_source = source_id(column_raw)
                column_name = display_name(column_raw, default=f"column_{column_index}")
                self._new_node(
                    "COLUMN",
                    column_raw,
                    parent_id=table_id,
                    model_id=model_id,
                    fallback=f"column:{column_source or column_index}",
                    properties=_raw_properties(
                        column_raw,
                        table_id=table_id,
                        datatype=pick(column_raw, "datatype", "dataType", "type"),
                        hidden=_bool(pick(column_raw, "hidden", "isHidden")),
                        expression=expression(column_raw),
                        format_string=pick(column_raw, "format_string", "formatString", "format"),
                        sort_by=pick(column_raw, "sort_by", "sortByColumn", "sortBy"),
                        summarize_by=pick(column_raw, "summarize_by", "summarizeBy"),
                    ),
                    aliases=(column_source, column_name),
                )
            for measure_index, measure_raw in enumerate(collection(table_raw, "measures", "calculations")):
                if not isinstance(measure_raw, Mapping):
                    continue
                measure_source = source_id(measure_raw)
                measure_name = display_name(measure_raw, default=f"measure_{measure_index}")
                self._new_node(
                    "MEASURE",
                    measure_raw,
                    parent_id=table_id,
                    model_id=model_id,
                    fallback=f"measure:{measure_source or measure_index}",
                    properties=_raw_properties(
                        measure_raw,
                        table_id=table_id,
                        expression=expression(measure_raw),
                        format_string=pick(measure_raw, "format_string", "formatString", "format"),
                        format_expression=pick(
                            measure_raw,
                            "format_expression",
                            "formatStringExpression",
                            "format_string_expression",
                        ),
                        hidden=_bool(pick(measure_raw, "hidden", "isHidden")),
                        display_folder=pick(measure_raw, "display_folder", "displayFolder"),
                    ),
                    aliases=(measure_source, measure_name),
                )

        # A few APIs expose measures at model level rather than inside tables.
        for measure_index, measure_raw in enumerate(collection(raw, "measures", "calculations")):
            if not isinstance(measure_raw, Mapping):
                continue
            table_ref = pick(measure_raw, "table", "table_id", "tableId", "entity")
            table_id = self._resolve_ref(table_ref, ["TABLE"], model_id) if table_ref is not None else None
            parent = table_id or model_id
            measure_source = source_id(measure_raw)
            measure_name = display_name(measure_raw, default=f"measure_{measure_index}")
            self._new_node(
                "MEASURE",
                measure_raw,
                parent_id=parent,
                model_id=model_id,
                fallback=f"measure:{measure_source or measure_index}",
                properties=_raw_properties(
                    measure_raw,
                    table_id=table_id,
                    expression=expression(measure_raw),
                    format_string=pick(measure_raw, "format_string", "formatString", "format"),
                    format_expression=pick(
                        measure_raw,
                        "format_expression",
                        "formatStringExpression",
                        "format_string_expression",
                    ),
                    hidden=_bool(pick(measure_raw, "hidden", "isHidden")),
                    display_folder=pick(measure_raw, "display_folder", "displayFolder"),
                ),
                aliases=(measure_source, measure_name),
            )

        self._normalize_model_extras(raw, model_id)
        self.identity.save()
        return NormalizationResult(list(self.nodes.values()), self.model_ids, self.report_ids)

    def _normalize_model_extras(self, raw: Mapping[str, Any], model_id: str) -> None:
        for relationship_index, relationship_raw in enumerate(collection(raw, "relationships", "relations")):
            if not isinstance(relationship_raw, Mapping):
                continue
            from_table = pick(relationship_raw, "from_table", "fromTable", "sourceTable")
            from_column = pick(relationship_raw, "from_column", "fromColumn", "sourceColumn")
            to_table = pick(relationship_raw, "to_table", "toTable", "targetTable")
            to_column = pick(relationship_raw, "to_column", "toColumn", "targetColumn")
            from_ref = pick(relationship_raw, "from", "source")
            to_ref = pick(relationship_raw, "to", "target")
            if from_table is not None or from_column is not None:
                # PBIP/TMDL adapters may already provide a structured
                # ``from_column`` endpoint.  Keep it intact so resolution can
                # use its table and column names instead of nesting a mapping
                # under ``column``.
                from_ref = (
                    from_column
                    if isinstance(from_column, Mapping) and from_table is None
                    else {"table": from_table, "column": from_column}
                )
            if to_table is not None or to_column is not None:
                to_ref = (
                    to_column
                    if isinstance(to_column, Mapping) and to_table is None
                    else {"table": to_table, "column": to_column}
                )
            if from_ref is None:
                from_ref = {"table": from_table, "column": from_column}
            if to_ref is None:
                to_ref = {"table": to_table, "column": to_column}
            from_id = self._resolve_ref(from_ref, ["COLUMN"], model_id)
            to_id = self._resolve_ref(to_ref, ["COLUMN"], model_id)
            relationship_source = source_id(relationship_raw)
            self._new_node(
                "RELATIONSHIP",
                relationship_raw,
                parent_id=model_id,
                model_id=model_id,
                fallback=f"relationship:{relationship_source or relationship_index}",
                properties=_raw_properties(
                    relationship_raw,
                    from_column_id=from_id,
                    to_column_id=to_id,
                    from_ref=_safe_value(from_ref),
                    to_ref=_safe_value(to_ref),
                    cardinality=pick(relationship_raw, "cardinality", "relationshipType"),
                    cross_filter_direction=pick(
                        relationship_raw,
                        "cross_filter_direction",
                        "crossFilterDirection",
                        "crossFilteringBehavior",
                        "filterDirection",
                    ),
                    active=_bool(pick(relationship_raw, "active", "isActive")),
                ),
                aliases=(relationship_source,),
            )

        for parameter_index, parameter_raw in enumerate(
            collection(raw, "field_parameters", "fieldParameters", "parameters")
        ):
            if not isinstance(parameter_raw, Mapping):
                continue
            entries = collection(parameter_raw, "entries", "parameter_entries", "parameterEntries", "values", "items")
            resolved: list[str] = []
            normalized_entries: list[Any] = []
            for entry in entries:
                ref = entry
                if isinstance(entry, Mapping):
                    ref = pick(entry, "field", "column", "measure", "reference", "object", "target", default=entry)
                resolved_id = self._resolve_ref(ref, None, model_id)
                if resolved_id:
                    resolved.append(resolved_id)
                normalized_entries.append({"value": _safe_value(entry), "resolved_id": resolved_id})
            parameter_source = source_id(parameter_raw)
            self._new_node(
                "FIELD_PARAMETER",
                parameter_raw,
                parent_id=model_id,
                model_id=model_id,
                fallback=f"field_parameter:{parameter_source or parameter_index}",
                properties=_raw_properties(
                    parameter_raw,
                    entries=normalized_entries,
                    referenced_object_ids=resolved,
                    ordering=pick(parameter_raw, "ordering", "order", "ordinal"),
                ),
                aliases=(parameter_source,),
            )

        for expression_index, expression_raw in enumerate(
            collection(raw, "shared_expressions", "sharedExpressions", "expressions")
        ):
            if not isinstance(expression_raw, Mapping):
                continue
            expr_source = source_id(expression_raw)
            self._new_node(
                "SHARED_EXPRESSION",
                expression_raw,
                parent_id=model_id,
                model_id=model_id,
                fallback=f"shared_expression:{expr_source or expression_index}",
                properties=_raw_properties(expression_raw, expression=expression(expression_raw)),
                aliases=(expr_source,),
            )

        for udf_index, udf_raw in enumerate(
            collection(raw, "user_defined_functions", "userDefinedFunctions", "udfs", "functions")
        ):
            if not isinstance(udf_raw, Mapping):
                continue
            udf_source = source_id(udf_raw)
            self._new_node(
                "USER_DEFINED_FUNCTION",
                udf_raw,
                parent_id=model_id,
                model_id=model_id,
                fallback=f"udf:{udf_source or udf_index}",
                properties=_raw_properties(
                    udf_raw,
                    parameters=pick(udf_raw, "parameters", "params", default=[]),
                    expression=expression(udf_raw),
                ),
                aliases=(udf_source,),
            )

        for group_index, group_raw in enumerate(
            collection(raw, "calculation_groups", "calculationGroups", "calculation_group")
        ):
            if not isinstance(group_raw, Mapping):
                continue
            group_source = source_id(group_raw)
            group = self._new_node(
                "CALCULATION_GROUP",
                group_raw,
                parent_id=model_id,
                model_id=model_id,
                fallback=f"calculation_group:{group_source or group_index}",
                properties=_raw_properties(
                    group_raw,
                    precedence=pick(group_raw, "precedence"),
                ),
                aliases=(group_source,),
            )
            for item_index, item_raw in enumerate(collection(group_raw, "items", "calculation_items", "calculationItems")):
                if not isinstance(item_raw, Mapping):
                    continue
                item_source = source_id(item_raw)
                self._new_node(
                    "CALCULATION_ITEM",
                    item_raw,
                    parent_id=group.id,
                    model_id=model_id,
                    properties=_raw_properties(
                        item_raw,
                        calculation_group_id=group.id,
                        expression=expression(item_raw),
                        format_expression=pick(
                            item_raw,
                            "format_expression",
                            "formatExpression",
                            "formatStringExpression",
                        ),
                        ordinal=pick(item_raw, "ordinal", "order", "index"),
                    ),
                    fallback=f"calculation_item:{item_source or item_index}",
                    aliases=(item_source,),
                )

    def normalize_report(self, source: Any, *, source_key: Any = 0) -> NormalizationResult:
        raw = ReportReader().read(source)
        report_source = source_id(raw)
        report_name = display_name(raw, default="report")
        report_id, report_effective_source = self.identity.object_id(
            "REPORT", report_source, fallback=f"report:{report_source or source_key}"
        )
        model_ref = pick(raw, "model_id", "modelId", "dataset_id", "datasetId", "dataset", "model", "semanticModelId")
        model_id = self._resolve_model(model_ref)
        report = Node(
            id=report_id,
            type="REPORT",
            name=report_name or report_effective_source,
            description=description(raw),
            model_id=model_id,
            report_id=report_id,
            source_id=report_effective_source,
            properties=_raw_properties(
                raw,
                exclude=("sections", "pages", "visualContainers"),
                model_ref=_safe_value(model_ref),
            ),
            source="report_metadata",
        )
        self._add(report, aliases=(report_source,))
        if report_id not in self._report_ids:
            self._report_ids.append(report_id)

        for page_index, page_raw in enumerate(collection(raw, "pages", "sections")):
            if not isinstance(page_raw, Mapping):
                continue
            page_source = source_id(page_raw)
            page_name = display_name(page_raw, default=f"page_{page_index}")
            page_id, page_effective_source = self.identity.object_id(
                "PAGE", page_source, parent_id=report_id, fallback=f"page:{page_source or page_index}:{page_name}"
            )
            page = Node(
                id=page_id,
                type="PAGE",
                name=page_name or page_effective_source,
                description=description(page_raw),
                model_id=model_id,
                report_id=report_id,
                source_id=page_effective_source,
                properties=_raw_properties(
                    page_raw,
                    exclude=("visualContainers", "visuals"),
                    parent_id=report_id,
                    display_name=pick(page_raw, "display_name", "displayName", "name"),
                    order=pick(page_raw, "order", "ordinal", "pageOrder"),
                ),
                source="report_metadata",
            )
            self._add(page, aliases=(page_source, page_name))
            for visual_index, visual_raw in enumerate(collection(page_raw, "visuals", "visualContainers")):
                if not isinstance(visual_raw, Mapping):
                    continue
                self._normalize_visual(visual_raw, visual_index, page, model_id)
            self._normalize_filters(collection(page_raw, "filters", "page_filters", "pageFilters"), "PAGE_FILTER", page, model_id)

        self._normalize_filters(collection(raw, "filters", "report_filters", "reportFilters"), "REPORT_FILTER", report, model_id)
        self.identity.save()
        return NormalizationResult(list(self.nodes.values()), self.model_ids, self.report_ids)

    def _normalize_visual(
        self, raw: Mapping[str, Any], visual_index: int, page: Node, model_id: str | None
    ) -> Node:
        source_raw = raw
        raw = _prepare_visual(raw)
        visual_source = source_id(raw)
        visual_title = _visual_title(raw)
        raw_name = pick(raw, "name", "displayName", "display_name")
        visual_name = str(raw_name) if raw_name is not None else f"visual_{visual_index}"
        visual_id, effective_source = self.identity.object_id(
            "VISUAL", visual_source, parent_id=page.id, fallback=f"visual:{visual_source or visual_index}:{visual_name}"
        )
        semantic_fields, query_refs, source_entities = _collect_semantic_bindings(raw)
        fields: list[tuple[str | None, Any]] = []
        for kind, ref in _collect_bindings(raw):
            if kind is None and isinstance(ref, str):
                mapped = query_refs.get(_norm(ref))
                if mapped:
                    fields.append(mapped)
                    continue
                if "." in ref:
                    alias, property_name = ref.rsplit(".", 1)
                    entity = source_entities.get(_norm(alias))
                    if entity:
                        fields.append(("COLUMN", {"table": entity, "column": property_name}))
                        continue
            fields.append((kind, ref))
        fields.extend(semantic_fields)
        unique_fields: list[tuple[str | None, Any]] = []
        seen_fields: set[str] = set()
        for kind, ref in fields:
            marker = json.dumps([kind, _safe_value(ref)], sort_keys=True, default=str)
            if marker not in seen_fields:
                seen_fields.add(marker)
                unique_fields.append((kind, ref))
        fields = unique_fields
        field_ids: list[str] = []
        measure_ids: list[str] = []
        column_ids: list[str] = []
        unresolved_bindings: list[dict[str, Any]] = []
        for kind, ref in fields:
            resolved = self._resolve_ref(ref, [kind] if kind else None, model_id)
            if resolved and resolved not in field_ids:
                field_ids.append(resolved)
            if not resolved:
                unresolved_bindings.append(
                    {
                        "kind": kind,
                        "reference": _safe_value(ref),
                        "source": "report_metadata",
                        "status": "candidate",
                    }
                )
            resolved_node = self.nodes.get(resolved) if resolved else None
            if resolved_node and resolved_node.type == "MEASURE" and resolved not in measure_ids:
                measure_ids.append(resolved)
            if resolved_node and resolved_node.type == "COLUMN" and resolved not in column_ids:
                column_ids.append(resolved)
        visual = Node(
            id=visual_id,
            type="VISUAL",
            name=visual_name or effective_source,
            description=description(raw),
            model_id=model_id,
            report_id=page.report_id,
            source_id=effective_source,
            properties=_raw_properties(
                source_raw,
                parent_id=page.id,
                visual_type=_visual_type(raw),
                title=visual_title,
                field_ids=field_ids,
                measure_ids=measure_ids,
                column_ids=column_ids,
                field_refs=[_safe_value(ref) for _, ref in fields],
                unresolved_field_refs=unresolved_bindings,
                binding_evidence=[
                    {"kind": kind, "reference": _safe_value(ref)} for kind, ref in fields
                ],
                config=pick(raw, "config"),
                query=pick(raw, "query"),
                filters=pick(raw, "filters"),
            ),
            source="report_metadata",
        )
        self._add(visual, aliases=(visual_source, visual_name))
        self._normalize_filters(
            collection(raw, "filters", "visual_filters", "visualFilters"),
            "VISUAL_FILTER",
            visual,
            model_id,
            source_entities=source_entities,
        )
        return visual

    def _normalize_filters(
        self,
        filters: Iterable[Any],
        object_type: str,
        parent: Node,
        model_id: str | None,
        *,
        source_entities: Mapping[str, str] | None = None,
    ) -> None:
        source_entities = source_entities or {}
        for filter_index, filter_raw in enumerate(filters):
            if not isinstance(filter_raw, Mapping):
                continue
            target_raw = pick(filter_raw, "target", "field", "column", "measure", "object")
            if target_raw is None:
                target_raw = pick(filter_raw, "expression")
            target_binding = _semantic_binding(target_raw, source_entities)
            target_kind, target_ref = target_binding if target_binding else (None, target_raw)
            target_id = self._resolve_ref(target_ref, [target_kind] if target_kind else None, model_id)
            filter_source = source_id(filter_raw)
            filter_id, effective_source = self.identity.object_id(
                object_type,
                filter_source,
                parent_id=parent.id,
                fallback=f"{object_type.casefold()}:{filter_source or filter_index}",
            )
            node = Node(
                id=filter_id,
                type=object_type,
                name=display_name(filter_raw, default=f"{object_type.casefold()}_{filter_index}"),
                description=description(filter_raw),
                model_id=model_id,
                report_id=parent.report_id,
                source_id=effective_source,
                properties=_raw_properties(
                    filter_raw,
                    parent_id=parent.id,
                    scope=object_type.casefold(),
                    target_id=target_id,
                    target_ref=_safe_value(target_raw),
                    unresolved_target=(
                        {
                            "kind": target_kind,
                            "reference": _safe_value(target_raw),
                            "source": "report_metadata",
                            "status": "candidate",
                        }
                        if target_raw is not None and target_id is None
                        else None
                    ),
                    condition=_safe_value(pick(filter_raw, "condition", "operator", "filter")),
                    value=_safe_value(pick(filter_raw, "value", "values")),
                ),
                source="report_metadata",
            )
            self._add(node, aliases=(filter_source,))


def _collect_bindings(raw: Mapping[str, Any]) -> list[tuple[str | None, Any]]:
    """Collect explicit visual field/measure bindings without interpreting meaning."""

    found: list[tuple[str | None, Any]] = []
    type_keys = {
        "measure": "MEASURE",
        "measures": "MEASURE",
        "measureid": "MEASURE",
        "measureids": "MEASURE",
        "column": "COLUMN",
        "columns": "COLUMN",
        "columnid": "COLUMN",
        "columnids": "COLUMN",
        "field": None,
        "fields": None,
        "bindings": None,
        "fieldbindings": None,
        "projections": None,
        "select": None,
        "selections": None,
        "queryref": None,
        "queryrefs": None,
    }

    def visit(value: Any, hinted: str | None = None) -> None:
        if isinstance(value, Mapping):
            object_ref = pick(value, "object_id", "objectId")
            binding_kind = pick(value, "kind", "field_type", "fieldType")
            if object_ref is not None and (binding_kind is not None or hinted is not None):
                found.append((str(binding_kind or hinted).upper() if (binding_kind or hinted) else None, object_ref))
                return
            for key, item in value.items():
                key_type = type_keys.get(_norm(key), hinted)
                if _norm(key) in {"title", "name", "displayname", "type", "visualtype", "filters"}:
                    continue
                if _norm(key) in type_keys:
                    if isinstance(item, (list, tuple)):
                        for child in item:
                            visit(child, key_type)
                    elif isinstance(item, Mapping):
                        # A field object may carry both the type and its ref.
                        explicit_type = pick(item, "type", "object_type", "objectType")
                        visit(item, str(explicit_type).upper() if explicit_type else key_type)
                    elif item is not None:
                        found.append((key_type, item))
                elif isinstance(item, (Mapping, list, tuple)):
                    visit(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                visit(item, hinted)
        elif value is not None and hinted is not None:
            found.append((hinted, value))

    visit(raw)
    unique: list[tuple[str | None, Any]] = []
    seen: set[str] = set()
    for kind, ref in found:
        marker = json.dumps([kind, _safe_value(ref)], sort_keys=True, default=str)
        if marker not in seen:
            seen.add(marker)
            unique.append((kind, ref))
    return unique


def normalize_model(
    source: Any,
    *,
    identity: StableIdentity | None = None,
    identity_path: str | Path | None = None,
    source_key: Any = 0,
) -> list[Node]:
    return Normalizer(identity=identity, identity_path=identity_path).normalize_model(source, source_key=source_key).nodes


def normalize_report(
    source: Any,
    *,
    identity: StableIdentity | None = None,
    identity_path: str | Path | None = None,
    normalizer: Normalizer | None = None,
    source_key: Any = 0,
) -> list[Node]:
    active = normalizer or Normalizer(identity=identity, identity_path=identity_path)
    return active.normalize_report(source, source_key=source_key).nodes


CanonicalNormalizer = Normalizer
