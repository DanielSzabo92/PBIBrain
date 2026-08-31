"""Read-only reconciliation of separate human override records."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any, Iterable, Mapping


def _record_target(record: Mapping[str, Any]) -> str:
    return str(record.get("target") or record.get("target_id") or "").strip()


def _record_id(record: Mapping[str, Any]) -> str:
    target = _record_target(record)
    return f"override:{target}:{record.get('property', '')}"


def _target_ids(values: Iterable[Any]) -> set[str]:
    result: set[str] = set()
    for value in values:
        if isinstance(value, Mapping):
            identifier = value.get("id")
            if identifier is not None:
                result.add(str(identifier))
            properties = value.get("properties")
            if isinstance(properties, Mapping):
                for key in ("target", "target_id", "object_id", "candidate_id"):
                    if properties.get(key) is not None:
                        result.add(str(properties[key]))
                candidates = properties.get("candidate_ids")
                if isinstance(candidates, (list, tuple, set, frozenset)):
                    result.update(str(item) for item in candidates)
        else:
            identifier = getattr(value, "id", None)
            if identifier is not None:
                result.add(str(identifier))
            properties = getattr(value, "properties", None)
            if isinstance(properties, Mapping):
                for key in ("target", "target_id", "object_id", "candidate_id"):
                    if properties.get(key) is not None:
                        result.add(str(properties[key]))
                candidates = properties.get("candidate_ids")
                if isinstance(candidates, (list, tuple, set, frozenset)):
                    result.update(str(item) for item in candidates)
    return result


@dataclass(slots=True)
class OverrideReconciliation:
    valid: list[dict[str, Any]] = field(default_factory=list)
    stale: list[dict[str, Any]] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)

    @property
    def stale_overrides(self) -> list[dict[str, Any]]:
        return self.stale

    @property
    def conflicting_overrides(self) -> list[dict[str, Any]]:
        return self.conflicts

    def to_dict(self) -> dict[str, list[dict[str, Any]]]:
        return {
            "valid": list(self.valid),
            "stale": list(self.stale),
            "stale_overrides": list(self.stale),
            "conflicts": list(self.conflicts),
        }


def reconcile_overrides(
    overrides: Any,
    nodes: Iterable[Any] = (),
    edges: Iterable[Any] = (),
) -> OverrideReconciliation:
    """Flag missing stable targets without deleting or mutating overrides."""

    if overrides is None:
        records: list[Any] = []
    elif callable(getattr(overrides, "records", None)):
        records = overrides.records()
    elif isinstance(overrides, Mapping):
        values = overrides.get("overrides", [overrides])
        records = list(values) if isinstance(values, (list, tuple)) else []
    else:
        records = list(overrides)
    known = _target_ids([*nodes, *edges])
    valid: list[dict[str, Any]] = []
    stale: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for raw in records:
        if not isinstance(raw, Mapping):
            continue
        record = dict(raw)
        target = _record_target(record)
        if target and target in known:
            grouped.setdefault((target, str(record.get("property", ""))), []).append(record)
            continue
        stale.append(
            {
                **record,
                "id": _record_id(record),
                "override_id": _record_id(record),
                "target_id": target,
                "issue_type": "stale",
                "status": "candidate",
            }
        )
    for (target, property_name), group in sorted(grouped.items()):
        if len(group) == 1:
            valid.append(group[0])
            continue
        values = {json.dumps(item.get("value"), ensure_ascii=False, sort_keys=True, default=str) for item in group}
        issue_type = "duplicate" if len(values) == 1 else "conflict"
        conflicts.append(
            {
                "id": f"override-conflict:{target}:{property_name}",
                "target_id": target,
                "property": property_name,
                "issue_type": issue_type,
                "status": "candidate",
                "source": "manual",
                "records": [dict(item) for item in group],
                "evidence": [
                    f"{len(group)} overrides target {target!r} property {property_name!r}",
                    "values agree" if issue_type == "duplicate" else "values disagree",
                ],
            }
        )
    return OverrideReconciliation(valid=valid, stale=stale, conflicts=conflicts)


__all__ = ["OverrideReconciliation", "reconcile_overrides"]
