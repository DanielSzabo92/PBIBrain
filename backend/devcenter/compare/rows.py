"""Compare rows of a merge session (technical design sections 4.2 and 14.1, UC23 to UC26).

Row key: the source row key (``<type>:<qualified name>``) of the target
object, else of the first donor object. A donor-only row whose key is in use
(for example the donor object of a name clash) gets ``@<source ID>`` at the
end. Merge Choices use the row key.

Source keys: each cell has ``source_key``, the row key of its object in that
source (``backend.devcenter.sources.objects``). The marks, ``row_confirm``,
and the row hashes use the source key with the source ID. A row shows each
mark whose source ID and source key are those of one of its cells.

Each cell has one state and a "changed" mark. The reference of a cell is the
target object, else (target = Missing) the first donor object of the row.
``row_state`` is the highest-precedence cell state.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Mapping, Sequence

from backend.devcenter.alignment.align import AlignedRow, DomainSources, align_domain
from backend.devcenter.alignment.keys import fold
from backend.devcenter.compare.extract import MODEL, REPORT, CompareObject, SourceObjects
from backend.devcenter.compare.normalize import NO_RENAMES, RenameMap
from backend.devcenter.compare.properties import compare_properties

STATE_TYPE_CONFLICT = "type_conflict"
STATE_MISSING = "missing"
STATE_RENAMED = "renamed"
STATE_MOVED = "moved"
STATE_DIFFERENT = "different"
STATE_SAME = "same"
# Highest precedence first (section 4.2).
STATES = (STATE_TYPE_CONFLICT, STATE_MISSING, STATE_RENAMED, STATE_MOVED, STATE_DIFFERENT, STATE_SAME)
PRECEDENCE = {state: index for index, state in enumerate(STATES)}

NOTE_SAME_AFTER_RENAME = "same_after_rename"
NOTE_IDS = ("same_after_rename", "possible_rename", "name_clash", "duplicate_lineage_tag")
WARNING_IDS = ("duplicate_lineage_tag",)

MODE_DEFAULT = "default"
MODE_STRICT = "strict"

KIND_ORDER = ("table", "column", "measure", "hierarchy", "partition", "calculation_item", "relationship", "role", "expression",
              "function", "page", "visual", "report_measure")
_MOVED_KINDS = {"measure", "report_measure"}
_NO_TABLE_STATE = {"page", "visual"}


@dataclass(frozen=True)
class SessionSource:
    source_id: str
    objects: SourceObjects | None


@dataclass
class CompareResult:
    rows: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    orphan_marks: list[dict[str, Any]]
    # The compare object of each cell, by (source ID, source key), for the code diff.
    objects: dict[tuple[str, str], CompareObject]


def row_id(row_key: str) -> str:
    """A short stable ID of a row key, for URL paths."""

    return "r-" + hashlib.sha256(row_key.encode("utf-8")).hexdigest()[:16]


def _renames(rows: Sequence[AlignedRow], target_id: str | None) -> dict[str, RenameMap]:
    """For each donor: the donor names to the target names of the aligned objects (default compare only)."""

    tables: dict[str, dict[str, str]] = {}
    measures: dict[str, dict[str, str]] = {}
    columns: dict[str, dict[tuple[str, str], str]] = {}
    for row in rows:
        if target_id is None or row.origin != target_id:
            continue
        target = row.reference
        for source_id, donor in row.members.items():
            if source_id == target_id or donor.kind != target.kind:
                continue
            if target.kind == "table" and donor.name != target.name:
                tables.setdefault(source_id, {})[fold(donor.name)] = target.name
            elif target.kind == "measure" and donor.name != target.name:
                measures.setdefault(source_id, {})[fold(donor.name)] = target.name
            elif target.kind == "column" and donor.name != target.name:
                columns.setdefault(source_id, {})[(fold(donor.table), fold(donor.name))] = target.name
    return {source_id: RenameMap(tables.get(source_id, {}), measures.get(source_id, {}), columns.get(source_id, {}))
            for source_id in set(tables) | set(measures) | set(columns)}


def _cell_state(reference: CompareObject, item: CompareObject, table_map: Mapping[str, str], *, strict: bool,
                renames: RenameMap) -> tuple[str, list[dict[str, Any]], bool]:
    if item.kind != reference.kind or item.subtype != reference.subtype:
        return STATE_TYPE_CONFLICT, [], False
    phrases, after_rename = compare_properties(reference, item, strict=strict, renames=renames)
    table = table_map.get(fold(item.table), item.table) if item.table is not None else None
    other_table = item.kind not in _NO_TABLE_STATE and fold(table) != fold(reference.table)
    if item.name != reference.name or (other_table and item.kind not in _MOVED_KINDS):
        return STATE_RENAMED, phrases, after_rename
    if other_table:
        return STATE_MOVED, phrases, after_rename
    return (STATE_DIFFERENT if phrases else STATE_SAME), phrases, after_rename


def _sort_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (0 if row["domain"] == MODEL else 1, KIND_ORDER.index(row["object_type"]) if row["object_type"] in KIND_ORDER else 99,
            fold(row["table"] or row["page"] or ""), fold(row["name"]), row["row_key"])


def build_rows(sources: Sequence[SessionSource], *, target_model: str | None, target_report: str | None,
               overrides: Mapping[str, Any] | None = None, mode: str = MODE_DEFAULT,
               merge_choices: Mapping[str, Any] | None = None, marks: Sequence[Mapping[str, Any]] = ()) -> CompareResult:
    """Align the sources and give the full compare row list in the default order."""

    strict = mode == MODE_STRICT
    merge_choices = merge_choices or {}
    rows: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    placed: dict[tuple[str, str], dict[str, Any]] = {}
    objects: dict[tuple[str, str], CompareObject] = {}
    model_renames: dict[str, RenameMap] = {}
    for domain, target_id in ((MODEL, target_model), (REPORT, target_report)):
        members = [(item.source_id, (item.objects.model if domain == MODEL else item.objects.report))
                   for item in sources if item.objects is not None]
        members = [(source_id, objects) for source_id, objects in members if objects or source_id == target_id]
        if not members:
            continue
        alignment = align_domain(DomainSources(domain, members, target_id), overrides)
        renames = _renames(alignment.rows, target_id) if not strict else {}
        if domain == MODEL:
            model_renames = renames
        warnings.extend(alignment.warnings)
        order = [source_id for source_id, _ in members]
        for aligned in alignment.rows:
            reference = aligned.reference
            cells = []
            for source_id in order:
                item = aligned.members.get(source_id)
                cell: dict[str, Any] = {"source_id": source_id, "role": "target" if source_id == target_id else "donor",
                                        "present": item is not None, "source_key": item.source_key if item else None,
                                        "name": item.name if item else None, "table": item.table if item else None,
                                        "subtype": item.subtype if item else None, "step": aligned.steps.get(source_id),
                                        "state": STATE_MISSING, "changed": False, "phrases": [], "notes": []}
                if item is not None:
                    if source_id == aligned.origin:
                        cell["state"] = STATE_SAME
                    else:
                        through = NO_RENAMES
                        if not strict and aligned.origin == target_id:
                            through = renames.get(source_id) or model_renames.get(source_id) or NO_RENAMES
                        table_map = alignment.table_maps.get(source_id, {}) if aligned.origin == target_id else {}
                        state, phrases, after_rename = _cell_state(reference, item, table_map, strict=strict, renames=through)
                        cell.update(state=state, changed=bool(phrases), phrases=phrases)
                        if after_rename:
                            cell["notes"].append({"note_id": NOTE_SAME_AFTER_RENAME})
                for note in aligned.notes.get(source_id, []):
                    cell["notes"].append({"note_id": note["note_id"], **({"other_row_key": note["row"].row_key} if "row" in note else {})})
                cells.append(cell)
            states = [cell["state"] for cell in cells]
            if target_id is None or target_id not in aligned.members:
                # The target object is Missing (also when the session has no target yet).
                states.append(STATE_MISSING)
            row_state = min(states, key=PRECEDENCE.__getitem__)
            row = {
                "row_key": aligned.row_key,
                "row_id": row_id(aligned.row_key),
                "domain": domain,
                "object_type": reference.kind,
                "subtype": reference.subtype,
                "name": reference.name,
                "table": reference.table if reference.kind not in {"page", "visual"} else None,
                "page": reference.table if reference.kind == "visual" else (reference.source_key.split(":", 1)[1] if reference.kind == "page" else None),
                "display_folder": reference.display_folder,
                "row_state": row_state,
                "changed": any(cell["changed"] for cell in cells),
                "cells": cells,
                "merge_choice": merge_choices.get(aligned.row_key),
                "proposal_status": None,
                "marks": [],
            }
            for cell in cells:
                if cell["present"]:
                    placed[(cell["source_id"], cell["source_key"])] = row
                    objects[(cell["source_id"], cell["source_key"])] = aligned.members[cell["source_id"]]
            rows.append(row)
    orphans: list[dict[str, Any]] = []
    for mark in marks:
        row = placed.get((mark.get("source_id"), mark.get("row_key")))
        entry = {"source_id": mark.get("source_id"), "row_key": mark.get("row_key"), "mark": mark.get("mark")}
        if row is not None:
            row["marks"].append(entry)
        else:
            orphans.append(entry)
    rows.sort(key=_sort_key)
    return CompareResult(rows, warnings, orphans, objects)


# Query: filters, sort, counts, and paging (UC23 to UC26) ----------------------

SORT_FIELDS = ("state", "name", "type", "table")
DEFAULT_LIMIT = 200
MAX_LIMIT = 1000


def _values(value: Any) -> list[str]:
    if value is None:
        return []
    items = value if isinstance(value, (list, tuple)) else [value]
    found: list[str] = []
    for item in items:
        found.extend(part for part in str(item).split(",") if part)
    return found


def _truth(value: Any) -> bool | None:
    values = _values(value)
    if not values:
        return None
    return values[0].casefold() in {"1", "true", "yes"}


def filter_rows(rows: Sequence[Mapping[str, Any]], query: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Filter by type, table, display folder (``folder`` or ``display_folder``), state, source, page, changed, marks, and ``q``."""

    types = {fold(item) for item in _values(query.get("type"))}
    tables = {fold(item) for item in _values(query.get("table"))}
    folders = {fold(item) for item in _values(query.get("display_folder")) + _values(query.get("folder"))}
    states = {fold(item) for item in _values(query.get("state"))}
    sources = set(_values(query.get("source")))
    pages = {fold(item) for item in _values(query.get("page"))}
    changed = _truth(query.get("changed"))
    marks = {fold(item) for item in _values(query.get("marks"))}
    text = fold(" ".join(_values(query.get("q")))).strip()
    selected = []
    for row in rows:
        if types and row["object_type"] not in types:
            continue
        if tables and fold(row["table"]) not in tables:
            continue
        if folders and fold(row["display_folder"]) not in folders:
            continue
        if states and row["row_state"] not in states:
            continue
        if sources and not any(cell["source_id"] in sources and cell["present"] for cell in row["cells"]):
            continue
        if pages and fold(row["page"]) not in pages:
            continue
        if changed is not None and row["changed"] != changed:
            continue
        if marks:
            kinds = {mark["mark"] for mark in row["marks"]}
            if not kinds or not ("any" in marks or "true" in marks or kinds & marks):
                continue
        if text and not any(text in fold(name) for name in [row["name"], *(cell["name"] for cell in row["cells"] if cell["name"])]):
            continue
        selected.append(row)
    return selected


def sort_rows(rows: Sequence[Mapping[str, Any]], sort: str | None, order: str | None) -> list[Mapping[str, Any]]:
    """Stable sort. Equal values keep the default row order, also in descending order."""

    if not sort:
        return list(rows)
    keys = {
        "state": lambda row: PRECEDENCE[row["row_state"]],
        "name": lambda row: (fold(row["name"]), row["name"]),
        "type": lambda row: (KIND_ORDER.index(row["object_type"]) if row["object_type"] in KIND_ORDER else 99, row["object_type"]),
        "table": lambda row: (fold(row["table"] or row["page"] or ""), row["table"] or row["page"] or ""),
    }
    position = {id(row): index for index, row in enumerate(rows)}
    if order == "desc":
        groups: dict[Any, list[Mapping[str, Any]]] = {}
        for row in rows:
            groups.setdefault(keys[sort](row), []).append(row)
        return [row for value in sorted(groups, reverse=True) for row in groups[value]]
    return sorted(rows, key=lambda row: (keys[sort](row), position[id(row)]))


def state_counts(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = {state: 0 for state in STATES}
    for row in rows:
        counts[row["row_state"]] += 1
    return counts
