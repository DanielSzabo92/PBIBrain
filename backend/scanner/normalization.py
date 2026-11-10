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
    excluded = {_norm(key) for key in (*exclude, "ast_location")}
    result = {key: _safe_value(value) for key, value in values.items() if value is not None}
    ast_location = raw.get("ast_location")
    if isinstance(ast_location, Mapping):
        result["ast_location"] = _safe_value(ast_location)
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
        for key in ("visualContainerObjects", "vcObjects", "objects"):
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


def _visual_position(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Read the PBIR position (or the legacy container fields) and the group name."""

    position = pick(raw, "position")
    source = position if isinstance(position, Mapping) else raw
    result = {key: pick(source, key) for key in ("x", "y", "z", "width", "height")}
    result["tab_order"] = pick(source, "tabOrder")
    result["parentGroupName"] = pick(raw, "parentGroupName")
    group = pick(raw, "visualGroup")
    if isinstance(group, Mapping):
        result["is_group"] = True
        result["group_mode"] = pick(group, "groupMode")
    return {key: value for key, value in result.items() if value is not None}


def _report_filters(raw: Mapping[str, Any], *keys: str) -> list[Any]:
    """Read both legacy JSON-string filters and PBIR filterConfig."""
    value = _decode_json_field(pick(raw, *keys))
    if isinstance(value, list):
        return value
    config = pick(raw, "filterConfig")
    return collection(config, "filters") if isinstance(config, Mapping) else []


def _visual_calculations(raw: Mapping[str, Any]) -> list[dict[str, Any]]:
    calculations: dict[str, dict[str, Any]] = {}

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            field = pick(value, "field")
            calc = pick(field, "NativeVisualCalculation") if isinstance(field, Mapping) else None
            calc = calc or pick(value, "NativeVisualCalculation")
            if isinstance(calc, Mapping) and pick(calc, "Expression") is not None:
                name = str(pick(calc, "Name") or pick(value, "queryRef") or "Calculation")
                # The same field can occur in projections and sorting metadata.
                record = calculations.setdefault(name, dict(calc))
                if pick(value, "displayName"):
                    record["display_name"] = pick(value, "displayName")
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(raw)
    return list(calculations.values())


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
    level = pick(value, "hierarchyLevel")
    if isinstance(level, Mapping):
        hierarchy_expression = pick(level, "expression")
        hierarchy = pick(hierarchy_expression, "hierarchy") if isinstance(hierarchy_expression, Mapping) else None
        if isinstance(hierarchy, Mapping):
            inner = pick(hierarchy, "expression")
            source_ref = pick(inner, "sourceRef") if isinstance(inner, Mapping) else None
            alias = pick(source_ref, "source", "name") if isinstance(source_ref, Mapping) else None
            table = entities.get(_norm(alias)) if alias is not None else None
            table = table or (pick(source_ref, "entity", "table") if isinstance(source_ref, Mapping) else None)
            name = pick(hierarchy, "hierarchy", "name")
            if name is not None:
                return "HIERARCHY", {"table": table, "hierarchy": name, "level": pick(level, "level")}
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


_SLICER_VISUAL_TYPES = frozenset({"slicer", "advancedslicervisual", "listslicer", "textslicer", "buttonslicer", "chicletslicer", "timeline"})
_ROLE_KINDS = {
    "category": "category", "axis": "category", "shared": "category",
    "y": "value", "y2": "value", "values": "value", "value": "value", "columnvalues": "value", "data": "value",
    "indicator": "value", "fields": "value", "x": "value",
    "series": "legend", "legend": "legend", "columnsseries": "legend",
    "tooltips": "tooltip", "tooltip": "tooltip",
    "rows": "rows", "columns": "columns",
    "smallmultiple": "small_multiples", "smallmultiples": "small_multiples",
    "details": "details", "size": "size", "playaxis": "play_axis",
    "goal": "target", "targetvalue": "target", "target": "target", "trendline": "trend",
    "minvalue": "range", "maxvalue": "range", "min": "range", "max": "range",
    "location": "location", "latitude": "location", "longitude": "location",
}
# The QueryAggregateFunction numbers of the Power BI semantic query.
_AGGREGATIONS = {0: "Sum", 1: "Avg", 2: "Count", 3: "Min", 4: "Max", 5: "CountNonNull", 6: "Median",
                 7: "StandardDeviation", 8: "Variance"}


def _role_kind(role: Any, visual_type: Any) -> str:
    """Map a projection role name (Y, Category, Values...) to a stable usage role."""

    key = _norm(role)
    if key in {"values", "field", "fields"} and _norm(visual_type) in _SLICER_VISUAL_TYPES:
        return "slicer_field"
    if key in _ROLE_KINDS:
        return _ROLE_KINDS[key]
    return re.sub(r"[^a-z0-9]+", "_", str(role).casefold()).strip("_") or "field"


def _aggregation_name(value: Any) -> str | None:
    """Return the aggregation function of an ``Aggregation`` field, if any."""

    if not isinstance(value, Mapping):
        return None
    aggregation = pick(value, "aggregation")
    if not isinstance(aggregation, Mapping):
        field_value = pick(value, "field", "expression")
        return _aggregation_name(field_value) if isinstance(field_value, Mapping) else None
    function = pick(aggregation, "function")
    if isinstance(function, bool):
        return None
    if isinstance(function, int):
        return _AGGREGATIONS.get(function, str(function))
    return str(function) if function is not None else None


def _sort_direction(value: Any) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        # The legacy prototypeQuery uses 1 = ascending and 2 = descending.
        return {1: "Ascending", 2: "Descending"}.get(value)
    return str(value)


def _object_properties(raw: Mapping[str, Any], name: str) -> list[Mapping[str, Any]]:
    """Return the ``properties`` of one formatting object of the visual container."""

    result: list[Mapping[str, Any]] = []
    for key in ("visualContainerObjects", "vcObjects"):
        objects = pick(raw, key)
        entries = pick(objects, name) if isinstance(objects, Mapping) else None
        for entry in entries if isinstance(entries, list) else [entries]:
            properties = pick(entry, "properties") if isinstance(entry, Mapping) else None
            if isinstance(properties, Mapping):
                result.append(properties)
    return result


def _visual_links(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Read the explicit tooltip page, drillthrough page, sync group and other report links of a visual."""

    result: dict[str, Any] = {}
    for properties in _object_properties(raw, "visualTooltip"):
        kind = _literal_text(pick(properties, "type"))
        section = _literal_text(pick(properties, "section"))
        if section and (kind is None or _norm(kind) == "reportpage"):
            result["tooltip_page_ref"] = section
    for properties in _object_properties(raw, "visualLink"):
        kind = _literal_text(pick(properties, "type"))
        if _norm(kind) == "drillthrough":
            section = _literal_text(pick(properties, "drillthroughSection"))
            if section:
                result["drillthrough_page_ref"] = section
        elif _norm(kind) == "pagenavigation":
            section = _literal_text(pick(properties, "navigationSection"))
            if section:
                result["navigation_page_ref"] = section
    sync = pick(raw, "syncGroup")
    if isinstance(sync, Mapping) and _present(pick(sync, "groupName")):
        result["sync_group"] = {
            "group_name": str(pick(sync, "groupName")),
            "field_changes": pick(sync, "fieldChanges"),
            "filter_changes": pick(sync, "filterChanges"),
        }
    return result


def _usage_bindings(
    raw: Mapping[str, Any], query_refs: Mapping[str, tuple[str, Any]], entities: Mapping[str, str]
) -> list[dict[str, Any]]:
    """Collect each bound field with its usage role: projection well, sort or conditional formatting.

    The result keeps the source spelling of the role (``Y``, ``Category``) and a
    stable ``role`` (``value``, ``category``) for the graph.
    """

    visual_type = _visual_type(raw)
    found: list[dict[str, Any]] = []
    query = pick(raw, "query")
    query = query if isinstance(query, Mapping) else {}
    query_state = pick(query, "queryState")
    if isinstance(query_state, Mapping):
        for role, state in query_state.items():
            if not isinstance(state, Mapping):
                continue
            for projection in collection(state, "projections"):
                binding = _semantic_binding(projection, entities) if isinstance(projection, Mapping) else None
                if not binding:
                    continue
                found.append({
                    "binding": binding, "usage": "projection", "projection": str(role),
                    "role": _role_kind(role, visual_type), "aggregation": _aggregation_name(projection),
                    "active": pick(projection, "active"), "hidden": pick(projection, "hidden"),
                    "display_name": pick(projection, "displayName"),
                })
            for parameter in collection(state, "fieldParameters"):
                expr = pick(parameter, "parameterExpr") if isinstance(parameter, Mapping) else None
                binding = _semantic_binding(expr, entities) if isinstance(expr, Mapping) else None
                if binding:
                    found.append({"binding": binding, "usage": "projection", "projection": str(role),
                                  "role": _role_kind(role, visual_type), "field_parameter": True})
    legacy = pick(raw, "projections")
    if isinstance(legacy, Mapping):
        # Legacy report.json: projections name the queryRef of a prototypeQuery select.
        aggregations: dict[str, str | None] = {}
        prototype = pick(raw, "prototypeQuery")
        for entry in collection(prototype, "select") if isinstance(prototype, Mapping) else []:
            if isinstance(entry, Mapping) and pick(entry, "name") is not None:
                aggregations[_norm(pick(entry, "name"))] = _aggregation_name({"field": entry})
        for role, items in legacy.items():
            for item in items if isinstance(items, list) else [items]:
                reference = pick(item, "queryRef") if isinstance(item, Mapping) else item
                binding = query_refs.get(_norm(reference)) if reference is not None else None
                if binding:
                    found.append({"binding": binding, "usage": "projection", "projection": str(role),
                                  "role": _role_kind(role, visual_type),
                                  "aggregation": aggregations.get(_norm(reference)),
                                  "active": pick(item, "active") if isinstance(item, Mapping) else None})
    sort_definition = pick(query, "sortDefinition")
    sorts = collection(sort_definition, "sort") if isinstance(sort_definition, Mapping) else []
    prototype = pick(raw, "prototypeQuery")
    sorts = [*sorts, *(collection(prototype, "orderBy") if isinstance(prototype, Mapping) else [])]
    for sort in sorts:
        if not isinstance(sort, Mapping):
            continue
        binding = _semantic_binding(pick(sort, "field", "expression"), entities)
        if binding:
            found.append({"binding": binding, "usage": "sort", "role": "sort",
                          "sort_direction": _sort_direction(pick(sort, "direction"))})

    def formatting(value: Any) -> None:
        if isinstance(value, Mapping):
            binding = _semantic_binding(value, entities)
            if binding:
                found.append({"binding": binding, "usage": "conditional_formatting", "role": "conditional_formatting"})
                return
            for child in value.values():
                formatting(child)
        elif isinstance(value, list):
            for child in value:
                formatting(child)

    for key in ("objects", "visualContainerObjects", "vcObjects"):
        formatting(pick(raw, key))
    for item in found:
        for key in [key for key, value in item.items() if value is None]:
            del item[key]
    return found


def _page_binding(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Read the drillthrough or tooltip binding of a page and its visibility."""

    binding = pick(raw, "pageBinding")
    binding = binding if isinstance(binding, Mapping) else {}
    page_type = pick(raw, "type") if not isinstance(pick(raw, "type"), Mapping) else None
    page_type = page_type or pick(binding, "type")
    if _norm(page_type) not in {"drillthrough", "tooltip"}:
        page_type = None
    visibility = pick(raw, "visibility")
    fields: list[tuple[str, Any]] = []
    for parameter in collection(binding, "parameters"):
        expr = pick(parameter, "fieldExpr") if isinstance(parameter, Mapping) else None
        found = _semantic_binding(expr, {}) if isinstance(expr, Mapping) else None
        if found:
            fields.append(found)
    return {
        "page_type": "Drillthrough" if _norm(page_type) == "drillthrough" else "Tooltip" if page_type else None,
        "hidden": True if _norm(visibility) == "hiddeninviewmode" or visibility == 1 else None,
        "binding_name": pick(binding, "name"),
        "binding_scope": pick(binding, "referenceScope"),
        "binding_fields": fields,
    }


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
        self._current_report: str | None = None
        self._workspaces: dict[str, str] = {}

    @property
    def model_ids(self) -> list[str]:
        return list(self._model_ids)

    @property
    def report_ids(self) -> list[str]:
        return list(self._report_ids)

    def _cloud_properties(self, raw: Mapping[str, Any]) -> dict[str, Any]:
        """Properties of a project root read from the cloud (issue #9), with its WORKSPACE node."""

        values: dict[str, Any] = {
            "check_status": pick(raw, "check_status"),
            "not_checked_reason": pick(raw, "not_checked_reason"),
            "connection_workspace": pick(raw, "connection_workspace"),
        }
        cloud = raw.get("cloud_source")
        if not isinstance(cloud, Mapping) or not cloud.get("workspace_id"):
            return values
        workspace_key = str(cloud["workspace_id"]).casefold()
        workspace_id = self._workspaces.get(workspace_key)
        if workspace_id is None:
            workspace_id, workspace_source = self.identity.object_id(
                "WORKSPACE", str(cloud["workspace_id"]), fallback=f"workspace:{cloud['workspace_id']}"
            )
            self._workspaces[workspace_key] = workspace_id
            self._add(Node(
                id=workspace_id,
                type="WORKSPACE",
                name=str(cloud.get("workspace_name") or cloud["workspace_id"]),
                source_id=workspace_source,
                properties={"origin": "cloud", "workspace_id": str(cloud["workspace_id"]),
                            "workspace_name": cloud.get("workspace_name")},
                source="model_metadata",
            ))
        values.update(
            origin="cloud",
            workspace_id=str(cloud["workspace_id"]),
            workspace_name=cloud.get("workspace_name"),
            workspace_node_id=workspace_id,
            cloud_item_id=cloud.get("item_id"),
            access_type=cloud.get("access_type"),
        )
        return values

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
            if node.type in {"COLUMN", "HIERARCHY"} and node.properties.get("table_id"):
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
            hierarchy_ref = pick(ref, "hierarchy")
            if hierarchy_ref is not None:
                table_id = self._resolve_ref(table_ref, ["TABLE"], model_id) if table_ref is not None else None
                if table_id:
                    return self._lookup.get((scope, "HIERARCHY", f"{_norm(table_id)}|{_norm(hierarchy_ref)}"))
                return self._lookup.get((scope, "HIERARCHY", _norm(hierarchy_ref)))
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
            if object_type == "MEASURE" and self._current_report:
                # A report measure (reportExtensions.json) is visible only in its own report.
                # Look it up before the global fallback, which can find a measure of another model.
                found = self._lookup.get(("report:" + self._current_report, "REPORT_MEASURE", _norm(text)))
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
                # Roles are SECURITY_ROLE nodes. Their members stay out of the graph.
                exclude=("tables", "entities", "relationships", "measures", "roles", "cloud_source"),
                **{"workspace_id": pick(raw, "workspace_id", "workspaceId"), **self._cloud_properties(raw)},
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
            self._normalize_table_parts(table_raw, table, model_id)

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

    def _normalize_table_parts(self, table_raw: Mapping[str, Any], table: Node, model_id: str) -> None:
        """Read the hierarchies, partitions, and calculation group of one TOM table."""

        table_id = table.id
        for hierarchy_index, hierarchy_raw in enumerate(collection(table_raw, "hierarchies")):
            if not isinstance(hierarchy_raw, Mapping):
                continue
            hierarchy_name = display_name(hierarchy_raw, default=f"hierarchy_{hierarchy_index}")
            hierarchy = self._new_node(
                "HIERARCHY",
                hierarchy_raw,
                parent_id=table_id,
                model_id=model_id,
                fallback=f"hierarchy:{hierarchy_name}",
                properties=_raw_properties(
                    hierarchy_raw,
                    exclude=("levels",),
                    table_id=table_id,
                    hidden=_bool(pick(hierarchy_raw, "hidden", "isHidden")),
                    display_folder=pick(hierarchy_raw, "displayFolder", "display_folder"),
                ),
                aliases=(hierarchy_name,),
            )
            for level_index, level_raw in enumerate(collection(hierarchy_raw, "levels")):
                if not isinstance(level_raw, Mapping):
                    continue
                level_name = display_name(level_raw, default=f"level_{level_index}")
                column_ref = pick(level_raw, "column", "columnName")
                column_id = self._resolve_ref({"table": table_id, "column": column_ref}, ["COLUMN"], model_id) if column_ref is not None else None
                self._new_node(
                    "LEVEL",
                    level_raw,
                    parent_id=hierarchy.id,
                    model_id=model_id,
                    fallback=f"level:{level_name}",
                    properties=_raw_properties(
                        level_raw,
                        hierarchy_id=hierarchy.id,
                        level_table_id=table_id,
                        column_id=column_id,
                        column_ref=_safe_value(column_ref),
                        ordinal=pick(level_raw, "ordinal"),
                    ),
                    aliases=(level_name,),
                )
        for partition_index, partition_raw in enumerate(collection(table_raw, "partitions")):
            if not isinstance(partition_raw, Mapping):
                continue
            partition_name = display_name(partition_raw, default=f"partition_{partition_index}")
            source_raw = pick(partition_raw, "source")
            source_raw = source_raw if isinstance(source_raw, Mapping) else {}
            source_type = str(pick(source_raw, "type") or pick(partition_raw, "sourceType") or "").strip() or None
            text = expression(source_raw) if source_raw else expression(partition_raw)
            self._new_node(
                "PARTITION",
                partition_raw,
                parent_id=table_id,
                model_id=model_id,
                fallback=f"partition:{partition_name}",
                properties=_raw_properties(
                    partition_raw,
                    table_id=table_id,
                    source_type=source_type,
                    mode=pick(partition_raw, "mode"),
                    expression=text,
                    # Only a calculated partition holds DAX. M text is not parsed.
                    expression_language="DAX" if (source_type or "").casefold() == "calculated" else ("M" if text else None),
                ),
                aliases=(partition_name,),
            )
        group_raw = pick(table_raw, "calculationGroup", "calculation_group")
        if isinstance(group_raw, Mapping):
            group = self._new_node(
                "CALCULATION_GROUP",
                {"name": table.name, **{key: value for key, value in group_raw.items() if key != "calculationItems"}},
                parent_id=table_id,
                model_id=model_id,
                fallback=f"calculation_group:{table.name}",
                properties=_raw_properties(group_raw, exclude=("calculationItems",), table_id=table_id, precedence=pick(group_raw, "precedence")),
                aliases=(table.name,),
            )
            for item_index, item_raw in enumerate(collection(group_raw, "calculationItems", "calculation_items", "items")):
                if not isinstance(item_raw, Mapping):
                    continue
                item_name = display_name(item_raw, default=f"calculation_item_{item_index}")
                format_raw = pick(item_raw, "formatStringDefinition", "format_string_definition")
                self._new_node(
                    "CALCULATION_ITEM",
                    item_raw,
                    parent_id=group.id,
                    model_id=model_id,
                    fallback=f"calculation_item:{item_name}",
                    properties=_raw_properties(
                        item_raw,
                        calculation_group_id=group.id,
                        expression=expression(item_raw),
                        format_expression=expression(format_raw) if isinstance(format_raw, Mapping) else format_raw,
                        ordinal=pick(item_raw, "ordinal"),
                    ),
                    aliases=(item_name,),
                )

    def _normalize_roles(self, raw: Mapping[str, Any], model_id: str) -> None:
        """Read RLS roles, their table filters, and their OLS permissions."""

        for role_index, role_raw in enumerate(collection(raw, "roles")):
            if not isinstance(role_raw, Mapping):
                continue
            role_name = display_name(role_raw, default=f"role_{role_index}")
            # Role members can be user names or e-mail addresses. Keep them out of the graph.
            role = self._new_node(
                "SECURITY_ROLE",
                role_raw,
                parent_id=model_id,
                model_id=model_id,
                fallback=f"security_role:{role_name}",
                properties=_raw_properties(
                    role_raw,
                    exclude=("tablePermissions", "members"),
                    model_permission=pick(role_raw, "modelPermission"),
                    member_count=len(collection(role_raw, "members")),
                ),
                aliases=(role_name,),
            )
            for permission_raw in collection(role_raw, "tablePermissions", "table_permissions"):
                if not isinstance(permission_raw, Mapping):
                    continue
                table_name = display_name(permission_raw)
                table_id = self._resolve_ref(table_name, ["TABLE"], model_id)
                filter_text = pick(permission_raw, "filterExpression", "filter_expression")
                if _present(filter_text):
                    self._new_node(
                        "ROLE_FILTER",
                        {"name": table_name},
                        parent_id=role.id,
                        model_id=model_id,
                        fallback=f"role_filter:{table_name}",
                        properties=_raw_properties(
                            permission_raw,
                            exclude=("columnPermissions",),
                            role_id=role.id,
                            table_id=table_id,
                            table_ref=table_name,
                            expression=str(filter_text),
                        ),
                    )
                table_permission = pick(permission_raw, "metadataPermission")
                if _present(table_permission):
                    self._new_node(
                        "OLS_PERMISSION",
                        {"name": table_name},
                        parent_id=role.id,
                        model_id=model_id,
                        fallback=f"ols_permission:{table_name}",
                        properties=_raw_properties(
                            {"table": table_name, "metadataPermission": table_permission},
                            role_id=role.id,
                            target_id=table_id,
                            target_ref=table_name,
                            permission=table_permission,
                        ),
                    )
                for column_raw in collection(permission_raw, "columnPermissions", "column_permissions"):
                    if not isinstance(column_raw, Mapping):
                        continue
                    column_name = display_name(column_raw)
                    column_id = self._resolve_ref({"table": table_id, "column": column_name}, ["COLUMN"], model_id) if table_id else None
                    label = f"{table_name}[{column_name}]"
                    self._new_node(
                        "OLS_PERMISSION",
                        {"name": label},
                        parent_id=role.id,
                        model_id=model_id,
                        fallback=f"ols_permission:{label}",
                        properties=_raw_properties(
                            {"table": table_name, **column_raw},
                            role_id=role.id,
                            target_id=column_id,
                            target_ref={"table": table_name, "column": column_name},
                            permission=pick(column_raw, "metadataPermission"),
                        ),
                    )

    def _normalize_model_extras(self, raw: Mapping[str, Any], model_id: str) -> None:
        self._normalize_roles(raw, model_id)
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
                exclude=("sections", "pages", "visualContainers", "report_extensions", "reportExtensions", "bookmarks",
                         "cloud_source"),
                model_ref=_safe_value(model_ref),
                **self._cloud_properties(raw),
            ),
            source="report_metadata",
        )
        self._add(report, aliases=(report_source,))
        if report_id not in self._report_ids:
            self._report_ids.append(report_id)
        self._current_report = report_id
        # Visuals and filters can use a report measure. Thus read the measures first.
        self._normalize_report_measures(raw, report, model_id)

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
                    width=pick(page_raw, "width"),
                    height=pick(page_raw, "height"),
                    display_option=pick(page_raw, "displayOption", "display_option"),
                ),
                source="report_metadata",
            )
            self._add(page, aliases=(page_source, page_name))
            visuals_by_name: dict[str, str] = {}
            for visual_index, visual_raw in enumerate(collection(page_raw, "visuals", "visualContainers")):
                if not isinstance(visual_raw, Mapping):
                    continue
                visual = self._normalize_visual(visual_raw, visual_index, page, model_id)
                for alias in (visual.properties.get("visual_name"), visual.source_id):
                    if _present(alias):
                        visuals_by_name.setdefault(str(alias), visual.id)
            self._normalize_page_usage(page_raw, page, model_id, visuals_by_name)
            self._normalize_filters(_report_filters(page_raw, "filters", "page_filters", "pageFilters"), "PAGE_FILTER", page, model_id)

        self._normalize_filters(_report_filters(raw, "filters", "report_filters", "reportFilters"), "REPORT_FILTER", report, model_id)
        self._normalize_bookmarks(raw, report, model_id)
        self._current_report = None
        self.identity.save()
        return NormalizationResult(list(self.nodes.values()), self.model_ids, self.report_ids)

    def _normalize_page_usage(
        self, page_raw: Mapping[str, Any], page: Node, model_id: str | None, visuals_by_name: Mapping[str, str]
    ) -> None:
        """Record the drillthrough/tooltip binding, visibility and visual interactions of one page."""

        binding = _page_binding(page_raw)
        field_ids: list[str] = []
        for kind, ref in binding.pop("binding_fields"):
            resolved = self._resolve_ref(ref, [kind], model_id)
            if resolved and resolved not in field_ids:
                field_ids.append(resolved)
        interactions: list[dict[str, Any]] = []
        for item in collection(page_raw, "visualInteractions"):
            if not isinstance(item, Mapping):
                continue
            source_visual = visuals_by_name.get(str(pick(item, "source")))
            target_visual = visuals_by_name.get(str(pick(item, "target")))
            if source_visual and target_visual and source_visual != target_visual:
                raw_type = pick(item, "type")
                interactions.append({
                    "source_id": source_visual,
                    "target_id": target_visual,
                    "type": str(raw_type) if raw_type is not None else "Default",
                    "interaction": {"datafilter": "filter", "highlightfilter": "highlight", "nofilter": "none"}.get(_norm(raw_type), "default"),
                })
        values = {**binding, "binding_field_ids": field_ids or None, "visual_interactions": interactions or None}
        page.properties.update({key: _safe_value(value) for key, value in values.items() if value is not None})

    def _normalize_report_measures(self, raw: Mapping[str, Any], report: Node, model_id: str | None) -> None:
        """Read the report-level measures of reportExtensions.json."""

        for entity_raw in collection(raw, "report_extensions", "reportExtensions"):
            if not isinstance(entity_raw, Mapping):
                continue
            entity = display_name(entity_raw)
            table_id = self._resolve_ref(entity, ["TABLE"], model_id) if _present(entity) else None
            for measure_raw in collection(entity_raw, "measures"):
                if not isinstance(measure_raw, Mapping):
                    continue
                name = display_name(measure_raw)
                measure_id, effective_source = self.identity.object_id(
                    "REPORT_MEASURE", source_id(measure_raw), parent_id=report.id, fallback=f"report_measure:{entity}|{name}"
                )
                node = Node(
                    id=measure_id,
                    type="REPORT_MEASURE",
                    name=name or effective_source,
                    description=description(measure_raw),
                    model_id=model_id,
                    report_id=report.id,
                    source_id=effective_source,
                    properties=_raw_properties(
                        measure_raw,
                        parent_id=report.id,
                        entity=entity,
                        entity_table_id=table_id,
                        expression=expression(measure_raw),
                        datatype=pick(measure_raw, "dataType"),
                        format_string=pick(measure_raw, "formatString"),
                        hidden=_bool(pick(measure_raw, "hidden", "isHidden")),
                    ),
                    source="report_metadata",
                )
                self._add(node)
                self._lookup.setdefault(("report:" + report.id, "REPORT_MEASURE", _norm(name)), node.id)

    def _normalize_bookmarks(self, raw: Mapping[str, Any], report: Node, model_id: str | None) -> None:
        """Read PBIR bookmarks: the page, the target visuals, and the filter fields. Read only."""

        pages = {_norm(node.source_id): node.id for node in self.nodes.values() if node.type == "PAGE" and node.report_id == report.id}
        visuals: dict[tuple[str, str], str] = {}
        for node in self.nodes.values():
            if node.type == "VISUAL" and node.report_id == report.id:
                visuals[(str(node.properties.get("parent_id")), _norm(node.source_id))] = node.id
        for bookmark_index, bookmark_raw in enumerate(collection(raw, "bookmarks")):
            if not isinstance(bookmark_raw, Mapping):
                continue
            state = pick(bookmark_raw, "explorationState")
            state = state if isinstance(state, Mapping) else {}
            options = pick(bookmark_raw, "options")
            options = options if isinstance(options, Mapping) else {}
            active = pick(state, "activeSection")
            page_id = pages.get(_norm(active)) if active is not None else None
            visual_names: list[tuple[str | None, str]] = [(page_id, str(name)) for name in collection(options, "targetVisualNames")]
            sections = pick(state, "sections")
            for section_name, section in (sections.items() if isinstance(sections, Mapping) else ()):
                section_page = pages.get(_norm(section_name))
                if isinstance(section, Mapping):
                    for key in ("visualContainers", "visualContainerGroups"):
                        containers = pick(section, key)
                        visual_names.extend((section_page, str(name)) for name in (containers or {}) if isinstance(containers, Mapping))
            visual_ids: list[str] = []
            unresolved: list[dict[str, Any]] = []
            for page_ref, name in visual_names:
                found = visuals.get((str(page_ref), _norm(name))) if page_ref else None
                if found is None:
                    candidates = [value for (_, visual_name), value in visuals.items() if visual_name == _norm(name)]
                    found = candidates[0] if len(candidates) == 1 else None
                if found and found not in visual_ids:
                    visual_ids.append(found)
                elif not found:
                    unresolved.append({"kind": "VISUAL", "reference": name, "source": "report_metadata", "status": "candidate"})
            bindings, _, _ = _collect_semantic_bindings(state)
            field_ids: list[str] = []
            for kind, ref in bindings:
                resolved = self._resolve_ref(ref, [kind] if kind else None, model_id)
                if resolved and resolved not in field_ids:
                    field_ids.append(resolved)
                elif not resolved:
                    unresolved.append({"kind": kind, "reference": _safe_value(ref), "source": "report_metadata", "status": "candidate"})
            if active is not None and page_id is None:
                unresolved.append({"kind": "PAGE", "reference": active, "source": "report_metadata", "status": "candidate"})
            name = str(pick(bookmark_raw, "name") or f"bookmark_{bookmark_index}")
            bookmark_id, effective_source = self.identity.object_id("BOOKMARK", name, parent_id=report.id)
            self._add(Node(
                id=bookmark_id,
                type="BOOKMARK",
                name=str(pick(bookmark_raw, "displayName") or name),
                model_id=model_id,
                report_id=report.id,
                source_id=effective_source,
                source="report_metadata",
                properties=_raw_properties(
                    bookmark_raw,
                    parent_id=report.id,
                    display_name=pick(bookmark_raw, "displayName"),
                    order=pick(bookmark_raw, "order"),
                    group_name=pick(bookmark_raw, "group_name"),
                    page_id=page_id,
                    visual_ids=visual_ids,
                    field_ids=field_ids,
                    unresolved_field_refs=unresolved,
                    # The app reads bookmarks for impact only. It does not copy them.
                    read_only=True,
                ),
            ))

    def _normalize_visual(
        self, raw: Mapping[str, Any], visual_index: int, page: Node, model_id: str | None
    ) -> Node:
        source_raw = raw
        raw = _prepare_visual(raw)
        visual_source = source_id(raw)
        visual_title = _visual_title(raw)
        raw_name = pick(raw, "displayName", "display_name", "name")
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
        field_roles: list[dict[str, Any]] = []
        role_markers: set[str] = set()
        for entry in _usage_bindings(raw, query_refs, source_entities):
            kind, ref = entry.pop("binding")
            resolved = self._resolve_ref(ref, [kind] if kind else None, model_id)
            if not resolved:
                continue
            record = {"object_id": resolved, **entry}
            marker = json.dumps(record, sort_keys=True, default=str)
            if marker in role_markers:
                continue
            role_markers.add(marker)
            field_roles.append(record)
            if resolved not in field_ids:
                field_ids.append(resolved)
                resolved_type = self.nodes[resolved].type
                if resolved_type == "MEASURE":
                    measure_ids.append(resolved)
                elif resolved_type == "COLUMN":
                    column_ids.append(resolved)
        hierarchy_ids = [item for item in field_ids if self.nodes[item].type == "HIERARCHY"]
        links = _visual_links(raw)
        visual = Node(
            id=visual_id,
            type="VISUAL",
            name=visual_title or visual_name or effective_source,
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
                hierarchy_ids=hierarchy_ids,
                **_visual_position(source_raw),
                field_refs=[_safe_value(ref) for _, ref in fields],
                field_roles=field_roles,
                visual_name=_safe_value(raw_name),
                hidden_visual=True if pick(source_raw, "isHidden") is True else None,
                **links,
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
            _report_filters(raw, "filters", "visual_filters", "visualFilters"),
            "VISUAL_FILTER",
            visual,
            model_id,
            source_entities=source_entities,
        )
        for calculation in _visual_calculations(raw):
            calc_name = str(pick(calculation, "Name") or "Calculation")
            calc_id, calc_source = self.identity.object_id("VISUAL_CALCULATION", calc_name, parent_id=visual.id)
            self._add(Node(
                id=calc_id, type="VISUAL_CALCULATION",
                name=str(pick(calculation, "display_name") or calc_name),
                model_id=model_id, report_id=page.report_id, source_id=calc_source,
                source="report_metadata",
                properties=_raw_properties(calculation, parent_id=visual.id, expression=str(pick(calculation, "Expression")), language=pick(calculation, "Language")),
            ))
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
            entities = {**source_entities, **_source_entities(pick(filter_raw, "filter") or {})}
            target_binding = _semantic_binding(target_raw, entities)
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
                name=str(pick(filter_raw, "displayName", "display_name") or
                         (self.nodes[target_id].name if target_id else display_name(filter_raw, default=f"{object_type.casefold()}_{filter_index}"))),
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
            field = pick(value, "field")
            if pick(value, "NativeVisualCalculation") is not None or (
                isinstance(field, Mapping) and pick(field, "NativeVisualCalculation") is not None
            ):
                # Explicit visual calculations belong to the visual, not the model.
                return
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
