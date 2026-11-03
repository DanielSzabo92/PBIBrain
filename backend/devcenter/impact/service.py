"""Session impact coordinator and service operations (technical design section 7, 14.1, 14.4).

Orchestrates impact analysis, filtering (UC29), pre-paging facet calculation,
path paging (UC30), removal preview (AC6), wireframe projection (AC7),
and atomic state mutations (UC28).
"""

from __future__ import annotations

import copy
from typing import Any, Mapping, Sequence

from backend.devcenter.compare import service as compare_service
from backend.devcenter.compare.extract import CompareObject, load_objects
from backend.devcenter.errors import DevCenterError
from backend.devcenter.impact.completeness import build_completeness
from backend.devcenter.impact.engine import ImpactEngine
from backend.devcenter.impact.offers import extract_offers
from backend.devcenter.impact.removal import get_removal_preview
from backend.devcenter.impact.wireframe import build_report_wireframe
from backend.devcenter.plan import service as plan_service


def _snapshot(devcenter: Any) -> dict[str, Any]:
    with devcenter._lock:
        return copy.deepcopy(devcenter._require_open().document)


def _get_query_val(query: Mapping[str, Sequence[str]], name: str) -> str | None:
    vals = list(query.get(name) or [])
    return str(vals[-1]) if vals else None


def _load_all_objects(devcenter: Any, document: Mapping[str, Any]) -> dict[str, list[CompareObject]]:
    by_source: dict[str, list[CompareObject]] = {}
    for record in document.get("sources", []):
        sid = record["source_id"]
        try:
            source = devcenter._load(record)
            by_source[sid] = load_objects(source).all()
        except Exception:
            by_source[sid] = []
    return by_source


def _get_engine(
    devcenter: Any,
    document: Mapping[str, Any],
    *,
    plan: Mapping[str, Any] | None = None,
) -> tuple[ImpactEngine, list[CompareObject], dict[str, list[CompareObject]]]:
    if plan is None:
        plan = plan_service.build_plan(devcenter, document)

    model_id, report_id = compare_service.targets(document)
    all_objs = _load_all_objects(devcenter, document)

    target_objs = []
    if model_id and model_id in all_objs:
        target_objs.extend([o for o in all_objs[model_id] if o.domain == "model"])
    if report_id and report_id in all_objs:
        target_objs.extend([o for o in all_objs[report_id] if o.domain == "report"])

    donor_objs = {sid: objs for sid, objs in all_objs.items() if sid not in {model_id, report_id}}

    engine = ImpactEngine(
        target_model_id=model_id,
        target_report_id=report_id,
        target_objects=target_objs,
        donor_objects=donor_objs,
        plan=plan,
        removal_policies=document.get("removal_policies") or {},
        need_mappings=document.get("need_mappings") or {},
        item_actions=document.get("item_actions") or {},
    )
    return engine, target_objs, donor_objs


