"""The Change Plan compiler (technical design section 6).

``compile_plan`` derives the plan from the compare rows and the session state
each time. Nobody edits the plan. The same input always gives the same plan
and the same plan hash.

Two levels: a plan step comes from one Merge Choice or one prerequisite (a
Need). A plan step compiles to one or more operations. Each operation keeps
the ID of its plan step.

Identities: each model or report object of the target after the plan has one
identity. The identity of a row is its row key. A promoted report measure also
has the model identity ``<row key>#model``. ``final_name`` gives the table and
the name of an identity after the plan.

The Merge Choice shape (``merge_choices`` of the session, by row key):
``{kind, source_id, properties, new_name, display_folder}``. The kinds are in
``CHOICE_KINDS``. The ``edit`` kind (issue #12, "Edit target") needs no donor:
``{kind: "edit", new_name, set}`` renames a target model object and sets the
properties in ``set`` (``EDITABLE_PROPERTIES``) to literal values. The plan
rewrites each target reference to an edited name (DAX, RLS, field parameters
and report bindings) without the "renamed" block: the user asked for the rename. The plan also reads ``removal_policies`` (by row key:
``{policy, replacement_row_key}``), ``need_mappings`` (by the row key of the
needed object: ``{row_key}`` of the target object), and ``item_actions`` (by
item ID: ``{action}``; ``include_in_rewrite`` selects a rename dependent).

``created_objects`` (issue #13, the agent's ``object_create`` proposal) holds new target
model objects with no donor, by a ``new:<object_type>:<table>/<name>`` row key:
``{object_type, table, name, properties}``. Each one is a synthetic compare row with no
cell and compiles to one CREATE. Its DAX is resolved against the target after the plan,
so a missing or deleted object blocks it (``need_missing`` / ``removed``) and a renamed
one is written with its new name. An ``edit`` choice that sets ``expression`` compiles to
REWRITE_EXPRESSION with the same resolution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any
from collections.abc import Iterable, Mapping, Sequence

from backend.devcenter.alignment.keys import fold
from backend.devcenter.compare.extract import MODEL, REPORT, CompareObject
from backend.devcenter.compare.rows import CompareResult
from backend.devcenter.naming.objects import NamedObject
from backend.devcenter.naming.proposer import clash_with, propose
from backend.devcenter.plan import refs
from backend.devcenter.plan.fields import FieldLocation, field_locations, new_native_query_ref, new_query_ref
from backend.devcenter.plan.lineage import TAGGED_KINDS, new_lineage_tag
from backend.devcenter.plan.sort import sort_operations

KEEP = "keep"
TAKE = "take"
TAKE_PROPERTIES = "take_properties"
ADD_NEW_NAME = "add_new_name"
REMOVE = "remove"
SKIP = "skip"
PROMOTE = "promote"
COPY_TO_REPORT = "copy_to_report"
EDIT = "edit"
CREATE = "create"
CREATE_KINDS = ("measure", "column")
CHOICE_KINDS = (KEEP, TAKE, TAKE_PROPERTIES, ADD_NEW_NAME, REMOVE, SKIP, PROMOTE, COPY_TO_REPORT, EDIT)
SOURCE_KINDS = (TAKE, TAKE_PROPERTIES, ADD_NEW_NAME, PROMOTE, COPY_TO_REPORT)
PROPERTY_KINDS = ("measure", "column", "relationship")

# The properties that an ``edit`` choice can set, by object type, with the value type
# (``str``: text or null, ``bool``, or a tuple of allowed text values). The names are the
# model writer names; ``COMPARE_NAMES`` maps the few that the compare extract names differently.
SUMMARIZE_BY = ("default", "none", "sum", "min", "max", "count", "average", "distinctcount")
EDITABLE_PROPERTIES: dict[str, dict[str, Any]] = {
    "measure": {"expression": str, "format_string": str, "display_folder": str, "description": str, "is_hidden": bool},
    "column": {"expression": str, "format_string": str, "display_folder": str, "description": str, "is_hidden": bool,
               "data_category": str, "summarize_by": SUMMARIZE_BY, "is_key": bool},
    "table": {"description": str, "is_hidden": bool, "data_category": str},
}
COMPARE_NAMES = {"is_hidden": "hidden", "is_key": "key"}
RENAMABLE_KINDS = ("measure", "column", "table", "hierarchy", "calculation_item", "role", "expression", "function")


def edit_value_error(object_type: str, prop: str, value: Any) -> str | None:
    """Give a reason code when an ``edit`` choice cannot set this property to this value, else None."""

    allowed = EDITABLE_PROPERTIES.get(object_type, {})
    if prop not in allowed:
        return "unknown_property"
    kind = allowed[prop]
    if prop == "expression":
        return None if isinstance(value, str) and value.strip() else "expression_required"
    if kind is bool:
        return None if isinstance(value, bool) else "invalid_value"
    if kind is str:
        return None if value is None or isinstance(value, str) else "invalid_value"
    return None if value in kind else "invalid_value"


def current_value(item: CompareObject, prop: str) -> Any:
    value = item.props.get(COMPARE_NAMES.get(prop, prop))
    if prop == "summarize_by" and value is None:
        return "default"
    return value

BLOCK = "block"
CASCADE = "cascade"
REPOINT = "repoint"
POLICIES = (BLOCK, CASCADE, REPOINT)
INCLUDE_IN_REWRITE = "include_in_rewrite"

STATUS_VALID = "valid"
STATUS_WARNINGS = "valid_with_warnings"
STATUS_INVALID = "invalid"

STEP_CHOICE = "merge_choice"
STEP_PREREQUISITE = "prerequisite"

# Blocking item kinds and warning kinds. The text of each kind is in ``MESSAGES``.
BLOCKING_KINDS = ("choice_source_removed", "choice_not_valid", "no_target_model", "name_clash", "renamed", "removed",
                  "need_missing", "need_clash", "repoint_not_valid", "udf_compatibility", "dependency_cycle", "source_marks",
                  "dax_parse")
WARNING_KINDS = ("need_added", "new_lineage_tag", "repoint_data_type", "not_checked")
MESSAGES = {
    "choice_source_removed": "The source of this Merge Choice is not in the session.",
    "choice_not_valid": "This Merge Choice is not possible for this row.",
    "no_target_model": "The session has no target model.",
    "name_clash": "The name is in use in the target.",
    "renamed": "This object uses an object that the plan renames.",
    "removed": "This object uses an object that the plan deletes.",
    "need_missing": "An object that this object needs is not available.",
    "need_clash": "An object that this object needs has a name that is in use in the target.",
    "repoint_not_valid": "The replacement object is not valid.",
    "udf_compatibility": "A user-defined function needs compatibility level 1702 or higher.",
    "dependency_cycle": "The plan has a dependency cycle.",
    "source_marks": "Rows changed in their source, and the user did not confirm them.",
    "dax_parse": "The DAX expression has a syntax error.",
    "need_added": "The plan adds an object from the donor, because an added object needs it.",
    "new_lineage_tag": "The target has the donor lineageTag already. The plan gives a new lineageTag.",
    "repoint_data_type": "The replacement object has a different data type.",
    "not_checked": "The app did not examine this area.",
}

GUARD_OPERATIONS = {
    "CREATE": "CREATE_OBJECT",
    "DELETE": "DELETE_OBJECT",
    "REPLACE": "SET_PROPERTY",
    "SET_PROPERTIES": "SET_PROPERTY",
    "RENAME": "RENAME_OBJECT",
    "RENAME_PAIR": "RENAME_PAIR",
    "REWRITE_EXPRESSION": "REPLACE_EXPRESSION",
    "COPY_PAGE": "CREATE_OBJECT",
    "COPY_VISUAL": "CREATE_OBJECT",
    "DELETE_PAGE": "DELETE_OBJECT",
    "DELETE_VISUAL": "DELETE_OBJECT",
    "CREATE_REPORT_MEASURE": "CREATE_OBJECT",
    "DELETE_REPORT_MEASURE": "DELETE_OBJECT",
    "REPLACE_REPORT_MEASURE": "CREATE_OBJECT",
    "REBIND_FIELD": "CHANGE_BINDING",
    "REMOVE_FIELD": "CHANGE_BINDING",
}

UDF_MIN_COMPATIBILITY = 1702

# The properties that hold DAX, for each object type.
DAX_PROPERTIES = {
    "measure": ("expression", "format_string_expression"),
    "column": ("expression",),
    "table": ("expression",),
    "calculation_item": ("expression", "format_string_expression"),
    "function": ("expression",),
    "report_measure": ("expression",),
}
_CHILD_KINDS = ("column", "measure", "hierarchy", "partition", "calculation_item")
_NAMING_TYPES = {"table": None, "column": None, "measure": "measure", "hierarchy": "hierarchy", "report_measure": "report_measure"}


@dataclass
class PlanInput:
    session_id: str
    result: CompareResult
    target_model: str | None
    target_report: str | None
    sources: Mapping[str, str]  # source ID to display name, in session order
    merge_choices: Mapping[str, Any] = field(default_factory=dict)
    removal_policies: Mapping[str, Any] = field(default_factory=dict)
    need_mappings: Mapping[str, Any] = field(default_factory=dict)
    item_actions: Mapping[str, Any] = field(default_factory=dict)
    compatibility_level: int | None = None
    naming_rules: Sequence[Mapping[str, Any]] = ()
    created_objects: Mapping[str, Any] = field(default_factory=dict)


def created_row(row_key: str, entry: Mapping[str, Any]) -> dict[str, Any]:
    """The synthetic compare row of a created object: no cell, so no source has it yet."""

    kind = str(entry.get("object_type") or "")
    subtype = "calculated" if kind == "column" else kind
    return {"row_key": row_key, "row_id": row_key, "domain": MODEL, "object_type": kind, "subtype": subtype,
            "name": str(entry.get("name") or ""), "table": entry.get("table"), "cells": [], "marks": [], "created": True}


@dataclass
class _Step:
    step_id: str
    kind: str
    row_key: str
    choice: str | None
    source_id: str | None
    domain: str
    object_type: str
    name: str
    operations: list[dict[str, Any]] = field(default_factory=list)


def _digest(*parts: Any) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()


def plan_hash(plan: Mapping[str, Any]) -> str:
    content = {key: plan[key] for key in ("status", "steps", "operations", "blocking", "warnings", "sources")}
    return "sha256:" + _digest(content)


class _Compiler:
    def __init__(self, data: PlanInput) -> None:
        self.data = data
        self.rows: list[dict[str, Any]] = list(data.result.rows)
        self.objects = data.result.objects
        self.authored: dict[str, Mapping[str, Any]] = {}  # created row key to its ``created_objects`` entry
        for key, entry in sorted(data.created_objects.items()):
            if isinstance(entry, Mapping) and key not in {row["row_key"] for row in self.rows}:
                self.rows.append(created_row(key, entry))
                self.authored[key] = entry
        self.by_key = {row["row_key"]: row for row in self.rows}
        self.row_of: dict[tuple[str, str], dict[str, Any]] = {}
        for row in self.rows:
            for cell in row["cells"]:
                if cell["present"]:
                    self.row_of[(cell["source_id"], cell["source_key"])] = row
        self.steps: list[_Step] = []
        self.step_of_row: dict[str, _Step] = {}
        self.blocking: list[dict[str, Any]] = []
        self.warnings: list[dict[str, Any]] = []
        self._item_ids: set[str] = set()
        self.op_needs: dict[str, set[str]] = {}
        # Identity state after the plan.
        self.own_name: dict[str, str] = {}
        self.home_row: dict[str, str | None] = {}
        self.kind_of: dict[str, str] = {}
        self.subtype_of: dict[str, str] = {}
        self.domain_of: dict[str, str] = {}
        self.created: dict[str, tuple[str, CompareObject]] = {}  # identity to (source ID, donor object)
        self.deleted: set[str] = set()
        self.resourced: dict[str, set[str] | None] = {}  # row key to its re-sourced DAX properties (None: all)
        self.promoted: dict[str, str] = {}  # report measure row key to its model identity
        self.repoints: dict[str, str] = {}  # removed row key to its replacement row key
        self.used_tags: set[str] = set()
        self.indexes: dict[str, refs.ModelIndex] = {}
        self.choices = {key: value for key, value in data.merge_choices.items() if isinstance(value, Mapping)}

    # Rows and cells -----------------------------------------------------------------

    def target_id(self, row: Mapping[str, Any]) -> str | None:
        return self.data.target_model if row["domain"] == MODEL else self.data.target_report

    def cell(self, row: Mapping[str, Any], source_id: str | None) -> dict[str, Any] | None:
        return next((item for item in row["cells"] if item["source_id"] == source_id and item["present"]), None)

    def target_object(self, row: Mapping[str, Any]) -> CompareObject | None:
        cell = self.cell(row, self.target_id(row))
        return self.objects[(cell["source_id"], cell["source_key"])] if cell else None

    def source_object(self, row: Mapping[str, Any], source_id: str | None) -> CompareObject | None:
        cell = self.cell(row, source_id)
        return self.objects[(source_id, cell["source_key"])] if cell else None

    def index(self, source_id: str) -> refs.ModelIndex:
        if source_id not in self.indexes:
            model = [item for (sid, _), item in self.objects.items() if sid == source_id and item.domain == MODEL]
            report = [item for (sid, _), item in self.objects.items() if sid == source_id and item.domain == REPORT]
            if source_id == self.data.target_model and self.data.target_report not in (None, source_id):
                report += [item for (sid, _), item in self.objects.items()
                           if sid == self.data.target_report and item.kind == "report_measure"]
            self.indexes[source_id] = refs.ModelIndex.build(sorted(model, key=lambda item: item.source_key),
                                                            sorted(report, key=lambda item: item.source_key))
        return self.indexes[source_id]

    def table_row(self, source_id: str, table: str | None) -> str | None:
        if table is None:
            return None
        row = self.row_of.get((source_id, f"table:{table}"))
        if row is None:
            found = self.index(source_id).tables.get(fold(table))
            row = self.row_of.get((source_id, found.source_key)) if found else None
        return row["row_key"] if row else None

    # Items ---------------------------------------------------------------------------

    def _item(self, target: list[dict[str, Any]], kind: str, row_key: str | None, *, step: _Step | None = None,
              item_id: str | None = None, **params: Any) -> None:
        item_id = item_id or f"{kind}:{row_key or ''}"
        if item_id in self._item_ids:
            return
        self._item_ids.add(item_id)
        row = self.by_key.get(row_key or "")
        target.append({
            "item_id": item_id,
            "kind": kind,
            "row_key": row_key,
            "row_id": row["row_id"] if row else None,
            "step_id": step.step_id if step else None,
            "object": self.object_view(row_key) if row_key else None,
            "message": MESSAGES[kind],
            "params": params,
            "actions": [INCLUDE_IN_REWRITE] if kind == "renamed" else [],
        })

    def block(self, kind: str, row_key: str | None, **params: Any) -> None:
        self._item(self.blocking, kind, row_key, **params)

    def warn(self, kind: str, row_key: str | None, **params: Any) -> None:
        self._item(self.warnings, kind, row_key, **params)

    def object_view(self, identity: str) -> dict[str, Any]:
        row = self.by_key.get(identity.split("#", 1)[0])
        table, name = self.original_name(identity)
        return {"object_type": self.kind_of.get(identity, row["object_type"] if row else None), "table": table, "name": name}

    # Names -----------------------------------------------------------------------------

    def register(self, identity: str, kind: str, subtype: str, domain: str, name: str, home: str | None) -> None:
        self.own_name[identity] = name
        self.home_row[identity] = home
        self.kind_of[identity] = kind
        self.subtype_of[identity] = subtype
        self.domain_of[identity] = domain

    def final_name(self, identity: str) -> tuple[str | None, str]:
        home = self.home_row.get(identity)
        table = self.own_name.get(home) if home else None
        if home and table is None:
            table = self.original_name(home)[1]
        return table, self.own_name[identity]

    def original_name(self, identity: str) -> tuple[str | None, str]:
        row = self.by_key.get(identity.split("#", 1)[0])
        if row is None:
            return None, identity
        if row.get("created"):
            return row.get("table"), row["name"]
        item = self.target_object(row)
        if item is None:
            first = next(cell for cell in row["cells"] if cell["present"])
            item = self.objects[(first["source_id"], first["source_key"])]
        return (item.table if item.kind not in {"table", "page", "visual"} else None), item.name

    def exists(self, identity: str) -> bool:
        return identity in self.own_name and identity not in self.deleted

    def _init_target(self) -> None:
        for row in self.rows:
            item = self.target_object(row)
            if item is None:
                continue
            home = None
            if item.kind in _CHILD_KINDS or item.kind == "report_measure":
                home = self.table_row(self.data.target_model, item.table) if self.data.target_model else None
            self.register(row["row_key"], item.kind, item.subtype, row["domain"], item.name, home)
            if item.lineage_tag:
                self.used_tags.add(item.lineage_tag)

    # Steps and operations ------------------------------------------------------------------

    def new_step(self, kind: str, row: Mapping[str, Any], choice: str | None, source_id: str | None, domain: str | None = None) -> _Step:
        step = _Step("step-" + _digest(kind, row["row_key"])[:12], kind, row["row_key"], choice, source_id,
                     domain or row["domain"], row["object_type"], row["name"])
        self.steps.append(step)
        self.step_of_row.setdefault(row["row_key"], step)
        return step

    def op(self, step: _Step, name: str, identity: str, *, domain: str | None = None, needs: Iterable[str] = (),
           **values: Any) -> dict[str, Any]:
        domain = domain or self.domain_of.get(identity) or self.by_key[identity.split("#", 1)[0]]["domain"]
        kind = self.kind_of.get(identity) or self.by_key[identity.split("#", 1)[0]]["object_type"]
        subtype = self.subtype_of.get(identity) or self.by_key[identity.split("#", 1)[0]]["subtype"]
        table, object_name = (self.final_name(identity) if identity in self.own_name else self.original_name(identity))
        if name in {"DELETE", "DELETE_PAGE", "DELETE_VISUAL", "DELETE_REPORT_MEASURE", "RENAME", "RENAME_PAIR"}:
            table, object_name = self.original_name(identity)
            if name in {"RENAME", "RENAME_PAIR"} and identity in self.home_row:
                table = self.final_name(identity)[0]
        operation = {
            "op_id": "",
            "step_id": step.step_id,
            "op": name,
            "guard_op": GUARD_OPERATIONS[name],
            "domain": domain,
            "object_type": kind,
            "subtype": subtype,
            "row_key": identity.split("#", 1)[0],
            "table": table,
            "name": object_name,
            **values,
        }
        operation["op_id"] = "op-" + _digest(step.step_id, name, identity, values.get("pointer"), values.get("property"),
                                             len(step.operations))[:12]
        step.operations.append(operation)
        self.op_needs[operation["op_id"]] = set(needs)
        return operation

    # Translation of donor DAX through the alignment (section 6.5) ----------------------------

    def resolve_identity(self, source_id: str, resolved: refs.Resolved, step: _Step) -> str | None:
        """Give the target identity of a donor reference. Add a Need when the target has no object for it."""

        row = self.row_of.get((source_id, resolved.key)) if resolved.key else None
        if row is None:
            return None
        identity = row["row_key"]
        if identity in self.promoted:
            identity = self.promoted[identity]
        if identity in self.deleted:
            self._item(self.blocking, "removed", step.row_key, step=step, item_id=f"removed:{step.row_key}:{identity}",
                       removed=self.object_view(identity))
            return identity
        if self.exists(identity):
            return identity
        mapping = self.data.need_mappings.get(row["row_key"])
        if isinstance(mapping, Mapping) and self.exists(str(mapping.get("row_key") or "")):
            return str(mapping["row_key"])
        return self.need(row, source_id, step)

    def need(self, row: Mapping[str, Any], source_id: str, step: _Step) -> str | None:
        """Add a Need as a prerequisite plan step with the default "add from donor" (section 6.7)."""

        key = row["row_key"]
        donor = self.source_object(row, source_id)
        if donor is None:
            donor_source = next((cell["source_id"] for cell in row["cells"] if cell["present"]), None)
            donor = self.source_object(row, donor_source)
            source_id = donor_source or source_id
        choice = self.choices.get(key) or {}
        if donor is None or choice.get("kind") in {KEEP, SKIP} or source_id == self.target_id(row) or donor.kind in {"page", "visual"}:
            self._item(self.blocking, "need_missing", step.row_key, step=step, item_id=f"need_missing:{step.row_key}:{key}",
                       needed=self.object_view(key))
            return None
        prerequisite = self.new_step(STEP_PREREQUISITE, row, TAKE, source_id)
        home = self.table_row(source_id, donor.table) if donor.kind in _CHILD_KINDS or donor.kind == "report_measure" else None
        self.register(key, donor.kind, donor.subtype, row["domain"], donor.name, home)
        if self._clashes(key):
            self.own_name.pop(key)
            self.steps.remove(prerequisite)
            self._item(self.blocking, "need_clash", step.row_key, step=step, item_id=f"need_clash:{step.row_key}:{key}",
                       needed=self.object_view(key))
            return None
        self.created[key] = (source_id, donor)
        self.warn("need_added", key, needed_by=step.row_key, source_id=source_id)
        self.pending.append((prerequisite, row, source_id, donor, False, None))
        return key

    def translate(self, step: _Step, source_id: str, text: str | None, home_table: str | None,
                  property_name: str) -> tuple[str | None, set[str]]:
        """Translate one donor DAX text to the target names. Give the new text and the needed identities."""

        if text is None:
            return None, set()
        index = self.index(source_id)
        resolved, failed = index.references(text, home_table)
        if failed:
            self._item(self.blocking, "dax_parse", step.row_key, step=step, item_id=f"dax_parse:{step.row_key}:{property_name}",
                       property=property_name)
        needs: set[str] = set()
        mapped: dict[int, tuple[str | None, str | None]] = {}
        for position, item in enumerate(resolved):
            if item.key is None:
                self._item(self.blocking, "need_missing", step.row_key, step=step,
                           item_id=f"need_missing:{step.row_key}:{fold(item.raw.table)}/{fold(item.raw.name)}",
                           needed={"object_type": item.kind, "table": item.raw.table, "name": item.raw.name})
                continue
            identity = self.resolve_identity(source_id, item, step)
            if identity is None:
                continue
            needs.add(identity)
            table, name = self.final_name(identity) if identity in self.own_name else self.original_name(identity)
            if item.kind == refs.TABLE:
                mapped[position] = (name, None)
            elif item.kind == refs.MEASURE or item.kind == refs.REPORT_MEASURE:
                prefix = None
                if item.raw.table is not None:
                    table_item = index.tables.get(fold(item.raw.table))
                    table_row = self.row_of.get((source_id, table_item.source_key)) if table_item else None
                    if table_row is not None and table_row["row_key"] in self.own_name:
                        prefix = self.final_name(table_row["row_key"])[1]
                mapped[position] = (prefix, name)
            else:
                mapped[position] = (table, name)
        positions = {id(item): position for position, item in enumerate(resolved)}
        new_text, _ = refs.rewrite(text, resolved, lambda item: mapped.get(positions[id(item)]))
        return new_text, needs

    # Carry-over of one donor object -------------------------------------------------------------

    def carried_properties(self, step: _Step, identity: str, source_id: str, donor: CompareObject,
                           selected: Sequence[str] | None = None) -> tuple[dict[str, Any], set[str]]:
        """The donor properties with the DAX and the names translated to the target. Give them and the needs."""

        props = {key: value for key, value in donor.props.items() if selected is None or key in selected}
        needs: set[str] = set()
        home = donor.table if donor.kind != "table" else donor.name
        for name in DAX_PROPERTIES.get(donor.kind, ()):
            if name in props and props[name] is not None:
                props[name], found = self.translate(step, source_id, props[name], home, name)
                needs |= found
        if donor.kind in _CHILD_KINDS or donor.kind == "report_measure":
            table = self.table_row(source_id, donor.table)
            if table is not None:
                found = self._need_identity(step, source_id, table)
                if found:
                    needs.add(found)
        if donor.kind == "column" and props.get("sort_by_column"):
            column = self._column_identity(step, source_id, donor.table, props["sort_by_column"])
            if column:
                needs.add(column)
                props["sort_by_column"] = self.final_name(column)[1]
        if donor.kind == "hierarchy" and "levels" in props:
            levels = []
            for level in props["levels"]:
                column = self._column_identity(step, source_id, donor.table, level)
                if column:
                    needs.add(column)
                levels.append(self.final_name(column)[1] if column else level)
            props["levels"] = levels
        if donor.kind == "relationship" and selected is None:
            ends = []
            for table, column in donor.extra.get("ends", []):
                found = self._column_identity(step, source_id, table, column)
                if found:
                    needs.add(found)
                ends.append(list(self.final_name(found)) if found else [table, column])
            props["ends"] = ends
        if donor.kind == "role" and "role_filters" in props:
            filters = {}
            for key, text in sorted(props["role_filters"].items()):
                table = donor.extra.get("tables", {}).get(key, key)
                table_identity = self._need_identity(step, source_id, self.table_row(source_id, table))
                if table_identity:
                    needs.add(table_identity)
                new_text, found = self.translate(step, source_id, text, table, f"role_filters/{key}")
                needs |= found
                filters[self.final_name(table_identity)[1] if table_identity else table] = new_text
            props["role_filters"] = filters
        needs.discard(identity)
        return props, needs

    def _need_identity(self, step: _Step, source_id: str, row_key: str | None) -> str | None:
        if row_key is None:
            return None
        row = self.by_key[row_key]
        cell = self.cell(row, source_id)
        if cell is None:
            return None
        return self.resolve_identity(source_id, refs.Resolved(refs.RawRef("table", None, None, None, None), row["object_type"],
                                                              cell["source_key"]), step)

    def _column_identity(self, step: _Step, source_id: str, table: str | None, column: str) -> str | None:
        item = self.index(source_id).columns.get((fold(table), fold(column)))
        if item is None:
            return None
        return self.resolve_identity(source_id, refs.Resolved(refs.RawRef("qualified", table, column, None, None), refs.COLUMN,
                                                              item.source_key), step)

    def lineage_tag(self, row: Mapping[str, Any], source_id: str, donor: CompareObject, *, new: bool) -> str | None:
        """The lineageTag rules of section 6.6 for a new object."""

        if donor.kind not in TAGGED_KINDS:
            return None
        cell = self.cell(row, source_id) or {}
        duplicate = any(note.get("note_id") == "duplicate_lineage_tag" for note in cell.get("notes", []))
        tag = donor.lineage_tag
        if new or duplicate or not tag or tag in self.used_tags:
            if tag and tag in self.used_tags and not new and not duplicate:
                self.warn("new_lineage_tag", row["row_key"], lineage_tag=tag)
            tag = new_lineage_tag(self.data.session_id, row["row_key"])
        self.used_tags.add(tag)
        return tag

    # Intents (names of the target after the plan) ----------------------------------------------------

    def valid_choice(self, row: Mapping[str, Any], choice: Mapping[str, Any]) -> str | None:
        """Give a reason code when the Merge Choice is not possible for the row, else None."""

        kind = choice.get("kind")
        target = self.target_object(row)
        source_id = choice.get("source_id")
        if kind not in CHOICE_KINDS:
            return "unknown_kind"
        if kind in SOURCE_KINDS and self.source_object(row, source_id) is None:
            return "no_source_object"
        if kind in SOURCE_KINDS and source_id == self.target_id(row) and kind not in {PROMOTE}:
            return "source_is_target"
        if kind in {TAKE_PROPERTIES, REMOVE} and target is None:
            return "no_target_object"
        if kind == TAKE_PROPERTIES:
            selected = choice.get("properties") or []
            if row["object_type"] not in PROPERTY_KINDS or not selected:
                return "no_properties"
            donor = self.source_object(row, source_id)
            if donor is not None and any(name not in donor.props for name in selected):
                return "unknown_property"
        if kind == ADD_NEW_NAME and not str(choice.get("new_name") or "").strip():
            return "new_name_required"
        if kind in {PROMOTE, COPY_TO_REPORT} and row["object_type"] != "report_measure":
            return "report_measure_only"
        if kind == EDIT:
            if target is None:
                return "no_target_object"
            if row["domain"] != MODEL:
                return "model_only"
            new_name = choice.get("new_name")
            values = choice.get("set") or {}
            if new_name is not None and (not isinstance(new_name, str) or not new_name.strip()):
                return "new_name_required"
            if new_name is not None and row["object_type"] not in RENAMABLE_KINDS:
                return "not_renamable"
            if not isinstance(values, Mapping):
                return "invalid_value"
            if new_name is None and not values:
                return "no_edit"
            for prop, value in values.items():
                reason = edit_value_error(row["object_type"], prop, value)
                if reason is not None:
                    return reason
            if "expression" in values and row["object_type"] == "column" and target.subtype != "calculated":
                return "not_calculated"
        if kind == PROMOTE and self.data.target_model is None:
            return "no_target_model"
        return None

    def intents(self) -> list[tuple[_Step, dict[str, Any], Mapping[str, Any]]]:
        work = []
        handled_keys = set()
        for row in self.rows:
            handled_keys.add(row["row_key"])
            choice = self.choices.get(row["row_key"])
            if not choice or choice.get("kind") in {KEEP, SKIP, None}:
                continue
            source_id = choice.get("source_id")
            if choice.get("kind") in SOURCE_KINDS and source_id not in self.data.sources:
                self.block("choice_source_removed", row["row_key"], source_id=source_id)
                continue
            reason = self.valid_choice(row, choice)
            if reason is not None:
                self.block("choice_not_valid", row["row_key"], reason=reason, choice=choice.get("kind"))
                continue
            if (row["domain"] == MODEL or choice["kind"] == PROMOTE) and self.data.target_model is None:
                self.block("no_target_model", row["row_key"])
                continue
            step = self.new_step(STEP_CHOICE, row, choice["kind"], source_id, MODEL if choice["kind"] == PROMOTE else None)
            self.register_intent(step, row, choice)
            work.append((step, row, choice))
        for row_key, choice in sorted(self.choices.items()):
            if row_key in handled_keys:
                continue
            if not choice or choice.get("kind") in {KEEP, SKIP, None}:
                continue
            source_id = choice.get("source_id")
            if choice.get("kind") in SOURCE_KINDS and source_id not in self.data.sources:
                self.block("choice_source_removed", row_key, source_id=source_id)
        return work

    def register_intent(self, step: _Step, row: Mapping[str, Any], choice: Mapping[str, Any]) -> None:
        kind = choice["kind"]
        key = row["row_key"]
        source_id = choice.get("source_id")
        donor = self.source_object(row, source_id)
        target = self.target_object(row)
        new_name = str(choice.get("new_name") or "").strip() or None
        if kind == REMOVE:
            self.deleted.add(key)
            return
        if kind == EDIT:
            if new_name is not None:
                self.own_name[key] = new_name
            return
        if kind == TAKE and target is not None:
            assert donor is not None
            self.own_name[key] = new_name or donor.name
            self.resourced[key] = None
            return
        if kind == TAKE_PROPERTIES:
            self.resourced[key] = set(choice.get("properties") or [])
            return
        if kind in {TAKE, ADD_NEW_NAME}:
            assert donor is not None
            identity = key if target is None else f"{key}#new"
            home = self.table_row(source_id, donor.table) if donor.kind in _CHILD_KINDS or donor.kind == "report_measure" else None
            self.register(identity, donor.kind, donor.subtype, row["domain"], new_name or donor.name, home)
            self.created[identity] = (source_id, donor)
            if kind == TAKE and donor.kind == "table":
                self.register_children(step, row, source_id, donor)
            return
        if kind == PROMOTE:
            assert donor is not None
            identity = f"{key}#model"
            home = self.table_row(source_id, donor.table) if source_id != self.data.target_report else (
                self.table_row(self.data.target_model, donor.table))
            self.register(identity, "measure", "measure", MODEL, new_name or donor.name, home)
            self.created[identity] = (source_id, donor)
            self.promoted[key] = identity
            if target is not None:
                self.deleted.add(key)
            return
        if kind == COPY_TO_REPORT:
            assert donor is not None
            if target is None:
                home = self.table_row(source_id, donor.table)
                self.register(key, donor.kind, donor.subtype, REPORT, new_name or donor.name, home)
                self.created[key] = (source_id, donor)
            else:
                self.own_name[key] = new_name or donor.name
                self.resourced[key] = None

    def register_children(self, step: _Step, table_row: Mapping[str, Any], source_id: str, table: CompareObject) -> None:
        """A new table brings its columns, measures, hierarchies, partitions, and calculation items, except rows with their own Merge Choice."""

        children = []
        for row in self.rows:
            donor = self.source_object(row, source_id)
            if donor is None or donor.kind not in _CHILD_KINDS or fold(donor.table) != fold(table.name):
                continue
            if self.target_object(row) is not None or row["row_key"] in self.choices:
                continue
            self.register(row["row_key"], donor.kind, donor.subtype, row["domain"], donor.name, table_row["row_key"])
            self.created[row["row_key"]] = (source_id, donor)
            children.append((row, donor))
        self.children[step.step_id] = children

    def register_authored(self) -> list[tuple[_Step, dict[str, Any], Mapping[str, Any]]]:
        """Register each created object of ``created_objects`` (issue #13) in its target table."""

        work = []
        for key, entry in sorted(self.authored.items()):
            row = self.by_key[key]
            if self.data.target_model is None:
                self.block("no_target_model", key)
                continue
            reason = None
            if row["object_type"] not in CREATE_KINDS:
                reason = "unknown_kind"
            elif not row["name"].strip():
                reason = "new_name_required"
            elif not isinstance((entry.get("properties") or {}).get("expression"), str) \
                    or not entry["properties"]["expression"].strip():
                reason = "expression_required"
            home = self.table_row(self.data.target_model, row.get("table"))
            if reason is None and (home is None or not self.exists(home)):
                reason = "no_table"
            if reason is not None:
                self.block("choice_not_valid", key, reason=reason, choice=CREATE)
                continue
            step = self.new_step(STEP_CHOICE, row, CREATE, None, MODEL)
            self.register(key, row["object_type"], row["subtype"], MODEL, row["name"], home)
            work.append((step, row, entry))
        return work

    def build_authored(self, step: _Step, row: Mapping[str, Any], entry: Mapping[str, Any]) -> None:
        assert self.data.target_model is not None
        key = row["row_key"]
        props = {name: value for name, value in sorted((entry.get("properties") or {}).items())
                 if edit_value_error(row["object_type"], name, value) is None and value is not None}
        props["expression"], needs = self.translate(step, self.data.target_model, props["expression"], row.get("table"), "expression")
        home = self.home_row.get(key)
        if home:
            needs.add(home)
        needs.discard(key)
        self.op(step, "CREATE", key, needs=needs, source_id=None, source_key=None,
                lineage_tag=new_lineage_tag(self.data.session_id, key), properties=props)

    # Compile ------------------------------------------------------------------------------------

    def build(self, step: _Step, row: Mapping[str, Any], choice: Mapping[str, Any]) -> None:
        kind = choice["kind"]
        source_id = choice.get("source_id")
        donor = self.source_object(row, source_id)
        target = self.target_object(row)
        key = row["row_key"]
        folder = choice.get("display_folder")
        if kind == REMOVE:
            self.build_remove(step, row, target)
            return
        if kind == EDIT:
            assert target is not None
            self.build_edit(step, row, target, choice)
            return
        if kind in {TAKE, ADD_NEW_NAME} and (target is None or kind == ADD_NEW_NAME):
            assert donor is not None
            self.pending.append((step, row, source_id, donor, kind == ADD_NEW_NAME, folder))
            for child, child_donor in self.children.get(step.step_id, []):
                self.pending.append((step, child, source_id, child_donor, False, None))
            return
        if kind == TAKE:
            assert donor is not None and target is not None
            self.build_take_existing(step, row, source_id, donor, target, folder)
            return
        if kind == TAKE_PROPERTIES:
            assert donor is not None
            props, needs = self.carried_properties(step, key, source_id, donor, choice.get("properties") or [])
            if folder is not None and "display_folder" in props:
                props["display_folder"] = folder
            self.op(step, "SET_PROPERTIES", key, needs=needs, source_id=source_id, source_key=donor.source_key, properties=props)
            return
        if kind == PROMOTE:
            assert donor is not None
            self.build_promote(step, row, source_id, donor, target, folder)
            return
        if kind == COPY_TO_REPORT:
            assert donor is not None
            props, needs = self.carried_properties(step, key, source_id, donor)
            if folder is not None:
                props["display_folder"] = folder
            name = "CREATE_REPORT_MEASURE" if target is None else "REPLACE_REPORT_MEASURE"
            self.op(step, name, key, needs=needs, source_id=source_id, source_key=donor.source_key, properties=props)

    def build_create(self, step: _Step, row: Mapping[str, Any], source_id: str, donor: CompareObject, new_tag: bool,
                     folder: str | None) -> None:
        key = row["row_key"]
        identity = key if key in self.created else f"{key}#new"
        if donor.kind == "page":
            self.op(step, "COPY_PAGE", identity, source_id=source_id, source_key=donor.source_key,
                    page_id=donor.extra.get("page_id"), replace=False)
            for visual_row in self.rows:
                visual = self.source_object(visual_row, source_id)
                if visual is None or visual.kind != "visual" or visual.table != donor.source_key.split(":", 1)[1]:
                    continue
                if visual_row["row_key"] in self.choices or self.target_object(visual_row) is not None:
                    continue
                self.register(visual_row["row_key"], "visual", visual.subtype, REPORT, visual.name, None)
                self.copy_visual(step, visual_row, source_id, visual, page_identity=identity)
            return
        if donor.kind == "visual":
            page_row = self.row_of.get((source_id, f"page:{donor.table}"))
            page_identity = page_row["row_key"] if page_row else None
            if page_identity is None or not self.exists(page_identity):
                self._item(self.blocking, "need_missing", key, step=step, item_id=f"need_missing:{key}:page",
                           needed={"object_type": "page", "table": None, "name": donor.table})
                return
            self.copy_visual(step, row, source_id, donor, page_identity=page_identity)
            return
        props, needs = self.carried_properties(step, identity, source_id, donor)
        if folder is not None:
            props["display_folder"] = folder
        name = "CREATE_REPORT_MEASURE" if donor.kind == "report_measure" else "CREATE"
        self.op(step, name, identity, needs=needs, source_id=source_id, source_key=donor.source_key,
                lineage_tag=self.lineage_tag(row, source_id, donor, new=new_tag), properties=props)

    def copy_visual(self, step: _Step, row: Mapping[str, Any], source_id: str, donor: CompareObject, *, page_identity: str) -> None:
        key = row["row_key"]
        self.op(step, "COPY_VISUAL", key, needs={page_identity}, source_id=source_id, source_key=donor.source_key,
                page_id=self.by_key[page_identity]["page"], visual_id=donor.extra.get("visual_id"))
        for location in field_locations(donor):
            identity = self.field_identity(step, source_id, location, donor=True)
            if identity is None:
                continue
            table, name = self.final_name(identity)
            if fold(table) != fold(location.entity) or fold(name) != fold(location.property):
                self.rebind(step, key, location, table or location.entity, name, needs={identity})

    def build_take_existing(self, step: _Step, row: Mapping[str, Any], source_id: str, donor: CompareObject,
                            target: CompareObject, folder: str | None) -> None:
        key = row["row_key"]
        if donor.kind == "page":
            self.op(step, "COPY_PAGE", key, source_id=source_id, source_key=donor.source_key, page_id=target.extra.get("page_id"),
                    replace=True)
            return
        if donor.kind == "visual":
            self.op(step, "DELETE_VISUAL", key)
            self.copy_visual(step, row, source_id, donor, page_identity=self.by_key[key]["row_key"] if False else
                             (self.row_of.get((self.data.target_report, f"page:{target.table}")) or {}).get("row_key", key))
            return
        self.rename_op(step, key, target)
        cell = self.cell(row, source_id) or {}
        changed = bool(cell.get("phrases")) or (folder is not None and folder != target.display_folder)
        if changed:
            props, needs = self.carried_properties(step, key, source_id, donor)
            if folder is not None and "display_folder" in props:
                props["display_folder"] = folder
            props.pop("ends", None)
            self.op(step, "REPLACE", key, needs=needs, source_id=source_id, source_key=donor.source_key,
                    lineage_tag=target.lineage_tag, properties=props)

    def rename_op(self, step: _Step, key: str, target: CompareObject) -> None:
        final = self.own_name[key]
        if final != target.name:
            name = "RENAME" if target.kind in TAGGED_KINDS else "RENAME_PAIR"
            values: dict[str, Any] = {"old_name": target.name, "new_name": final}
            if name == "RENAME_PAIR":
                values["pair_id"] = "pair-" + _digest(step.step_id, key)[:12]
            self.op(step, name, key, **values)

    def build_edit(self, step: _Step, row: Mapping[str, Any], target: CompareObject, choice: Mapping[str, Any]) -> None:
        """An ``edit`` choice: a rename of the target object and literal property values. A value equal to the target value gives no operation."""

        key = row["row_key"]
        self.rename_op(step, key, target)
        props = {prop: value for prop, value in sorted((choice.get("set") or {}).items()) if current_value(target, prop) != value}
        if "expression" in props and self.data.target_model is not None:
            # A new DAX text is resolved against the target like a donor text: renamed names are written
            # with the plan's names, and a missing or deleted object blocks.
            old = target.props.get("expression")
            new_text, needs = self.translate(step, self.data.target_model, props.pop("expression"), target.table, "expression")
            needs.discard(key)
            if new_text != old:
                self.op(step, "REWRITE_EXPRESSION", key, needs=needs, property="expression", old_text=old, new_text=new_text)
        # The model writer skips a null value; an empty text clears the property in the model library.
        props = {prop: "" if value is None else value for prop, value in props.items()}
        if props:
            self.op(step, "SET_PROPERTIES", key, properties=props)

    def build_promote(self, step: _Step, row: Mapping[str, Any], source_id: str, donor: CompareObject,
                      target: CompareObject | None, folder: str | None) -> None:
        key = row["row_key"]
        identity = self.promoted[key]
        props, needs = self.carried_properties(step, identity, source_id, donor)
        if folder is not None:
            props["display_folder"] = folder
        self.op(step, "CREATE", identity, domain=MODEL, needs=needs, source_id=source_id, source_key=donor.source_key,
                lineage_tag=new_lineage_tag(self.data.session_id, key), properties=props)
        if target is None:
            return
        table, name = self.final_name(identity)
        for visual_key, location in self.field_dependents.get(key, []):
            if visual_key in self.deleted:
                continue
            self.rebind(step, visual_key, location, table or location.entity, name, needs={identity}, new_kind="measure")
        self.op(step, "DELETE_REPORT_MEASURE", key)

    def rebind(self, step: _Step, visual_key: str, location: FieldLocation, entity: str, prop: str, *,
               needs: Iterable[str] = (), new_kind: str | None = None) -> None:
        self.rebound.add((visual_key, location.pointer))
        self.op(step, "REBIND_FIELD", visual_key, domain=REPORT, needs=needs, pointer=location.pointer,
                old={"kind": location.kind, "entity": location.entity, "property": location.property},
                new={"kind": new_kind or location.kind, "entity": entity, "property": prop},
                query_ref={"old": location.query_ref, "new": new_query_ref(location.query_ref, location.entity, location.property, entity, prop)},
                native_query_ref={"old": location.native_query_ref,
                                  "new": new_native_query_ref(location.native_query_ref, location.property, prop)})

    def field_identity(self, step: _Step, source_id: str, location: FieldLocation, *, donor: bool) -> str | None:
        index = self.index(source_id)
        item: CompareObject | None
        if location.kind == "column":
            item = index.columns.get((fold(location.entity), fold(location.property)))
        else:
            item = index.measures.get(fold(location.property)) or index.report_measures.get((fold(location.entity), fold(location.property)))
        if item is None:
            if donor:
                self._item(self.blocking, "need_missing", step.row_key, step=step,
                           item_id=f"need_missing:{step.row_key}:{fold(location.entity)}/{fold(location.property)}",
                           needed={"object_type": location.kind, "table": location.entity, "name": location.property})
            return None
        if not donor:
            row = self.row_of.get((source_id, item.source_key))
            return row["row_key"] if row else None
        return self.resolve_identity(source_id, refs.Resolved(refs.RawRef("qualified", location.entity, location.property, None, None),
                                                              item.kind, item.source_key), step)

    # Removal and removal policies (section 6.4) ------------------------------------------------------

    def dependents(self, identity: str) -> list[tuple[str, str, Any]]:
        """The target objects that use an object: ``(kind, dependent row key, detail)`` with kind ``dax``, ``structural``, or ``field``."""

        found: list[tuple[str, str, Any]] = []
        members = {identity} | set(self.children_of(identity))
        for member in sorted(members):
            for dependent, prop in self.dax_dependents.get(member, []):
                if dependent not in members:
                    found.append(("dax", dependent, prop))
            for dependent in self.structural_dependents.get(member, []):
                if dependent not in members:
                    found.append(("structural", dependent, None))
            for visual_key, location in self.field_dependents.get(member, []):
                found.append(("field", visual_key, location))
        return found

    def children_of(self, identity: str) -> list[str]:
        if self.kind_of.get(identity) == "table":
            return [key for key, home in self.home_row.items() if home == identity and key in self.by_key and self.target_object(self.by_key[key])]
        return []

    def build_remove(self, step: _Step, row: Mapping[str, Any], target: CompareObject | None) -> None:
        key = row["row_key"]
        names = {"page": "DELETE_PAGE", "visual": "DELETE_VISUAL", "report_measure": "DELETE_REPORT_MEASURE"}
        self.op(step, names.get(row["object_type"], "DELETE"), key)
        for child in self.children_of(key):
            self.deleted.add(child)
        policy = self.data.removal_policies.get(key) or {}
        policy_kind = policy.get("policy") if isinstance(policy, Mapping) else None
        policy_kind = policy_kind if policy_kind in POLICIES else BLOCK
        if policy_kind == REPOINT:
            replacement = str(policy.get("replacement_row_key") or "")
            if not self.exists(replacement) or self.kind_of.get(replacement) != self.kind_of.get(key) or replacement == key:
                self.block("repoint_not_valid", key, replacement_row_key=replacement or None)
                policy_kind = BLOCK
            else:
                self.repoints[key] = replacement
                old = target.props.get("data_type") if target else None
                new_target = self.target_object(self.by_key[replacement]) if replacement in self.by_key else None
                new = new_target.props.get("data_type") if new_target else None
                if old != new and (old is not None or new is not None):
                    self.warn("repoint_data_type", key, replacement_row_key=replacement, old=old, new=new)
        self.removals.append((step, key, policy_kind))

    def apply_policies(self) -> None:
        """Block, Cascade, or Repoint the dependents of each removed object."""

        queue = list(self.removals)
        while queue:
            step, key, policy = queue.pop(0)
            for kind, dependent, detail in self.dependents(key):
                if dependent in self.deleted and kind != "field":
                    continue
                if kind == "field":
                    if dependent in self.deleted:
                        continue
                    if policy == CASCADE:
                        self.removed_fields.setdefault(dependent, []).append((step, detail))
                    elif policy == BLOCK:
                        self._item(self.blocking, "removed", dependent, step=step, item_id=f"removed:{dependent}:{key}",
                                   removed=self.object_view(key))
                    continue
                if dependent in self.choices and (self.choices[dependent] or {}).get("kind") in {TAKE, TAKE_PROPERTIES}:
                    # A dependent with its own Merge Choice keeps it. Its translation checks the new version.
                    continue
                if policy == CASCADE and kind in {"dax", "structural"}:
                    self.deleted.add(dependent)
                    for child in self.children_of(dependent):
                        self.deleted.add(child)
                    names = {"report_measure": "DELETE_REPORT_MEASURE"}
                    self.op(step, names.get(self.kind_of.get(dependent, ""), "DELETE"), dependent)
                    queue.append((step, dependent, CASCADE))
                elif policy == REPOINT and kind == "dax":
                    continue
                else:
                    self._item(self.blocking, "removed", dependent, step=step, item_id=f"removed:{dependent}:{key}",
                               removed=self.object_view(key))

    def finish_fields(self) -> None:
        """Cascade in visuals: remove the field and its filters; remove the visual only when no field stays."""

        for visual_key in sorted(self.removed_fields):
            entries = self.removed_fields[visual_key]
            step = entries[0][0]
            visual = self.target_object(self.by_key[visual_key])
            if visual is None:
                continue
            removed = {location.pointer for _, location in entries}
            stays = [location for location in field_locations(visual) if location.projection and location.pointer not in removed]
            if not stays and visual.kind == "visual":
                self.deleted.add(visual_key)
                self.op(step, "DELETE_VISUAL", visual_key)
                continue
            for entry_step, location in sorted(entries, key=lambda item: item[1].pointer):
                self.rebound.add((visual_key, location.pointer))
                self.op(entry_step, "REMOVE_FIELD", visual_key, domain=REPORT, pointer=location.pointer,
                        field={"kind": location.kind, "entity": location.entity, "property": location.property})

    # Target dependents of renamed, moved, and repointed objects (section 6.5) --------------------------

    def index_target(self) -> None:
        self.dax_dependents: dict[str, list[tuple[str, str]]] = {}
        self.structural_dependents: dict[str, list[str]] = {}
        self.field_dependents: dict[str, list[tuple[str, FieldLocation]]] = {}
        self.target_texts: list[tuple[str, str, str, list[refs.Resolved], str]] = []
        model_id = self.data.target_model
        if model_id is not None:
            index = self.index(model_id)
            for row in self.rows:
                item = self.target_object(row)
                if item is None:
                    continue
                source_id = self.target_id(row) or model_id
                home = item.table if item.kind != "table" else item.name
                texts = [(name, item.props.get(name)) for name in DAX_PROPERTIES.get(item.kind, ())]
                if item.kind == "role":
                    texts += [(f"role_filters/{key}", value) for key, value in sorted(item.props.get("role_filters", {}).items())]
                for name, text in texts:
                    if not text:
                        continue
                    table = item.extra.get("tables", {}).get(name.split("/", 1)[1]) if name.startswith("role_filters/") else home
                    resolved, _ = index.references(text, table)
                    found = []
                    for ref in resolved:
                        ref_row = self.row_of.get((model_id, ref.key)) if ref.key else None
                        if ref_row is None and ref.key and self.data.target_report:
                            ref_row = self.row_of.get((self.data.target_report, ref.key))
                        if ref_row is not None and ref_row["row_key"] != row["row_key"]:
                            self.dax_dependents.setdefault(ref_row["row_key"], []).append((row["row_key"], name))
                            found.append(ref)
                    self.target_texts.append((row["row_key"], source_id, name, resolved, text))
                for other in self.structural(item):
                    other_row = self.row_of.get((model_id, other))
                    if other_row is not None:
                        self.structural_dependents.setdefault(other_row["row_key"], []).append(row["row_key"])
        report_id = self.data.target_report
        if report_id is not None and model_id is not None:
            for row in self.rows:
                item = self.target_object(row)
                if item is None or item.kind not in {"visual", "page"}:
                    continue
                for location in field_locations(item):
                    identity = self.field_identity(_Step("", "", "", None, None, REPORT, "", ""), model_id, location, donor=False)
                    if identity is None and location.kind == "measure":
                        report_item = self.index(model_id).report_measures.get((fold(location.entity), fold(location.property)))
                        found = self.row_of.get((report_id, report_item.source_key)) if report_item else None
                        identity = found["row_key"] if found else None
                    if identity is not None:
                        self.field_dependents.setdefault(identity, []).append((row["row_key"], location))
                        self.field_users.setdefault(row["row_key"], []).append((identity, location))

    def structural(self, item: CompareObject) -> list[str]:
        """The source keys of the columns that a relationship, a hierarchy, or a sort-by column uses."""

        found = []
        if item.kind == "relationship":
            found += [f"column:{table}/{column}" for table, column in item.extra.get("ends", [])]
        if item.kind == "hierarchy":
            found += [f"column:{item.table}/{level}" for level in item.props.get("levels", [])]
        if item.kind == "column" and item.props.get("sort_by_column"):
            found.append(f"column:{item.table}/{item.props['sort_by_column']}")
        return found

    def mapped_name(self, identity: str) -> tuple[str, tuple[str | None, str]] | None:
        """The cause and the new name of a target object that the plan renames, moves, or repoints, else None."""

        cause = identity
        if identity in self.repoints:
            cause, identity = identity, self.repoints[identity]
        if identity in self.promoted:
            identity = self.promoted[identity]
        if identity not in self.own_name:
            return None
        new = self.final_name(identity)
        old = self.original_name(cause)
        if cause == identity and fold(new[0]) == fold(old[0]) and fold(new[1]) == fold(old[1]):
            return None
        if cause == identity and self.home_row.get(identity) and fold(new[1]) == fold(old[1]):
            home = self.home_row[identity]
            cause = home if home and fold(self.own_name.get(home, "")) != fold(self.original_name(home)[1]) else cause
        return cause, new

    def rewrite_dependents(self) -> None:
        for dependent, source_id, prop, resolved, text in self.target_texts:
            if dependent in self.deleted:
                continue
            if prop == "expression" and "expression" in ((self.choices.get(dependent) or {}).get("set") or {}):
                continue  # The edit gives the whole new text; build_edit resolves it.
            resourced = self.resourced.get(dependent, set())
            if dependent in self.resourced and (resourced is None or prop.split("/", 1)[0] in resourced):
                continue
            row = self.by_key[dependent]
            mapping: dict[int, tuple[str | None, str | None]] = {}
            causes: list[str] = []
            for position, ref in enumerate(resolved):
                ref_row = self.row_of.get((source_id, ref.key)) if ref.key else None
                if ref_row is None and ref.key and self.data.target_report:
                    ref_row = self.row_of.get((self.data.target_report, ref.key))
                if ref_row is None:
                    continue
                found = self.mapped_name(ref_row["row_key"])
                if found is None:
                    continue
                cause, (table, name) = found
                repoint = ref_row["row_key"] in self.repoints
                if not repoint and row["domain"] == MODEL and not self.included(dependent, cause):
                    self._item(self.blocking, "renamed", dependent, step=self.step_of_row.get(cause),
                               item_id=f"renamed:{dependent}:{cause}", renamed=self.object_view(cause),
                               new_name=self.final_name(cause)[1] if cause in self.own_name else None)
                    continue
                if ref.kind == refs.TABLE:
                    mapping[position] = (name, None)
                elif ref.kind in {refs.MEASURE, refs.REPORT_MEASURE}:
                    prefix = None
                    if ref.raw.table is not None and table is not None and fold(ref.raw.table) != fold(table):
                        table_item = self.index(source_id).tables.get(fold(ref.raw.table))
                        table_row = self.row_of.get((source_id, table_item.source_key)) if table_item else None
                        if table_row is not None and self.mapped_name(table_row["row_key"]):
                            prefix = self.final_name(table_row["row_key"])[1]
                    mapping[position] = (prefix, name)
                else:
                    mapping[position] = (table, name)
                causes.append(cause)
            if not mapping:
                continue
            positions = {id(item): position for position, item in enumerate(resolved)}
            new_text, count = refs.rewrite(text, resolved, lambda item: mapping.get(positions[id(item)]))
            if not count:
                continue
            step = next((self.step_of_row[cause] for cause in causes if cause in self.step_of_row), None)
            if step is None:
                continue
            identity = dependent if dependent in self.own_name else dependent
            self.op(step, "REWRITE_EXPRESSION", identity, domain=row["domain"], property=prop, old_text=text, new_text=new_text)

    def included(self, dependent: str, cause: str) -> bool:
        if (self.choices.get(cause) or {}).get("kind") == EDIT:
            return True
        action = self.data.item_actions.get(f"renamed:{dependent}:{cause}")
        return isinstance(action, Mapping) and action.get("action") == INCLUDE_IN_REWRITE

    def rebind_fields(self) -> None:
        for visual_key in sorted(self.field_users):
            if visual_key in self.deleted:
                continue
            for identity, location in self.field_users[visual_key]:
                if (visual_key, location.pointer) in self.rebound:
                    continue
                found = self.mapped_name(identity)
                if found is None:
                    continue
                cause, (table, name) = found
                step = self.step_of_row.get(cause) or self.step_of_row.get(identity)
                if step is None:
                    continue
                self.rebind(step, visual_key, location, table or location.entity, name)

    # Checks ----------------------------------------------------------------------------------

    def named(self, identity: str) -> NamedObject:
        kind = self.kind_of[identity]
        subtype = self.subtype_of.get(identity, kind)
        table, name = self.final_name(identity)
        if kind == "table":
            object_type = subtype if subtype in {"calculated_table", "calculation_group"} else "table"
        elif kind == "column":
            object_type = subtype
        else:
            object_type = kind
        return NamedObject(object_type, name, table)

    def _clashes(self, identity: str) -> NamedObject | None:
        kind = self.kind_of[identity]
        live = [key for key in self.own_name if key != identity and self.exists(key) and key in self.kind_of]
        table, name = self.final_name(identity)
        if kind in _NAMING_TYPES:
            item = self.named(identity)
            others = [self.named(key) for key in live if self.kind_of[key] in _NAMING_TYPES]
            return clash_with(name, item.object_type, table, others)
        for key in live:
            if self.kind_of[key] == kind and fold(self.final_name(key)[0]) == fold(table) and fold(self.final_name(key)[1]) == fold(name):
                return NamedObject(kind, self.final_name(key)[1], self.final_name(key)[0])
        return None

    def check_names(self) -> None:
        for row in self.rows:
            key = row["row_key"]
            clash_note = any(note.get("note_id") == "name_clash" for cell in row["cells"] for note in cell["notes"])
            choice = self.choices.get(key) or {}
            if clash_note and choice.get("kind") in {None, SKIP}:
                self.block("name_clash", key, name=row["name"], proposed_name=self.proposal(key, row["name"], None))
        changed = sorted(identity for identity in self.own_name
                         if self.exists(identity) and (identity in self.created or identity in self.authored or fold(self.own_name[identity]) != fold(self.original_name(identity)[1])))
        for identity in changed:
            clash = self._clashes(identity)
            if clash is None:
                continue
            source_id = self.created.get(identity, (None,))[0]
            table, name = self.final_name(identity)
            row_key = identity.split("#", 1)[0]
            self._item(self.blocking, "name_clash", row_key, step=self.step_of_row.get(row_key), item_id=f"name_clash:{identity}",
                       name=name, table=table, clash=clash.view(), proposed_name=self.proposal(identity, name, source_id))

    def proposal(self, identity: str, name: str, source_id: str | None) -> str | None:
        if identity not in self.kind_of or self.kind_of[identity] not in _NAMING_TYPES:
            return None
        item = self.named(identity)
        live = [self.named(key) for key in self.own_name if key != identity and self.exists(key) and self.kind_of.get(key) in _NAMING_TYPES]
        donor = self.data.sources.get(source_id or "")
        return propose(name, item.object_type, {"table": item.table}, self.data.naming_rules, live, donor)["name"]

    def check_functions(self) -> None:
        level = self.data.compatibility_level
        for step in self.steps:
            for operation in step.operations:
                if operation["object_type"] == "function" and operation["op"] in {"CREATE", "REPLACE", "SET_PROPERTIES"}:
                    if level is None or level < UDF_MIN_COMPATIBILITY:
                        self._item(self.blocking, "udf_compatibility", operation["row_key"], step=step,
                                   item_id=f"udf_compatibility:{operation['row_key']}", compatibility_level=level,
                                   required=UDF_MIN_COMPATIBILITY)

    def check_marks(self) -> None:
        marked = [row["row_key"] for row in self.rows if row["marks"]]
        if marked:
            self.block("source_marks", None, count=len(marked), row_keys=marked)

    # Run -------------------------------------------------------------------------------------

    def run(self) -> dict[str, Any]:
        self.pending: list[tuple[_Step, Mapping[str, Any], str, CompareObject, bool, str | None]] = []
        self.children: dict[str, list[tuple[Mapping[str, Any], CompareObject]]] = {}
        self.removals: list[tuple[_Step, str, str]] = []
        self.removed_fields: dict[str, list[tuple[_Step, FieldLocation]]] = {}
        self.rebound: set[tuple[str, str]] = set()
        self.field_users: dict[str, list[tuple[str, FieldLocation]]] = {}
        self._init_target()
        self.index_target()
        work = self.intents()
        authored = self.register_authored()
        for step, row, choice in work:
            if choice["kind"] == REMOVE:
                self.build(step, row, choice)
        self.apply_policies()
        for step, row, choice in work:
            if choice["kind"] != REMOVE:
                self.build(step, row, choice)
            while self.pending:
                pending_step, pending_row, source_id, donor, new_tag, folder = self.pending.pop(0)
                self.build_create(pending_step, pending_row, source_id, donor, new_tag, folder)
        for step, row, entry in authored:
            self.build_authored(step, row, entry)
        self.finish_fields()
        self.rewrite_dependents()
        self.rebind_fields()
        self.check_names()
        self.check_functions()
        self.check_marks()
        return self.result()

    def result(self) -> dict[str, Any]:
        operations = [operation for step in self.steps for operation in step.operations]
        targets: dict[str, list[str]] = {}
        for operation in operations:
            identity = operation["row_key"]
            if operation["op"] == "CREATE" and operation["domain"] == MODEL and operation["object_type"] == "measure" \
                    and self.by_key.get(identity, {}).get("object_type") == "report_measure":
                identity = self.promoted.get(identity, identity)
            targets.setdefault(identity, []).append(operation["op_id"])
        needs: dict[str, set[str]] = {}
        for operation in operations:
            needs[operation["op_id"]] = {op_id for identity in self.op_needs.get(operation["op_id"], set())
                                         for op_id in targets.get(identity, [])}
        ordered, cycles = sort_operations(operations, needs)
        by_id = {operation["op_id"]: operation for operation in ordered}
        for cycle in cycles:
            first = by_id[cycle[0]]
            self._item(self.blocking, "dependency_cycle", first["row_key"], item_id="dependency_cycle:" + ",".join(cycle),
                       operations=cycle)
        for position, operation in enumerate(ordered):
            operation["order"] = position + 1
            operation["needs"] = sorted(needs[operation["op_id"]])
        steps = []
        for step in self.steps:
            if not step.operations:
                continue
            steps.append({
                "step_id": step.step_id,
                "kind": step.kind,
                "row_key": step.row_key,
                "row_id": self.by_key[step.row_key]["row_id"],
                "choice": step.choice,
                "source_id": step.source_id,
                "domain": step.domain,
                "object_type": step.object_type,
                "name": step.name,
                "change": change_of(step),
                "operation_ids": [operation["op_id"] for operation in sorted(step.operations, key=lambda item: item["order"])],
            })
        steps.sort(key=lambda item: (min(by_id[op_id]["order"] for op_id in item["operation_ids"]), item["step_id"]))
        blocking = sorted(self.blocking, key=lambda item: item["item_id"])
        warnings = sorted(self.warnings, key=lambda item: item["item_id"])
        status = STATUS_INVALID if blocking else STATUS_WARNINGS if warnings else STATUS_VALID
        return {
            "status": status,
            "summary": summary(steps),
            "steps": steps,
            "operations": ordered,
            "blocking": blocking,
            "warnings": warnings,
            "sources": list(self.data.sources.keys()),
        }


def change_of(step: _Step) -> str:
    names = {operation["op"] for operation in step.operations}
    if step.choice == PROMOTE or names & {"CREATE", "COPY_PAGE", "COPY_VISUAL", "CREATE_REPORT_MEASURE"} and step.choice != TAKE_PROPERTIES:
        if not any(operation["op"] == "COPY_PAGE" and operation.get("replace") for operation in step.operations):
            return "created"
    if step.choice == REMOVE:
        return "deleted"
    if names & {"RENAME", "RENAME_PAIR"}:
        return "renamed"
    return "modified"


def summary(steps: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    counts: dict[str, Any] = {}
    for domain in (MODEL, REPORT):
        selected = [step for step in steps if step["domain"] == domain]
        part: dict[str, Any] = {"steps": len(selected)}
        for change in ("created", "deleted", "modified", "renamed"):
            by_type: dict[str, int] = {}
            for step in selected:
                if step["change"] == change:
                    kind = "measure" if step["choice"] == PROMOTE else step["object_type"]
                    by_type[kind] = by_type.get(kind, 0) + 1
            part[change] = {"total": sum(by_type.values()), "by_type": dict(sorted(by_type.items()))}
        counts[domain] = part
    counts["steps"] = len(steps)
    return counts


def compile_plan(data: PlanInput) -> dict[str, Any]:
    """Give the plan: status, summary, plan steps, sorted operations, blocking items, and warnings."""

    return _Compiler(data).run()
