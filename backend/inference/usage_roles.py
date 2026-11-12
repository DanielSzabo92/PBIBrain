"""Derived usage roles: how an object is used in reports and what it is for there.

The facts come from ``USES``/``FILTERS``/report link edges. The summary on top
of them ("used as KPI value on 3 cards", "only as tooltip") is a reading of
those facts, so the profile is marked ``INFERRED``. It is computed on request
and never stored as edges, because stored INFERRED edges would enter the
semantic review queue.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any
from collections.abc import Iterable, Mapping

from backend.graph.schema import Edge, Node
from backend.text_keys import alnum_key as _norm

KPI_VISUAL_TYPES = frozenset({"card", "cardvisual", "multirowcard", "kpi", "gauge"})
_FIELD_TYPES = frozenset({"COLUMN", "MEASURE", "HIERARCHY", "REPORT_MEASURE", "FIELD_PARAMETER", "CALCULATION_ITEM", "LEVEL"})
_LINK_TYPES = frozenset({"DRILLS_THROUGH_TO", "TOOLTIP_PAGE", "INTERACTS_WITH", "SYNCED_WITH", "FORMATS_BY"})
_ROLE_LABELS = {
    "value": "value", "category": "category or axis", "legend": "legend", "tooltip": "tooltip", "rows": "matrix rows",
    "columns": "matrix columns", "small_multiples": "small multiples", "slicer_field": "slicer field", "sort": "sort field",
    "conditional_formatting": "conditional formatting", "drillthrough_field": "drillthrough field",
    "tooltip_page_field": "tooltip page field", "target": "target value", "details": "details", "size": "size",
}
MAX_USAGES = 50


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def _roles(edge: Edge) -> list[str]:
    roles = [str(item.get("role")) for item in edge.properties.get("roles", []) or [] if isinstance(item, Mapping) and item.get("role")]
    if not roles and edge.properties.get("role"):
        roles = [str(edge.properties["role"])]
    return roles or ["field"]


def _page_of(node: Node, nodes: Mapping[str, Node]) -> Node | None:
    current, seen = node, set()
    while current is not None and current.type != "PAGE" and current.id not in seen:
        seen.add(current.id)
        parent = current.properties.get("parent_id")
        current = nodes.get(str(parent)) if parent else None
    return current if current is not None and current.type == "PAGE" else None


def _field_profile(target: Node, nodes: Mapping[str, Node], edges: list[Edge]) -> dict[str, Any]:
    object_ids = {target.id}
    if target.type == "TABLE":
        object_ids |= {edge.to_id for edge in edges if edge.type == "CONTAINS" and edge.from_id == target.id}
    uses = [edge for edge in edges if edge.type == "USES" and edge.to_id in object_ids and edge.from_id in nodes]
    filters = [edge for edge in edges if edge.type == "FILTERS" and edge.to_id in object_ids and edge.from_id in nodes]
    visual_uses = [edge for edge in uses if nodes[edge.from_id].type == "VISUAL"]
    page_uses = [edge for edge in uses if nodes[edge.from_id].type == "PAGE"]

    usages: list[dict[str, Any]] = []
    role_counts: Counter[str] = Counter()
    role_visual_types: dict[str, Counter[str]] = defaultdict(Counter)
    visual_types: Counter[str] = Counter()
    visuals_by_role: dict[str, set[str]] = defaultdict(set)
    pages: dict[str, Node] = {}
    reports: set[str] = set()
    kpi_visuals: set[str] = set()
    for edge in sorted(visual_uses, key=lambda item: item.from_id):
        visual = nodes[edge.from_id]
        page = _page_of(visual, nodes)
        visual_type = str(visual.properties.get("visual_type") or edge.properties.get("visual_type") or "unknown")
        roles = _roles(edge)
        visual_types[visual_type] += 1
        for role in dict.fromkeys(roles):
            role_counts[role] += 1
            role_visual_types[role][visual_type] += 1
            visuals_by_role[role].add(visual.id)
        if _norm(visual_type) in KPI_VISUAL_TYPES and {"value", "target"} & set(roles):
            kpi_visuals.add(visual.id)
        if page is not None:
            pages[page.id] = page
        if visual.report_id:
            reports.add(str(visual.report_id))
        usages.append({
            "visual_id": visual.id, "visual_name": visual.name, "visual_type": visual_type,
            "page_id": page.id if page else None, "page_name": page.name if page else None,
            "page_hidden": bool(page and page.properties.get("hidden")),
            "page_type": page.properties.get("page_type") if page else None,
            "report_id": visual.report_id, "object_id": edge.to_id, "roles": roles,
            **({"aggregation": edge.properties["aggregation"]} if edge.properties.get("aggregation") else {}),
        })
    drillthrough_pages = sorted({edge.from_id for edge in page_uses if nodes[edge.from_id].properties.get("page_type") == "Drillthrough"})
    tooltip_pages = sorted({edge.from_id for edge in page_uses if nodes[edge.from_id].properties.get("page_type") == "Tooltip"})
    for edge in page_uses:
        if nodes[edge.from_id].report_id:
            reports.add(str(nodes[edge.from_id].report_id))

    facts: list[dict[str, Any]] = []

    def fact(code: str, text: str, ids: Iterable[str] = ()) -> None:
        ids = sorted(set(ids))
        facts.append({"code": code, "text": text, **({"count": len(ids), "object_ids": ids[:MAX_USAGES]} if ids else {})})

    if kpi_visuals:
        fact("KPI_VALUE", f"Used as KPI value on {_plural(len(kpi_visuals), 'card or KPI visual')}", kpi_visuals)
    if visuals_by_role.get("slicer_field"):
        fact("SLICER_DIMENSION", f"Slicer dimension on {_plural(len(visuals_by_role['slicer_field']), 'slicer')}", visuals_by_role["slicer_field"])
    projection_roles = set(role_counts) - {"sort", "conditional_formatting"}
    if visual_uses and projection_roles == {"tooltip"}:
        fact("ONLY_TOOLTIP", "Used only as a tooltip field", visuals_by_role["tooltip"])
    elif visual_uses and pages and all(page.properties.get("page_type") == "Tooltip" for page in pages.values()):
        fact("ONLY_TOOLTIP_PAGES", "Used only on tooltip pages", pages)
    if visual_uses and not projection_roles:
        fact("FORMATTING_OR_SORT_ONLY", "Used only for conditional formatting or sorting", {edge.from_id for edge in visual_uses})
    if visual_uses and pages and all(page.properties.get("hidden") for page in pages.values()):
        fact("ONLY_HIDDEN_PAGES", "Used only on hidden pages", pages)
    if drillthrough_pages:
        fact("DRILLTHROUGH_FIELD", f"Drillthrough field of {_plural(len(drillthrough_pages), 'page')}", drillthrough_pages)
    if tooltip_pages:
        fact("TOOLTIP_PAGE_FIELD", f"Field of {_plural(len(tooltip_pages), 'tooltip page')}", tooltip_pages)
    for role, count in sorted(role_counts.items(), key=lambda item: (-item[1], item[0])):
        if role not in {"slicer_field"}:
            fact("ROLE", f"Used as {_ROLE_LABELS.get(role, role.replace('_', ' '))} on {_plural(count, 'visual')}", visuals_by_role[role])
    if not uses and filters:
        fact("FILTER_ONLY", f"Used only in {_plural(len(filters), 'filter')}", {edge.from_id for edge in filters})
    if not uses and not filters:
        model_reports = [node for node in nodes.values() if node.type == "REPORT" and target.model_id and node.model_id == target.model_id]
        if model_reports:
            fact("UNUSED_IN_REPORTS", f"Not used in any of the {_plural(len(model_reports), 'scanned report')} of its model")
        else:
            fact("NO_REPORTS_SCANNED", "No report of its model was scanned, so its report usage is unknown")

    usages.sort(key=lambda item: (str(item["report_id"]), str(item["page_name"]), item["visual_name"], item["visual_id"]))
    return {
        "object_id": target.id,
        "object_type": target.type,
        "evidence_class": "INFERRED",
        "basis": "Field usage and visual filters across scanned reports.",
        "visual_count": len({edge.from_id for edge in visual_uses}),
        "page_count": len(pages),
        "report_count": len(reports),
        "filter_count": len(filters),
        "roles": [{"role": role, "count": count, "visual_types": dict(sorted(role_visual_types[role].items()))}
                  for role, count in sorted(role_counts.items(), key=lambda item: (-item[1], item[0]))],
        "visual_types": dict(sorted(visual_types.items())),
        "drillthrough_page_ids": drillthrough_pages,
        "tooltip_page_ids": tooltip_pages,
        "facts": facts,
        "usages": usages[:MAX_USAGES],
        "usages_truncated": len(usages) > MAX_USAGES,
    }


def _link_records(target: Node, nodes: Mapping[str, Node], edges: list[Edge]) -> list[dict[str, Any]]:
    records = []
    for edge in edges:
        if edge.type not in _LINK_TYPES or target.id not in {edge.from_id, edge.to_id}:
            continue
        other = nodes.get(edge.to_id if edge.from_id == target.id else edge.from_id)
        records.append({
            "type": edge.type, "direction": "out" if edge.from_id == target.id else "in",
            "object_id": other.id if other else None, "object_name": other.name if other else None,
            "object_type": other.type if other else None,
            **{key: value for key, value in edge.properties.items() if key in {"interaction", "via", "group_name", "matched_field_ids", "scope"}},
        })
    return sorted(records, key=lambda item: (item["type"], item["direction"], str(item["object_name"]), str(item["object_id"])))


def _visual_profile(target: Node, nodes: Mapping[str, Node], edges: list[Edge]) -> dict[str, Any]:
    fields = []
    for edge in edges:
        if edge.type == "USES" and edge.from_id == target.id and edge.to_id in nodes:
            fields.append({"object_id": edge.to_id, "name": nodes[edge.to_id].name, "object_type": nodes[edge.to_id].type,
                           "roles": _roles(edge), **({"aggregation": edge.properties["aggregation"]} if edge.properties.get("aggregation") else {})})
    page = _page_of(target, nodes)
    fields.sort(key=lambda item: (item["roles"][0], item["name"], item["object_id"]))
    facts = []
    if page is not None and page.properties.get("hidden"):
        facts.append({"code": "ON_HIDDEN_PAGE", "text": "The visual is on a hidden page"})
    if page is not None and page.properties.get("page_type"):
        facts.append({"code": "ON_SPECIAL_PAGE", "text": f"The visual is on a {page.properties['page_type'].casefold()} page"})
    return {
        "object_id": target.id, "object_type": target.type, "evidence_class": "INFERRED",
        "basis": "Field wells, formatting and report links of the visual.",
        "visual_type": target.properties.get("visual_type"),
        "page_id": page.id if page else None,
        "fields": fields, "links": _link_records(target, nodes, edges), "facts": facts,
    }


def _page_profile(target: Node, nodes: Mapping[str, Node], edges: list[Edge]) -> dict[str, Any]:
    links = []
    for edge in edges:
        if edge.type in {"DRILLS_THROUGH_TO", "TOOLTIP_PAGE"} and edge.to_id == target.id and edge.from_id in nodes:
            links.append({"type": edge.type, "visual_id": edge.from_id, "visual_name": nodes[edge.from_id].name,
                          "page_id": nodes[edge.from_id].properties.get("parent_id"),
                          **({"via": edge.properties["via"]} if edge.properties.get("via") else {})})
    links.sort(key=lambda item: (item["type"], item["visual_name"], item["visual_id"]))
    fields = [{"object_id": edge.to_id, "name": nodes[edge.to_id].name, "roles": _roles(edge)}
              for edge in edges if edge.type == "USES" and edge.from_id == target.id and edge.to_id in nodes]
    page_type = target.properties.get("page_type")
    facts = []
    if page_type == "Drillthrough":
        facts.append({"code": "DRILLTHROUGH_PAGE", "text": f"Drillthrough page, reached from {_plural(len({item['visual_id'] for item in links if item['type'] == 'DRILLS_THROUGH_TO'}), 'visual')}"})
    if page_type == "Tooltip":
        facts.append({"code": "TOOLTIP_PAGE", "text": f"Tooltip page, named by {_plural(len({item['visual_id'] for item in links if item['type'] == 'TOOLTIP_PAGE'}), 'visual')}"})
    if target.properties.get("hidden"):
        facts.append({"code": "HIDDEN_PAGE", "text": "Hidden in view mode"})
    return {
        "object_id": target.id, "object_type": target.type, "evidence_class": "INFERRED",
        "basis": "Page binding, visibility and the report links that reach the page.",
        "page_type": page_type, "hidden": bool(target.properties.get("hidden")),
        "binding_fields": sorted(fields, key=lambda item: (item["name"], item["object_id"])),
        "incoming_links": links[:MAX_USAGES], "facts": facts,
    }


def usage_profile(
    nodes: Iterable[Node] | Mapping[str, Node], edges: Iterable[Edge], object_id: str
) -> dict[str, Any] | None:
    """Return the usage profile of one object, or ``None`` for a type without report usage."""

    by_id = dict(nodes) if isinstance(nodes, Mapping) else {node.id: node for node in nodes}
    target = by_id.get(str(object_id))
    if target is None:
        return None
    edge_list = list(edges)
    if target.type in _FIELD_TYPES or target.type == "TABLE":
        return _field_profile(target, by_id, edge_list)
    if target.type == "VISUAL":
        return _visual_profile(target, by_id, edge_list)
    if target.type == "PAGE":
        return _page_profile(target, by_id, edge_list)
    return None


__all__ = ["KPI_VISUAL_TYPES", "usage_profile"]