def get_impact(devcenter: Any, query: Mapping[str, Sequence[str]]) -> dict[str, Any]:
    """``GET impact`` (UC29): paged impact items with pre-paging total and facet breakdown."""
    document = _snapshot(devcenter)
    revision = document["revision"]

    target_param = _get_query_val(query, "target") or "plan"
    single_row = None if target_param == "plan" else target_param

    # Cache check
    cache_key = (revision, target_param)
    cached = getattr(devcenter, "_cached_impact", None)
    if cached and cached.get("key") == cache_key:
        all_items = cached["items"]
        offers = cached["offers"]
        completeness = cached["completeness"]
    else:
        plan = plan_service.build_plan(devcenter, document)
        engine, target_objs, donor_objs = _get_engine(devcenter, document, plan=plan)

        all_items = engine.evaluate_all(single_row_key=single_row)

        # Carry-over offers
        source_names = {s["source_id"]: s.get("display_name", s["source_id"]) for s in document.get("sources", [])}
        added_keys = {
            s.get("row_key", "")
            for s in plan.get("steps", [])
            if s.get("source_id") and s.get("domain") == "model"
        }
        target_keys = {o.source_key for o in target_objs if o.domain == "model"}
        offers = extract_offers(
            donor_sources=donor_objs,
            source_names=source_names,
            added_model_keys=added_keys,
            target_existing_keys=target_keys,
            selected_offers=document.get("selected_offers") or (),
        )

        completeness = build_completeness(
            not_checked_object_types=[],
            unresolved_bindings=[],
            unreadable_reports=[],
            bookmarks=[],
            possible_only_areas=[],
        )

        devcenter._cached_impact = {
            "key": cache_key,
            "items": all_items,
            "offers": offers,
            "completeness": completeness,
        }

    # Apply filters (UC29)
    filtered = list(all_items)

    direction_val = _get_query_val(query, "direction")
    if direction_val:
        filtered = [it for it in filtered if it["direction"] == direction_val]

    blocking_val = _get_query_val(query, "blocking")
    if blocking_val is not None:
        want_blocking = blocking_val.lower() in {"true", "1"}
        filtered = [it for it in filtered if it["blocking"] == want_blocking]

    severity_val = _get_query_val(query, "severity")
    if severity_val:
        filtered = [it for it in filtered if it["severity"] == severity_val]

    certainty_val = _get_query_val(query, "certainty")
    if certainty_val:
        filtered = [it for it in filtered if it["certainty"] == certainty_val]

    source_val = _get_query_val(query, "source")
    if source_val:
        filtered = [it for it in filtered if it["impacted_object"].get("source_id") == source_val]

    type_val = _get_query_val(query, "object_type")
    if type_val:
        filtered = [it for it in filtered if it["impacted_object"].get("object_type") == type_val]

    q_val = _get_query_val(query, "q")
    if q_val:
        q_lower = q_val.lower()
        filtered = [
            it for it in filtered
            if q_lower in it["impacted_object"]["name"].lower()
            or q_lower in it.get("reason_text", "").lower()
        ]

    # Pre-paging total and facets computation (AC12)
    total = len(filtered)
    facets: dict[str, dict[str, int]] = {
        "direction": {"breaks": 0, "needs": 0},
        "blocking": {"true": 0, "false": 0},
        "severity": {},
        "certainty": {"certain": 0, "possible": 0},
        "object_type": {},
    }

    for it in filtered:
        d = it["direction"]
        facets["direction"][d] = facets["direction"].get(d, 0) + 1

        b = "true" if it["blocking"] else "false"
        facets["blocking"][b] = facets["blocking"].get(b, 0) + 1

        s = it["severity"]
        facets["severity"][s] = facets["severity"].get(s, 0) + 1

        c = it["certainty"]
        facets["certainty"][c] = facets["certainty"].get(c, 0) + 1

        ot = it["impacted_object"]["object_type"]
        facets["object_type"][ot] = facets["object_type"].get(ot, 0) + 1

    # Paging
    limit_val = _get_query_val(query, "limit")
    limit = int(limit_val) if limit_val and limit_val.isdigit() else 50

    offset_val = _get_query_val(query, "offset")
    offset = int(offset_val) if offset_val and offset_val.isdigit() else 0

    paged_items = filtered[offset : offset + limit]
    has_more = (offset + limit) < total

    return {
        "revision": revision,
        "target": target_param,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": has_more,
        "facets": facets,
        "items": paged_items,
        "completeness": completeness,
        "offers": offers,
    }


def get_removal(devcenter: Any, query: Mapping[str, Sequence[str]]) -> dict[str, Any]:
    """``GET impact/removal/{object}`` (AC6): cascade effects and repoint candidates."""
    document = _snapshot(devcenter)
    obj_key = _get_query_val(query, "object")
    if not obj_key:
        raise DevCenterError("not_found", "Specify an object to inspect.")

    model_id, _ = compare_service.targets(document)
    all_objs = _load_all_objects(devcenter, document)
    target_objs = all_objs.get(model_id, []) if model_id else []

    return get_removal_preview(
        revision=document["revision"],
        object_key=obj_key,
        target_objects=target_objs,
    )


