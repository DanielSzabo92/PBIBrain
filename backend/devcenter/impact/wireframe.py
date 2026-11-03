"""Wireframe model generator with strict status priority resolution (technical design section 7, 14.1, AC7).

Generates layout geometry and visual statuses for target or donor reports.
Visual statuses are resolved in strict priority order:
    removed > breaks > changes > new > not_checked > unchanged
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from backend.devcenter.compare.extract import CompareObject

STATUS_PRIORITY = [
    "removed",
    "breaks",
    "changes",
    "new",
    "not_checked",
    "unchanged",
]


def resolve_visual_status(statuses: Sequence[str]) -> str:
    """Resolve the final status for a visual according to AC7 priority order."""
    if not statuses:
        return "unchanged"
    status_set = set(statuses)
    for candidate in STATUS_PRIORITY:
        if candidate in status_set:
            return candidate
    return "unchanged"


def build_report_wireframe(
    *,
    revision: int,
    report_name: str,
    report_objects: Sequence[CompareObject],
    impact_items: Sequence[Mapping[str, Any]] = (),
    removed_visual_keys: Sequence[str] = (),
    new_visual_keys: Sequence[str] = (),
    changed_visual_keys: Sequence[str] = (),
) -> dict[str, Any]:
    """Emit wireframe structure with page geometry, visual boxes, and priority status."""
    pages = [obj for obj in report_objects if obj.kind == "page"]
    visuals = [obj for obj in report_objects if obj.kind == "visual"]

    removed_set = set(removed_visual_keys)
    new_set = set(new_visual_keys)
    changed_set = set(changed_visual_keys)

    # Map visual keys to impacting item IDs and their severities/directions
    vis_causes: dict[str, list[str]] = {}
    vis_statuses: dict[str, list[str]] = {}

    for item in impact_items:
        impacted = item.get("impacted_object", {})
        obj_id = impacted.get("object_id", "")
        sev = item.get("severity", "")
        direction = item.get("direction", "")
        iid = item.get("id", "")

        # Target can be visual key or matching visual name
        for v in visuals:
            if v.source_key == obj_id or v.name == obj_id or f"visual:{v.table}/{v.name}" == obj_id:
                vis_causes.setdefault(v.source_key, []).append(iid)
                if sev in {"breaks", "high"} or direction == "breaks":
                    vis_statuses.setdefault(v.source_key, []).append("breaks")
                elif sev in {"changes_value", "low", "modified"} or direction == "changes":
                    vis_statuses.setdefault(v.source_key, []).append("changes")
                elif sev == "needs_review":
                    vis_statuses.setdefault(v.source_key, []).append("not_checked")

    wireframe_pages: list[dict[str, Any]] = []

    for page in pages:
        page_id = page.extra.get("page_id") or page.source_key.split(":")[-1]
        page_size = page.props.get("page_size", {})
        width = int(page_size.get("width") or 1280)
        height = int(page_size.get("height") or 720)
        hidden = bool(page.props.get("hidden", False))

        page_visuals: list[dict[str, Any]] = []
        # Filter visuals belonging to this page (CompareObject.table holds page_id/folder)
        matching_visuals = [v for v in visuals if v.table == page_id or v.table == page.name]

        for v in matching_visuals:
            pos = v.props.get("position", {})
            vx = int(pos.get("x", 0))
            vy = int(pos.get("y", 0))
            vz = int(pos.get("z", 0))
            vw = int(pos.get("width", 300))
            vh = int(pos.get("height", 200))
            vgroup = v.props.get("parentGroupName")
            vhidden = bool(v.props.get("hidden", False))
            vtype = str(v.props.get("visual_type") or "card")
            title = str(v.props.get("title") or v.name)

            # Candidate statuses
            candidates: list[str] = list(vis_statuses.get(v.source_key, []))
            if v.source_key in removed_set or v.name in removed_set:
                candidates.append("removed")
            if v.source_key in new_set or v.name in new_set:
                candidates.append("new")
            if v.source_key in changed_set or v.name in changed_set:
                candidates.append("changes")

            if not candidates:
                candidates.append("unchanged")

            final_status = resolve_visual_status(candidates)
            cause_ids = sorted(set(vis_causes.get(v.source_key, [])))

            page_visuals.append({
                "id": v.name,
                "type": vtype,
                "title": title,
                "x": vx,
                "y": vy,
                "z": vz,
                "width": vw,
                "height": vh,
                "group": vgroup,
                "hidden": vhidden,
                "status": final_status,
                "cause_item_ids": cause_ids,
            })

        wireframe_pages.append({
            "id": page_id,
            "name": page.name,
            "width": width,
            "height": height,
            "hidden": hidden,
            "visuals": page_visuals,
        })

    return {
        "revision": revision,
        "report": report_name,
        "pages": wireframe_pages,
    }
