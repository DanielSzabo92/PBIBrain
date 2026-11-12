"""In-place bulk edits of the target, with no donor (issue #12, operation source "Edit target").

A bulk edit is one operation on a scope of target rows:

- ``rename``: ``{kind, find, replace, regex, match_case}``. Plain text or a regular
  expression; the replacement can use ``$1`` / ``${name}`` or ``\\1`` / ``\\g<name>``.
- ``set_property``: ``{kind, property, value}`` (``EDITABLE_PROPERTIES`` of the compiler).
- ``move_folder``: ``{kind, folder}``: the display folder of measures and columns.
- ``apply_naming_rules``: ``{kind, rule_ids}``: the name (and folder) that the confirmed
  Naming Rules propose, for each object that breaks one of them.
- ``delete``: ``{kind, policy}``: Remove with a Removal Policy (block or cascade).

The scope is ``{row_keys}`` or ``{filter}`` (the compare-row filters of section 6.5). Only
rows with a target model object are edited; each other row is in ``skipped`` with a reason.

Each edit becomes the ``edit`` Merge Choice of its row (or ``remove`` and a Removal
Policy), so the Change Plan, impact, validation, apply, and undo stay unchanged.
``POST edit-preview`` is a read: it compiles the plan with the edits and changes nothing.
The JS API ``target_edit_apply`` stores the same edits (ADR 0003: accepted state is
written only in process).
"""

from __future__ import annotations

import copy
import re
from typing import Any
from collections.abc import Mapping, Sequence

from backend.devcenter.compare import service as compare_service
from backend.devcenter.compare.extract import MODEL
from backend.devcenter.compare.rows import filter_rows
from backend.devcenter.errors import DevCenterError
from backend.devcenter.naming.objects import NamedObject
from backend.devcenter.naming.proposer import breaks, propose
from backend.devcenter.plan import compiler
from backend.devcenter.plan.compiler import EDIT, REMOVE, current_value, edit_value_error

RENAME = "rename"
SET_PROPERTY = "set_property"
MOVE_FOLDER = "move_folder"
APPLY_NAMING_RULES = "apply_naming_rules"
DELETE = "delete"
OPERATION_KINDS = (RENAME, SET_PROPERTY, MOVE_FOLDER, APPLY_NAMING_RULES, DELETE)
DELETE_POLICIES = (compiler.BLOCK, compiler.CASCADE)
FOLDER_KINDS = ("measure", "column")
MAX_ROWS = 5000
MAX_REFERENCES = 500
PREVIEW_REQUEST = "http/edit-preview.request.json"

_DOLLAR = re.compile(r"\$(?:(\d+)|\{(\w+)\})")


def _invalid(message: str, reason: str, **details: Any) -> DevCenterError:
    return DevCenterError("invalid_payload", message, {"reason": reason, **details})


def _python_replacement(text: str) -> str:
    """Accept ``$1`` and ``${name}`` (the form of most editors) next to Python's ``\\1`` and ``\\g<name>``."""

    return _DOLLAR.sub(lambda match: f"\\g<{match.group(1) or match.group(2)}>", text)


class _Renamer:
    def __init__(self, operation: Mapping[str, Any]) -> None:
        find = operation.get("find")
        replace = operation.get("replace", "")
        if not isinstance(find, str) or not find:
            raise _invalid("The rename needs a text to find.", "find_required", field="find")
        if not isinstance(replace, str):
            raise _invalid("The replacement must be text.", "invalid_replace", field="replace")
        flags = 0 if operation.get("match_case", True) else re.IGNORECASE
        pattern = find if operation.get("regex") else re.escape(find)
        try:
            self.pattern = re.compile(pattern, flags)
        except re.error as exc:
            raise _invalid(f"The regular expression is not valid: {exc}.", "invalid_regex", field="find") from exc
        self.replace = _python_replacement(replace) if operation.get("regex") else replace.replace("\\", "\\\\")
        try:
            self.pattern.sub(self.replace, "")
        except (re.error, IndexError) as exc:
            raise _invalid(f"The replacement is not valid: {exc}.", "invalid_replace", field="replace") from exc

    def __call__(self, name: str) -> str:
        try:
            return self.pattern.sub(self.replace, name)
        except (re.error, IndexError) as exc:
            raise _invalid(f"The replacement is not valid: {exc}.", "invalid_replace", field="replace") from exc