def get_impact_paths(devcenter: Any, query: Mapping[str, Sequence[str]]) -> dict[str, Any]:
    """``GET impact/{item}/paths`` (UC30): paged graph paths for an impact item."""
    document = _snapshot(devcenter)
    item_id = _get_query_val(query, "item")
    if not item_id:
        raise DevCenterError("not_found", "Specify an item ID.")

    limit_val = _get_query_val(query, "limit")
    limit = int(limit_val) if limit_val and limit_val.isdigit() else 50
    offset_val = _get_query_val(query, "offset")
    offset = int(offset_val) if offset_val and offset_val.isdigit() else 0

    # Retrieve item from impact calculation
    impact_data = get_impact(devcenter, {"target": ["plan"]})
    found_item = next((it for it in impact_data.get("items", []) if it["id"] == item_id), None)
    if not found_item:
        # Check all items in cache
        cached = getattr(devcenter, "_cached_impact", {}).get("items", [])
        found_item = next((it for it in cached if it["id"] == item_id), None)

    if not found_item:
        raise DevCenterError("not_found", f"Impact item {item_id} not found.", {"item_id": item_id})

    # Single path or alternative paths
    all_paths = [found_item.get("path", [])] if found_item.get("path") else []
    total = len(all_paths)
    paged = all_paths[offset : offset + limit]
    has_more = (offset + limit) < total

    return {
        "revision": document["revision"],
        "item_id": item_id,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": has_more,
        "paths": paged,
    }


def get_wireframe(devcenter: Any, query: Mapping[str, Sequence[str]]) -> dict[str, Any]:
    """``GET wireframe/{report}`` (AC7): wireframe geometry with resolved visual status."""
    document = _snapshot(devcenter)
    report_param = _get_query_val(query, "report") or "target"

    _, target_report_id = compare_service.targets(document)
    all_objs = _load_all_objects(devcenter, document)

    report_source_id = target_report_id if report_param in {"target", "plan"} else report_param
    if report_source_id not in all_objs:
        for s in document.get("sources", []):
            if s.get("display_name") == report_param or s.get("source_id") == report_param:
                report_source_id = s["source_id"]
                break
    report_objs = all_objs.get(report_source_id, [])
    if not report_objs and target_report_id:
        report_objs = all_objs.get(target_report_id, [])

    # Fetch impact items to determine visual status
    impact_data = get_impact(devcenter, {"target": ["plan"]})
    impact_items = impact_data.get("items", [])

    return build_report_wireframe(
        revision=document["revision"],
        report_name=report_param,
        report_objects=report_objs,
        impact_items=impact_items,
    )


# JSAPI State Mutations --------------------------------------------------------


