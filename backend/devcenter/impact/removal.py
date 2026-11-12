"""Removal policy preview and repoint candidate finder (technical design section 6.4, 7, 14.1, AC6).

When an object is deleted or selected for removal:
1. Lists all transitive certain dependents.
2. Specifies exact cascade effects:
   - remove_object: for model measures, calculated columns, tables
   - remove_field_from_visual: when visual has other remaining projection fields
   - remove_filter: for filter configurations
   - remove_visual: when visual has 0 remaining projection fields
3. Finds valid repoint candidates of identical kind with data type warning flags.
"""

from __future__ import annotations

from typing import Any
from collections.abc import Mapping, Sequence

from backend.devcenter.compare.extract import CompareObject
from backend.devcenter.plan.fields import field_locations


def _normalize_type(kind: str) -> str:
    k = kind.lower().strip()
    if k in {"measure", "report_measure"}:
        return "measure"
    if k in {"column", "calculated_column"}:
        return "column"
    return k


def get_removal_preview(
    *,
    revision: int,
    object_key: str,
    target_objects: Sequence[CompareObject],
    graph_dependents: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compute cascade effects and repoint candidates for a removed object."""
    # Find the target object
    obj_by_key = {obj.source_key: obj for obj in target_objects}
    obj_by_name = {obj.name.casefold(): obj for obj in target_objects}
    target_obj = obj_by_key.get(object_key)
    if target_obj is None:
        # Try matching by name or qualified name
        clean_key = object_key.split(":")[-1]
        target_obj = obj_by_key.get(clean_key) or obj_by_name.get(clean_key.casefold())

    target_name = target_obj.name if target_obj else object_key.split("/")[-1].split(":")[-1]
    target_kind = target_obj.kind if target_obj else (object_key.split(":")[0] if ":" in object_key else "measure")
    target_table = target_obj.table if target_obj else (object_key.split(":")[1].split("/")[0] if "/" in object_key and ":" in object_key else None)
    target_dtype = (target_obj.props.get("data_type") if target_obj else None)

    # 1. Dependents identification
    # If explicit graph dependents passed, use them; else inspect target_objects references
    dependents: list[dict[str, Any]] = []
    effects: list[dict[str, Any]] = []

    visuals = [obj for obj in target_objects if obj.kind == "visual"]
    model_objs = [obj for obj in target_objects if obj.domain == "model" and obj.source_key != object_key]

    matched_visual_keys: set[str] = set()

    for vis in visuals:
        locs = field_locations(vis)
        # Check if visual references target_obj
        uses_target = False
        remaining_projections = 0

        for loc in locs:
            matches_entity = (target_table is None or loc.entity.casefold() == target_table.casefold())
            matches_prop = loc.property.casefold() == target_name.casefold()
            if matches_entity and matches_prop:
                uses_target = True
            else:
                if loc.projection:
                    remaining_projections += 1

        if uses_target:
            matched_visual_keys.add(vis.source_key)
            dep = {
                "object_id": vis.source_key,
                "name": vis.name,
                "type": "visual",
                "domain": "report",
            }
            dependents.append(dep)
            effect_type = "remove_visual" if remaining_projections == 0 else "remove_field_from_visual"
            effects.append({
                "object_id": vis.source_key,
                "name": vis.name,
                "type": "visual",
                "effect": effect_type,
            })

    # Model dependents: measures/columns that reference target_obj in expression
    for m_obj in model_objs:
        expr = str(m_obj.props.get("expression") or "")
        # Check if expr mentions target_name
        if target_name.casefold() in expr.casefold():
            dependents.append({
                "object_id": m_obj.source_key,
                "name": m_obj.name,
                "type": m_obj.kind,
                "domain": "model",
            })
            effects.append({
                "object_id": m_obj.source_key,
                "name": m_obj.name,
                "type": m_obj.kind,
                "effect": "remove_object",
            })

    # If external graph_dependents provided, merge any additional dependents
    if graph_dependents:
        for gd in graph_dependents:
            oid = gd.get("object_id") or gd.get("id")
            if oid and not any(d["object_id"] == oid for d in dependents):
                dependents.append({
                    "object_id": oid,
                    "name": gd.get("name") or oid,
                    "type": gd.get("type") or gd.get("object_type") or "object",
                    "domain": gd.get("domain", "model"),
                })
                effects.append({
                    "object_id": oid,
                    "name": gd.get("name") or oid,
                    "type": gd.get("type") or gd.get("object_type") or "object",
                    "effect": gd.get("effect", "remove_object"),
                })

    # 2. Repoint candidates
    # Candidates must be of identical object kind (measure -> measure, column -> column)
    target_norm_kind = _normalize_type(target_kind)
    candidates: list[dict[str, Any]] = []

    for obj in target_objects:
        if obj.source_key == object_key or obj.name == target_name:
            continue
        if _normalize_type(obj.kind) == target_norm_kind:
            c_dtype = obj.props.get("data_type")
            type_warning = False
            if target_dtype and c_dtype:
                type_warning = str(target_dtype).casefold() != str(c_dtype).casefold()

            candidates.append({
                "object_id": obj.source_key,
                "name": obj.name,
                "type": obj.kind,
                "data_type": c_dtype,
                "type_warning": type_warning,
            })

    # Deterministic sort
    dependents.sort(key=lambda d: d["object_id"])
    effects.sort(key=lambda e: (e["effect"], e["object_id"]))
    candidates.sort(key=lambda c: (c["type_warning"], c["name"]))

    return {
        "revision": revision,
        "object": object_key,
        "dependents": dependents,
        "cascade": {
            "count": len(effects),
            "effects": effects,
        },
        "repoint_candidates": candidates,
    }
