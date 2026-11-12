"""N-way alignment of the objects of a merge session (technical design section 4.1).

Steps, in this sequence, for each donor against the target:

0. Manual alignment from the session overrides (``confirm``). The user decision wins.
1. Same lineageTag. A lineageTag that occurs two times in one source is ignored
   for those objects, with a warning.
2. Same alignment key (qualified name and type, or the key of ``keys``), then
   the second pass keys (partition table, page display name). A column and a
   measure with the same name in the same table align with a type conflict.
3. Same name in a different table ("Moved"): measures and report measures only.
4. Same expression with a different name ("possible rename"): only a note, and
   only when exactly one candidate exists on each side. The user confirms it.

An object that aligns at a step leaves the pool. A ``break`` override forbids
one pair at each step. Tables align first, so that the objects of a renamed
table use the target table name in their keys.

A row starts from the target object. A donor object with no target object gets
its own row (target = Missing). Donor objects of different donors with no
target object share one row when their lineageTag or their key is equal.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any
from collections.abc import Callable, Iterable, Mapping, Sequence

from backend.devcenter.alignment import keys
from backend.devcenter.compare.extract import CompareObject
from backend.devcenter.compare.normalize import dax_key, exact_text

STEP_MANUAL = "manual"
STEP_LINEAGE_TAG = "lineage_tag"
STEP_KEY = "key"
STEP_TYPE_CONFLICT = "type_conflict"
STEP_MOVED = "moved"

NOTE_POSSIBLE_RENAME = "possible_rename"
NOTE_NAME_CLASH = "name_clash"
NOTE_DUPLICATE_LINEAGE_TAG = "duplicate_lineage_tag"
WARNING_DUPLICATE_LINEAGE_TAG = "duplicate_lineage_tag"

OVERRIDE_CONFIRM = "confirm"
OVERRIDE_BREAK = "break"
OVERRIDE_REJECT_RENAME = "reject_rename"
OVERRIDE_KINDS = (OVERRIDE_CONFIRM, OVERRIDE_BREAK, OVERRIDE_REJECT_RENAME)

_MOVED_KINDS = {"measure", "report_measure"}
_FIELD_KINDS = {"measure", "column"}
_TABLE_KINDS = {"column", "measure", "hierarchy", "partition", "calculation_item", "report_measure"}


@dataclass
class AlignedRow:
    """One row of the alignment: one object or none for each source."""

    domain: str
    origin: str
    members: dict[str, CompareObject] = field(default_factory=dict)
    steps: dict[str, str] = field(default_factory=dict)
    notes: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    row_key: str = ""

    @property
    def reference(self) -> CompareObject:
        return self.members[self.origin]

    def note(self, source_id: str, note: dict[str, Any]) -> None:
        self.notes.setdefault(source_id, []).append(note)


@dataclass
class Alignment:
    rows: list[AlignedRow]
    warnings: list[dict[str, Any]]
    # For each donor: the donor table name (case-folded) to the target table name.
    table_maps: dict[str, dict[str, str]]


@dataclass(frozen=True)
class DomainSources:
    """The sources of one domain (model or report), in session order, and the target of the domain."""

    domain: str
    objects: Sequence[tuple[str, Sequence[CompareObject]]]
    target_id: str | None


def _signature(item: CompareObject) -> tuple[Any, ...] | None:
    """The "same expression" value of the possible rename step (default normalization)."""

    signature = item.extra.get("signature")
    if item.kind == "measure":
        return ("measure", dax_key(item.props.get("expression")))
    if signature is None:
        return None
    if signature[0] == "expression":
        return (item.kind, item.subtype, dax_key(signature[1]))
    if signature[0] == "m":
        return (item.kind, exact_text(signature[1]))
    if signature[0] == "source":
        return (item.kind, item.subtype, keys.fold(signature[1]), keys.fold(signature[2]))
    return None


class _Space:
    """The target names of one source: the donor table names after the table alignment."""

    def __init__(self, table_map: Mapping[str, str] | None = None) -> None:
        self.table_map = dict(table_map or {})

    def table(self, name: str | None) -> str | None:
        return None if name is None else self.table_map.get(keys.fold(name), name)

    def key(self, item: CompareObject) -> tuple[Any, ...]:
        kind = item.kind
        if kind == "relationship":
            return keys.relationship_key([(self.table(table) or "", column) for table, column in item.extra["ends"]])
        if kind == "calculation_item":
            return keys.calculation_item_key(self.table(item.table) or "", item.name)
        if kind == "partition":
            return keys.partition_key(self.table(item.table) or "", item.name)
        if kind == "role":
            return keys.role_key(item.name)
        if kind == "page":
            return keys.page_id_key(item.extra["page_id"])
        if kind == "visual":
            return keys.visual_key(item.extra["visual_id"])
        if kind == "report_measure":
            return keys.report_measure_key(self.table(item.table) or "", item.name)
        return keys.qualified_key(kind, self.table(item.table) if kind in _TABLE_KINDS else None, item.name)

    def second_key(self, item: CompareObject) -> tuple[Any, ...] | None:
        if item.kind == "partition" and item.extra.get("partition_count") == 1:
            return keys.partition_table_key(self.table(item.table) or "")
        if item.kind == "page":
            return keys.page_name_key(item.extra.get("display_name"))
        return None

    def field(self, item: CompareObject) -> tuple[Any, ...] | None:
        return keys.field_key(self.table(item.table), item.name) if item.kind in _FIELD_KINDS else None

    def moved(self, item: CompareObject) -> tuple[Any, ...] | None:
        return (item.kind, keys.fold(item.name)) if item.kind in _MOVED_KINDS else None


def _unique_index(items: Iterable[CompareObject], key: Callable[[CompareObject], Any]) -> dict[Any, CompareObject]:
    found: dict[Any, list[CompareObject]] = {}
    for item in items:
        value = key(item)
        if value is not None:
            found.setdefault(value, []).append(item)
    return {value: group[0] for value, group in found.items() if len(group) == 1}


def _pair(targets: Sequence[CompareObject], donors: Sequence[CompareObject], target_space: _Space, donor_space: _Space, *,
          target_tags: Mapping[str, CompareObject], donor_dups: set[str], confirms: Sequence[tuple[str, str]],
          forbidden: set[tuple[str, str]], moved: bool = True,
          type_conflict: bool = True) -> list[tuple[CompareObject, CompareObject, str]]:
    """Align two object lists. Give ``(target object, donor object, step)`` for each pair."""

    target_pool = {id(item): item for item in targets}
    donor_pool = {id(item): item for item in donors}
    pairs: list[tuple[CompareObject, CompareObject, str]] = []

    def take(target: CompareObject, donor: CompareObject, step: str) -> None:
        if (target.source_key, donor.source_key) in forbidden or id(target) not in target_pool or id(donor) not in donor_pool:
            return
        pairs.append((target, donor, step))
        del target_pool[id(target)]
        del donor_pool[id(donor)]

    for target_key, donor_key in confirms:
        target = next((item for item in target_pool.values() if item.source_key == target_key), None)
        donor = next((item for item in donor_pool.values() if item.source_key == donor_key), None)
        if target is not None and donor is not None:
            take(target, donor, STEP_MANUAL)
    for donor in sorted(donor_pool.values(), key=lambda item: item.source_key):
        if donor.lineage_tag and donor.lineage_tag not in donor_dups:
            target = target_tags.get(donor.lineage_tag)
            if target is not None:
                take(target, donor, STEP_LINEAGE_TAG)
    passes: list[tuple[Callable[[CompareObject], Any], Callable[[CompareObject], Any], str]] = [
        (target_space.key, donor_space.key, STEP_KEY),
        (target_space.second_key, donor_space.second_key, STEP_KEY),
    ]
    if type_conflict:
        passes.append((target_space.field, donor_space.field, STEP_TYPE_CONFLICT))
    if moved:
        passes.append((target_space.moved, donor_space.moved, STEP_MOVED))
    for target_key, donor_key, step in passes:
        target_index = _unique_index(target_pool.values(), target_key)
        donor_index = _unique_index(donor_pool.values(), donor_key)
        for value in sorted(donor_index, key=repr):
            if value in target_index:
                take(target_index[value], donor_index[value], step)
    return pairs


def _tag_index(items: Sequence[CompareObject]) -> tuple[dict[str, CompareObject], set[str]]:
    counts = Counter(item.lineage_tag for item in items if item.lineage_tag)
    dups = {tag for tag, count in counts.items() if count > 1}
    return {item.lineage_tag: item for item in items if item.lineage_tag and item.lineage_tag not in dups}, dups


def _overrides(overrides: Mapping[str, Sequence[Mapping[str, Any]]], source_id: str, kind: str) -> list[tuple[str, str]]:
    return [(str(item.get("target_key")), str(item.get("donor_key"))) for item in overrides.get(source_id, [])
            if isinstance(item, Mapping) and item.get("kind") == kind]


def align_domain(sources: DomainSources, overrides: Mapping[str, Sequence[Mapping[str, Any]]] | None = None) -> Alignment:
    """Align the objects of one domain. The result is the same for the same input."""

    overrides = overrides or {}
    by_source = {source_id: list(items) for source_id, items in sources.objects}
    warnings: list[dict[str, Any]] = []
    dups: dict[str, set[str]] = {}
    tag_indexes: dict[str, dict[str, CompareObject]] = {}
    for source_id, items in sources.objects:
        tag_indexes[source_id], dups[source_id] = _tag_index(items)
        for tag in sorted(dups[source_id]):
            warnings.append({"warning_id": WARNING_DUPLICATE_LINEAGE_TAG, "source_id": source_id, "lineage_tag": tag,
                             "source_keys": sorted(item.source_key for item in items if item.lineage_tag == tag)})

    rows: list[AlignedRow] = []
    target_id = sources.target_id if sources.target_id in by_source else None
    target_rows: dict[str, AlignedRow] = {}
    target_items = by_source.get(target_id, []) if target_id else []
    for item in target_items:
        row = AlignedRow(sources.domain, target_id, {target_id: item})
        rows.append(row)
        target_rows[item.source_key] = row
    target_space = _Space()
    target_keys = {target_space.key(item): target_rows[item.source_key] for item in target_items}
    table_maps: dict[str, dict[str, str]] = {}
    donor_rows: list[AlignedRow] = []

    for donor_id, donor_items in sources.objects:
        if donor_id == target_id:
            continue
        confirms = _overrides(overrides, donor_id, OVERRIDE_CONFIRM)
        forbidden = set(_overrides(overrides, donor_id, OVERRIDE_BREAK))
        rejected = set(_overrides(overrides, donor_id, OVERRIDE_REJECT_RENAME))
        common = {"target_tags": tag_indexes.get(target_id, {}) if target_id else {}, "donor_dups": dups[donor_id],
                  "confirms": confirms, "forbidden": forbidden}
        pairs = _pair([item for item in target_items if item.kind == "table"], [item for item in donor_items if item.kind == "table"],
                      target_space, _Space(), **common)
        table_map = {keys.fold(donor.name): target.name for target, donor, _ in pairs}
        table_maps[donor_id] = table_map
        donor_space = _Space(table_map)
        pairs += _pair([item for item in target_items if item.kind != "table"], [item for item in donor_items if item.kind != "table"],
                       target_space, donor_space, **common)
        for target, donor, step in pairs:
            row = target_rows[target.source_key]
            row.members[donor_id] = donor
            row.steps[donor_id] = step
        aligned_targets = {id(target) for target, _, _ in pairs}
        aligned_donors = {id(donor) for _, donor, _ in pairs}
        left_targets = [item for item in target_items if id(item) not in aligned_targets]
        left_donors = [item for item in donor_items if id(item) not in aligned_donors]

        # Step 4: possible rename, only with one candidate on each side.
        target_groups: dict[Any, list[CompareObject]] = {}
        donor_groups: dict[Any, list[CompareObject]] = {}
        for group, items in ((target_groups, left_targets), (donor_groups, left_donors)):
            for item in items:
                signature = _signature(item)
                if signature is not None:
                    group.setdefault(signature, []).append(item)
        renames: dict[str, CompareObject] = {}
        for signature, donors in donor_groups.items():
            candidates = target_groups.get(signature, [])
            if len(donors) == 1 and len(candidates) == 1:
                target, donor = candidates[0], donors[0]
                pair = (target.source_key, donor.source_key)
                if keys.fold(target.name) != keys.fold(donor.name) and pair not in rejected and pair not in forbidden:
                    renames[donor.source_key] = target

        # Donor objects with no target object: join a row of an earlier donor, or start a row.
        open_rows = [row for row in donor_rows if donor_id not in row.members]
        by_reference = {id(row.reference): row for row in open_rows}
        references = [row.reference for row in open_rows]
        joined = _pair(references, left_donors, _ReferenceSpace(open_rows, table_maps), donor_space,
                       target_tags=_tag_index(references)[0], donor_dups=dups[donor_id], confirms=(), forbidden=set(),
                       moved=False, type_conflict=False)
        joined_rows: dict[int, AlignedRow] = {}
        for reference, donor, step in joined:
            row = by_reference[id(reference)]
            row.members[donor_id] = donor
            row.steps[donor_id] = step
            joined_rows[id(donor)] = row
        for donor in sorted(left_donors, key=lambda item: item.source_key):
            row = joined_rows.get(id(donor))
            if row is None:
                row = AlignedRow(sources.domain, donor_id, {donor_id: donor})
                rows.append(row)
                donor_rows.append(row)
            clash = target_keys.get(donor_space.key(donor))
            if clash is not None:
                row.note(donor_id, {"note_id": NOTE_NAME_CLASH, "row": clash})
            target = renames.get(donor.source_key)
            if target is not None:
                target_row = target_rows[target.source_key]
                target_row.note(donor_id, {"note_id": NOTE_POSSIBLE_RENAME, "row": row})
                row.note(donor_id, {"note_id": NOTE_POSSIBLE_RENAME, "row": target_row})

    for row in rows:
        for source_id, item in row.members.items():
            if item.lineage_tag and item.lineage_tag in dups.get(source_id, set()):
                row.note(source_id, {"note_id": NOTE_DUPLICATE_LINEAGE_TAG})
    _assign_keys(rows)
    return Alignment(rows, warnings, table_maps)


class _ReferenceSpace(_Space):
    """The names of the first object of donor-only rows, in target names."""

    def __init__(self, rows: Sequence[AlignedRow], table_maps: Mapping[str, Mapping[str, str]]) -> None:
        super().__init__()
        self._spaces = {id(row.reference): _Space(table_maps.get(row.origin)) for row in rows}

    def _space(self, item: CompareObject) -> _Space:
        return self._spaces.get(id(item), _Space())

    def key(self, item: CompareObject) -> tuple[Any, ...]:
        return self._space(item).key(item)

    def second_key(self, item: CompareObject) -> tuple[Any, ...] | None:
        return self._space(item).second_key(item)


def _assign_keys(rows: Sequence[AlignedRow]) -> None:
    """Give each row its key: the source row key of the target object, else of the first donor object.

    A donor-only row whose key is already in use gets ``@<source ID>`` at the end.
    """

    used: set[str] = set()
    for row in rows:
        key = row.reference.source_key
        if key in used:
            base = f"{key}@{row.origin}"
            key, number = base, 2
            while key in used:
                key, number = f"{base}-{number}", number + 1
        used.add(key)
        row.row_key = key