def impact_action_apply(devcenter: Any, request: Mapping[str, Any]) -> dict[str, Any]:
    """UC28: atomic bulk execution of impact actions updating session revision in one step."""
    item_ids = list(request.get("item_ids") or [])
    action = request.get("action")
    payload = request.get("payload") or {}

    if not item_ids:
        raise DevCenterError("invalid_payload", "No items specified.", {"reason": "item_ids_required"})

    with devcenter._lock:
        applied: list[str] = []
        failed: list[dict[str, str]] = []

        # Validate against existing impact items
        eng, _, _ = _get_engine(devcenter, devcenter._require_open().document)
        existing_items = {it["id"]: it for it in eng.evaluate_all()}

        def mutate(document: dict[str, Any]) -> tuple[Any, Any]:
            before = {
                "item_actions": copy.deepcopy(document.get("item_actions")),
                "removal_policies": copy.deepcopy(document.get("removal_policies")),
                "need_mappings": copy.deepcopy(document.get("need_mappings")),
            }
            item_actions = document.setdefault("item_actions", {})
            removal_policies = document.setdefault("removal_policies", {})
            need_mappings = document.setdefault("need_mappings", {})

            for iid in item_ids:
                if iid not in existing_items:
                    failed.append({"item_id": iid, "reason": "item_not_found"})
                    continue
                item = existing_items[iid]
                allowed = item.get("allowed_actions", [])
                if allowed and action not in allowed:
                    failed.append({"item_id": iid, "reason": "action_not_allowed"})
                    continue

                if action == "include_in_rewrite":
                    item_actions[iid] = {"action": "include_in_rewrite"}
                    applied.append(iid)
                elif action in {"set_policy_block", "set_policy_cascade", "set_policy_repoint"}:
                    pol = action.replace("set_policy_", "")
                    row_key = payload.get("row_key") or item.get("cause") or iid
                    repoint_t = payload.get("repoint_target")
                    removal_policies[row_key] = {"policy": pol, "repoint_target": repoint_t}
                    applied.append(iid)
                elif action in {"add_from_donor", "map_to_target", "drop_added_object"}:
                    need_mappings[iid] = {
                        "action": action,
                        "target_object": payload.get("target_object"),
                    }
                    applied.append(iid)
                elif action == "remove_field":
                    item_actions[iid] = {"action": "remove_field"}
                    applied.append(iid)
                else:
                    failed.append({"item_id": iid, "reason": "unsupported_action"})

            after = {
                "item_actions": copy.deepcopy(document.get("item_actions")),
                "removal_policies": copy.deepcopy(document.get("removal_policies")),
                "need_mappings": copy.deepcopy(document.get("need_mappings")),
            }
            return before, after

        document = devcenter._change(request, "impact_action_apply", item_ids, mutate)
        devcenter._cached_impact = None
        return {
            "revision": document["revision"],
            "applied": applied,
            "failed": failed,
        }


def removal_policy_set(devcenter: Any, request: Mapping[str, Any]) -> dict[str, Any]:
    """AC6: set removal policy (block, cascade, repoint) for a removed row."""
    row_key = request.get("row_key")
    policy = request.get("policy")
    repoint_target = request.get("repoint_target")

    with devcenter._lock:
        def mutate(document: dict[str, Any]) -> tuple[Any, Any]:
            policies = document.setdefault("removal_policies", {})
            before = copy.deepcopy(policies.get(row_key))
            policies[row_key] = {
                "policy": policy,
                "repoint_target": repoint_target,
            }
            return before, policies[row_key]

        document = devcenter._change(request, "removal_policy_set", row_key, mutate)
        devcenter._cached_impact = None
        return {
            "revision": document["revision"],
            "row_key": row_key,
            "policy": policy,
            "repoint_target": repoint_target,
        }


def need_mapping_set(devcenter: Any, request: Mapping[str, Any]) -> dict[str, Any]:
    """AC4: set need mapping (add_from_donor, map_to_target, drop_added_object)."""
    need_id = request.get("need_id")
    action = request.get("action")
    target_object = request.get("target_object")

    with devcenter._lock:
        def mutate(document: dict[str, Any]) -> tuple[Any, Any]:
            mappings = document.setdefault("need_mappings", {})
            before = copy.deepcopy(mappings.get(need_id))
            mappings[need_id] = {
                "action": action,
                "target_object": target_object,
            }
            return before, mappings[need_id]

        document = devcenter._change(request, "need_mapping_set", need_id, mutate)
        devcenter._cached_impact = None
        return {
            "revision": document["revision"],
            "need_id": need_id,
            "action": action,
            "target_object": target_object,
        }


def offer_select(devcenter: Any, request: Mapping[str, Any]) -> dict[str, Any]:
    """AC8: toggle selection of a donor carry-over offer."""
    offer_id = request.get("offer_id")
    selected = bool(request.get("selected"))

    with devcenter._lock:
        def mutate(document: dict[str, Any]) -> tuple[Any, Any]:
            offers = document.setdefault("selected_offers", [])
            before = list(offers)
            if selected and offer_id not in offers:
                offers.append(offer_id)
            elif not selected and offer_id in offers:
                offers.remove(offer_id)
            return before, list(offers)

        document = devcenter._change(request, "offer_select", offer_id, mutate)
        devcenter._cached_impact = None
        return {
            "revision": document["revision"],
            "offer_id": offer_id,
            "selected": selected,
        }
