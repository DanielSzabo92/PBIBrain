"""Change Plan service of the open merge session (technical design sections 6 and 14).

Derive a deterministic, sorted plan of plan steps and operations from session state.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from backend.devcenter.compare import service as compare_service
from backend.devcenter.errors import DevCenterError
from backend.devcenter.naming import service as naming_service
from backend.devcenter.naming.rules import is_active
from backend.devcenter.plan.compiler import PlanInput, compile_plan, plan_hash
from backend.devcenter.session import proposals


def _detect_compatibility_level(devcenter: Any, document: Mapping[str, Any], target_model: str | None) -> int | None:
    if not target_model:
        return None
    try:
        record = devcenter._source(document, target_model)
        source = devcenter._load(record)
        if source.model_dir is not None:
            tmdl_db = source.model_dir / "definition" / "database.tmdl"
            if tmdl_db.is_file():
                for line in tmdl_db.read_text(encoding="utf-8").splitlines():
                    match = re.match(r"^\s*compatibilityLevel\s*:\s*(\d+)", line)
                    if match:
                        return int(match.group(1))
            bim = source.model_dir / "model.bim"
            if bim.is_file():
                data = json.loads(bim.read_text(encoding="utf-8"))
                level = data.get("compatibilityLevel") or (data.get("model") or {}).get("compatibilityLevel")
                if level is not None:
                    return int(level)
    except Exception:
        pass
    return None


def _load_naming_rules(devcenter: Any, document: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    try:
        target = naming_service._load_target(devcenter, document, required=False)
        if target is not None:
            return [rule for rule in target.stored if is_active(rule)]
    except Exception:
        pass
    return ()


def _snapshot(devcenter: Any) -> dict[str, Any]:
    with devcenter._lock:
        return copy.deepcopy(devcenter._require_open().document)


def build_plan(devcenter: Any, document: Mapping[str, Any], *, include_proposals: bool = False) -> dict[str, Any]:
    """Derive the Change Plan from the session document.

    Assembles PlanInput using S3 compare results and S4 naming rules,
    calls compile_plan, attaches plan_hash, and caches the result.
    """
    model, report = compare_service.targets(document)
    compare_result = compare_service.compute(devcenter, document)
    sources = {s["source_id"]: s.get("display_name", s["source_id"]) for s in document.get("sources", [])}
    compatibility_level = _detect_compatibility_level(devcenter, document, model)
    rules = _load_naming_rules(devcenter, document)

    plan_input = PlanInput(
        session_id=document["session_id"],
        result=compare_result,
        target_model=model,
        target_report=report,
        sources=sources,
        merge_choices=document.get("merge_choices") or {},
        removal_policies=document.get("removal_policies") or {},
        need_mappings=document.get("need_mappings") or {},
        item_actions=document.get("item_actions") or {},
        compatibility_level=compatibility_level,
        naming_rules=rules,
    )

    plan = compile_plan(plan_input)
    plan["plan_hash"] = plan_hash(plan)

    if not include_proposals:
        devcenter._cached_plan = plan
        devcenter._plan_state = "ready"

    return plan


def _one(query: Mapping[str, Sequence[str]], name: str) -> str | None:
    values = list(query.get(name) or [])
    return str(values[-1]) if values else None


def get_plan(devcenter: Any, query: Mapping[str, Sequence[str]]) -> dict[str, Any]:
    """``GET plan``: plan status, summary, steps, operations, blocking items, warnings, plan_hash.

    ``include_proposals`` (S10, UC11): ``true`` adds the open agent proposals, ``ready``
    adds only the proposals that ``proposal_accept_all`` accepts. The default is the
    accepted state only.
    """
    mode = proposals.include_mode(_one(query, "include_proposals"))
    document = _snapshot(devcenter)
    plan = build_plan(devcenter, proposals.with_proposals(document, mode), include_proposals=mode is not None)
    return {
        "revision": document["revision"],
        **plan,
    }


def validate_plan(devcenter: Any, payload: Mapping[str, Any]) -> dict[str, Any]:
    """``POST plan-validate``: validate the current plan in quick or full mode."""
    mode = payload.get("mode", "quick")
    if mode not in {"quick", "full"}:
        raise DevCenterError("invalid_payload", "The mode must be quick or full.", {"reason": "invalid_mode", "field": "mode"})

    include = proposals.include_mode(payload.get("include_proposals"))
    document = _snapshot(devcenter)
    plan = build_plan(devcenter, proposals.with_proposals(document, include), include_proposals=include is not None)

    return {
        "revision": document["revision"],
        "mode": mode,
        "status": plan["status"],
        "blocking": plan["blocking"],
        "warnings": plan["warnings"],
        "plan_hash": plan["plan_hash"],
    }
