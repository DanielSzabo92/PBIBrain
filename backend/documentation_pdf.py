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
    _json,
    _source_path,
    _unresolved,
    snapshot_content_identity,
)
from backend.graph.repository import GraphRepository
from backend.graph.schema import Edge, Node
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
_SEMANTIC = {"BUSINESS_CONCEPT", "ROLE", "GRAIN", "KPI", "METRIC_FAMILY", "SEMANTIC_LABEL"}


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


def _marker(node: Node) -> str:
    """FACT for extracted metadata; anything not factual is shown with its status."""

    return "FACT" if node.status in ("factual", "fact", "", None) else f"INFERRED ({node.status})"


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
        add(Block("paragraph", "This document is a read-only view of the metadata PBIBrain recorded at the last scan. "
                  "It is not a check of runtime data or business correctness. Descriptions and expressions are reproduced "
                  "from the source files as evidence."))
        add(Block("table", headers=("Field", "Value"), widths=(1, 3), rows=[
            ("Project", project_name),
            ("Generated", stamp),
            ("Last scan", _last_scan(repository) or "Unknown"),
            ("Content identity (whole project)", snapshot_content_identity(repository)),
            ("Graph validation", getattr(repository, "validation_state", None) or "not_run"),
            ("Models in this document", f"{len(models)} of {len(models_all)}"),
            ("Reports in this document", f"{len(reports)} of {len(reports_all)}"),
            ("Sections", ", ".join(SECTIONS[item] for item in chosen_sections)),
        ]))
        add(Block("heading", "How to read the markers", 2))
        add(Block("table", headers=("Marker", "Meaning"), widths=(1, 4), rows=[
            ("FACT", "Read from the model or report files: names, expressions, bindings, relationships."),
            ("INFERRED", "An interpretation PBIBrain suggested, such as a business meaning. Not verified unless a reviewer approved it."),
            ("OBSERVED", "Recorded usage, such as two fields used together in a visual."),
            ("Not checked", "PBIBrain could not read the object (for example M code it does not understand). Its links may be incomplete."),
        ]))
        rows = []
        for model in models:
            counts = Counter(node.type for node in all_nodes if node.model_id == model.id and not node.report_id)
            rows.append(("Model", model.name or model.id, counts["TABLE"], counts["MEASURE"], counts["RELATIONSHIP"],
                         _props(model).get("check_status") or "read", _source_path(model) or ""))
        for report in reports:
            counts = Counter(node.type for node in all_nodes if node.report_id == report.id)
            bound = nodes.get(report.model_id or "")
            rows.append(("Report", report.name or report.id, counts["PAGE"], counts["VISUAL"],
                         f"model: {bound.name if bound else report.model_id or 'not resolved'}",
                         _props(report).get("check_status") or "read", _source_path(report) or ""))
        add(Block("heading", "Contents of this export", 2))
        add(Block("table", headers=("Kind", "Name", "Tables / pages", "Measures / visuals", "Relationships / model", "Read", "Source path"),
                  widths=(0.8, 2, 0.9, 1, 1.5, 0.8, 2.4), rows=rows))

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
        add(Block("note", f"ID {model.id} · {_count(len(tables), 'table')} · {_count(len(measures), 'measure')} · {_count(len(relationships), 'relationship')}"))
        if "models" in chosen_sections:
            add(Block("heading", "Model diagram", 2))
            if tables:
                add(_model_diagram(tables, relationships, nodes, children))
                add(Block("note", "Boxes are tables; lines are relationships labelled with cardinality. Dashed lines are inactive relationships."))
            else:
                add(Block("paragraph", "No tables recorded."))
            add(Block("heading", "Relationships", 2))
            if relationships:
                add(Block("table", headers=("From", "To", "Cardinality", "Cross-filter", "Active", "Evidence"),
                          widths=(2.2, 2.2, 0.9, 1, 0.6, 0.7), rows=[
                    (qualified(_props(rel).get("from_column_id")) if _props(rel).get("from_column_id") else f"{_json(_props(rel).get('from_ref'))} (unresolved)",
                     qualified(_props(rel).get("to_column_id")) if _props(rel).get("to_column_id") else f"{_json(_props(rel).get('to_ref'))} (unresolved)",
                     _cardinality(_props(rel).get("cardinality")) or "Not recorded",
                     _props(rel).get("cross_filter_direction") or "Not recorded",
                     _flag(_props(rel).get("active")) or "Not recorded", _marker(rel))
                    for rel in relationships]))
            else:
                add(Block("paragraph", "No relationships recorded."))
            add(Block("heading", "Tables", 2))
            if tables:
                add(Block("table", headers=("Table", "Columns", "Measures", "Hidden", "Storage mode", "Description", "Evidence"),
                          widths=(1.6, 0.7, 0.7, 0.6, 0.9, 2.6, 0.7), rows=[
                    (table.name, sum(1 for child in children[table.id] if child.type == "COLUMN"),
                     sum(1 for child in children[table.id] if child.type == "MEASURE"),
                     _flag(_props(table).get("hidden")), _props(table).get("storage_mode") or _props(table).get("mode") or "",
                     table.description or "", _marker(table)) for table in tables]))
            meanings = _meanings(all_edges, nodes, scoped, model.id, store)
            if meanings:
                add(Block("heading", "Inferred meanings", 2))
                add(Block("paragraph", "Business meanings PBIBrain suggested for objects in this model. They are interpretations, not facts."))
                add(Block("table", headers=("Object", "Meaning", "Marker", "Review status", "Confidence"),
                          widths=(2, 2, 0.9, 1, 0.8), rows=[(qualified(item["from"]), item["meaning"], item["marker"], item["status"], item["confidence"])
                                                            for item in meanings]))
        if "measures" in chosen_sections:
            add(Block("heading", "Measure catalogue", 2))
            if not measures:
                add(Block("paragraph", "No measures recorded."))
            for measure in measures:
                add(Block("heading", qualified(measure.id), 3))
                details = [f"Evidence: {_marker(measure)}"]
                if _props(measure).get("format_string"):
                    details.append(f"Format: {_props(measure)['format_string']}")
                if _props(measure).get("display_folder"):
                    details.append(f"Folder: {_props(measure)['display_folder']}")
                if str(_props(measure).get("hidden", "")).casefold() == "true":
                    details.append("Hidden")
                add(Block("note", " · ".join(details)))
                add(Block("paragraph", f"Description: {measure.description}" if measure.description else "Description: none recorded in the source."))
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
            add(Block("note", f"ID {report.id} · model: {bound.name if bound else (report.model_id or 'not resolved')} · {_count(len(pages), 'page')}"))
            if not pages:
                add(Block("paragraph", "No pages recorded."))
            for page in pages:
                visuals = sorted((child for child in children[page.id] if child.type == "VISUAL"),
                                 key=lambda n: (_num(_props(n).get("y")), _num(_props(n).get("x")), (n.name or "").casefold(), n.id))
                filters = [child for child in children[page.id] if child.type in _REPORT_FILTERS]
                add(Block("heading", f"Page: {_props(page).get('display_name') or page.name or page.id}", 2))
                add(Block("note", f"{_count(len(visuals), 'visual')} · {_count(len(filters), 'page filter')}"))
                if visuals:
                    add(Block("table", headers=("Visual", "Type", "Fields used", "Unresolved fields", "Evidence"),
                              widths=(1.5, 1, 3.2, 1.3, 0.6), rows=[
                        (_props(visual).get("title") or visual.name or visual.id, _props(visual).get("visual_type") or "",
                         "; ".join(qualified(item) for item in _list(_props(visual).get("field_ids"))) or "None",
                         "; ".join(_json(item) if not isinstance(item, str) else item for item in _list(_props(visual).get("unresolved_field_refs"))) or "",
                         _marker(visual)) for visual in visuals]))
                if filters:
                    add(Block("table", headers=("Filter", "Kind", "Target", "Evidence"), widths=(1.6, 1, 2.6, 0.6), rows=[
                        (item.name or item.id, item.type.replace("_", " ").title(),
                         qualified(_props(item).get("target_id")) if _props(item).get("target_id") else _json(_props(item).get("unresolved_target") or _props(item).get("target_ref")) or "",
                         _marker(item)) for item in sorted(filters, key=_sort_key)]))
            report_filters = sorted((child for child in children[report.id] if child.type in _REPORT_FILTERS), key=_sort_key)
            if report_filters:
                add(Block("heading", "Report-level filters", 2))
                add(Block("table", headers=("Filter", "Target", "Evidence"), widths=(1.6, 3, 0.6), rows=[
                    (item.name or item.id, qualified(_props(item).get("target_id")) if _props(item).get("target_id") else _json(_props(item).get("target_ref")) or "",
                     _marker(item)) for item in report_filters]))

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
        add(Block("note", "Green: data sources. Blue: models. Orange: reports. Grey boxes are not checked."))
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
            add(Block("table", headers=("Query", "Model", "Kind", "Mode", "Reads", "Read status"), widths=(1.8, 1.1, 0.9, 0.7, 2, 1), rows=[
                (_query_label(query, nodes), (nodes.get(query.model_id or "") or query).name,
                 "Partition" if query.type == "PARTITION" else "Shared expression", _props(query).get("mode") or "",
                 "; ".join(sorted(nodes[item].name for item in reads[query.id])) or "",
                 "Not checked" if _props(query).get("check_status") == "not_checked" else (_props(query).get("source_status") or "").replace("_", " "))
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
        counts = Counter((edge.type, edge.evidence_class) for edge in all_edges
                         if edge.from_id in scoped and edge.to_id in scoped and edge.type != "CONTAINS")
        add(Block("heading", "Links recorded in scope", 2))
        add(Block("table", headers=("Link type", "Marker", "Count"), widths=(2, 1, 0.6),
                  rows=[(kind, marker, count) for (kind, marker), count in sorted(counts.items())] or [("None", "", 0)]))

    if "not_checked" in chosen_sections:
        add(Block("heading", "Not checked and unresolved", 1))
        add(Block("paragraph", "Objects PBIBrain could not read, and references it could not tie to an object. Lineage and impact for these may be incomplete."))
        not_checked = sorted((node for node in scoped.values() if _props(node).get("check_status") == "not_checked"),
                             key=lambda n: (n.type, (n.name or "").casefold(), n.id))
        add(Block("heading", "Not checked", 2))
        if not_checked:
            add(Block("table", headers=("Object", "Type", "Reason", "Detail"), widths=(1.8, 1, 1.2, 3), rows=[
                (_query_label(node, nodes) if node.type in {"PARTITION", "SHARED_EXPRESSION"} else node.name or node.id, node.type,
                 str(_props(node).get("not_checked_reason") or "").replace("_", " "), _props(node).get("not_checked_detail") or "")
                for node in not_checked]))
        else:
            add(Block("paragraph", "Nothing in this document is marked not checked."))
        unresolved = [item for item in _unresolved(repository) if item["object_id"] in scoped]
        add(Block("heading", "Unresolved references", 2))
        if unresolved:
            add(Block("table", headers=("Object", "What is unresolved", "Evidence"), widths=(2, 1.4, 2.6), rows=[
                (qualified(item["object_id"]), item["kind"], _json(item["evidence"])) for item in unresolved]))
        else:
            add(Block("paragraph", "No unresolved references in this document."))
        diagnostics = [item for item in _diagnostics(repository) if item["object_id"] in scoped]
        if diagnostics:
            add(Block("heading", "DAX diagnostics", 2))
            add(Block("table", headers=("Object", "Code", "Evidence"), widths=(2, 1.2, 2.8), rows=[
                (qualified(item["object_id"]), item["code"], _json(item["evidence"])) for item in diagnostics]))

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


def _meanings(edges: Iterable[Edge], nodes: Mapping[str, Node], scoped: Mapping[str, Node], model_id: str, store: Any) -> list[dict[str, Any]]:
    out = []
    for edge in edges:
        source = scoped.get(edge.from_id)
        meaning = nodes.get(edge.to_id)
        if source is None or meaning is None or meaning.type not in _SEMANTIC or source.model_id != model_id or source.report_id:
            continue
        values = edge.to_dict()
        if store is not None:
            from backend.api.review import apply_overrides_to_dict
            values = apply_overrides_to_dict(values, store)
        out.append({"from": edge.from_id, "meaning": meaning.name, "marker": values.get("evidence_class") or edge.evidence_class,
                    "status": values.get("status") or edge.status, "confidence": f"{float(values.get('confidence') or 0):.2f}", "id": edge.id})
    return sorted(out, key=lambda item: (item["from"], item["meaning"].casefold(), item["id"]))


def _model_diagram(tables: list[Node], relationships: list[Node], nodes: Mapping[str, Node], children: Mapping[str, list[Node]]) -> Block:
    def table_of(column_id: Any) -> str | None:
        column = nodes.get(str(column_id or ""))
        return str(_props(column).get("table_id")) if column is not None and _props(column).get("table_id") else None

    links = []
    degree: Counter[str] = Counter()
    for rel in relationships:
        source, target = table_of(_props(rel).get("from_column_id")), table_of(_props(rel).get("to_column_id"))
        if source and target:
            degree[source] += 1
            degree[target] += 1
            links.append(DiagramLink(source, target, _cardinality(_props(rel).get("cardinality")),
                                     dashed=str(_props(rel).get("active", "true")).casefold() == "false"))
    ordered = sorted(tables, key=lambda n: (-degree[n.id], (n.name or "").casefold(), n.id))
    columns = max(1, min(5, math.ceil(math.sqrt(len(ordered) * 1.6))))
    w, h, gap_x, gap_y = 130.0, 38.0, 42.0, 46.0
    boxes = []
    for index, table in enumerate(ordered):
        row, column = divmod(index, columns)
        counts = Counter(child.type for child in children.get(table.id, []))
        detail = f"{_count(counts['COLUMN'], 'column')} · {_count(counts['MEASURE'], 'measure')}"
        kind = "muted" if str(_props(table).get("hidden", "")).casefold() == "true" else "fact"
        boxes.append(DiagramBox(table.id, (table.name or table.id, detail), column * (w + gap_x), row * (h + gap_y), w, h, kind))
    return Block("diagram", "Model diagram", boxes=tuple(boxes), links=tuple(sorted(links, key=lambda item: (item.source, item.target, item.label))))


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
            label = {"source": "Data source", "fact": "Model", "report": "Report"}[kind]
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
    lines = [f"# {document.title}", "", f"Generated {document.generated_at}. Read-only metadata from the last scan; "
             "FACT is read from source files, INFERRED is an interpretation, OBSERVED is recorded usage.", ""]
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
