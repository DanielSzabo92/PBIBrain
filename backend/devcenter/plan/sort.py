"""The fixed phases and the dependency sort of the Change Plan operations (technical design section 6.3).

Phases: deletes (dependents first), renames, creates (needs first), replaces
and property sets, expression rewrites, then the report operations in the same
phase order. In each phase, a dependency sort. Ties sort by object type, then
name. A dependency cycle makes the plan Invalid.
"""

from __future__ import annotations

import heapq
from typing import Any
from collections.abc import Mapping, Sequence

from backend.devcenter.alignment.keys import fold

PHASES = ("deletes", "renames", "creates", "changes", "rewrites")

MODEL_PHASE = {
    "DELETE": "deletes",
    "RENAME": "renames",
    "RENAME_PAIR": "renames",
    "CREATE": "creates",
    "REPLACE": "changes",
    "SET_PROPERTIES": "changes",
    "REWRITE_EXPRESSION": "rewrites",
}
REPORT_PHASE = {
    "DELETE_PAGE": "deletes",
    "DELETE_VISUAL": "deletes",
    "DELETE_REPORT_MEASURE": "deletes",
    "REMOVE_FIELD": "deletes",
    "COPY_PAGE": "creates",
    "COPY_VISUAL": "creates",
    "CREATE_REPORT_MEASURE": "creates",
    "REPLACE_REPORT_MEASURE": "changes",
    "REWRITE_EXPRESSION": "rewrites",
    "REBIND_FIELD": "rewrites",
}

# Tie order of the object types: needs first (table, column, relationship, hierarchy, measure, calculation group, role).
TYPE_ORDER = ("expression", "table", "column", "partition", "relationship", "hierarchy", "function", "measure",
              "calculation_group", "calculation_item", "role", "page", "visual", "report_measure")


def phase_of(operation: Mapping[str, Any]) -> tuple[int, str]:
    """Give the sort index and the phase name of one operation."""

    table = MODEL_PHASE if operation["domain"] == "model" else REPORT_PHASE
    phase = table[operation["op"]]
    if operation["op"] == "COPY_PAGE" and operation.get("replace"):
        phase = "changes"
    offset = 0 if operation["domain"] == "model" else len(PHASES)
    return offset + PHASES.index(phase), phase


def _type_rank(operation: Mapping[str, Any]) -> int:
    kind = "calculation_group" if operation.get("subtype") == "calculation_group" else operation["object_type"]
    return TYPE_ORDER.index(kind) if kind in TYPE_ORDER else len(TYPE_ORDER)


def tie_key(operation: Mapping[str, Any]) -> tuple[Any, ...]:
    return (_type_rank(operation), fold(operation.get("table") or ""), fold(operation.get("name") or ""),
            operation.get("pointer") or "", operation["op_id"])


def sort_operations(operations: Sequence[dict[str, Any]], needs: Mapping[str, set[str]]) -> tuple[list[dict[str, Any]], list[list[str]]]:
    """Sort the operations. ``needs`` gives, for each operation ID, the IDs of the operations that must come first.

    Give the sorted list and the cycles (each cycle as a sorted list of operation IDs).
    In the delete phase the needs go the other way: a dependent goes first.
    """

    groups: dict[int, list[dict[str, Any]]] = {}
    for operation in operations:
        index, phase = phase_of(operation)
        operation["phase"] = phase
        groups.setdefault(index, []).append(operation)
    result: list[dict[str, Any]] = []
    cycles: list[list[str]] = []
    for index in sorted(groups):
        members = groups[index]
        ids = {item["op_id"] for item in members}
        by_id = {item["op_id"]: item for item in members}
        before: dict[str, set[str]] = {op_id: set() for op_id in ids}
        deletes = PHASES[index % len(PHASES)] == "deletes"
        for op_id in ids:
            for other in needs.get(op_id, set()) & ids:
                if other == op_id:
                    continue
                if deletes:
                    before[other].add(op_id)
                else:
                    before[op_id].add(other)
        waiting = {op_id: len(items) for op_id, items in before.items()}
        after: dict[str, list[str]] = {op_id: [] for op_id in ids}
        for op_id, items in before.items():
            for other in items:
                after[other].append(op_id)
        ready = [(tie_key(by_id[op_id]), op_id) for op_id, count in waiting.items() if count == 0]
        heapq.heapify(ready)
        done: list[str] = []
        while ready:
            _, op_id = heapq.heappop(ready)
            done.append(op_id)
            for other in after[op_id]:
                waiting[other] -= 1
                if waiting[other] == 0:
                    heapq.heappush(ready, (tie_key(by_id[other]), other))
        if len(done) < len(ids):
            rest = sorted(ids - set(done), key=lambda op_id: tie_key(by_id[op_id]))
            cycles.append(sorted(rest))
            done.extend(rest)
        result.extend(by_id[op_id] for op_id in done)
    return result, cycles
