"""Compare objects of one local source (technical design sections 4.1 and 4.2).

The model part comes from the trusted TOM bridge, for TMDL and for TMSL. Thus
both formats give the same property values (TOM fills the default values). The
report part comes from the PBIR files, or from ``report.json`` of a PBIR-Legacy
report.

Each object has the source row key of ``backend.devcenter.sources.objects``
(``<type>:<qualified name>``). The session marks, ``row_confirm``, and the
row hashes use this key. Bookmarks are read only for impact, so they are not
compare objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import threading
from typing import Any, Iterator, Mapping

from backend.adapters.tabular_metadata.bridge import MetadataUnavailable, TabularMetadataAdapter
from backend.devcenter.errors import not_allowed
from backend.devcenter.sources.fingerprint import source_fingerprint
from backend.devcenter.sources.kinds import MODEL_TMDL, MODEL_TMSL, REPORT_PBIR, REPORT_PBIR_LEGACY, LocalSource

MODEL = "model"
REPORT = "report"

DAX = "dax"
M = "m"
JSON = "json"


@dataclass
class CompareObject:
    """One object of one source, with the values that the compare uses."""

    kind: str
    subtype: str
    domain: str
    source_key: str
    name: str
    table: str | None = None
    lineage_tag: str | None = None
    display_folder: str | None = None
    props: dict[str, Any] = field(default_factory=dict)
    strict_props: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)
    code: str = ""
    language: str = JSON

    @property
    def qualified_name(self) -> str:
        return f"{self.table}/{self.name}" if self.table is not None else self.name


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        return "\n".join(str(item) for item in value)
    return str(value)


def _json_code(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _annotations(item: Mapping[str, Any]) -> dict[str, Any]:
    return {str(entry.get("name")): entry.get("value") for entry in item.get("annotations") or [] if isinstance(entry, Mapping)}


def _strict(item: Mapping[str, Any]) -> dict[str, Any]:
    metadata = {key: item[key] for key in ("sourceLineageTag", "changedProperties", "extendedProperties") if key in item}
    return {"annotations": _annotations(item), "lineage_tag": item.get("lineageTag"), "metadata": metadata}


def _named(items: Any) -> Iterator[Mapping[str, Any]]:
    for item in items or []:
        if isinstance(item, Mapping) and isinstance(item.get("name"), str):
            yield item


def _format_expression(item: Mapping[str, Any]) -> str | None:
    definition = item.get("formatStringDefinition")
    return _text(definition.get("expression")) if isinstance(definition, Mapping) else None


# Model ----------------------------------------------------------------------


def _measure(table: str, item: Mapping[str, Any]) -> CompareObject:
    return CompareObject(
        kind="measure", subtype="measure", domain=MODEL, source_key=f"measure:{table}/{item['name']}", name=item["name"], table=table,
        lineage_tag=item.get("lineageTag"), display_folder=item.get("displayFolder"),
        props={"expression": _text(item.get("expression")), "format_string": item.get("formatString"),
               "format_string_expression": _format_expression(item), "display_folder": item.get("displayFolder"),
               "description": _text(item.get("description")), "hidden": bool(item.get("isHidden", False)),
               "data_category": item.get("dataCategory")},
        strict_props=_strict(item), code=_text(item.get("expression")) or "", language=DAX)


def _column(table: str, item: Mapping[str, Any]) -> CompareObject | None:
    column_type = item.get("type") or "data"
    if column_type == "rowNumber":
        return None
    calculated = column_type == "calculated"
    props = {"data_type": item.get("dataType"), "source_column": item.get("sourceColumn"), "format_string": item.get("formatString"),
             "display_folder": item.get("displayFolder"), "description": _text(item.get("description")),
             "hidden": bool(item.get("isHidden", False)), "summarize_by": item.get("summarizeBy") or "default",
             "sort_by_column": item.get("sortByColumn"), "data_category": item.get("dataCategory"), "key": bool(item.get("isKey", False))}
    if calculated:
        props["expression"] = _text(item.get("expression"))
    return CompareObject(
        kind="column", subtype="calculated_column" if calculated else "data_column", domain=MODEL,
        source_key=f"column:{table}/{item['name']}", name=item["name"], table=table, lineage_tag=item.get("lineageTag"),
        display_folder=item.get("displayFolder"), props=props, strict_props=_strict(item),
        extra={"signature": ("expression", props.get("expression")) if calculated else ("source", item.get("dataType"), item.get("sourceColumn"))},
        code=_text(item.get("expression")) if calculated else _json_code(item), language=DAX if calculated else JSON)


def _hierarchy(table: str, item: Mapping[str, Any]) -> CompareObject:
    levels = sorted(_named(item.get("levels")), key=lambda level: level.get("ordinal", 0))
    return CompareObject(
        kind="hierarchy", subtype="hierarchy", domain=MODEL, source_key=f"hierarchy:{table}/{item['name']}", name=item["name"], table=table,
        lineage_tag=item.get("lineageTag"), display_folder=item.get("displayFolder"),
        props={"levels": [str(level.get("column", "")) for level in levels], "display_folder": item.get("displayFolder"),
               "description": _text(item.get("description")), "hidden": bool(item.get("isHidden", False))},
        strict_props=_strict(item), extra={"signature": ("levels", tuple(str(level.get("column", "")).casefold() for level in levels))},
        code=_json_code(item))


def _partition(table: str, item: Mapping[str, Any]) -> CompareObject | None:
    source = item.get("source") if isinstance(item.get("source"), Mapping) else {}
    if source.get("type") in {"calculated", "calculationGroup"}:
        # The table row compares the expression of a calculated table.
        return None
    expression = _text(source.get("expression"))
    other = {key: value for key, value in source.items() if key not in {"expression"}}
    return CompareObject(
        kind="partition", subtype="partition", domain=MODEL, source_key=f"partition:{table}/{item['name']}", name=item["name"], table=table,
        props={"mode": item.get("mode") or "default", "m_text": expression, "partition_source": other},
        strict_props=_strict(item), code=expression if expression is not None else _json_code(source), language=M if expression is not None else JSON)


def _calculation_items(table: str, group: Mapping[str, Any]) -> Iterator[CompareObject]:
    for item in _named(group.get("calculationItems")):
        yield CompareObject(
            kind="calculation_item", subtype="calculation_item", domain=MODEL, source_key=f"calculation_item:{table}/{item['name']}",
            name=item["name"], table=table,
            props={"expression": _text(item.get("expression")), "order": item.get("ordinal"),
                   "format_string_expression": _format_expression(item)},
            strict_props=_strict(item), extra={"signature": ("expression", _text(item.get("expression")))},
            code=_text(item.get("expression")) or "", language=DAX)


def _table(item: Mapping[str, Any]) -> Iterator[CompareObject]:
    name = item["name"]
    partitions = list(_named(item.get("partitions")))
    calculated = next((part["source"] for part in partitions
                       if isinstance(part.get("source"), Mapping) and part["source"].get("type") == "calculated"), None)
    group = item.get("calculationGroup") if isinstance(item.get("calculationGroup"), Mapping) else None
    props: dict[str, Any] = {"description": _text(item.get("description")), "hidden": bool(item.get("isHidden", False)),
                             "data_category": item.get("dataCategory")}
    subtype = "table"
    extra: dict[str, Any] = {}
    if calculated is not None:
        subtype = "calculated_table"
        props["expression"] = _text(calculated.get("expression"))
        extra["signature"] = ("expression", props["expression"])
    elif group is not None:
        subtype = "calculation_group"
    own = {key: value for key, value in item.items() if key not in {"columns", "measures", "hierarchies", "partitions", "calculationGroup"}}
    yield CompareObject(kind="table", subtype=subtype, domain=MODEL, source_key=f"table:{name}", name=name,
                        lineage_tag=item.get("lineageTag"), props=props, strict_props=_strict(item), extra=extra,
                        code=props.get("expression") or _json_code(own), language=DAX if calculated is not None else JSON)
    for measure in _named(item.get("measures")):
        yield _measure(name, measure)
    for column in _named(item.get("columns")):
        value = _column(name, column)
        if value is not None:
            yield value
    for hierarchy in _named(item.get("hierarchies")):
        yield _hierarchy(name, hierarchy)
    for partition in partitions:
        value = _partition(name, partition)
        if value is not None:
            value.extra["partition_count"] = len(partitions)
            yield value
    if group is not None:
        yield from _calculation_items(name, group)


_CARDINALITY = {"one": "one", "many": "many"}


def _relationship(item: Mapping[str, Any]) -> CompareObject:
    ends = [(str(item.get("fromTable", "")), str(item.get("fromColumn", ""))), (str(item.get("toTable", "")), str(item.get("toColumn", "")))]
    cardinality = [item.get("fromCardinality") or "many", item.get("toCardinality") or "one"]
    if [part.casefold() for part in ends[1]] < [part.casefold() for part in ends[0]]:
        # The ends align in any order. Keep one order, so the cardinality reads the same way.
        ends.reverse()
        cardinality.reverse()
    return CompareObject(
        kind="relationship", subtype="relationship", domain=MODEL, source_key=f"relationship:{item['name']}", name=item["name"],
        props={"cardinality": ":".join(cardinality), "cross_filter_direction": item.get("crossFilteringBehavior") or "oneDirection",
               "active": bool(item.get("isActive", True)), "security_filter_direction": item.get("securityFilteringBehavior") or "oneDirection",
               "referential_integrity": bool(item.get("relyOnReferentialIntegrity", False))},
        strict_props=_strict(item), extra={"ends": ends}, code=_json_code(item))


def _role(item: Mapping[str, Any]) -> CompareObject:
    from backend.devcenter.alignment.keys import ols_key

    filters: dict[str, Any] = {}
    ols: dict[str, Any] = {}
    names: dict[str, str] = {}
    for permission in _named(item.get("tablePermissions")):
        table = permission["name"]
        key = "/".join(ols_key(item["name"], table)[1:])
        names[key] = table
        if permission.get("filterExpression") is not None:
            filters[key] = _text(permission.get("filterExpression"))
        if permission.get("metadataPermission") is not None:
            ols[key] = permission.get("metadataPermission")
        for column in _named(permission.get("columnPermissions")):
            ols["/".join(ols_key(item["name"], table, column["name"])[1:])] = column.get("metadataPermission")
    own = {key: value for key, value in item.items() if key != "members"}
    return CompareObject(
        kind="role", subtype="role", domain=MODEL, source_key=f"role:{item['name']}", name=item["name"],
        props={"model_permission": item.get("modelPermission") or "read", "role_filters": filters, "ols": dict(sorted(ols.items()))},
        strict_props=_strict(item), extra={"tables": names}, code=_json_code(own))


def _expression(item: Mapping[str, Any]) -> CompareObject:
    text = _text(item.get("expression"))
    return CompareObject(
        kind="expression", subtype="expression", domain=MODEL, source_key=f"expression:{item['name']}", name=item["name"],
        lineage_tag=item.get("lineageTag"), props={"m_text": text, "expression_kind": item.get("kind") or "m"},
        strict_props=_strict(item), extra={"signature": ("m", text)}, code=text or "", language=M)


def _function(item: Mapping[str, Any]) -> CompareObject:
    text = _text(item.get("expression"))
    return CompareObject(
        kind="function", subtype="function", domain=MODEL, source_key=f"function:{item['name']}", name=item["name"],
        lineage_tag=item.get("lineageTag"),
        props={"expression": text, "description": _text(item.get("description")), "hidden": bool(item.get("isHidden", False))},
        strict_props=_strict(item), extra={"signature": ("expression", text)}, code=text or "", language=DAX)


def model_objects(model: Mapping[str, Any]) -> list[CompareObject]:
    """Give the compare objects of one TOM model (the ``model`` part of a TMSL database)."""

    found: list[CompareObject] = []
    for table in _named(model.get("tables")):
        found.extend(_table(table))
    found.extend(_relationship(item) for item in _named(model.get("relationships")))
    found.extend(_role(item) for item in _named(model.get("roles")))
    found.extend(_expression(item) for item in _named(model.get("expressions")))
    found.extend(_function(item) for item in _named(model.get("functions")))
    return found


# Report ---------------------------------------------------------------------

_PAGE_AREAS = {"displayName": "display_name", "height": "page_size", "width": "page_size", "displayOption": "page_size",
               "filterConfig": "filters"}
_VISUAL_AREAS = {"position": "position", "parentGroupName": "position", "filterConfig": "filters"}


def _areas(document: Mapping[str, Any], areas: Mapping[str, str], default: str) -> dict[str, Any]:
    grouped: dict[str, dict[str, Any]] = {}
    for key, value in document.items():
        if key in {"$schema", "name"}:
            continue
        grouped.setdefault(areas.get(key, default), {})[key] = value
    return grouped


def _visual_props(document: Mapping[str, Any]) -> dict[str, Any]:
    grouped = _areas(document, _VISUAL_AREAS, "formatting")
    visual = document.get("visual") if isinstance(document.get("visual"), Mapping) else None
    formatting = grouped.pop("formatting", {})
    if visual is not None:
        formatting.pop("visual", None)
        rest = {key: value for key, value in visual.items() if key not in {"visualType", "query"}}
        if rest:
            formatting["visual"] = rest
    return {"position": grouped.get("position", {}), "visual_type": visual.get("visualType") if visual else None,
            "fields": visual.get("query") if visual else None, "filters": grouped.get("filters", {}), "formatting": formatting}


def _page_props(document: Mapping[str, Any]) -> dict[str, Any]:
    grouped = _areas(document, _PAGE_AREAS, "formatting")
    return {"display_name": document.get("displayName"), "page_size": grouped.get("page_size", {}),
            "filters": grouped.get("filters", {}), "formatting": grouped.get("formatting", {})}


def _schema_strict(document: Mapping[str, Any]) -> dict[str, Any]:
    return {"metadata": {"$schema": document.get("$schema")}}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _pbir_objects(report_dir: Path) -> list[CompareObject]:
    definition = report_dir / "definition"
    found: list[CompareObject] = []
    for page_file in sorted((definition / "pages").glob("*/page.json")):
        folder = page_file.parent.name
        page = _read_json(page_file)
        found.append(CompareObject(
            kind="page", subtype="page", domain=REPORT, source_key=f"page:{folder}", name=str(page.get("displayName") or folder),
            props=_page_props(page), strict_props=_schema_strict(page),
            extra={"page_id": str(page.get("name") or folder), "display_name": page.get("displayName")}, code=_json_code(page)))
        for visual_file in sorted(page_file.parent.glob("visuals/*/visual.json")):
            visual = _read_json(visual_file)
            visual_id = str(visual.get("name") or visual_file.parent.name)
            found.append(CompareObject(
                kind="visual", subtype="visual_group" if "visualGroup" in visual else "visual", domain=REPORT,
                source_key=f"visual:{folder}/{visual_file.parent.name}", name=visual_id, table=folder,
                props=_visual_props(visual), strict_props=_schema_strict(visual), extra={"visual_id": visual_id},
                code=_json_code(visual)))
    extensions = definition / "reportExtensions.json"
    if extensions.is_file():
        document = _read_json(extensions)
        for entity in _named(document.get("entities")):
            for measure in _named(entity.get("measures")):
                found.append(CompareObject(
                    kind="report_measure", subtype="report_measure", domain=REPORT,
                    source_key=f"report_measure:{entity['name']}/{measure['name']}", name=measure["name"], table=entity["name"],
                    display_folder=measure.get("displayFolder"),
                    props={"expression": _text(measure.get("expression")), "format_string": measure.get("formatString"),
                           "display_folder": measure.get("displayFolder")},
                    strict_props={"metadata": {key: value for key, value in measure.items()
                                               if key not in {"name", "expression", "formatString", "displayFolder"}}},
                    extra={"signature": ("expression", _text(measure.get("expression")))},
                    code=_text(measure.get("expression")) or "", language=DAX))
    return found


def _parsed(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def _pbir_legacy_objects(report_dir: Path) -> list[CompareObject]:
    document = _read_json(report_dir / "report.json")
    found: list[CompareObject] = []
    for section in _named(document.get("sections")):
        page_id = section["name"]
        page = {key: _parsed(value) for key, value in section.items() if key != "visualContainers"}
        page["filterConfig"] = page.pop("filters", None)
        found.append(CompareObject(
            kind="page", subtype="page", domain=REPORT, source_key=f"page:{page_id}", name=str(section.get("displayName") or page_id),
            props=_page_props(page), extra={"page_id": page_id, "display_name": section.get("displayName")}, code=_json_code(page)))
        for position, container in enumerate(section.get("visualContainers") or []):
            if not isinstance(container, Mapping):
                continue
            config = _parsed(container.get("config"))
            config = config if isinstance(config, Mapping) else {}
            visual_id = str(config.get("name") or position)
            single = config.get("singleVisual") if isinstance(config.get("singleVisual"), Mapping) else {}
            shaped = {
                "position": {key: container.get(key) for key in ("x", "y", "z", "width", "height") if key in container},
                "filterConfig": _parsed(container.get("filters")),
                "visual": {"visualType": single.get("visualType"),
                           "query": {key: single.get(key) for key in ("projections", "prototypeQuery") if key in single},
                           **{key: value for key, value in single.items() if key not in {"visualType", "projections", "prototypeQuery"}}},
            }
            found.append(CompareObject(
                kind="visual", subtype="visual", domain=REPORT, source_key=f"visual:{page_id}/{visual_id}", name=visual_id, table=page_id,
                props=_visual_props(shaped), extra={"visual_id": visual_id}, code=_json_code(shaped)))
    return found


# Loading with a cache ---------------------------------------------------------


@dataclass
class SourceObjects:
    """The compare objects of one source, in source key order."""

    model: list[CompareObject]
    report: list[CompareObject]

    def all(self) -> list[CompareObject]:
        return self.model + self.report


_CACHE: dict[tuple[str, str], SourceObjects] = {}
_CACHE_LOCK = threading.Lock()
_CACHE_SIZE = 32


def _read_model(source: LocalSource, adapter: TabularMetadataAdapter) -> dict[str, Any]:
    assert source.model_dir is not None
    path = source.model_dir / "model.bim" if source.model_format == MODEL_TMSL else source.model_dir
    try:
        payload = adapter.read(path)
    except MetadataUnavailable as exc:
        raise not_allowed("The app could not read the model of this source.", "model_unreadable",
                          source=source.display_name) from exc
    model = payload["database"].get("model")
    return model if isinstance(model, dict) else {}


def load_objects(source: LocalSource, *, adapter: TabularMetadataAdapter | None = None) -> SourceObjects:
    """Read the compare objects of a source. The cache key is the path and the Source Fingerprint."""

    key = (str(source.root), source_fingerprint(source))
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
    if cached is not None:
        return cached
    model: list[CompareObject] = []
    report: list[CompareObject] = []
    if source.model_dir is not None and source.model_format in {MODEL_TMDL, MODEL_TMSL}:
        model = model_objects(_read_model(source, adapter or TabularMetadataAdapter()))
    if source.report_dir is not None and source.report_format == REPORT_PBIR:
        report = _pbir_objects(source.report_dir)
    elif source.report_dir is not None and source.report_format == REPORT_PBIR_LEGACY:
        report = _pbir_legacy_objects(source.report_dir)
    value = SourceObjects(sorted(model, key=lambda item: item.source_key), sorted(report, key=lambda item: item.source_key))
    with _CACHE_LOCK:
        if len(_CACHE) >= _CACHE_SIZE:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[key] = value
    return value
