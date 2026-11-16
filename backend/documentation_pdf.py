"""Scoped documentation export as PDF or Markdown (issue #15).

One content model, two renderers. ``build_document`` reads the loaded graph (the same snapshot the app
shows) and returns ordered blocks: headings, paragraphs, tables, code and diagrams. ``render_pdf``
lays them out with :mod:`backend.pdf_writer` (table of contents with links, bookmarks, page numbers);
``render_document_markdown`` writes the same blocks as Markdown, diagrams as Mermaid.

Every list is sorted, so a repeated export of the same snapshot and scope is byte-identical except
the generation timestamp (pass ``generated_at`` to pin it).
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Any
from collections.abc import Iterable, Mapping, Sequence

from backend.documentation_export import (
    UNKNOWN,
    _diagnostics,
    _expression_items,
    _cell,
    _fenced,
    _source_path,
    _unresolved,
)
from backend.graph.repository import GraphRepository
from backend.graph.schema import Node
from backend.pdf_writer import BOTTOM, CONTENT_WIDTH, MARGIN, TOP, DiagramBox, DiagramLink, PdfDocument, pdf_text, text_width

SECTIONS: dict[str, str] = {
    "overview": "Overview and scope",
    "models": "Model diagram, relationships and tables",
    "measures": "Measure catalogue with DAX",
    "reports": "Report pages and visual fields",
    "lineage": "Lineage summary",
    "not_checked": "Not checked and unresolved",
}
FORMATS = ("pdf", "markdown")
_REPORT_FILTERS = {"VISUAL_FILTER", "PAGE_FILTER", "REPORT_FILTER"}


class DocumentationScopeError(ValueError):
    """The requested scope names an unknown model, report, section or format."""


@dataclass
class Block:
    kind: str  # heading | paragraph | note | table | code | diagram
    text: str = ""
    level: int = 0
    headers: tuple[str, ...] = ()
    rows: list[tuple[Any, ...]] = field(default_factory=list)
    widths: tuple[float, ...] | None = None
    boxes: tuple[DiagramBox, ...] = ()
    links: tuple[DiagramLink, ...] = ()
    language: str = ""


@dataclass
class Document:
    title: str
    project: str
    generated_at: str
    blocks: list[Block]
    scope: dict[str, Any]


# Small helpers ----------------------------------------------------------------------------------

def _props(node: Node) -> Mapping[str, Any]:
    return node.properties if isinstance(node.properties, Mapping) else {}


def _sort_key(node: Node) -> tuple[str, str]:
    return ((node.name or "").casefold(), node.id)


_STORAGE_MODES = {"import": "Import", "directquery": "DirectQuery", "dual": "Dual", "directlake": "Direct Lake",
                  "push": "Push", "default": "Import"}


def _storage_mode(table: Node, children: Sequence[Node]) -> str:
    """The storage mode of a table as Power BI shows it. TMDL and TOM keep it on the partitions."""

    own = _props(table).get("storage_mode") or _props(table).get("mode")
    if own:
        return _STORAGE_MODES.get(re.sub(r"[^a-z]", "", str(own).casefold()), str(own))
    partitions = [child for child in children if child.type == "PARTITION"]
    if not partitions:
        return "Not recorded"
    modes = set()
    for partition in partitions:
        mode = _props(partition).get("mode")
        if mode:
            modes.add(_STORAGE_MODES.get(re.sub(r"[^a-z]", "", str(mode).casefold()), str(mode)))
        elif str(_props(partition).get("source_type") or "").casefold() == "entity":
            modes.add("Direct Lake")
        else:
            modes.add("Import")
    return " / ".join(sorted(modes)) if len(modes) > 1 else modes.pop()


_TABLE_KEYS = ("table", "Table", "entity", "Entity", "table_name", "tableName")
_FIELD_KEYS = ("column", "Column", "measure", "Measure", "property", "Property", "hierarchy", "Hierarchy", "level", "Level", "name", "Name")


def _plain(value: Any) -> str:
    """A reference or detail written as text a Power BI developer reads, never as JSON.

    ``{"table": "Sales", "column": "Amount"}`` and the PBIR form
    ``{"Column": {"Expression": {"SourceRef": {"Entity": "Sales"}}, "Property": "Amount"}}`` both give
    ``Sales[Amount]``; a DAX diagnostic gives its message; anything else gives "name: value" pairs.
    """

    if value in (None, "", [], {}):
        return ""
    if isinstance(value, (list, tuple)):
        return "; ".join(text for text in (_plain(item) for item in value) if text)
    if not isinstance(value, Mapping):
        return str(value)
    field_ref = _field_reference(value)
    if field_ref:
        return field_ref
    if value.get("message"):
        position = value.get("position") if isinstance(value.get("position"), Mapping) else {}
        where = value.get("line") or position.get("line")
        return f"{value['message']} (line {where})" if where else str(value["message"])
    parts = []
    for key in sorted(value):
        text = _plain(value[key])
        if text:
            parts.append(f"{str(key).replace('_', ' ')}: {text}")
    return ", ".join(parts)


def _field_reference(value: Mapping[str, Any]) -> str:
    table = next((value[key] for key in _TABLE_KEYS if isinstance(value.get(key), str)), None)
    field_name = next((value[key] for key in _FIELD_KEYS if isinstance(value.get(key), str)), None)
    if table is None:
        source = value.get("Expression") or value.get("expression")
        if isinstance(source, Mapping):
            source = source.get("SourceRef") or source.get("sourceRef") or source
            if isinstance(source, Mapping):
                table = next((source[key] for key in _TABLE_KEYS if isinstance(source.get(key), str)), None)
    if table and field_name:
        return f"{table}[{field_name}]"
    for key in ("Column", "Measure", "Hierarchy", "HierarchyLevel", "Aggregation", "column", "measure"):
        inner = value.get(key)
        if isinstance(inner, Mapping):
            found = _field_reference(inner)
            if found:
                return found
    return f"'{table}'" if table and len(value) == 1 else ""


def _list(value: Any) -> list[Any]:
    if value in (None, ""):
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


def _flag(value: Any) -> str:
    if value is None or value == "":
        return ""
    return "Yes" if str(value).casefold() in {"true", "1", "yes"} else "No" if str(value).casefold() in {"false", "0", "no"} else str(value)


def _cardinality(value: Any) -> str:
    text = re.sub(r"[^a-z]", "", str(value or "").casefold())
    return {"manytoone": "*:1", "onetomany": "1:*", "onetoone": "1:1", "manytomany": "*:*"}.get(text, str(value or ""))


def _count(number: int, word: str) -> str:
    return f"{number} {word}" if number == 1 else f"{number} {word}s"


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _pdf_date(stamp: str) -> str:
    digits = re.sub(r"\D", "", stamp)[:14].ljust(14, "0")
    return f"D:{digits}Z"


# Content model ----------------------------------------------------------------------------------

def build_document(
    repository: GraphRepository,
    *,
    project_name: str = "PBIBrain",
    model_ids: Sequence[str] | None = None,
    report_ids: Sequence[str] | None = None,
    sections: Sequence[str] | None = None,
    generated_at: str | None = None,
    store: Any = None,
) -> Document:
    """Build the ordered blocks for the chosen models, reports and sections. ``None`` means all."""

    all_nodes = repository.all_nodes()
    all_edges = repository.all_edges()
    nodes = {node.id: node for node in all_nodes}
    models_all = sorted((node for node in all_nodes if node.type == "MODEL"), key=_sort_key)
    reports_all = sorted((node for node in all_nodes if node.type == "REPORT"), key=_sort_key)
    chosen_sections = list(SECTIONS) if sections is None else [item for item in SECTIONS if item in set(sections)]
    unknown_sections = sorted(set(sections or ()) - set(SECTIONS))
    if unknown_sections:
        raise DocumentationScopeError(f"Unknown documentation sections: {', '.join(unknown_sections)}")
    if sections is not None and not chosen_sections:
        raise DocumentationScopeError("Choose at least one documentation section")
    models = _pick(models_all, model_ids, "model")
    reports = _pick(reports_all, report_ids, "report")
    if not models and not reports:
        raise DocumentationScopeError("Choose at least one model or report to document")
    model_set = {node.id for node in models}
    report_set = {node.id for node in reports}

    def in_scope(node: Node) -> bool:
        if node.id in model_set or node.id in report_set:
            return True
        if node.report_id:
            return node.report_id in report_set
        return bool(node.model_id) and node.model_id in model_set

    scoped = {node.id: node for node in all_nodes if in_scope(node)}
    # Data sources have no model id: include those an in-scope query reads.
    for edge in all_edges:
        if edge.type == "SOURCES_FROM" and edge.from_id in scoped and edge.to_id in nodes:
            scoped[edge.to_id] = nodes[edge.to_id]
    children: dict[str, list[Node]] = defaultdict(list)
    for node in all_nodes:
        parent = _props(node).get("table_id") or _props(node).get("calculation_group_id") or _props(node).get("parent_id")
        if parent:
            children[str(parent)].append(node)
    for items in children.values():
        items.sort(key=_sort_key)

    def qualified(node_id: Any) -> str:
        node = nodes.get(str(node_id)) if node_id else None
        if node is None:
            return f"{node_id} (not in snapshot)" if node_id else UNKNOWN
        table = nodes.get(str(_props(node).get("table_id") or ""))
        if node.type in {"COLUMN", "MEASURE", "HIERARCHY"} and table is not None:
            return f"{table.name}[{node.name}]"
        if node.type == "LEVEL":
            hierarchy = nodes.get(str(_props(node).get("hierarchy_id") or _props(node).get("parent_id") or ""))
            return f"{hierarchy.name if hierarchy else '?'}.{node.name}"
        return node.name or node.id

    stamp = generated_at or _now()
    blocks: list[Block] = []
    add = blocks.append

    if "overview" in chosen_sections:
        add(Block("heading", "Overview and scope", 1))
        add(Block("paragraph", "This document describes the semantic models and reports below as they were saved in their "
                  "Power BI project files at the last scan: tables, relationships, measures with their DAX, report pages "
                  "and the fields each visual uses. It describes the design, not the data in it."))
        add(Block("table", headers=("Field", "Value"), widths=(1, 3), rows=[
            ("Project", project_name),
            ("Generated", stamp),
            ("Read from the files", _last_scan(repository) or "Unknown"),
            ("Semantic models", f"{len(models)} of {len(models_all)}"),
            ("Reports", f"{len(reports)} of {len(reports_all)}"),
            ("Sections", ", ".join(SECTIONS[item] for item in chosen_sections)),
        ]))
        if models:
            add(Block("heading", "Semantic models", 2))
            rows = []
            for model in models:
                counts = Counter(node.type for node in all_nodes if node.model_id == model.id and not node.report_id)
                rows.append((model.name or model.id, counts["TABLE"], counts["MEASURE"], counts["RELATIONSHIP"],
                             "Could not be read" if _props(model).get("check_status") == "not_checked" else "Read",
                             _source_path(model) or ""))
            add(Block("table", headers=("Model", "Tables", "Measures", "Relationships", "Status", "Location"),
                      widths=(2, 0.7, 0.8, 1, 0.9, 3), rows=rows))
        if reports:
            add(Block("heading", "Reports", 2))
            rows = []
            for report in reports:
                counts = Counter(node.type for node in all_nodes if node.report_id == report.id)
                bound = nodes.get(report.model_id or "")
                rows.append((report.name or report.id, bound.name if bound else "Not found in this project", counts["PAGE"], counts["VISUAL"],
                             "Could not be read" if _props(report).get("check_status") == "not_checked" else "Read",
                             _source_path(report) or ""))
            add(Block("table", headers=("Report", "Semantic model", "Pages", "Visuals", "Status", "Location"),
                      widths=(2, 1.6, 0.6, 0.7, 0.9, 2.6), rows=rows))

    for model in models:
        if not {"models", "measures"} & set(chosen_sections):
            break
        tables = sorted((node for node in all_nodes if node.type == "TABLE" and node.model_id == model.id), key=_sort_key)
        relationships = sorted((node for node in all_nodes if node.type == "RELATIONSHIP" and node.model_id == model.id), key=lambda n: n.id)
        measures = sorted((node for node in all_nodes if node.type == "MEASURE" and node.model_id == model.id),
                          key=lambda n: (qualified(n.id).casefold(), n.id))
        add(Block("heading", f"Model: {model.name or model.id}", 1))
        if model.description:
            add(Block("paragraph", f"Description (from source): {model.description}"))
        add(Block("note", f"{_count(len(tables), 'table')} · {_count(len(measures), 'measure')} · {_count(len(relationships), 'relationship')}"))
        if "models" in chosen_sections:
            add(Block("heading", "Model diagram", 2))
            if tables:
                diagram, unrelated = _model_diagram(tables, relationships, nodes, children)
                if diagram.boxes:
                    add(diagram)
                    add(Block("note", "Each box is a table with its storage mode and the key columns of its relationships. "
                              "Tables on the many side of relationships (fact tables) are in the middle row, the tables they "
                              "look up (dimensions) around them. Lines show cardinality (many *, one 1) and filter direction; "
                              "dashed lines are inactive relationships. Blue: Import, orange: DirectQuery, purple: Dual, green: Direct Lake."))
                if unrelated:
                    add(Block("paragraph", "Tables without relationships: " + ", ".join(table.name or table.id for table in unrelated) + "."))
            else:
                add(Block("paragraph", "No tables recorded."))
            add(Block("heading", "Relationships", 2))
            if relationships:
                add(Block("table", headers=("From (many side)", "To (one side)", "Cardinality", "Cross-filter direction", "Active"),
                          widths=(2.2, 2.2, 0.9, 1.2, 0.6), rows=[
                    (qualified(_props(rel).get("from_column_id")) if _props(rel).get("from_column_id") else f"{_plain(_props(rel).get('from_ref'))} (not found in the model)",
                     qualified(_props(rel).get("to_column_id")) if _props(rel).get("to_column_id") else f"{_plain(_props(rel).get('to_ref'))} (not found in the model)",
                     _cardinality(_props(rel).get("cardinality")) or "*:1",
                     _cross_filter(_props(rel).get("cross_filter_direction")),
                     _flag(_props(rel).get("active")) or "Yes")
                    for rel in relationships]))
            else:
                add(Block("paragraph", "No relationships recorded."))
            add(Block("heading", "Tables", 2))
            if tables:
                add(Block("table", headers=("Table", "Storage mode", "Columns", "Measures", "Hidden", "Description"),
                          widths=(1.6, 1, 0.7, 0.7, 0.6, 3), rows=[
                    (table.name, _storage_mode(table, children[table.id]),
                     sum(1 for child in children[table.id] if child.type == "COLUMN"),
                     sum(1 for child in children[table.id] if child.type == "MEASURE"),
                     _flag(_props(table).get("hidden")) or "No", table.description or "") for table in tables]))
        if "measures" in chosen_sections:
            add(Block("heading", "Measure catalogue", 2))
            if not measures:
                add(Block("paragraph", "No measures recorded."))
            for measure in measures:
                add(Block("heading", qualified(measure.id), 3))
                details = []
                if _props(measure).get("format_string"):
                    details.append(f"Format: {_props(measure)['format_string']}")
                if _props(measure).get("display_folder"):
                    details.append(f"Folder: {_props(measure)['display_folder']}")
                if str(_props(measure).get("hidden", "")).casefold() == "true":
                    details.append("Hidden")
                if details:
                    add(Block("note", " · ".join(details)))
                add(Block("paragraph", f"Description: {measure.description}" if measure.description else "Description: none."))
                items = _expression_items(measure)
                if items:
                    for label, expression in items:
                        if label != "Expression":
                            add(Block("note", label))
                        add(Block("code", expression, language="dax"))
                else:
                    add(Block("paragraph", "No expression recorded."))

    if "reports" in chosen_sections:
        for report in reports:
            pages = sorted((node for node in all_nodes if node.type == "PAGE" and node.report_id == report.id),
                           key=lambda n: (_order(n), (n.name or "").casefold(), n.id))
            bound = nodes.get(report.model_id or "")
            add(Block("heading", f"Report: {report.name or report.id}", 1))
            add(Block("note", f"Semantic model: {bound.name if bound else 'not found in this project'} · {_count(len(pages), 'page')}"))
            if not pages:
                add(Block("paragraph", "No pages recorded."))
            for page in pages:
                visuals = sorted((child for child in children[page.id] if child.type == "VISUAL"),
                                 key=lambda n: (_num(_props(n).get("y")), _num(_props(n).get("x")), (n.name or "").casefold(), n.id))
                filters = [child for child in children[page.id] if child.type in _REPORT_FILTERS]
                add(Block("heading", f"Page: {_props(page).get('display_name') or page.name or page.id}", 2))
                add(Block("note", f"{_count(len(visuals), 'visual')} · {_count(len(filters), 'page filter')}"))
                if visuals:
                    add(Block("table", headers=("Visual", "Type", "Fields used", "Fields not in the model"),
                              widths=(1.5, 1, 3.4, 1.5), rows=[
                        (_props(visual).get("title") or visual.name or visual.id, _visual_type(_props(visual).get("visual_type")),
                         "; ".join(qualified(item) for item in _list(_props(visual).get("field_ids"))) or "None",
                         _plain(_list(_props(visual).get("unresolved_field_refs")))) for visual in visuals]))
                if filters:
                    add(Block("table", headers=("Filter", "Kind", "Field"), widths=(1.6, 1, 3.2), rows=[
                        (item.name or item.id, item.type.replace("_", " ").capitalize(),
                         qualified(_props(item).get("target_id")) if _props(item).get("target_id") else _plain(_props(item).get("unresolved_target") or _props(item).get("target_ref")))
                        for item in sorted(filters, key=_sort_key)]))
            report_filters = sorted((child for child in children[report.id] if child.type in _REPORT_FILTERS), key=_sort_key)
            if report_filters:
                add(Block("heading", "Report-level filters", 2))
                add(Block("table", headers=("Filter", "Field"), widths=(1.6, 3.2), rows=[
                    (item.name or item.id, qualified(_props(item).get("target_id")) if _props(item).get("target_id") else _plain(_props(item).get("target_ref")))
                    for item in report_filters]))

    if "lineage" in chosen_sections:
        add(Block("heading", "Lineage summary", 1))
        sources = sorted((node for node in scoped.values() if node.type == "DATA_SOURCE"), key=_sort_key)
        queries = sorted((node for node in scoped.values() if node.type in {"PARTITION", "SHARED_EXPRESSION"}),
                         key=lambda n: ((nodes.get(n.model_id or "") or n).name.casefold(), qualified(n.id).casefold(), n.id))
        reads: dict[str, list[str]] = defaultdict(list)
        for edge in all_edges:
            if edge.type == "SOURCES_FROM" and edge.from_id in scoped and edge.to_id in scoped:
                reads[edge.from_id].append(edge.to_id)
        add(Block("paragraph", "Where the data comes from and who uses it: data sources read by Power Query, the models that load them, "
                  "and the reports bound to those models."))
        add(_lineage_diagram(sources, models, reports, reads, scoped, nodes))
        add(Block("note", "Green: data sources. Blue: semantic models. Orange: reports. Grey boxes could not be read."))
        add(Block("heading", "Data sources", 2))
        if sources:
            readers: dict[str, list[str]] = defaultdict(list)
            for query_id, targets in reads.items():
                for target in targets:
                    readers[target].append(query_id)
            add(Block("table", headers=("Data source", "Kind", "Location", "Read by", "Models"), widths=(1.5, 0.9, 2.2, 2, 1.2), rows=[
                (source.name, _props(source).get("connector") or _props(source).get("kind") or "", _props(source).get("location") or "",
                 "; ".join(sorted(_query_label(nodes[item], nodes) for item in readers[source.id])),
                 "; ".join(sorted((nodes[item].name if item in nodes else item) for item in _list(_props(source).get("model_ids")) if item in model_set)))
                for source in sources]))
        else:
            add(Block("paragraph", "No data sources recorded for the models in this document."))
        add(Block("heading", "Power Query queries", 2))
        if queries:
            add(Block("table", headers=("Query", "Model", "Kind", "Storage mode", "Reads", "Status"), widths=(1.8, 1.1, 0.9, 0.8, 2, 1), rows=[
                (_query_label(query, nodes), (nodes.get(query.model_id or "") or query).name,
                 "Table partition" if query.type == "PARTITION" else "Shared query / parameter",
                 _STORAGE_MODES.get(re.sub(r"[^a-z]", "", str(_props(query).get("mode") or "").casefold()), _props(query).get("mode") or "") if query.type == "PARTITION" else "",
                 "; ".join(sorted(nodes[item].name for item in reads[query.id])) or "",
                 "Could not be read" if _props(query).get("check_status") == "not_checked" else (_props(query).get("source_status") or "").replace("_", " ").capitalize())
                for query in queries]))
        else:
            add(Block("paragraph", "No Power Query queries recorded."))
        add(Block("heading", "Report usage", 2))
        if reports:
            usage_rows = []
            for report in reports:
                visuals = [node for node in all_nodes if node.type == "VISUAL" and node.report_id == report.id]
                fields = {item for visual in visuals for item in _list(_props(visual).get("field_ids"))}
                bound = nodes.get(report.model_id or "")
                usage_rows.append((report.name, bound.name if bound else report.model_id or "Not resolved", len(visuals), len(fields)))
            add(Block("table", headers=("Report", "Model", "Visuals", "Distinct fields used"), widths=(2, 2, 0.8, 1.2), rows=usage_rows))
        else:
            add(Block("paragraph", "No reports in this document."))

    if "not_checked" in chosen_sections:
        add(Block("heading", "Not checked and unresolved", 1))
        add(Block("paragraph", "Items PBIBrain could not read, and references to tables, columns or measures it could not find. "
                  "The lineage of these items may be incomplete."))
        not_checked = sorted((node for node in scoped.values() if _props(node).get("check_status") == "not_checked"),
                             key=lambda n: (n.type, (n.name or "").casefold(), n.id))
        add(Block("heading", "Not read", 2))
        if not_checked:
            add(Block("table", headers=("Item", "Type", "Reason", "Detail"), widths=(1.8, 1, 1.2, 3), rows=[
                (_query_label(node, nodes) if node.type in {"PARTITION", "SHARED_EXPRESSION"} else node.name or node.id, _type_label(node.type),
                 str(_props(node).get("not_checked_reason") or "").replace("_", " ").capitalize(), _plain(_props(node).get("not_checked_detail")))
                for node in not_checked]))
        else:
            add(Block("paragraph", "Everything in this document was read."))
        unresolved = [item for item in _unresolved(repository) if item["object_id"] in scoped]
        add(Block("heading", "References not found", 2))
        if unresolved:
            add(Block("table", headers=("Item", "What", "Reference"), widths=(2, 1.4, 2.6), rows=[
                (qualified(item["object_id"]), item["kind"].capitalize(), _plain(item["evidence"]) or "None") for item in unresolved]))
        else:
            add(Block("paragraph", "Every reference in this document was found."))
        diagnostics = [item for item in _diagnostics(repository) if item["object_id"] in scoped]
        if diagnostics:
            add(Block("heading", "DAX problems", 2))
            add(Block("table", headers=("Item", "Problem"), widths=(2, 4), rows=[
                (qualified(item["object_id"]), _plain(item["evidence"]) or item["code"].replace("_", " ")) for item in diagnostics]))

    title = f"{project_name} documentation"
    scope = {"model_ids": [node.id for node in models], "report_ids": [node.id for node in reports], "sections": chosen_sections}
    return Document(title=title, project=project_name, generated_at=stamp, blocks=blocks, scope=scope)


def _pick(candidates: list[Node], wanted: Sequence[str] | None, label: str) -> list[Node]:
    if wanted is None:
        return candidates
    known = {node.id for node in candidates}
    missing = sorted(set(wanted) - known)
    if missing:
        raise DocumentationScopeError(f"Unknown {label} IDs: {', '.join(missing)}")
    chosen = set(wanted)
    return [node for node in candidates if node.id in chosen]


def _last_scan(repository: GraphRepository) -> Any:
    return next((getattr(repository, name, None) for name in ("last_scan", "scan_timestamp", "last_scan_at") if getattr(repository, name, None)), None)


def _order(node: Node) -> float:
    return _num(_props(node).get("order"), default=1e9)


def _num(value: Any, *, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _query_label(node: Node, nodes: Mapping[str, Node]) -> str:
    table = nodes.get(str(_props(node).get("table_id") or ""))
    if node.type == "PARTITION" and table is not None:
        return table.name if node.name == table.name else f"{table.name} / {node.name}"
    return node.name or node.id


_MODE_KIND = {"Import": "fact", "DirectQuery": "directquery", "Dual": "dual", "Direct Lake": "source"}
_ROW_LIMIT = 6


def _cross_filter(value: Any) -> str:
    text = re.sub(r"[^a-z]", "", str(value or "").casefold())
    if text in {"bothdirections", "both"}:
        return "Both"
    if text in {"", "onedirection", "single", "automatic", "default"}:
        return "Single"
    return str(value)


_VISUAL_TYPES = {"tableex": "Table", "pivottable": "Matrix", "multirowcard": "Multi-row card", "cardvisual": "Card",
                 "textbox": "Text box", "actionbutton": "Button", "kpi": "KPI", "shape": "Shape", "image": "Image",
                 "map": "Map", "filledmap": "Filled map", "shapemap": "Shape map", "azuremap": "Azure map"}


def _visual_type(value: Any) -> str:
    """``clusteredColumnChart`` as "Clustered column chart", ``tableEx`` as "Table"."""

    known = _VISUAL_TYPES.get(str(value or "").casefold())
    if known:
        return known
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", str(value or "")).strip()
    return text[:1].upper() + text[1:].lower() if text else ""


def _type_label(value: Any) -> str:
    return {"SHARED_EXPRESSION": "Shared query", "PARTITION": "Table partition", "MODEL": "Semantic model",
            "DATA_SOURCE": "Data source"}.get(str(value), str(value or "").replace("_", " ").capitalize())


def _model_diagram(tables: list[Node], relationships: list[Node], nodes: Mapping[str, Node],
                   children: Mapping[str, list[Node]]) -> tuple[Block, list[Node]]:
    """A star layout: fact tables (the many side) in the middle row, the tables they look up above and below.

    Gives the diagram and the tables that have no relationship (listed under it, not drawn).
    """

    def column_of(column_id: Any) -> Node | None:
        return nodes.get(str(column_id or ""))

    def table_of(column: Node | None) -> str | None:
        return str(_props(column).get("table_id")) if column is not None and _props(column).get("table_id") else None

    by_id = {table.id: table for table in tables}
    links: list[DiagramLink] = []
    neighbours: dict[str, set[str]] = defaultdict(set)
    many: Counter[str] = Counter()
    one: Counter[str] = Counter()
    keys: dict[str, set[str]] = defaultdict(set)
    for rel in relationships:
        from_column, to_column = column_of(_props(rel).get("from_column_id")), column_of(_props(rel).get("to_column_id"))
        source, target = table_of(from_column), table_of(to_column)
        if not (source in by_id and target in by_id) or source == target:
            continue
        cardinality = _cardinality(_props(rel).get("cardinality")) or "*:1"
        if cardinality == "1:*":
            source, target, from_column, to_column = target, source, to_column, from_column
            cardinality = "*:1"
        many[source] += 1
        one[target] += 1
        neighbours[source].add(target)
        neighbours[target].add(source)
        keys[source].add(from_column.name)
        keys[target].add(to_column.name)
        label = cardinality + (" (both)" if _cross_filter(_props(rel).get("cross_filter_direction")) == "Both" else "")
        links.append(DiagramLink(source, target, label, dashed=str(_props(rel).get("active", "true")).casefold() == "false"))
    related = [table for table in tables if table.id in neighbours]
    unrelated = [table for table in tables if table.id not in neighbours]
    if not related:
        return Block("diagram", "Model diagram"), unrelated

    facts = [table for table in related if many[table.id] > one[table.id]]
    if not facts:
        facts = [max(related, key=lambda table: (len(neighbours[table.id]), (table.name or "").casefold()))]
    level = {table.id: 0 for table in facts}
    frontier = [table.id for table in facts]
    while frontier:
        following = []
        for table_id in sorted(frontier):
            for other in sorted(neighbours[table_id]):
                if other not in level:
                    level[other] = level[table_id] + 1
                    following.append(other)
        frontier = following
    # Rows from the top: ... level 2 above, level 1 above, facts, level 1 below, level 2 below ...
    rows: dict[int, list[Node]] = defaultdict(list)
    rows[0] = sorted(facts, key=lambda table: (-len(neighbours[table.id]), (table.name or "").casefold(), table.id))
    side: dict[str, int] = {}
    outer = sorted((table for table in related if level.get(table.id, 0) > 0),
                   key=lambda table: (level[table.id], -len(neighbours[table.id]), (table.name or "").casefold(), table.id))
    counts = Counter()
    for table in outer:
        parents = [side[item] for item in neighbours[table.id] if item in side]
        sign = parents[0] if parents else (-1 if counts[-level[table.id]] <= counts[level[table.id]] else 1)
        side[table.id] = sign
        rows[sign * level[table.id]].append(table)
        counts[sign * level[table.id]] += 1
    # Long rows wrap outward, so the diagram stays readable at page width.
    stacked: list[list[Node]] = []
    for key in sorted(rows):
        items = rows[key]
        chunks = [items[index:index + _ROW_LIMIT] for index in range(0, len(items), _ROW_LIMIT)] or [[]]
        stacked.extend(reversed(chunks) if key < 0 else chunks)
    w, gap_x, gap_y = 150.0, 34.0, 48.0
    position: dict[str, float] = {}
    boxes = []
    y = 0.0
    widest = max(len(row) for row in stacked) * (w + gap_x)
    for row in stacked:
        # Order each row by where its neighbours already are, to keep lines short and uncrossed.
        row = sorted(row, key=lambda table: (
            sum(position[item] for item in neighbours[table.id] if item in position) / max(1, sum(1 for item in neighbours[table.id] if item in position))
            if any(item in position for item in neighbours[table.id]) else 1e9,
            (table.name or "").casefold(), table.id))
        start = (widest - len(row) * (w + gap_x)) / 2
        height = 0.0
        for index, table in enumerate(row):
            mode = _storage_mode(table, children.get(table.id, []))
            hidden = str(_props(table).get("hidden", "")).casefold() == "true"
            lines = [f"{table.name or table.id}{' (hidden)' if hidden else ''}", mode]
            listed = sorted(keys[table.id], key=str.casefold)
            lines.extend(f"Key: {name}" for name in listed[:3])
            if len(listed) > 3:
                lines.append(f"+{len(listed) - 3} more keys")
            h = 14.0 + 10.5 * len(lines)
            x = start + index * (w + gap_x)
            position[table.id] = x
            boxes.append(DiagramBox(table.id, tuple(lines), x, y, w, h, "muted" if hidden else _MODE_KIND.get(mode, "fact")))
            height = max(height, h)
        y += height + gap_y
    return (Block("diagram", "Model diagram", boxes=tuple(boxes),
                  links=tuple(sorted(links, key=lambda item: (item.source, item.target, item.label)))), unrelated)


def _lineage_diagram(sources: list[Node], models: list[Node], reports: list[Node], reads: Mapping[str, list[str]],
                     scoped: Mapping[str, Node], nodes: Mapping[str, Node]) -> Block:
    links = set()
    for query_id, targets in reads.items():
        query = nodes.get(query_id)
        if query is None or not query.model_id:
            continue
        for target in targets:
            links.add((target, query.model_id))
    for report in reports:
        if report.model_id:
            links.add((report.model_id, report.id))
    model_lane = list(models)
    for model_id in sorted({model for _, model in links if model in nodes and nodes[model].type == "MODEL"} - {m.id for m in models}):
        model_lane.append(nodes[model_id])
    model_row = {node.id: index for index, node in enumerate(model_lane)}
    placed_reports, row = [], -1
    # A report sits level with its model when it can, so most lines run straight across.
    for report in sorted(reports, key=lambda n: (model_row.get(n.model_id or "", len(model_lane)), (n.name or "").casefold(), n.id)):
        row = max(row + 1, model_row.get(report.model_id or "", row + 1))
        placed_reports.append((row, report))
    lanes = [(kind, items) for kind, items in (("source", list(enumerate(sources))), ("fact", list(enumerate(model_lane))),
                                               ("report", placed_reports)) if items]
    w, h, gap_x, gap_y = 150.0, 34.0, 70.0, 14.0
    boxes = []
    for column, (kind, items) in enumerate(lanes):
        for row, node in items:
            muted = _props(node).get("check_status") == "not_checked"
            label = {"source": "Data source", "fact": "Semantic model", "report": "Report"}[kind]
            boxes.append(DiagramBox(node.id, (node.name or node.id, label), column * (w + gap_x), row * (h + gap_y), w, h, "muted" if muted else kind))
    return Block("diagram", "Lineage", boxes=tuple(boxes),
                 links=tuple(DiagramLink(a, b) for a, b in sorted(links)))


# Markdown ---------------------------------------------------------------------------------------

def _mermaid(block: Block) -> list[str]:
    ids = {box.key: f"n{index}" for index, box in enumerate(block.boxes)}
    lines = ["flowchart LR" if block.text == "Lineage" else "flowchart TB"]
    for box in block.boxes:
        label = "<br/>".join(part.replace('"', "#quot;") for part in box.lines)
        lines.append(f'  {ids[box.key]}["{label}"]')
    for link in block.links:
        if link.source in ids and link.target in ids:
            arrow = "-.-" if link.dashed else "---" if block.text != "Lineage" else "-->"
            label = f"|{link.label}|" if link.label else ""
            lines.append(f"  {ids[link.source]} {arrow}{label} {ids[link.target]}")
    return lines


def _md_table(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> list[str]:
    """A Markdown table where an empty cell stays empty (the content model already says "Not recorded" where it matters)."""

    out = ["| " + " | ".join(_cell(item, unknown="") for item in headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    out.extend("| " + " | ".join(_cell(item, unknown="") for item in row) + " |" for row in rows)
    return out


def render_document_markdown(document: Document) -> str:
    lines = [f"# {document.title}", "", f"Generated {document.generated_at} from the Power BI project files.", ""]
    for block in document.blocks:
        if block.kind == "heading":
            lines.extend([f"{'#' * min(block.level + 1, 6)} {block.text}", ""])
        elif block.kind == "paragraph":
            lines.extend([block.text, ""])
        elif block.kind == "note":
            lines.extend([f"_{block.text}_", ""])
        elif block.kind == "table":
            lines.extend([*_md_table(block.headers, block.rows), ""])
        elif block.kind == "code":
            lines.extend([*_fenced(block.text, block.language), ""])
        elif block.kind == "diagram":
            lines.extend([*_fenced("\n".join(_mermaid(block)), "mermaid"), ""])
    return "\n".join(lines).rstrip() + "\n"


# PDF --------------------------------------------------------------------------------------------

_TOC_STEP = 14.0
_TOC_START = TOP - 110  # below the title block on the first page
_TOC_NEXT = TOP - 10


def render_pdf(document: Document) -> bytes:
    """Lay the blocks out on A4 pages with a linked table of contents and bookmarks."""

    pdf = PdfDocument(title=document.title, footer=f"{document.title} · generated {document.generated_at}",
                      created=_pdf_date(document.generated_at))
    entries = [block for block in document.blocks if block.kind == "heading" and block.level <= 2]
    first_capacity = int((_TOC_START - BOTTOM) / _TOC_STEP)
    other_capacity = int((_TOC_NEXT - BOTTOM) / _TOC_STEP)
    toc_pages = 1 + max(0, math.ceil((len(entries) - first_capacity) / other_capacity))
    for _ in range(toc_pages - 1):
        pdf.new_page()
    pdf.new_page()
    marks = []
    for block in document.blocks:
        if block.kind == "heading":
            mark = pdf.heading(block.text, block.level)
            if block.level <= 2:
                marks.append(mark)
        elif block.kind == "paragraph":
            pdf.paragraph(block.text)
        elif block.kind == "note":
            pdf.paragraph(block.text, font="italic", size=8.5, color=(0.35, 0.38, 0.45))
        elif block.kind == "table":
            pdf.table(block.headers, block.rows, widths=block.widths)
        elif block.kind == "code":
            pdf.code(block.text)
        elif block.kind == "diagram":
            pdf.diagram(block.boxes, block.links)
    _draw_toc(pdf, document, marks, toc_pages)
    return pdf.render()


def _draw_toc(pdf: PdfDocument, document: Document, marks: list, toc_pages: int) -> None:
    y = TOP - 24
    pdf.text(MARGIN, y, document.title, font="bold", size=22, color=(0.1, 0.18, 0.32), page=0)
    y -= 22
    pdf.text(MARGIN, y, f"Generated {document.generated_at} from the last PBIBrain scan. Read-only metadata.", size=9.5, color=(0.35, 0.38, 0.45), page=0)
    y -= 14
    pdf.text(MARGIN, y, "Characters outside Western European fonts show as their nearest letter or '?'; the Markdown export keeps exact text.",
             font="italic", size=8, color=(0.45, 0.45, 0.5), page=0)
    y -= 40
    pdf.text(MARGIN, y, "Contents", font="bold", size=14, color=(0.1, 0.18, 0.32), page=0)
    y = _TOC_START
    page = 0
    for mark in marks:
        if y - _TOC_STEP < BOTTOM:
            page += 1
            y = _TOC_NEXT
        y -= _TOC_STEP
        indent = 0 if mark.level == 1 else 16
        font = "bold" if mark.level == 1 else "regular"
        size = 10 if mark.level == 1 else 9
        number = str(mark.page + 1)
        right = MARGIN + CONTENT_WIDTH
        title = pdf_text(mark.title)
        room = CONTENT_WIDTH - indent - text_width(number, "regular", size) - 20
        while len(title) > 4 and text_width(title, font, size) > room:
            title = title[:-4].rstrip() + "..."
        pdf.text(MARGIN + indent, y, title, font=font, size=size, color=(0.1, 0.1, 0.12), page=page)
        dots_from = MARGIN + indent + text_width(title, font, size) + 6
        dots_to = right - text_width(number, "regular", size) - 6
        if dots_to > dots_from:
            pdf.text(dots_from, y, "." * int((dots_to - dots_from) / text_width(".", "regular", size)), size=size, color=(0.7, 0.7, 0.72), page=page)
        pdf.text(right - text_width(number, "regular", size), y, number, size=size, color=(0.1, 0.1, 0.12), page=page)
        pdf.link((MARGIN, y - 3, right, y + size), mark.page, mark.y, on_page=page)
    if page != toc_pages - 1:
        raise RuntimeError("Table of contents page count changed during layout")


def export_documentation(repository: GraphRepository, *, fmt: str, project_name: str = "PBIBrain",
                         model_ids: Sequence[str] | None = None, report_ids: Sequence[str] | None = None,
                         sections: Sequence[str] | None = None, generated_at: str | None = None, store: Any = None) -> dict[str, Any]:
    """Build and render one export. Returns bytes plus a file name and media type."""

    if fmt not in FORMATS:
        raise DocumentationScopeError(f"Unknown documentation format: {fmt}. Use pdf or markdown.")
    document = build_document(repository, project_name=project_name, model_ids=model_ids, report_ids=report_ids,
                              sections=sections, generated_at=generated_at, store=store)
    slug = re.sub(r"[^A-Za-z0-9]+", "-", project_name).strip("-").lower() or "pbibrain"
    if fmt == "pdf":
        data = render_pdf(document)
        return {"format": "pdf", "filename": f"{slug}-documentation.pdf", "content_type": "application/pdf", "data": data,
                "generated_at": document.generated_at, "scope": document.scope}
    data = render_document_markdown(document).encode("utf-8")
    return {"format": "markdown", "filename": f"{slug}-documentation.md", "content_type": "text/markdown; charset=utf-8", "data": data,
            "generated_at": document.generated_at, "scope": document.scope}