def _operation(payload: Mapping[str, Any]) -> dict[str, Any]:
    operation = payload.get("operation")
    if not isinstance(operation, Mapping) or operation.get("kind") not in OPERATION_KINDS:
        raise _invalid("The operation kind is not valid.", "invalid_operation", field="operation")
    operation = dict(operation)
    kind = operation["kind"]
    if kind == SET_PROPERTY and not isinstance(operation.get("property"), str):
        raise _invalid("The property is required.", "property_required", field="property")
    if kind == MOVE_FOLDER and operation.get("folder") is not None and not isinstance(operation.get("folder"), str):
        raise _invalid("The folder must be text or null.", "invalid_folder", field="folder")
    if kind == DELETE and operation.get("policy", compiler.BLOCK) not in DELETE_POLICIES:
        raise _invalid("The Removal Policy must be block or cascade.", "invalid_policy", field="policy")
    if kind == APPLY_NAMING_RULES and operation.get("rule_ids") is not None and not isinstance(operation.get("rule_ids"), list):
        raise _invalid("The rule IDs must be a list.", "invalid_rule_ids", field="rule_ids")
    return operation


def _scope_rows(rows: Sequence[Mapping[str, Any]], payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    scope = payload.get("scope")
    if not isinstance(scope, Mapping) or ("row_keys" not in scope and "filter" not in scope):
        raise _invalid("The scope needs row keys or a filter.", "scope_required", field="scope")
    if "row_keys" in scope:
        keys = scope.get("row_keys")
        if not isinstance(keys, list) or not keys or not all(isinstance(key, str) for key in keys):
            raise _invalid("The scope row keys must be a list of row keys.", "row_keys_required", field="scope")
        by_key = {row["row_key"]: row for row in rows}
        unknown = sorted(set(keys) - set(by_key))
        if unknown:
            raise DevCenterError("not_found", "A row key of the scope is not in the compare result.", {"row_keys": unknown[:20]})
        selected = [by_key[key] for key in dict.fromkeys(keys)]
    else:
        query = scope.get("filter")
        if not isinstance(query, Mapping):
            raise _invalid("The scope filter must be an object.", "invalid_filter", field="scope")
        selected = filter_rows(rows, {key: value if isinstance(value, list) else [value] for key, value in query.items()})
    if len(selected) > MAX_ROWS:
        raise _invalid(f"A bulk edit can change at most {MAX_ROWS} rows.", "too_many_rows", count=len(selected))
    return selected


class _Context:
    def __init__(self, devcenter: Any, document: Mapping[str, Any]) -> None:
        from backend.devcenter.plan import service as plan_service

        self.document = document
        self.model, self.report = compare_service.targets(document)
        if self.model is None:
            raise DevCenterError("action_not_allowed", "The session has no target model.", {"reason": "no_target_model"})
        self.result = compare_service.compute(devcenter, document)
        self.choices = document.get("merge_choices") or {}
        self.rules = list(plan_service._load_naming_rules(devcenter, document))

    def target(self, row: Mapping[str, Any]) -> Any:
        cell = next((item for item in row["cells"] if item["source_id"] == self.model and item["present"]), None)
        return self.result.objects[(self.model, cell["source_key"])] if cell else None

    def planned(self, row: Mapping[str, Any]) -> dict[str, Any]:
        """The current ``edit`` choice of the row, or an empty one."""

        choice = self.choices.get(row["row_key"])
        if isinstance(choice, Mapping) and choice.get("kind") == EDIT:
            return copy.deepcopy(dict(choice))
        return {"kind": EDIT}

    def named(self, row: Mapping[str, Any], item: Any, name: str) -> NamedObject:
        # The same object types as the plan compiler's name check (``_Compiler.named``).
        if item.kind == "table":
            object_type = item.subtype if item.subtype in {"calculated_table", "calculation_group"} else "table"
        elif item.kind == "column":
            object_type = item.subtype
        else:
            object_type = item.kind
        return NamedObject(object_type, name, item.table if item.kind != "table" else None)


def _row_view(row: Mapping[str, Any], item: Any) -> dict[str, Any]:
    return {"row_key": row["row_key"], "object_type": row["object_type"], "table": item.table if item.kind != "table" else None,
            "name": item.name}


def edit_changes(context: _Context, rows: Sequence[Mapping[str, Any]], operation: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Give ``changes`` (``{row_key, ..., choice, change}``) and ``skipped`` (``{row_key, reason}``) for the operation."""

    kind = operation["kind"]
    renamer = _Renamer(operation) if kind == RENAME else None
    rule_ids = set(operation.get("rule_ids") or [])
    rules = [rule for rule in context.rules if not rule_ids or rule["rule_id"] in rule_ids]
    if kind == APPLY_NAMING_RULES and not rules:
        raise DevCenterError("action_not_allowed", "No confirmed Naming Rule applies.", {"reason": "no_confirmed_rule"})
    changes: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for row in rows:
        item = context.target(row) if row["domain"] == MODEL else None
        if item is None:
            skipped.append({"row_key": row["row_key"], "reason": "no_target_object"})
            continue
        planned = context.planned(row)
        current_name = planned.get("new_name") or item.name
        values = dict(planned.get("set") or {})
        change: dict[str, Any]
        if kind == DELETE:
            changes.append({**_row_view(row, item), "choice": {"kind": REMOVE},
                            "policy": operation.get("policy", compiler.BLOCK), "change": {"kind": DELETE}})
            continue
        if kind == RENAME:
            assert renamer is not None
            if item.kind not in compiler.RENAMABLE_KINDS:
                skipped.append({"row_key": row["row_key"], "reason": "not_renamable"})
                continue
            new_name = renamer(current_name).strip()
            if not new_name:
                skipped.append({"row_key": row["row_key"], "reason": "empty_name"})
                continue
            if new_name == current_name:
                skipped.append({"row_key": row["row_key"], "reason": "no_match"})
                continue
            planned["new_name"] = new_name
            change = {"kind": RENAME, "old_name": current_name, "new_name": new_name}
        elif kind in {SET_PROPERTY, MOVE_FOLDER}:
            prop = "display_folder" if kind == MOVE_FOLDER else operation["property"]
            value = operation.get("folder") if kind == MOVE_FOLDER else operation.get("value")
            if kind == MOVE_FOLDER and item.kind not in FOLDER_KINDS:
                skipped.append({"row_key": row["row_key"], "reason": "no_folder"})
                continue
            if isinstance(value, str) and prop in {"display_folder", "description", "format_string", "data_category"}:
                value = value.strip() or None
            reason = edit_value_error(item.kind, prop, value)
            if reason is not None:
                skipped.append({"row_key": row["row_key"], "reason": reason})
                continue
            old = values.get(prop, current_value(item, prop))
            if old == value:
                skipped.append({"row_key": row["row_key"], "reason": "no_change"})
                continue
            values[prop] = value
            change = {"kind": SET_PROPERTY, "property": prop, "old": old, "new": value}
        else:
            if item.kind not in {"measure", "column", "table", "hierarchy"}:
                skipped.append({"row_key": row["row_key"], "reason": "not_renamable"})
                continue
            named = context.named(row, item, current_name)
            folder = values.get("display_folder", item.display_folder)
            context_of = {"table": named.table, "display_folder": folder}
            if not breaks(current_name, named.object_type, context_of, rules):
                skipped.append({"row_key": row["row_key"], "reason": "conforms"})
                continue
            proposal = propose(current_name, named.object_type, context_of, rules, [])
            change = {"kind": APPLY_NAMING_RULES, "old_name": current_name, "new_name": proposal["name"], "rule_ids": proposal["rule_ids"]}
            if proposal["name"] != current_name:
                planned["new_name"] = proposal["name"]
            if item.kind in FOLDER_KINDS and proposal.get("display_folder") != folder and proposal.get("display_folder") is not None:
                values["display_folder"] = proposal["display_folder"]
                change.update(old_folder=folder, new_folder=proposal["display_folder"])
            if "new_name" not in planned and "new_folder" not in change:
                skipped.append({"row_key": row["row_key"], "reason": "no_change"})
                continue
        if values:
            planned["set"] = values
        if planned.get("new_name") == item.name:
            planned.pop("new_name")
        changes.append({**_row_view(row, item), "choice": planned, "change": change})
    return changes, skipped


def with_edits(document: Mapping[str, Any], changes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """A copy of the session document with the edits as accepted Merge Choices and Removal Policies."""

    draft = copy.deepcopy(dict(document))
    choices = draft.setdefault("merge_choices", {})
    policies = draft.setdefault("removal_policies", {})
    for change in changes:
        choice = change["choice"]
        if choice.get("kind") == EDIT and "new_name" not in choice and not choice.get("set"):
            choices.pop(change["row_key"], None)
        else:
            choices[change["row_key"]] = copy.deepcopy(choice)
        if "policy" in change:
            policies[change["row_key"]] = {"policy": change["policy"]}
    return draft


def _references(plan: Mapping[str, Any], row_keys: set[str]) -> list[dict[str, Any]]:
    """Each rewritten reference of the plan steps of the edited rows: DAX (model and report) and report bindings."""

    steps = {step["step_id"] for step in plan["steps"] if step["row_key"] in row_keys}
    found = []
    for operation in plan["operations"]:
        if operation["step_id"] not in steps:
            continue
        if operation["op"] == "REWRITE_EXPRESSION":
            found.append({"kind": "expression", "domain": operation["domain"], "row_key": operation["row_key"],
                          "object_type": operation["object_type"], "table": operation["table"], "name": operation["name"],
                          "property": operation["property"], "old_text": operation["old_text"], "new_text": operation["new_text"]})
        elif operation["op"] == "REBIND_FIELD":
            found.append({"kind": "binding", "domain": operation["domain"], "row_key": operation["row_key"],
                          "object_type": operation["object_type"], "table": operation["table"], "name": operation["name"],
                          "pointer": operation["pointer"], "old": operation["old"], "new": operation["new"]})
    return found


def _compute(devcenter: Any, document: Mapping[str, Any], payload: Mapping[str, Any]) -> tuple[_Context, list, list]:
    operation = _operation(payload)
    context = _Context(devcenter, document)
    rows = _scope_rows(context.result.rows, payload)
    changes, skipped = edit_changes(context, rows, operation)
    return context, changes, skipped


def preview(devcenter: Any, payload: Mapping[str, Any]) -> dict[str, Any]:
    """``POST edit-preview``: the changes of a bulk edit and the plan with them. Changes no state and no file."""

    from backend.devcenter import contracts
    from backend.devcenter.plan import service as plan_service

    problems = contracts.errors(PREVIEW_REQUEST, payload)
    if problems:
        raise DevCenterError("invalid_payload", "The request is not valid.", {"errors": problems[:20]})
    document = plan_service._snapshot(devcenter)
    _, changes, skipped = _compute(devcenter, document, payload)
    plan = plan_service.build_plan(devcenter, with_edits(document, changes), include_proposals=True)
    references = _references(plan, {change["row_key"] for change in changes})
    keys = {change["row_key"] for change in changes}
    return {
        "revision": document["revision"],
        "operation": _operation(payload),
        "changes": [{key: value for key, value in change.items() if key != "choice"} for change in changes],
        "skipped": skipped,
        "references": references[:MAX_REFERENCES],
        "references_total": len(references),
        "plan": {
            "status": plan["status"],
            "summary": plan["summary"],
            "blocking": [item for item in plan["blocking"] if item["row_key"] in keys or item["row_key"] is None
                         or item["step_id"] in {step["step_id"] for step in plan["steps"] if step["row_key"] in keys}],
            "blocking_total": len(plan["blocking"]),
            "warnings_total": len(plan["warnings"]),
            "plan_hash": plan["plan_hash"],
        },
    }


def apply_edits(devcenter: Any, request: Mapping[str, Any]) -> dict[str, Any]:
    """JS API ``target_edit_apply``: store the edits as Merge Choices (and Removal Policies) in one revision."""

    with devcenter._lock:
        document = copy.deepcopy(devcenter._require_open().document)
        _, changes, skipped = _compute(devcenter, document, request)
        if not changes:
            raise DevCenterError("action_not_allowed", "The bulk edit changes no row.", {"reason": "no_change", "skipped": len(skipped)})
        keys = [change["row_key"] for change in changes]

        def mutate(draft: dict[str, Any]) -> tuple[Any, Any]:
            before = {"merge_choices": {key: copy.deepcopy(draft["merge_choices"].get(key)) for key in keys},
                      "removal_policies": {key: copy.deepcopy(draft.setdefault("removal_policies", {}).get(key)) for key in keys}}
            edited = with_edits(draft, changes)
            draft["merge_choices"] = edited["merge_choices"]
            draft["removal_policies"] = edited["removal_policies"]
            after = {"merge_choices": {key: copy.deepcopy(draft["merge_choices"].get(key)) for key in keys},
                     "removal_policies": {key: copy.deepcopy(draft["removal_policies"].get(key)) for key in keys}}
            return before, after

        saved = devcenter._change(request, "target_edit_apply", None, mutate)
        return {"revision": saved["revision"], "count": len(keys), "row_keys": keys, "skipped": skipped}
