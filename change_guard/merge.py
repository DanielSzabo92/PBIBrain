"""Guard for a merge Change Plan (technical design section 8, build step S8, ADR 0001).

The app writes the candidate files. No agent edits them, so an app write record
replaces the isolation receipt. The guard then proves the candidate:

- Write record: the candidate is exactly the baseline files plus the files of
  the app write step, and a hash binds the record to the compiled contract.
- Model: each changed TMDL file is canonical (byte-equal to the TOM
  serialization), the candidate model files are byte-equal to a new write of
  the plan operations, and each difference of the full TOM tree compare
  matches a plan operation. New and removed lineageTags match planned creates
  and deletes. A rename keeps all properties except the name.
- Report: a new file equals the planned content (normalized JSON), a removed
  file needs a planned delete, and a changed file has only its listed changes.
- Any other changed file rejects.
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
from typing import Any
from collections.abc import Callable, Iterable, Mapping, Sequence

from backend.diff.snapshots import MISSING
from backend.snapshots.manifest import canonical_json, content_hash, safe_path, source_manifest

MERGE_PROFILE = "merge"
MERGE_POLICY_VERSION = "guard-policy-merge-1"
WRITE_RECORD_VERSION = 1

MODEL_DOMAIN, REPORT_DOMAIN = "model", "report"
CHILD_KINDS = {"column": "columns", "measure": "measures", "hierarchy": "hierarchies", "partition": "partitions"}
MODEL_COLLECTIONS = {"table": "tables", "relationship": "relationships", "role": "roles", "expression": "expressions",
                     "function": "functions", "perspective": "perspectives", "culture": "cultures"}
TYPE_ALIASES = {"shared_expression": "expression", "calculation_group": "table"}
# Plan property names that the TOM tree compare reports under another name.
PROPERTY_ALIASES = {"role_filters": "tablePermissions", "format_string_expression": "formatStringExpression"}
RENAME_OPS = {"RENAME", "RENAME_PAIR"}

# Reject codes and the gate of each code.
GATES = {
    "WRITE_RECORD_MISSING": "security", "WRITE_RECORD_HASH_MISMATCH": "security", "WRITE_RECORD_FILE_MISMATCH": "security",
    "NON_CANONICAL_BASELINE_FILE": "source", "NON_CANONICAL_MODEL_FILE": "source", "MODEL_NOT_PLAN_OUTPUT": "source",
    "MODEL_LOAD_FAILED": "source", "UNPLANNED_FILE_CREATED": "source", "UNPLANNED_FILE_DELETED": "source",
    "UNPLANNED_FILE_CHANGED": "source",
    "UNPLANNED_MODEL_CHANGE": "scope", "REQUIRED_MODEL_CHANGE_MISSING": "scope", "UNPLANNED_IDENTITY_ENTRY": "scope",
    "UNPLANNED_IDENTITY_REMOVAL": "scope", "RENAME_PAIR_PROPERTY_CHANGED": "scope", "FORMAT_ONLY_MODEL_CHANGED": "scope",
    "UNPLANNED_REPORT_PROPERTY": "scope", "REQUIRED_REPORT_CHANGE_MISSING": "scope", "REPORT_FILE_CONTENT_MISMATCH": "scope",
}


class MergeGuardError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def is_merge_contract(document: Mapping[str, Any]) -> bool:
    return isinstance(document.get("merge"), Mapping)


def _fold(value: Any) -> str:
    return str(value or "").casefold()


def _kind(value: Any) -> str:
    kind = _fold(value)
    return TYPE_ALIASES.get(kind, kind)


def _camel(name: str) -> str:
    if name in PROPERTY_ALIASES:
        return PROPERTY_ALIASES[name]
    head, *rest = name.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in rest)


def _json(data: bytes) -> Any:
    return json.loads(data.decode("utf-8-sig"))


def _under(relative: str, folder: str | None) -> bool:
    return bool(folder) and (relative == folder or relative.startswith(folder.rstrip("/") + "/"))


# JSON property differences (report files) -------------------------------------------------

def _escape(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def json_changes(before: Any, after: Any, pointer: str = "") -> list[dict[str, Any]]:
    """Give the leaf changes between two JSON values. Arrays are atomic values."""
    if canonical_json(before) == canonical_json(after):
        return []
    if isinstance(before, dict) and isinstance(after, dict):
        changes = []
        for key in sorted(set(before) | set(after)):
            changes.extend(json_changes(before.get(key, MISSING), after.get(key, MISSING), pointer + "/" + _escape(key)))
        return changes
    return [{"pointer": pointer, "before": before, "after": after}]


# Contract compile -------------------------------------------------------------------------

def _mutation(op: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    object_id = f"{op['row_key']}#{op['op_id']}"
    guard_op = op.get("guard_op") or "SET_PROPERTY"
    if guard_op in {"CREATE_OBJECT", "DELETE_OBJECT"}:
        prop = "$object"
    elif guard_op in {"RENAME_OBJECT", "RENAME_PAIR"}:
        prop = "name"
    elif guard_op == "REPLACE_EXPRESSION":
        prop = str(op.get("property") or "expression")
    elif guard_op == "CHANGE_BINDING":
        prop = str(op.get("pointer") or "$binding")
    else:
        prop = "$properties"
    before = MISSING if guard_op == "CREATE_OBJECT" else {"plan_operation": op["op_id"]}
    after = MISSING if guard_op == "DELETE_OBJECT" else {"plan_operation_hash": content_hash(dict(op))}
    target = {"object_id": object_id, "object_type": str(op.get("object_type") or "object").upper()}
    return target, {"object_id": object_id, "operation": guard_op, "property": prop, "expected_before": before, "expected_after": after}


def _report_expectations(baseline_root: Path, staged_root: Path, written: Mapping[str, Any]) -> dict[str, Any]:
    created, deleted, changed = {}, [], {}
    for relative in sorted(written):
        if written[relative] is None:
            deleted.append(relative)
            continue
        new = safe_path(staged_root, relative, must_exist=True).read_bytes()
        old_path = baseline_root / relative
        if not old_path.is_file():
            created[relative] = _json(new) if Path(relative).suffix.casefold() in {".json", ".pbir"} else {"$content_hash": content_hash(new)}
        elif Path(relative).suffix.casefold() in {".json", ".pbir"}:
            changed[relative] = json_changes(_json(old_path.read_bytes()), _json(new))
        else:
            changed[relative] = [{"pointer": "$content_hash", "before": content_hash(old_path.read_bytes()), "after": content_hash(new)}]
    return {"created": created, "deleted": deleted, "changed": changed}


def build_merge_proposal(source_root: str | Path, plan: Mapping[str, Any], *, project_id: str, baseline: Mapping[str, Any],
                         model_path: str | None, report_path: str | None, adapter: Any, task_id: str | None = None,
                         donor_paths: Mapping[str, str] | None = None, format_only: bool = False,
                         unchecked_items: Sequence[Mapping[str, Any]] = (), report_writer: Callable | None = None) -> dict[str, Any]:
    """Compile a merge Change Plan into an exact guard contract.

    The contract holds the ordered plan operations. The report file changes come
    from a trial write, so the guard can compare each report file property later.
    """
    root = Path(source_root).absolute()
    operations = [dict(item) for item in plan.get("operations", [])]
    if format_only and operations:
        raise MergeGuardError("INVALID_CONTRACT", "A format only apply has no plan operations")
    if not format_only and not operations:
        raise MergeGuardError("INVALID_CONTRACT", "The plan has no operations")
    merge = {"profile": MERGE_PROFILE, "plan_hash": str(plan.get("plan_hash") or content_hash(operations)), "format_only": format_only,
             "model_path": model_path, "report_path": report_path, "donor_paths": dict(donor_paths or {}),
             "operations": operations, "unchecked_items": [dict(item) for item in unchecked_items],
             "report_files": {"created": {}, "deleted": [], "changed": {}}}
    with tempfile.TemporaryDirectory(prefix="merge-plan-") as work:
        staged = Path(work) / "staged"
        written = write_merge_files(root, staged, merge, adapter, Path(work) / "writers", report_writer=report_writer, stage_only=True)
        merge["report_files"] = _report_expectations(root, staged, {key: value for key, value in written.items() if _under(key, report_path)})
    if format_only:
        targets = [{"object_id": "model#format-only", "object_type": "MODEL"}]
        mutations = [{"object_id": "model#format-only", "operation": "SET_PROPERTY", "property": "$format",
                      "expected_before": {"format_only": True}, "expected_after": {"format_only": True}}]
    else:
        pairs = [_mutation(op) for op in operations]
        targets, mutations = [pair[0] for pair in pairs], [pair[1] for pair in pairs]
    creates = any(item["operation"] == "CREATE_OBJECT" for item in mutations)
    deletes = any(item["operation"] == "DELETE_OBJECT" for item in mutations)
    return {"contract_version": 1, "task_id": task_id or "merge-" + merge["plan_hash"][:16], "project_id": project_id,
            "baseline": {"snapshot_id": baseline["snapshot_id"], "source_revision": baseline.get("source_revision")},
            "intent": {"description": "Apply the merge Change Plan " + merge["plan_hash"][:16], "category": "MERGE"},
            "targets": targets, "allowed_mutations": mutations,
            "forbidden": {"allow_unlisted_mutations": False, "allow_object_creation": creates, "allow_object_deletion": deletes,
                          "allow_identity_changes": creates or deletes},
            "behavior": {"permitted_effects": [], "invariants": []},
            "validation": {"require_static_validation": True, "require_runtime_validation": False, "require_impact_analysis": False,
                           "require_complete_dependency_coverage": False},
            "approval": {"scope_expansion": "EXPLICIT", "unexpected_behavior": "EXPLICIT", "high_risk_promotion": "EXPLICIT"},
            "merge": merge}


def merge_impact(contract: Mapping[str, Any], baseline_snapshot_id: str) -> dict[str, Any]:
    """Impact record for a merge. The app impact data (S6) is the source; the guard does not compute it.

    The policy needs the explicit user approval for each item that the app did not check.
    """
    merge = contract["merge"]
    body = {"impact_version": 1, "kind": "MERGE_PLAN", "baseline_snapshot_id": baseline_snapshot_id, "plan_hash": merge["plan_hash"],
            "unchecked_items": merge["unchecked_items"], "unknown_impacts": [],
            "completeness": {"status": "INCOMPLETE" if merge["unchecked_items"] else "COMPLETE", "source": "change_plan"}}
    return {**body, "impact_report_id": content_hash(body)}


def validate_merge_section(merge: Any) -> None:
    """Fail closed on a malformed merge section. The guard trusts nothing that it does not check."""
    required = {"profile", "plan_hash", "format_only", "model_path", "report_path", "donor_paths", "operations", "unchecked_items", "report_files"}
    if not isinstance(merge, dict) or set(merge) != required or merge["profile"] != MERGE_PROFILE or type(merge["format_only"]) is not bool:
        raise MergeGuardError("INVALID_CONTRACT", "Merge section is missing or has unknown fields")
    if not isinstance(merge["operations"], list) or any(not isinstance(item, dict) or not item.get("op_id") or item.get("domain") not in {MODEL_DOMAIN, REPORT_DOMAIN}
                                                        for item in merge["operations"]):
        raise MergeGuardError("INVALID_CONTRACT", "Each merge operation needs an op_id and a domain")
    for key in ("model_path", "report_path"):
        if merge[key] is not None and (not isinstance(merge[key], str) or not merge[key] or merge[key].startswith(("/", "\\")) or ".." in Path(merge[key]).parts):
            raise MergeGuardError("INVALID_CONTRACT", "Merge paths must be relative to the project root")
    files = merge["report_files"]
    if not isinstance(files, dict) or set(files) != {"created", "deleted", "changed"} or not isinstance(files["deleted"], list):
        raise MergeGuardError("INVALID_CONTRACT", "Report file expectations are invalid")
    for relative in [*files["created"], *files["deleted"], *files["changed"]]:
        if not _under(relative, merge["report_path"]):
            raise MergeGuardError("INVALID_CONTRACT", "A report file expectation is outside the report folder")
    if not isinstance(merge["donor_paths"], dict) or not isinstance(merge["unchecked_items"], list):
        raise MergeGuardError("INVALID_CONTRACT", "Donor paths or unchecked items are invalid")


# App write step and write record ----------------------------------------------------------

def write_merge_files(baseline_root: Path, candidate_root: Path, merge: Mapping[str, Any], adapter: Any, work: Path, *,
                      report_writer: Callable | None = None, stage_only: bool = False) -> dict[str, str | None]:
    """Run the app writers. Copy only the changed files into the candidate. Give {relative path: hash or None}."""
    written: dict[str, str | None] = {}
    operations = merge["operations"]

    def take(folder: str, output: Path, result: Mapping[str, Any]) -> None:
        for name in [*result.get("changed_files", []), *result.get("added_files", [])]:
            relative = folder.rstrip("/") + "/" + name.replace("\\", "/")
            data = safe_path(output, name, must_exist=True).read_bytes()
            target = candidate_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            written[relative] = content_hash(data)
        for name in result.get("removed_files", []):
            relative = folder.rstrip("/") + "/" + name.replace("\\", "/")
            target = candidate_root / relative
            if not stage_only and target.is_file():
                target.unlink()
            written[relative] = None

    model_ops = [item for item in operations if item["domain"] == MODEL_DOMAIN]
    if merge["model_path"] and (model_ops or merge["format_only"]):
        output = work / "model"
        result = adapter.write_model(baseline_root / merge["model_path"], output, model_ops)
        take(merge["model_path"], output, result)
    report_ops = [item for item in operations if item["domain"] == REPORT_DOMAIN]
    if merge["report_path"] and report_ops:
        if report_writer is None:
            from backend.adapters.pbir import write_report as report_writer
        output = work / "report"
        result = report_writer(baseline_root / merge["report_path"], output, report_ops, donor_paths=merge["donor_paths"] or None)
        take(merge["report_path"], output, result)
    return written


def write_record(contract_hash: str, baseline_manifest: Sequence[Mapping[str, Any]], files: Mapping[str, str | None]) -> dict[str, Any]:
    body = {"record_version": WRITE_RECORD_VERSION, "contract_hash": contract_hash, "baseline_manifest_hash": content_hash(list(baseline_manifest)),
            "files": dict(sorted(files.items()))}
    return {**body, "record_hash": content_hash(body)}


def _check_write_record(record: Any, contract_hash: str, baseline: list, candidate: list) -> list[dict[str, Any]]:
    if not isinstance(record, dict) or not record:
        return [{"code": "WRITE_RECORD_MISSING"}]
    body = {key: value for key, value in record.items() if key != "record_hash"}
    if record.get("record_hash") != content_hash(body) or record.get("contract_hash") != contract_hash \
            or record.get("baseline_manifest_hash") != content_hash(baseline) or record.get("record_version") != WRITE_RECORD_VERSION:
        return [{"code": "WRITE_RECORD_HASH_MISMATCH"}]
    expected = {item["path"]: item["hash"] for item in baseline}
    for relative, digest in record["files"].items():
        if digest is None:
            expected.pop(relative, None)
        else:
            expected[relative] = digest
    actual = {item["path"]: item["hash"] for item in candidate}
    extra = sorted(set(actual) - set(expected))
    missing = sorted(set(expected) - set(actual))
    different = sorted(key for key in set(actual) & set(expected) if actual[key] != expected[key])
    if extra or missing or different:
        return [{"code": "WRITE_RECORD_FILE_MISMATCH", "extra_files": extra, "missing_files": missing, "changed_files": different}]
    return []


# Model proof -------------------------------------------------------------------------------

def _named(items: Iterable[Any], name: str) -> dict | None:
    matches = [item for item in items or [] if isinstance(item, dict) and _fold(item.get("name")) == _fold(name)]
    return matches[0] if len(matches) == 1 else None


def find_object(database: Mapping[str, Any], kind: str, name: str, table: str | None) -> dict | None:
    model = database.get("model") or {}
    kind = _kind(kind)
    if kind in MODEL_COLLECTIONS:
        return _named(model.get(MODEL_COLLECTIONS[kind]), name)
    owner = _named(model.get("tables"), table or "")
    if owner is None:
        return None
    if kind == "calculation_item":
        return _named((owner.get("calculationGroup") or {}).get("calculationItems"), name)
    if kind in CHILD_KINDS:
        return _named(owner.get(CHILD_KINDS[kind]), name)
    return None


def lineage_tags(value: Any) -> set[str]:
    tags = set()
    if isinstance(value, dict):
        if isinstance(value.get("lineageTag"), str):
            tags.add(value["lineageTag"])
        for item in value.values():
            tags |= lineage_tags(item)
    elif isinstance(value, list):
        for item in value:
            tags |= lineage_tags(item)
    return tags


def _planned_tags(value: Any) -> set[str]:
    tags = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"lineage_tag", "lineageTag"} and isinstance(item, str) and item:
                tags.add(item)
            else:
                tags |= _planned_tags(item)
    elif isinstance(value, list):
        for item in value:
            tags |= _planned_tags(item)
    return tags


class ModelPlan:
    """The model operations of a plan, with the name aliases that renames make."""

    def __init__(self, operations: Sequence[Mapping[str, Any]]) -> None:
        self.ops = [dict(item) for item in operations if item.get("domain", MODEL_DOMAIN) == MODEL_DOMAIN]
        # Each rename: (kind, folded table, folded old name, new name as written).
        self.renames = [(_kind(op["object_type"]), _fold(op.get("table")), _fold(op.get("old_name") or op["name"]), str(op["new_name"]))
                        for op in self.ops if op["op"] in RENAME_OPS]
        self.table_renames = {old: new for kind, _, old, new in self.renames if kind == "table"}

    def table_aliases(self, table: str | None) -> set[str]:
        folded = _fold(table)
        aliases = {folded}
        for old, new in self.table_renames.items():
            if folded in {old, _fold(new)}:
                aliases |= {old, _fold(new)}
        return aliases

    def name_aliases(self, kind: str, name: str, table: str | None) -> set[str]:
        folded = _fold(name)
        aliases = {folded}
        for rename_kind, rename_table, old, new in self.renames:
            if rename_kind == kind and folded in {old, _fold(new)} and (kind not in CHILD_KINDS and kind != "calculation_item" or rename_table in self.table_aliases(table)):
                aliases |= {old, _fold(new)}
        return aliases

    def targets(self, op: Mapping[str, Any], kind: str, name: str, table: str | None) -> bool:
        if _kind(op["object_type"]) != kind:
            return False
        own = {_fold(op["name"]), _fold(op.get("old_name")), _fold(op.get("new_name"))} - {""}
        if not own & self.name_aliases(kind, name, table):
            return False
        if kind in CHILD_KINDS or kind == "calculation_item":
            return bool(self.table_aliases(op.get("table")) & self.table_aliases(table))
        return True

    def ops_for(self, kind: str, name: str, table: str | None, names: set[str]) -> list[dict[str, Any]]:
        return [op for op in self.ops if op["op"] in names and self.targets(op, kind, name, table)]

    def parent_changed(self, op: Mapping[str, Any]) -> bool:
        """True when the table of a child object is created, deleted, or renamed (tree compare does not go into it)."""
        if _kind(op["object_type"]) not in CHILD_KINDS and _kind(op["object_type"]) != "calculation_item":
            return False
        aliases = self.table_aliases(op.get("table"))
        return any(_kind(item["object_type"]) == "table" and item["op"] in {"CREATE", "DELETE", *RENAME_OPS}
                   and ({_fold(item["name"]), _fold(item.get("new_name"))} & aliases) for item in self.ops)

    def substitute(self, value: Any, kinds: set[str]) -> Any:
        """Replace renamed names in a reference value (rename consequences that TOM writes)."""
        if isinstance(value, str):
            for kind, _, old, new in self.renames:
                if kind in kinds and _fold(value) == old:
                    return new
            return value
        return value

    def references(self, value: Any) -> Any:
        """Give a copy of a TOM JSON value with renamed tables and columns in its reference fields."""
        if isinstance(value, list):
            return [self.references(item) for item in value]
        if not isinstance(value, dict):
            return value
        result = {}
        for key, item in value.items():
            if key in {"fromTable", "toTable", "table"}:
                result[key] = self.substitute(item, {"table"})
            elif key in {"fromColumn", "toColumn", "sortByColumn", "column"}:
                result[key] = self.substitute(item, {"column"})
            elif key == "tablePermissions" and isinstance(item, list):
                result[key] = [{**entry, "name": self.substitute(entry.get("name"), {"table"})} if isinstance(entry, dict) else entry for entry in item]
            else:
                result[key] = self.references(item)
        return result


def _property_planned(op: Mapping[str, Any], prop: str) -> bool:
    keys = {_camel(key) for key in (op.get("properties") or {})}
    if op.get("lineage_tag"):
        keys.add("lineageTag")
    return prop in keys


def _calculated_partition_planned(plan: ModelPlan, diff: Mapping[str, Any]) -> bool:
    """A calculated table keeps its DAX in its partition. A table expression operation changes that partition."""
    for op in plan.ops_for("table", diff.get("table") or "", None, {"SET_PROPERTIES", "REPLACE", "REWRITE_EXPRESSION"}):
        if op["op"] == "REPLACE" or (op["op"] == "SET_PROPERTIES" and "expression" in (op.get("properties") or {})):
            return True
        if op["op"] == "REWRITE_EXPRESSION" and op.get("property", "expression") == "expression" \
                and diff.get("old_value") == op.get("old_text") and diff.get("new_value") == op.get("new_text"):
            return True
    return False


def _match_difference(plan: ModelPlan, diff: Mapping[str, Any], base_db: Mapping, cand_db: Mapping, paired: set[str]) -> bool:
    kind, name, table, change = _kind(diff["object_type"]), diff["object_name"], diff.get("table"), diff["change_type"]
    if change == "ADDED":
        if plan.ops_for(kind, name, table, {"CREATE"}):
            return True
        return any(_fold(op["new_name"]) == _fold(name) for op in plan.ops_for(kind, name, table, RENAME_OPS)) or (kind == "relationship" and _fold(name) in paired)
    if change == "DELETED":
        if plan.ops_for(kind, name, table, {"DELETE"}):
            return True
        return any(_fold(op.get("old_name") or op["name"]) == _fold(name) for op in plan.ops_for(kind, name, table, RENAME_OPS)) \
            or (kind == "relationship" and _fold(name) in paired)
    prop = diff.get("property") or ""
    if kind == "partition" and prop == "expression" and _calculated_partition_planned(plan, diff):
        return True
    if prop == "lineageTag":
        return any(_property_planned(op, prop) for op in plan.ops_for(kind, name, table, {"SET_PROPERTIES"}))
    for op in plan.ops_for(kind, name, table, {"SET_PROPERTIES", "REPLACE", "REWRITE_EXPRESSION"}):
        if op["op"] == "REPLACE":
            return True
        if op["op"] == "SET_PROPERTIES" and _property_planned(op, prop):
            return True
        if op["op"] == "REWRITE_EXPRESSION":
            planned = _camel(str(op.get("property") or "expression"))
            planned = "tablePermissions" if planned.startswith("role_filters/") or planned.startswith("roleFilters/") else planned
            if planned == prop and (prop != "expression" or (diff.get("old_value") == op.get("old_text") and diff.get("new_value") == op.get("new_text"))):
                return True
    if prop == "sortByColumn" and plan.renames:
        return plan.substitute(diff.get("old_value"), {"column"}) == diff.get("new_value")
    if prop == "tablePermissions" and plan.table_renames:
        old = str(diff.get("old_value") or "")
        for before, after in plan.table_renames.items():
            old = ";".join((after if _fold(part.split(":", 1)[0]) == before else part.split(":", 1)[0]) + (":" + part.split(":", 1)[1] if ":" in part else "")
                           for part in old.split(";"))
        return old == diff.get("new_value")
    return False


def _relationship_pairs(plan: ModelPlan, differences: Sequence[Mapping[str, Any]], base_db: Mapping, cand_db: Mapping) -> set[str]:
    """Relationships that TOM keys again only because a planned rename changed a table or column name."""
    if not plan.renames:
        return set()
    added = {_fold(item["object_name"]) for item in differences if item["object_type"] == "relationship" and item["change_type"] == "ADDED"}
    deleted = {_fold(item["object_name"]) for item in differences if item["object_type"] == "relationship" and item["change_type"] == "DELETED"}
    pairs = set()
    for name in added & deleted:
        if plan.ops_for("relationship", name, None, {"CREATE", "DELETE", *RENAME_OPS}):
            continue
        old, new = find_object(base_db, "relationship", name, None), find_object(cand_db, "relationship", name, None)
        if old is None or new is None:
            continue
        expected = dict(old)
        for side in ("from", "to"):
            table = old.get(side + "Table")
            expected[side + "Table"] = next((n for o, n in plan.table_renames.items() if _fold(table) == o), table)
            column = old.get(side + "Column")
            expected[side + "Column"] = next((n for k, t, o, n in plan.renames if k == "column" and _fold(column) == o and t in plan.table_aliases(table)), column)
        if canonical_json(expected) == canonical_json(new):
            pairs.add(name)
    return pairs


def _strip_for_rename(plan: ModelPlan, op: Mapping[str, Any], value: Mapping[str, Any], *, before: bool) -> dict[str, Any]:
    kind = _kind(op["object_type"])
    name = op["new_name"]
    result = {key: item for key, item in value.items() if key != "name"}
    for other in plan.ops_for(kind, name, op.get("table"), {"SET_PROPERTIES", "REPLACE", "REWRITE_EXPRESSION"}):
        if other["op"] == "REPLACE":
            return {}
        for key in [*(other.get("properties") or {}), other.get("property") or ""]:
            result.pop(_camel(key) if key else "", None)
        if other["op"] == "REWRITE_EXPRESSION" and kind == "table":
            result.pop("partitions", None)
    if kind == "table":
        aliases = plan.table_aliases(name)
        touched = {_fold(n) for item in plan.ops if _kind(item["object_type"]) in {*CHILD_KINDS, "calculation_item"} and plan.table_aliases(item.get("table")) & aliases
                   for n in (item["name"], item.get("new_name"), item.get("old_name")) if n}
        for collection in CHILD_KINDS.values():
            if isinstance(result.get(collection), list):
                result[collection] = [child for child in result[collection] if _fold(child.get("name")) not in touched]
    return plan.references(result) if before else result


def _model_violations(baseline_model: Path, candidate_model: Path, merge: Mapping[str, Any], changed_tmdl: Sequence[str],
                      adapter: Any, work: Path) -> list[dict[str, Any]]:
    from backend.adapters.tabular_metadata import MetadataUnavailable
    violations: list[dict[str, Any]] = []
    plan = ModelPlan(merge["operations"])
    try:
        baseline_check = adapter.canonical_check(baseline_model)
        candidate_check = adapter.canonical_check(candidate_model)
        compare = adapter.tree_compare(baseline_model, candidate_model)
        base_db = adapter.read(baseline_model)["database"]
        cand_db = adapter.read(candidate_model)["database"]
        regenerated = work / "regenerated"
        adapter.write_model(baseline_model, regenerated, plan.ops)
    except MetadataUnavailable as error:
        return [{"code": "MODEL_LOAD_FAILED", "reason": getattr(error, "code", type(error).__name__)}]
    if not merge["format_only"]:
        for item in baseline_check.get("non_canonical_files", []):
            violations.append({"code": "NON_CANONICAL_BASELINE_FILE", "file": item["file"], "differences": item.get("differences", [])})
    changed = set(changed_tmdl)
    for item in candidate_check.get("non_canonical_files", []):
        violations.append({"code": "NON_CANONICAL_MODEL_FILE" if item["file"] in changed else "NON_CANONICAL_BASELINE_FILE",
                           "file": item["file"], "differences": item.get("differences", [])})
    # ADR 0001: the candidate model files must be the TOM output of the plan, byte for byte.
    candidate_files = {path.relative_to(candidate_model).as_posix(): path.read_bytes() for path in candidate_model.rglob("*.tmdl")}
    expected_files = {path.relative_to(regenerated).as_posix(): path.read_bytes() for path in regenerated.rglob("*.tmdl")}
    different = sorted(key for key in set(candidate_files) | set(expected_files) if candidate_files.get(key) != expected_files.get(key))
    if different:
        violations.append({"code": "MODEL_NOT_PLAN_OUTPUT", "files": different})
    differences = compare.get("differences", [])
    if merge["format_only"]:
        violations.extend({"code": "FORMAT_ONLY_MODEL_CHANGED", "difference": dict(item)} for item in differences)
        return violations
    paired = _relationship_pairs(plan, differences, base_db, cand_db)
    for item in differences:
        if not _match_difference(plan, item, base_db, cand_db, paired):
            violations.append({"code": "UNPLANNED_MODEL_CHANGE", "difference": dict(item)})
    reported = {(_kind(item["object_type"]), _fold(item["object_name"]), item["change_type"]) for item in differences}
    for op in plan.ops:
        kind = _kind(op["object_type"])
        if plan.parent_changed(op):
            continue
        expected = {"CREATE": [(op["name"], "ADDED")], "DELETE": [(op["name"], "DELETED")]}.get(op["op"], [])
        if op["op"] in RENAME_OPS:
            expected = [(op.get("old_name") or op["name"], "DELETED"), (op["new_name"], "ADDED")]
        for name, change in expected:
            if (kind, _fold(name), change) not in reported:
                violations.append({"code": "REQUIRED_MODEL_CHANGE_MISSING", "operation": op["op_id"], "object_type": kind, "object_name": name})
    # Identity map: new entries only for planned creates, removed entries only for planned deletes.
    base_tags, cand_tags = lineage_tags(base_db), lineage_tags(cand_db)
    planned_new, planned_removed = set(), set()
    for op in plan.ops:
        if op["op"] == "CREATE":
            planned_new |= _planned_tags(op)
        elif op["op"] == "DELETE":
            planned_removed |= lineage_tags(find_object(base_db, op["object_type"], op["name"], op.get("table")) or {})
        elif op["op"] in {"SET_PROPERTIES", "REPLACE"} and op.get("lineage_tag"):
            current = find_object(base_db, op["object_type"], op["name"], op.get("table")) or {}
            if current.get("lineageTag") != op["lineage_tag"]:
                planned_new.add(op["lineage_tag"])
                planned_removed |= {current["lineageTag"]} if current.get("lineageTag") else set()
    for tag in sorted((cand_tags - base_tags) - planned_new):
        violations.append({"code": "UNPLANNED_IDENTITY_ENTRY", "lineage_tag": tag})
    for tag in sorted((base_tags - cand_tags) - planned_removed):
        violations.append({"code": "UNPLANNED_IDENTITY_REMOVAL", "lineage_tag": tag})
    # A rename (also a delete-and-create pair without a lineageTag) changes only the name.
    for op in plan.ops:
        if op["op"] not in RENAME_OPS or plan.parent_changed(op):
            continue
        old = find_object(base_db, op["object_type"], op.get("old_name") or op["name"], op.get("table"))
        new = find_object(cand_db, op["object_type"], op["new_name"], op.get("table"))
        if old is None or new is None:
            continue
        if canonical_json(_strip_for_rename(plan, op, old, before=True)) != canonical_json(_strip_for_rename(plan, op, new, before=False)):
            violations.append({"code": "RENAME_PAIR_PROPERTY_CHANGED", "operation": op["op_id"], "object_type": _kind(op["object_type"]),
                               "old_name": op.get("old_name") or op["name"], "new_name": op["new_name"]})
    return violations


# Report proof ------------------------------------------------------------------------------

def _report_violations(baseline_root: Path, candidate_root: Path, files: Mapping[str, Any]) -> list[dict[str, Any]]:
    violations = []
    for relative, expected in files["created"].items():
        path = candidate_root / relative
        if not path.is_file():
            violations.append({"code": "REQUIRED_REPORT_CHANGE_MISSING", "file": relative})
            continue
        data = path.read_bytes()
        actual = _json(data) if "$content_hash" not in expected else {"$content_hash": content_hash(data)}
        if canonical_json(actual) != canonical_json(expected):
            violations.append({"code": "REPORT_FILE_CONTENT_MISMATCH", "file": relative,
                               "changes": json_changes(expected, actual)[:20] if "$content_hash" not in expected else []})
    for relative in files["deleted"]:
        if (candidate_root / relative).exists():
            violations.append({"code": "REQUIRED_REPORT_CHANGE_MISSING", "file": relative})
    for relative, listed in files["changed"].items():
        path = candidate_root / relative
        if not path.is_file():
            violations.append({"code": "UNPLANNED_FILE_DELETED", "file": relative})
            continue
        old, new = (baseline_root / relative).read_bytes(), path.read_bytes()
        if listed and listed[0]["pointer"] == "$content_hash":
            actual = [] if old == new else [{"pointer": "$content_hash", "before": content_hash(old), "after": content_hash(new)}]
        else:
            actual = json_changes(_json(old), _json(new))
        planned = {item["pointer"]: canonical_json([item["before"], item["after"]]) for item in listed}
        found = {item["pointer"]: canonical_json([item["before"], item["after"]]) for item in actual}
        for pointer in sorted(found):
            if planned.get(pointer) != found[pointer]:
                violations.append({"code": "UNPLANNED_REPORT_PROPERTY", "file": relative, "pointer": pointer})
        for pointer in sorted(set(planned) - set(found)):
            violations.append({"code": "REQUIRED_REPORT_CHANGE_MISSING", "file": relative, "pointer": pointer})
    return violations


# Verification ------------------------------------------------------------------------------

def verify_merge_candidate(contract: Mapping[str, Any], contract_hash: str, baseline_root: str | Path, candidate_root: str | Path,
                           record: Mapping[str, Any] | None, adapter: Any) -> dict[str, Any]:
    """Give the merge gate results: security (write record), source (file proof), and scope (plan match)."""
    merge = contract["merge"]
    validate_merge_section(merge)
    baseline_root, candidate_root = Path(baseline_root).absolute(), Path(candidate_root).absolute()
    baseline, candidate = source_manifest(baseline_root), source_manifest(candidate_root)
    violations = _check_write_record(record, contract_hash, baseline, candidate)
    old = {item["path"]: item["hash"] for item in baseline}
    new = {item["path"]: item["hash"] for item in candidate}
    changes = {key: "SOURCE_CREATED" if key not in old else "SOURCE_DELETED" if key not in new else "SOURCE_CHANGED"
               for key in sorted(set(old) | set(new)) if old.get(key) != new.get(key)}
    files = merge["report_files"]
    planned_report = {*files["created"], *files["deleted"], *files["changed"]}
    model_path = merge["model_path"]
    proven, changed_tmdl = [], []
    for relative, kind in changes.items():
        if _under(relative, model_path) and relative.casefold().endswith(".tmdl"):
            proven.append(relative)
            changed_tmdl.append(relative[len(model_path.rstrip("/")) + 1:])
        elif relative in planned_report:
            proven.append(relative)
        else:
            code = {"SOURCE_CREATED": "UNPLANNED_FILE_CREATED", "SOURCE_DELETED": "UNPLANNED_FILE_DELETED"}.get(kind, "UNPLANNED_FILE_CHANGED")
            violations.append({"code": code, "file": relative})
    if model_path and (baseline_root / model_path).is_dir():
        with tempfile.TemporaryDirectory(prefix="merge-guard-") as work:
            violations.extend(_model_violations(baseline_root / model_path, candidate_root / model_path, merge, changed_tmdl, adapter, Path(work)))
    if planned_report:
        violations.extend(_report_violations(baseline_root, candidate_root, files))
    for item in violations:
        item["gate"] = GATES[item["code"]]
    by_gate = {gate: [item for item in violations if item["gate"] == gate] for gate in ("security", "source", "scope")}
    return {"merge_verification_version": 1, "violations": violations, "proven_sources": sorted(proven),
            "security": {"status": "FAILED" if by_gate["security"] else "PASSED", "violations": by_gate["security"],
                         "write_record_hash": (record or {}).get("record_hash")},
            "source": {"status": "FAILED" if by_gate["source"] else "PASSED", "violations": by_gate["source"]},
            "scope": {"status": "REJECTED_SCOPE" if by_gate["scope"] else "PASSED", "scope_compliant": not by_gate["scope"], "violations": by_gate["scope"]}}

