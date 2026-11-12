"""Report usage facts on graph edges: field roles and the links between pages and visuals.

The normalizer records what each visual and page declares (projection roles,
tooltip/drillthrough targets, interactions, slicer sync groups). This module
turns those properties into edge properties and report link edges. Every edge
here is a FACT: it repeats report metadata or Power BI's own drillthrough rule,
it does not guess a meaning.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any
from collections.abc import Iterable, Iterator, Mapping

from .schema import Node
from backend.text_keys import alnum_key as _norm

_PRIMARY_ORDER = ("projection", "page_binding", "sort", "conditional_formatting")


def visual_usage_properties(visual: Node) -> dict[str, dict[str, Any]]:
    """Return the ``USES`` edge properties of a visual per bound object ID."""

    properties = visual.properties
    by_object: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in properties.get("field_roles", []) or []:
        if not isinstance(item, Mapping) or not item.get("object_id"):
            continue
        record = {key: value for key, value in item.items() if key != "object_id" and value is not None}
        if record not in by_object[str(item["object_id"])]:
            by_object[str(item["object_id"])].append(record)
    result: dict[str, dict[str, Any]] = {}
    for object_id, roles in by_object.items():
        ordered = sorted(roles, key=lambda item: _PRIMARY_ORDER.index(item.get("usage")) if item.get("usage") in _PRIMARY_ORDER else len(_PRIMARY_ORDER))
        primary = ordered[0]
        value: dict[str, Any] = {
            "role": primary.get("role"),
            "roles": ordered,
            "visual_type": properties.get("visual_type"),
        }
        for key in ("aggregation", "projection"):
            if primary.get(key) is not None:
                value[key] = primary[key]
        sort = next((item.get("sort_direction") for item in ordered if item.get("usage") == "sort"), None)
        if sort:
            value["sort_direction"] = sort
        result[object_id] = value
    return result


def _page_lookup(pages: Iterable[Node]) -> dict[tuple[str | None, str], str]:
    lookup: dict[tuple[str | None, str], str] = {}
    for page in pages:
        names = (page.source_id, page.name, page.properties.get("display_name"), page.properties.get("name"))
        for name in names:
            if name is not None:
                lookup.setdefault((page.report_id, _norm(name)), page.id)
    return lookup


def report_link_edges(nodes: Iterable[Node]) -> Iterator[tuple[str, str, str, str, dict[str, Any]]]:
    """Yield ``(type, from, to, evidence, properties)`` for the report link edges.

    - ``TOOLTIP_PAGE``: a visual names a report page as its tooltip.
    - ``DRILLS_THROUGH_TO``: a drillthrough button, or a visual that uses a
      drillthrough field of the page (Power BI offers the drillthrough there).
    - ``SYNCED_WITH``: slicers of one report in the same sync group.
    """

    values = list(nodes)
    pages = [node for node in values if node.type == "PAGE"]
    visuals = [node for node in values if node.type == "VISUAL"]
    lookup = _page_lookup(pages)
    page_types = {page.id: page.properties.get("page_type") for page in pages}

    for visual in visuals:
        props = visual.properties
        tooltip = props.get("tooltip_page_ref")
        target = lookup.get((visual.report_id, _norm(tooltip))) if tooltip else None
        if target and target != props.get("parent_id"):
            yield "TOOLTIP_PAGE", visual.id, target, "visual tooltip page", {"page_ref": tooltip}
        button = props.get("drillthrough_page_ref")
        target = lookup.get((visual.report_id, _norm(button))) if button else None
        if target and target != props.get("parent_id"):
            yield "DRILLS_THROUGH_TO", visual.id, target, "drillthrough button", {"via": "button", "page_ref": button}

    for page in pages:
        if page.properties.get("page_type") != "Drillthrough":
            continue
        drill_fields = [str(item) for item in page.properties.get("binding_field_ids", []) or []]
        if not drill_fields:
            continue
        cross_report = _norm(page.properties.get("binding_scope")) == "crossreport"
        for visual in visuals:
            parent = visual.properties.get("parent_id")
            if parent == page.id or page_types.get(parent) == "Tooltip":
                continue
            if cross_report:
                if visual.model_id is None or visual.model_id != page.model_id:
                    continue
            elif visual.report_id != page.report_id:
                continue
            matched = [item for item in drill_fields if item in (visual.properties.get("field_ids") or [])]
            if matched:
                yield ("DRILLS_THROUGH_TO", visual.id, page.id, "visual uses a drillthrough field",
                       {"via": "field", "fields": drill_fields, "matched_field_ids": matched,
                        "scope": "cross_report" if cross_report else "report"})

    groups: dict[tuple[str | None, str], list[Node]] = defaultdict(list)
    for visual in visuals:
        sync = visual.properties.get("sync_group")
        if isinstance(sync, Mapping) and sync.get("group_name"):
            groups[(visual.report_id, str(sync["group_name"]))].append(visual)
    for (_, group_name), members in sorted(groups.items(), key=lambda item: (str(item[0][0]), item[0][1])):
        members = sorted(members, key=lambda item: item.id)
        for index, left in enumerate(members):
            for right in members[index + 1:]:
                sync = left.properties["sync_group"]
                yield ("SYNCED_WITH", left.id, right.id, "slicer sync group",
                       {"group_name": group_name, "field_changes": sync.get("field_changes"),
                        "filter_changes": sync.get("filter_changes"), "symmetric": True})


__all__ = ["report_link_edges", "visual_usage_properties"]
