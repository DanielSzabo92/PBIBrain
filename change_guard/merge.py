"""Change guard profile for Development Center merge operations (technical design sections 8, 16 S8, UC32)."""

from __future__ import annotations

import copy
from dataclasses import dataclass
import getpass
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from backend.adapters.pbir.validation import validate_report_documents
from backend.adapters.tabular_metadata import (
    CanonicalCheckFailed,
    MetadataUnavailable,
    TabularMetadataAdapter,
    TreeCompareFailed,
)
from backend.snapshots.manifest import canonical_json, content_hash, utc_now
from change_guard.audit import AuditStore
from change_guard.contracts import authorize_contract, validate_contract
from change_guard.policy.engine import MERGE_POLICY, Policy, classify_risk, evaluate_candidate

_EMPTY_MODEL_TMDL = re.compile(r"^\s*model\s+Model\s*$", re.IGNORECASE)
_STRUCTURAL_PBIR_CODES = frozenset({
    "PBIR_REQUIRED_ARTIFACT_MISSING",
    "PBIR_PAGE_COVERAGE_MISMATCH",
    "PBIR_ACTIVE_PAGE_UNRESOLVED",
    "PBIR_PAGE_ID_PATH_MISMATCH",
    "PBIR_UNSUPPORTED_ARTIFACT",
    "PBIR_SCHEMA_UNSUPPORTED",
    "PBIR_SCHEMA_INVALID",
})
_PROP_ALIASES: dict[str, str] = {
    "format_string": "formatString",
    "display_folder": "displayFolder",
    "is_hidden": "isHidden",
    "hidden": "isHidden",
    "data_type": "dataType",
    "summarize_by": "summarizeBy",
    "sort_by": "sortByColumn",
    "active": "isActive",
    "is_active": "isActive",
    "cross_filter_direction": "crossFilteringBehavior",
    "from_cardinality": "fromCardinality",
    "to_cardinality": "toCardinality",
    "assume_referential_integrity": "relyOnReferentialIntegrity",
    "lineage_tag": "lineageTag",
    "data_category": "dataCategory",
    "format_string_expression": "formatStringExpression",
    "ordinal": "ordinal",
    "model_permission": "modelPermission",
    "role_filters": "tablePermissions",
    "source_type": "sourceType",
    "expression": "expression",
    "description": "description",
    "mode": "mode",
    "levels": "levels",
    "kind": "kind",
}


class MergeGuardError(RuntimeError):
    """Structured rejection from the merge guard with UC32 check metadata."""

    def __init__(self, code: str, message: str, *, check: str, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.check = check
        self.details = {"check": check, **(dict(details or {}))}


def dir_file_hashes(root: Path | None, *, ignore_parts: Sequence[str] = (".pbi", ".pbibrain", ".git")) -> dict[str, str]:
    """Deterministic POSIX relative path -> content_hash map under root."""
    if root is None or not root.exists():
        return {}
    ignored = set(ignore_parts)
    out: dict[str, str] = {}
    for item in sorted(root.rglob("*")):
        if not item.is_file():
            continue
        rel_parts = item.relative_to(root).parts
        if any(part in ignored for part in rel_parts):
            continue
        out[item.relative_to(root).as_posix()] = content_hash(item.read_bytes())
    return out


def compute_write_record_hash(record: Mapping[str, Any]) -> str:
    payload = {k: v for k, v in dict(record).items() if k != "write_record_hash"}
    return content_hash(payload)


def build_write_record(
    *,
    contract_hash: str,
    plan_hash: str,
    mode: str = "apply",
    baseline_model_hashes: Mapping[str, str] | None = None,
    candidate_model_hashes: Mapping[str, str] | None = None,
    model_write: Mapping[str, Any] | None = None,
    baseline_report_hashes: Mapping[str, str] | None = None,
    candidate_report_hashes: Mapping[str, str] | None = None,
    report_write: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Create the deterministic app write record replacing container isolation receipt (section 8)."""
    mw = dict(model_write or {})
    rw = dict(report_write or {})
    record: dict[str, Any] = {
        "record_version": 1,
        "contract_hash": contract_hash,
        "plan_hash": plan_hash,
        "mode": mode,
        "baseline_model_hashes": dict(sorted((baseline_model_hashes or {}).items())),
        "candidate_model_hashes": dict(sorted((candidate_model_hashes or {}).items())),
        "model_changed_files": sorted(str(p) for p in mw.get("changed_files", ())),
        "model_added_files": sorted(str(p) for p in mw.get("added_files", ())),
        "model_removed_files": sorted(str(p) for p in mw.get("removed_files", ())),
        "baseline_report_hashes": dict(sorted((baseline_report_hashes or {}).items())),
        "candidate_report_hashes": dict(sorted((candidate_report_hashes or {}).items())),
        "report_changed_files": sorted(str(p) for p in rw.get("changed_files", ())),
        "report_added_files": sorted(str(p) for p in rw.get("added_files", ())),
        "report_removed_files": sorted(str(p) for p in rw.get("removed_files", ())),
    }
    record["write_record_hash"] = compute_write_record_hash(record)
    return record


def _safe_id(text: str) -> str:
    cleaned = re.sub(r"[*?\[\]{}]+", "_", text).strip()
    return cleaned or "object"


def build_merge_contract(
    *,
    project_id: str,
    session_id: str,
    baseline_snapshot_id: str,
    plan: Mapping[str, Any],
    mode: str = "apply",
    not_checked_items: Sequence[Mapping[str, Any]] = (),
    expected_created_definitions: Mapping[str, Mapping[str, Any]] | None = None,
    expected_added_pbir: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compile a validated Change Plan into a Guard v1 merge contract payload + auxiliary plan spec."""
    ops = list(plan.get("operations") or [])
    targets_map: dict[str, str] = {}
    mutations: list[dict[str, Any]] = []
    seen_mutation_keys: set[tuple[str, str]] = set()
    allow_create = False
    allow_delete = False
    allow_identity = False

    def _add_mut(oid: str, otype: str, op_name: str, prop: str, before: Any, after: Any) -> None:
        safe_oid = _safe_id(oid)
        targets_map.setdefault(safe_oid, _safe_id(otype.upper()))
        safe_prop = _safe_id(prop)
        idx = 0
        key = (safe_oid, safe_prop)
        while key in seen_mutation_keys:
            idx += 1
            safe_prop = _safe_id(f"{prop}#{idx}")
            key = (safe_oid, safe_prop)
        seen_mutation_keys.add(key)
        mutations.append({
            "object_id": safe_oid,
            "operation": op_name,
            "property": safe_prop,
            "expected_before": before,
            "expected_after": after,
        })

    if mode == "format_only":
        targets_map["$model"] = "MODEL"
        contract_doc = {
            "contract_version": 1,
            "task_id": _safe_id(f"merge-format-{session_id}"),
            "project_id": _safe_id(project_id),
            "profile": "merge",
            "mode": "format_only",
            "baseline": {"snapshot_id": _safe_id(baseline_snapshot_id), "source_revision": None},
            "intent": {"description": "Format target TMDL files canonically with zero semantic changes", "category": "MERGE_FORMAT_ONLY"},
            "targets": [{"object_id": "$model", "object_type": "MODEL"}],
            "allowed_mutations": [],
            "forbidden": {
                "allow_unlisted_mutations": False,
                "allow_object_creation": False,
                "allow_object_deletion": False,
                "allow_identity_changes": False,
            },
            "behavior": {"permitted_effects": [], "invariants": []},
            "validation": {
                "require_static_validation": True,
                "require_runtime_validation": False,
                "require_impact_analysis": True,
                "require_complete_dependency_coverage": False,
            },
            "approval": {"scope_expansion": "EXPLICIT", "unexpected_behavior": "EXPLICIT", "high_risk_promotion": "EXPLICIT"},
        }
        validate_contract(contract_doc)
        return {
            "contract": contract_doc,
            "contract_hash": content_hash(contract_doc),
            "plan_hash": plan.get("plan_hash"),
            "mode": mode,
            "model_operations": [],
            "report_operations": [],
            "not_checked_items": list(not_checked_items),
            "expected_created_definitions": {},
            "expected_added_pbir": {},
        }

    for op in ops:
        op_kind = str(op.get("op") or "")
        guard_op = str(op.get("guard_op") or "SET_PROPERTY")
        oid = str(op.get("row_key") or op.get("op_id") or "$model")
        otype = str(op.get("object_type") or "OBJECT")
        if guard_op == "CREATE_OBJECT":
            allow_create = True
            allow_identity = True
            _add_mut(oid, otype, "CREATE_OBJECT", "$object", {"$absent": True}, op.get("properties") or {"name": op.get("name")})
        elif guard_op == "DELETE_OBJECT":
            allow_delete = True
            allow_identity = True
            _add_mut(oid, otype, "DELETE_OBJECT", "$object", {"name": op.get("name"), "table": op.get("table")}, {"$absent": True})
        elif guard_op == "RENAME_OBJECT":
            _add_mut(oid, otype, "RENAME_OBJECT", "name", op.get("old_name") or op.get("name"), op.get("new_name"))
        elif guard_op == "RENAME_PAIR":
            allow_create = True
            allow_delete = True
            _add_mut(
                oid,
                otype,
                "RENAME_PAIR",
                "name",
                {"name": op.get("old_name") or op.get("name"), "properties": {"table": op.get("table")}},
                {"name": op.get("new_name"), "properties": {"table": op.get("table")}},
            )
        elif guard_op == "REPLACE_EXPRESSION":
            _add_mut(
                oid,
                otype,
                "REPLACE_EXPRESSION",
                op.get("property") or "expression",
                op.get("old_text", ""),
                op.get("new_text", ""),
            )
        elif guard_op == "CHANGE_BINDING":
            _add_mut(
                oid,
                otype,
                "CHANGE_BINDING",
                str(op.get("pointer") or "binding"),
                op.get("old") or op.get("query_ref", {}).get("old") or "",
                op.get("new") or op.get("query_ref", {}).get("new") or op_kind,
            )
        else:
            props = op.get("properties") or {}
            if not props:
                _add_mut(oid, otype, "SET_PROPERTY", "properties", None, True)
            else:
                for p_name, p_val in sorted(props.items()):
                    _add_mut(oid, otype, "SET_PROPERTY", str(p_name), None, p_val)

    if not targets_map:
        targets_map["$model"] = "MODEL"
        _add_mut("$model", "MODEL", "SET_PROPERTY", "$canonical_format", False, True)

    contract_doc = {
        "contract_version": 1,
        "task_id": _safe_id(f"merge-{session_id}"),
        "project_id": _safe_id(project_id),
        "profile": "merge",
        "mode": mode,
        "baseline": {"snapshot_id": _safe_id(baseline_snapshot_id), "source_revision": None},
        "intent": {"description": f"Apply Change Plan {plan.get('plan_hash', '')}", "category": "MERGE_PLAN"},
        "targets": [{"object_id": k, "object_type": v} for k, v in sorted(targets_map.items())],
        "allowed_mutations": mutations,
        "forbidden": {
            "allow_unlisted_mutations": False,
            "allow_object_creation": allow_create,
            "allow_object_deletion": allow_delete,
            "allow_identity_changes": allow_identity,
        },
        "behavior": {"permitted_effects": [], "invariants": []},
        "validation": {
            "require_static_validation": True,
            "require_runtime_validation": False,
            "require_impact_analysis": True,
            "require_complete_dependency_coverage": False,
        },
        "approval": {"scope_expansion": "EXPLICIT", "unexpected_behavior": "EXPLICIT", "high_risk_promotion": "EXPLICIT"},
    }
    validate_contract(contract_doc)
    return {
        "contract": contract_doc,
        "contract_hash": content_hash(contract_doc),
        "plan_hash": plan.get("plan_hash"),
        "mode": mode,
        "model_operations": [op for op in ops if op.get("domain") == "model"],
        "report_operations": [op for op in ops if op.get("domain") == "report"],
        "not_checked_items": list(not_checked_items),
        "expected_created_definitions": dict(expected_created_definitions or {}),
        "expected_added_pbir": dict(expected_added_pbir or {}),
    }


def _is_minimal_empty_model_tmdl(model_dir: Path | None, rel_path: str) -> bool:
    if model_dir is None:
        return False
    norm = rel_path.replace("\\", "/").casefold()
    if norm not in {"model.tmdl", "definition/model.tmdl"}:
        return False
    target = model_dir / rel_path
    if not target.is_file():
        return False
    text = target.read_text(encoding="utf-8-sig")
    if "culture:" in text.casefold():
        return False
    return bool(_EMPTY_MODEL_TMDL.match(text))


def _canonical_prop_name(name: str) -> str:
    return _PROP_ALIASES.get(name, name)


def _norm_str(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, bool):
        return "True" if val else "False"
    return str(val).replace("\r\n", "\n").strip()


def _extract_lineage_tags(tom_payload: Mapping[str, Any]) -> dict[str, tuple[str, str | None, str]]:
    """Map lineageTag -> (object_type, table, name) across a TOM read payload."""
    tags: dict[str, tuple[str, str | None, str]] = {}
    model = (tom_payload.get("database") or {}).get("model") or {}
    for tbl in model.get("tables", []):
        tname = tbl.get("name", "")
        if tbl.get("lineageTag"):
            tags[str(tbl["lineageTag"])] = ("table", None, tname)
        for col in tbl.get("columns", []):
            if col.get("lineageTag"):
                tags[str(col["lineageTag"])] = ("column", tname, col.get("name", ""))
        for ms in tbl.get("measures", []):
            if ms.get("lineageTag"):
                tags[str(ms["lineageTag"])] = ("measure", tname, ms.get("name", ""))
        for hi in tbl.get("hierarchies", []):
            if hi.get("lineageTag"):
                tags[str(hi["lineageTag"])] = ("hierarchy", tname, hi.get("name", ""))
    for expr in model.get("expressions", []):
        if expr.get("lineageTag"):
            tags[str(expr["lineageTag"])] = ("expression", None, expr.get("name", ""))
    for fn in model.get("functions", []):
        if fn.get("lineageTag"):
            tags[str(fn["lineageTag"])] = ("function", None, fn.get("name", ""))
    return tags


def _find_tom_object(tom_payload: Mapping[str, Any], obj_type: str, name: str, table: str | None) -> dict[str, Any] | None:
    model = (tom_payload.get("database") or {}).get("model") or {}
    ot = obj_type.casefold()
    n_fold = name.casefold()
    t_fold = (table or "").casefold()
    if ot == "table":
        return next((t for t in model.get("tables", []) if (t.get("name") or "").casefold() == n_fold), None)
    if ot in {"column", "measure", "hierarchy", "partition"}:
        tbl = next((t for t in model.get("tables", []) if (t.get("name") or "").casefold() == t_fold), None)
        if tbl is None:
            return None
        key = {"column": "columns", "measure": "measures", "hierarchy": "hierarchies", "partition": "partitions"}[ot]
        return next((item for item in tbl.get(key, []) if (item.get("name") or "").casefold() == n_fold), None)
    if ot == "calculation_item":
        tbl = next((t for t in model.get("tables", []) if (t.get("name") or "").casefold() == t_fold), None)
        if tbl is None:
            return None
        items = (tbl.get("calculationGroup") or {}).get("calculationItems") or []
        return next((item for item in items if (item.get("name") or "").casefold() == n_fold), None)
    if ot == "expression":
        return next((e for e in model.get("expressions", []) if (e.get("name") or "").casefold() == n_fold), None)
    if ot == "function":
        return next((f for f in model.get("functions", []) if (f.get("name") or "").casefold() == n_fold), None)
    if ot == "relationship":
        return next((r for r in model.get("relationships", []) if (r.get("name") or "").casefold() == n_fold), None)
    if ot == "role":
        return next((r for r in model.get("roles", []) if (r.get("name") or "").casefold() == n_fold), None)
    return None


@dataclass
class _ScopeRules:
    added: set[tuple[str, str, str]]
    deleted: set[tuple[str, str, str]]
    modified: dict[tuple[str, str, str, str], list[Mapping[str, Any]]]
    rename_pairs: list[Mapping[str, Any]]
    created_ops: list[Mapping[str, Any]]
    deleted_ops: list[Mapping[str, Any]]


def _compile_model_scope(model_operations: Sequence[Mapping[str, Any]]) -> _ScopeRules:
    added: set[tuple[str, str, str]] = set()
    deleted: set[tuple[str, str, str]] = set()
    modified: dict[tuple[str, str, str, str], list[Mapping[str, Any]]] = {}
    rename_pairs: list[Mapping[str, Any]] = []
    created_ops: list[Mapping[str, Any]] = []
    deleted_ops: list[Mapping[str, Any]] = []
    renamed_names: dict[tuple[str, str], str] = {}

    def _tbl(op: Mapping[str, Any]) -> str:
        return (op.get("table") or "").casefold()

    for op in model_operations:
        kind = str(op.get("op") or "")
        otype = str(op.get("object_type") or "").casefold()
        tbl = _tbl(op)
        name = str(op.get("name") or "")
        if kind in {"RENAME", "RENAME_PAIR"}:
            old_n = str(op.get("old_name") or name)
            new_n = str(op.get("new_name") or name)
            deleted.add((otype, old_n.casefold(), tbl))
            added.add((otype, new_n.casefold(), tbl))
            renamed_names[(otype, str(op.get("row_key") or ""))] = new_n
            if kind == "RENAME_PAIR":
                rename_pairs.append(op)
        elif kind == "CREATE":
            added.add((otype, name.casefold(), tbl))
            created_ops.append(op)
        elif kind == "DELETE":
            deleted.add((otype, name.casefold(), tbl))
            deleted_ops.append(op)

    for op in model_operations:
        kind = str(op.get("op") or "")
        otype = str(op.get("object_type") or "").casefold()
        tbl = _tbl(op)
        rk = str(op.get("row_key") or "")
        name = renamed_names.get((otype, rk), str(op.get("name") or ""))
        if kind in {"SET_PROPERTIES", "REPLACE"}:
            props = op.get("properties") or {}
            for p_name in props:
                tom_prop = _canonical_prop_name(str(p_name)).casefold()
                modified.setdefault((otype, name.casefold(), tbl, tom_prop), []).append(op)
            if kind == "REPLACE" and op.get("lineage_tag"):
                modified.setdefault((otype, name.casefold(), tbl, "lineagetag"), []).append(op)
        elif kind == "REWRITE_EXPRESSION":
            tom_prop = _canonical_prop_name(str(op.get("property") or "expression")).casefold()
            modified.setdefault((otype, name.casefold(), tbl, tom_prop), []).append(op)

    return _ScopeRules(
        added=added,
        deleted=deleted,
        modified=modified,
        rename_pairs=rename_pairs,
        created_ops=created_ops,
        deleted_ops=deleted_ops,
    )


def _json_leaf_diffs(before: Any, after: Any, path: str = "") -> list[tuple[str, Any, Any]]:
    if canonical_json(before) == canonical_json(after):
        return []
    if isinstance(before, dict) and isinstance(after, dict):
        out: list[tuple[str, Any, Any]] = []
        for k in sorted(set(before) | set(after)):
            sub = f"{path}.{k}" if path else str(k)
            if k not in before:
                out.append((sub, None, after[k]))
            elif k not in after:
                out.append((sub, before[k], None))
            else:
                out.extend(_json_leaf_diffs(before[k], after[k], sub))
        return out
    return [(path or "$", before, after)]


class MergeGuard:
    """Trusted verification and atomic promotion/recovery controller for Development Center merges (S8)."""

    def __init__(
        self,
        state_root: str | Path,
        *,
        adapter: TabularMetadataAdapter | None = None,
        policy: Policy | None = None,
        allowed_principals: Sequence[str] | None = None,
    ) -> None:
        self.store = AuditStore(state_root)
        self.adapter = adapter or TabularMetadataAdapter()
        self.policy = policy or MERGE_POLICY
        if self.policy.profile != "merge":
            raise ValueError("MergeGuard requires a Policy with profile='merge'")
        self.allowed_principals = tuple(allowed_principals or (getpass.getuser(),))

    def validate(
        self,
        *,
        merge_spec: Mapping[str, Any],
        write_record: Mapping[str, Any] | None,
        baseline_model_dir: Path | None = None,
        candidate_model_dir: Path | None = None,
        baseline_report_dir: Path | None = None,
        candidate_report_dir: Path | None = None,
        approvals: Sequence[str] = (),
        operation_id: str | None = None,
    ) -> dict[str, Any]:
        """Run every S8 gate on a candidate and evaluate the merge policy."""
        contract_doc = copy.deepcopy(dict(merge_spec["contract"]))
        contract_hash = str(merge_spec.get("contract_hash") or content_hash(contract_doc))
        mode = str(merge_spec.get("mode") or contract_doc.get("mode") or "apply")
        plan_hash = str(merge_spec.get("plan_hash") or "")
        model_ops = list(merge_spec.get("model_operations") or [])
        report_ops = list(merge_spec.get("report_operations") or [])
        not_checked = list(merge_spec.get("not_checked_items") or [])
        created_defs = dict(merge_spec.get("expected_created_definitions") or {})
        added_pbir = dict(merge_spec.get("expected_added_pbir") or {})

        principal = getpass.getuser()
        if principal not in self.allowed_principals:
            raise MergeGuardError("PRINCIPAL_NOT_AUTHORIZED", "Current OS user cannot verify merge.", check="policy")

        contract_obj = authorize_contract(contract_doc, principal, self.policy.version, objects=None)
        checks: dict[str, dict[str, Any]] = {
            "write_record": {"status": "NOT_RUN"},
            "scope": {"status": "NOT_RUN"},
            "baseline": {"status": "PASSED"},
            "source": {"status": "PASSED"},
            "static": {"status": "PASSED"},
            "canonical": {"status": "PASSED"},
            "tree_compare": {"status": "PASSED"},
            "pbir": {"status": "PASSED"},
            "identity_map": {"status": "PASSED"},
        }
        failures: list[dict[str, Any]] = []

        # 1. Write record & candidate folder scope proof
        wr_ok, wr_fail = self._check_write_record(
            write_record=write_record,
            contract_hash=contract_hash,
            plan_hash=plan_hash,
            mode=mode,
            baseline_model_dir=baseline_model_dir,
            candidate_model_dir=candidate_model_dir,
            baseline_report_dir=baseline_report_dir,
            candidate_report_dir=candidate_report_dir,
        )
        checks["write_record"] = {"status": "PASSED" if wr_ok else "FAILED", **({"failure": wr_fail} if wr_fail else {})}
        if not wr_ok:
            checks["scope"] = {"status": "FAILED", "failure": wr_fail}
            failures.append(wr_fail)
        else:
            checks["scope"] = {"status": "PASSED"}

        # 2. Model gates: Canonical TMDL check, TOM read, Full Tree Compare, Rename Pair, Identity Map
        baseline_tom: dict[str, Any] | None = None
        candidate_tom: dict[str, Any] | None = None
        if candidate_model_dir is not None and candidate_model_dir.exists():
            canon_ok, canon_fail = self._check_canonical(
                mode=mode,
                baseline_model_dir=baseline_model_dir,
                candidate_model_dir=candidate_model_dir,
            )
            checks["canonical"] = {"status": "PASSED" if canon_ok else "FAILED", **({"failure": canon_fail} if canon_fail else {})}
            if not canon_ok:
                failures.append(canon_fail)

            try:
                candidate_tom = self.adapter.read(candidate_model_dir)
                if baseline_model_dir is not None and baseline_model_dir.exists():
                    baseline_tom = self.adapter.read(baseline_model_dir)
            except MetadataUnavailable as exc:
                st_fail = {"check": "canonical", "code": "TOM_READ_FAILED", "message": str(exc)}
                checks["static"] = {"status": "FAILED", "failure": st_fail}
                failures.append(st_fail)

            if baseline_model_dir is not None and baseline_model_dir.exists() and candidate_tom is not None:
                tc_ok, tc_fail, id_ok, id_fail, sc_fail = self._check_tree_and_identity(
                    mode=mode,
                    baseline_model_dir=baseline_model_dir,
                    candidate_model_dir=candidate_model_dir,
                    baseline_tom=baseline_tom,
                    candidate_tom=candidate_tom,
                    model_ops=model_ops,
                    created_defs=created_defs,
                )
                checks["tree_compare"] = {"status": "PASSED" if tc_ok else "FAILED", **({"failure": tc_fail} if tc_fail else {})}
                checks["identity_map"] = {"status": "PASSED" if id_ok else "FAILED", **({"failure": id_fail} if id_fail else {})}
                if sc_fail is not None:
                    checks["scope"] = {"status": "FAILED", "failure": sc_fail}
                    failures.append(sc_fail)
                if not tc_ok:
                    failures.append(tc_fail)
                if not id_ok:
                    failures.append(id_fail)

        # 3. PBIR report gates
        if candidate_report_dir is not None and candidate_report_dir.exists():
            pbir_ok, pbir_fail = self._check_pbir(
                mode=mode,
                baseline_report_dir=baseline_report_dir,
                candidate_report_dir=candidate_report_dir,
                report_ops=report_ops,
                expected_added_pbir=added_pbir,
            )
            checks["pbir"] = {"status": "PASSED" if pbir_ok else "FAILED", **({"failure": pbir_fail} if pbir_fail else {})}
            if not pbir_ok:
                failures.append(pbir_fail)

        risk = classify_risk(contract_obj, self.policy)
        evidence_payload: dict[str, Any] = {
            **checks,
            "not_checked_items": not_checked,
            "contract_hash": contract_hash,
            "plan_hash": plan_hash,
            "risk": risk,
        }
        evidence_hash = content_hash(evidence_payload)
        valid_approvals = [purpose for purpose in approvals if purpose in {"HIGH_RISK_PROMOTION", "NOT_CHECKED_ITEMS", "UNEXPECTED_BEHAVIOR"}]
        decision = evaluate_candidate(contract_obj, {**evidence_payload, "valid_approval_operations": valid_approvals}, self.policy)

        approval_records: list[dict[str, Any]] = []
        if operation_id and valid_approvals and not failures:
            for purpose in dict.fromkeys(valid_approvals):
                rec = {
                    "operation_id": operation_id,
                    "contract_hash": contract_hash,
                    "evidence_hash": evidence_hash,
                    "policy_hash": self.policy.policy_hash,
                    "principal": principal,
                    "authorized_operation": purpose,
                    "authorized_at": utc_now(),
                }
                signed = self.store.sign(rec)
                self.store.save(f"{operation_id}/approval-{purpose}.json", signed)
                approval_records.append(rec)

        return {
            "decision": decision["decision"],
            "eligible_for_promotion": decision["eligible_for_promotion"] and not failures,
            "risk": risk,
            "checks": checks,
            "failures": failures,
            "blocking_reasons": decision["blocking_reasons"],
            "approval_reasons": decision["approval_reasons"],
            "approval_records": approval_records,
            "contract_hash": contract_hash,
            "evidence_hash": evidence_hash,
            "policy_hash": self.policy.policy_hash,
        }

    def _check_write_record(
        self,
        *,
        write_record: Mapping[str, Any] | None,
        contract_hash: str,
        plan_hash: str,
        mode: str,
        baseline_model_dir: Path | None,
        candidate_model_dir: Path | None,
        baseline_report_dir: Path | None,
        candidate_report_dir: Path | None,
    ) -> tuple[bool, dict[str, Any] | None]:
        if not isinstance(write_record, Mapping):
            return False, {"check": "scope", "code": "MISSING_WRITE_RECORD", "message": "Missing app write record."}
        expected_hash = compute_write_record_hash(write_record)
        if write_record.get("write_record_hash") != expected_hash:
            return False, {"check": "scope", "code": "WRITE_RECORD_HASH_MISMATCH", "message": "Write record hash does not match contents."}
        if write_record.get("contract_hash") != contract_hash:
            return False, {"check": "scope", "code": "WRITE_RECORD_HASH_MISMATCH", "message": "Write record is bound to a different contract."}
        if plan_hash and write_record.get("plan_hash") != plan_hash:
            return False, {"check": "scope", "code": "WRITE_RECORD_HASH_MISMATCH", "message": "Write record plan hash mismatch."}
        if write_record.get("mode") != mode:
            return False, {"check": "scope", "code": "WRITE_RECORD_HASH_MISMATCH", "message": "Write record mode mismatch."}

        if candidate_model_dir is not None and candidate_model_dir.exists():
            actual_cand = dir_file_hashes(candidate_model_dir)
            if actual_cand != write_record.get("candidate_model_hashes"):
                base_h = dir_file_hashes(baseline_model_dir) if baseline_model_dir else {}
                extra = sorted(set(actual_cand) - set(base_h) - set(write_record.get("model_added_files") or ()))
                removed = sorted(set(base_h) - set(actual_cand) - set(write_record.get("model_removed_files") or ()))
                code = "EXTRA_FILE" if extra else "REMOVED_FILE" if removed else "CANDIDATE_FILE_MISMATCH"
                return False, {
                    "check": "scope",
                    "code": code,
                    "message": "Candidate model files differ from write record.",
                    "extra_files": extra,
                    "removed_files": removed,
                }

        if candidate_report_dir is not None and candidate_report_dir.exists():
            actual_rep = dir_file_hashes(candidate_report_dir)
            if actual_rep != write_record.get("candidate_report_hashes"):
                base_r = dir_file_hashes(baseline_report_dir) if baseline_report_dir else {}
                extra = sorted(set(actual_rep) - set(base_r) - set(write_record.get("report_added_files") or ()))
                removed = sorted(set(base_r) - set(actual_rep) - set(write_record.get("report_removed_files") or ()))
                code = "EXTRA_FILE" if extra else "REMOVED_FILE" if removed else "CANDIDATE_FILE_MISMATCH"
                return False, {
                    "check": "scope",
                    "code": code,
                    "message": "Candidate report files differ from write record.",
                    "extra_files": extra,
                    "removed_files": removed,
                }
        return True, None

    def _check_canonical(
        self,
        *,
        mode: str,
        baseline_model_dir: Path | None,
        candidate_model_dir: Path,
    ) -> tuple[bool, dict[str, Any] | None]:
        if mode == "apply" and baseline_model_dir is not None and baseline_model_dir.exists():
            try:
                base_check = self.adapter.canonical_check(baseline_model_dir)
            except CanonicalCheckFailed as exc:
                return False, {"check": "canonical", "code": exc.code, "message": str(exc)}
            non_canon = [
                item["file"]
                for item in base_check.get("non_canonical_files", [])
                if not _is_minimal_empty_model_tmdl(baseline_model_dir, item.get("file", ""))
            ]
            if non_canon:
                return False, {
                    "check": "canonical",
                    "code": "NON_CANONICAL_BASELINE",
                    "message": "Target model has non-canonical TMDL files. Run Format only first.",
                    "files": non_canon,
                }

        try:
            cand_check = self.adapter.canonical_check(candidate_model_dir)
        except CanonicalCheckFailed as exc:
            return False, {"check": "canonical", "code": exc.code, "message": str(exc)}
        cand_bad = [
            item["file"]
            for item in cand_check.get("non_canonical_files", [])
            if not _is_minimal_empty_model_tmdl(candidate_model_dir, item.get("file", ""))
        ]
        if cand_bad:
            return False, {
                "check": "canonical",
                "code": "NON_CANONICAL_CANDIDATE",
                "message": "Candidate model contains non-canonical TMDL bytes.",
                "files": cand_bad,
            }
        return True, None

    def _check_tree_and_identity(
        self,
        *,
        mode: str,
        baseline_model_dir: Path,
        candidate_model_dir: Path,
        baseline_tom: Mapping[str, Any] | None,
        candidate_tom: Mapping[str, Any],
        model_ops: Sequence[Mapping[str, Any]],
        created_defs: Mapping[str, Mapping[str, Any]],
    ) -> tuple[bool, dict[str, Any] | None, bool, dict[str, Any] | None, dict[str, Any] | None]:
        try:
            tc = self.adapter.tree_compare(baseline_model_dir, candidate_model_dir)
        except TreeCompareFailed as exc:
            fail = {"check": "tree_compare", "code": exc.code, "message": str(exc)}
            return False, fail, True, None, None

        diffs = list(tc.get("differences") or [])
        if mode == "format_only":
            if not tc.get("identical", False) or diffs:
                return (
                    False,
                    {
                        "check": "tree_compare",
                        "code": "FORMAT_ONLY_SEMANTIC_CHANGE",
                        "message": "Format-only apply must leave the semantic model tree identical.",
                        "differences": diffs,
                    },
                    True,
                    None,
                    None,
                )
            return True, None, True, None, None

        rules = _compile_model_scope(model_ops)

        # Verify created definitions match plan when supplied
        for rk, expected in created_defs.items():
            otype = str(expected.get("object_type") or "")
            name = str(expected.get("name") or "")
            table = expected.get("table")
            actual = _find_tom_object(candidate_tom, otype, name, table)
            if actual is None:
                return (
                    True,
                    None,
                    True,
                    None,
                    {"check": "scope", "code": "CREATED_OBJECT_MISSING", "message": f"Planned created object {rk} missing in candidate."},
                )
            for k, v in (expected.get("properties") or {}).items():
                if k in {"source_file", "source_location"}:
                    continue
                tom_key = _canonical_prop_name(str(k))
                if tom_key in actual and _norm_str(actual.get(tom_key)) != _norm_str(v):
                    return (
                        True,
                        None,
                        True,
                        None,
                        {"check": "scope", "code": "CREATED_OBJECT_MISMATCH", "message": f"Created object {rk} property {k} differs from plan."},
                    )

        # Verify RENAME_PAIR invariance: all non-name properties must match baseline
        if baseline_tom is not None:
            for op in rules.rename_pairs:
                otype = str(op.get("object_type") or "")
                old_name = str(op.get("old_name") or op.get("name") or "")
                new_name = str(op.get("new_name") or "")
                tbl = op.get("table")
                before_obj = _find_tom_object(baseline_tom, otype, old_name, tbl)
                after_obj = _find_tom_object(candidate_tom, otype, new_name, tbl)
                if before_obj is None or after_obj is None:
                    return (
                        False,
                        {"check": "tree_compare", "code": "RENAME_PAIR_MISSING", "message": f"Rename pair target missing: {old_name} -> {new_name}"},
                        True,
                        None,
                        None,
                    )
                b_rest = {k: v for k, v in before_obj.items() if k not in {"name", "lineageTag"}}
                a_rest = {k: v for k, v in after_obj.items() if k not in {"name", "lineageTag"}}
                if canonical_json(b_rest) != canonical_json(a_rest):
                    return (
                        True,
                        None,
                        True,
                        None,
                        {"check": "scope", "code": "RENAME_PAIR_EXTRA_PROPERTY", "message": f"Rename pair {old_name} -> {new_name} altered another property."},
                    )

        # Every TreeCompare diff must correspond to an explicit planned op
        unplanned: list[Mapping[str, Any]] = []
        for diff in diffs:
            ot = str(diff.get("object_type") or "").casefold()
            oname = str(diff.get("object_name") or "").casefold()
            tbl = str(diff.get("table") or "").casefold()
            ctype = str(diff.get("change_type") or "")
            prop = str(diff.get("property") or "").casefold()
            if ctype == "ADDED":
                if (ot, oname, tbl) not in rules.added:
                    unplanned.append(diff)
            elif ctype == "DELETED":
                if (ot, oname, tbl) not in rules.deleted:
                    unplanned.append(diff)
            elif ctype == "MODIFIED":
                matching_ops = rules.modified.get((ot, oname, tbl, prop))
                if not matching_ops:
                    unplanned.append(diff)
                elif prop == "expression":
                    new_v = _norm_str(diff.get("new_value"))
                    matched_expr = any(
                        _norm_str(op.get("new_text") if op.get("op") == "REWRITE_EXPRESSION" else (op.get("properties") or {}).get("expression")) == new_v
                        for op in matching_ops
                    )
                    if not matched_expr:
                        unplanned.append(diff)
            else:
                unplanned.append(diff)

        if unplanned:
            tc_fail = {
                "check": "tree_compare",
                "code": "UNPLANNED_MODEL_CHANGE",
                "message": "Candidate model has changes outside the plan.",
                "differences": unplanned,
            }
            return False, tc_fail, True, None, None

        # Identity map (lineageTag) check
        if baseline_tom is not None:
            b_tags = _extract_lineage_tags(baseline_tom)
            c_tags = _extract_lineage_tags(candidate_tom)
            added_tags = set(c_tags) - set(b_tags)
            removed_tags = set(b_tags) - set(c_tags)
            planned_new_tags = {str(op["lineage_tag"]) for op in model_ops if op.get("lineage_tag")}
            extra_tags = [
                t for t in sorted(added_tags)
                if t not in planned_new_tags
                and (c_tags[t][0].casefold(), c_tags[t][2].casefold(), (c_tags[t][1] or "").casefold()) not in rules.added
            ]
            # Removing a deleted table also removes its child objects' lineageTags.
            deleted_tables = {name for otype, name, _tbl in rules.deleted if otype == "table"}
            extra_removed = [
                t for t in sorted(removed_tags)
                if (b_tags[t][0].casefold(), b_tags[t][2].casefold(), (b_tags[t][1] or "").casefold()) not in rules.deleted
                and (b_tags[t][1] or "").casefold() not in deleted_tables
            ]
            if extra_tags or extra_removed:
                id_fail = {
                    "check": "identity_map",
                    "code": "UNPLANNED_IDENTITY_CHANGE",
                    "message": "Unplanned lineageTag identity map additions or removals detected.",
                    "added_tags": extra_tags,
                    "removed_tags": extra_removed,
                }
                return True, None, False, id_fail, None

        return True, None, True, None, None

    def _check_pbir(
        self,
        *,
        mode: str,
        baseline_report_dir: Path | None,
        candidate_report_dir: Path,
        report_ops: Sequence[Mapping[str, Any]],
        expected_added_pbir: Mapping[str, Any],
    ) -> tuple[bool, dict[str, Any] | None]:
        base_files = dir_file_hashes(baseline_report_dir) if (baseline_report_dir and baseline_report_dir.exists()) else {}
        cand_files = dir_file_hashes(candidate_report_dir)
        if baseline_report_dir is not None and baseline_report_dir.exists() and base_files == cand_files and not report_ops:
            return True, None

        docs: dict[str, Any] = {}
        root_name = candidate_report_dir.name if candidate_report_dir.name.casefold().endswith(".report") else f"{candidate_report_dir.name}.Report"
        for fpath in sorted(candidate_report_dir.rglob("*")):
            if not fpath.is_file() or fpath.name == ".platform":
                continue
            if any(p in {".pbi", ".pbibrain", ".git"} for p in fpath.relative_to(candidate_report_dir).parts):
                continue
            if fpath.suffix.casefold() in {".json", ".pbir"}:
                rel = fpath.relative_to(candidate_report_dir).as_posix()
                try:
                    docs[f"{root_name}/{rel}"] = json.loads(fpath.read_text(encoding="utf-8-sig"))
                except (OSError, ValueError) as exc:
                    return False, {"check": "pbir", "code": "PBIR_SCHEMA_INVALID", "message": f"Invalid JSON in {rel}: {exc}"}

        if docs:
            val = validate_report_documents(docs)
            issues = []
            for issue in val.get("issues", []):
                if issue.get("code") not in _STRUCTURAL_PBIR_CODES:
                    continue
                if (
                    issue.get("code") == "PBIR_SCHEMA_UNSUPPORTED"
                    and issue.get("schema") is None
                    and str(issue.get("source_file") or "").endswith("/definition.pbir")
                    and base_files.get("definition.pbir") == cand_files.get("definition.pbir")
                    and isinstance(docs.get(issue["source_file"]), dict)
                    and isinstance(docs[issue["source_file"]].get("version"), str)
                    and "datasetReference" in docs[issue["source_file"]]
                ):
                    continue
                issues.append(issue)
            if issues:
                return False, {"check": "pbir", "code": "PBIR_SCHEMA_INVALID", "message": "Candidate PBIR failed validation.", "issues": issues}

        if baseline_report_dir is None or not baseline_report_dir.exists():
            return True, None

        if mode == "format_only":
            if base_files != cand_files:
                return False, {"check": "pbir", "code": "UNPLANNED_PBIR_CHANGE", "message": "Format-only must not modify report files."}
            return True, None

        added = set(cand_files) - set(base_files)
        removed = set(base_files) - set(cand_files)
        changed = {p for p in (set(cand_files) & set(base_files)) if cand_files[p] != base_files[p]}

        has_page_copy = any(op.get("op") == "COPY_PAGE" for op in report_ops)
        has_visual_copy = any(op.get("op") == "COPY_VISUAL" for op in report_ops)
        has_page_delete = any(op.get("op") == "DELETE_PAGE" for op in report_ops)
        has_visual_delete = any(op.get("op") == "DELETE_VISUAL" for op in report_ops)
        has_rm_op = any(op.get("op") in {"CREATE_REPORT_MEASURE", "REPLACE_REPORT_MEASURE", "DELETE_REPORT_MEASURE"} for op in report_ops)
        has_rebind = any(op.get("op") in {"REBIND_FIELD", "REMOVE_FIELD"} for op in report_ops)

        for rel, exp_doc in expected_added_pbir.items():
            target_f = candidate_report_dir / rel
            if not target_f.is_file():
                return False, {"check": "pbir", "code": "UNPLANNED_PBIR_CHANGE", "message": f"Missing planned PBIR file {rel}."}
            try:
                actual_doc = json.loads(target_f.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError):
                return False, {"check": "pbir", "code": "PBIR_SCHEMA_INVALID", "message": f"Added file {rel} is invalid JSON."}
            if canonical_json(actual_doc) != canonical_json(exp_doc):
                return False, {"check": "pbir", "code": "UNPLANNED_PBIR_CHANGE", "message": f"Added PBIR content mismatch at {rel}."}

        if added and not (has_page_copy or has_visual_copy or has_rm_op):
            return False, {"check": "pbir", "code": "UNPLANNED_PBIR_CHANGE", "message": "Unplanned added report files.", "files": sorted(added)}
        if removed and not (has_page_delete or has_visual_delete or has_rm_op):
            return False, {"check": "pbir", "code": "UNPLANNED_PBIR_CHANGE", "message": "Unplanned removed report files.", "files": sorted(removed)}

        allowed_visual_prefixes = ("visual.query", "visual.visualContainerObjects", "visual.objects", "filterConfig", "howCreated")
        allowed_page_prefixes = ("visualInteractions", "pageBinding", "filterConfig", "autoPageGenerationConfig")
        for rel in sorted(changed):
            if not rel.endswith(".json"):
                return False, {"check": "pbir", "code": "UNPLANNED_PBIR_CHANGE", "message": f"Unexpected changed report file {rel}."}
            old_doc = json.loads((baseline_report_dir / rel).read_text(encoding="utf-8-sig"))
            new_doc = json.loads((candidate_report_dir / rel).read_text(encoding="utf-8-sig"))
            leafs = _json_leaf_diffs(old_doc, new_doc)
            if rel == "definition/pages/pages.json":
                if not (has_page_copy or has_page_delete):
                    return False, {"check": "pbir", "code": "UNPLANNED_PBIR_CHANGE", "message": "pages.json changed without page copy/delete."}
                if any(not (path == "pageOrder" or path.startswith("pageOrder") or path == "activePageName") for path, _, _ in leafs):
                    return False, {"check": "pbir", "code": "UNPLANNED_PBIR_CHANGE", "message": "Unexpected property change in pages.json."}
            elif rel == "definition/reportExtensions.json":
                if not (has_rm_op or has_rebind):
                    return False, {"check": "pbir", "code": "UNPLANNED_PBIR_CHANGE", "message": "reportExtensions.json changed without report measure operation."}
            elif rel == "definition/report.json":
                if any(not (path.startswith("filterConfig") or path.startswith("objects")) for path, _, _ in leafs) or not (has_rebind or has_rm_op or has_page_copy):
                    return False, {"check": "pbir", "code": "UNPLANNED_PBIR_CHANGE", "message": f"Unexpected change in {rel}."}
            elif rel.endswith("/visual.json"):
                if not (has_rebind or has_visual_copy or has_page_copy):
                    return False, {"check": "pbir", "code": "UNPLANNED_PBIR_CHANGE", "message": f"{rel} changed without field/visual operation."}
                parts = rel.split("/")
                vid = parts[-2] if len(parts) >= 2 else ""
                if has_rebind and not (has_page_copy or has_visual_copy):
                    targeted_vids = {
                        str(op.get("row_key") or "").split("/")[-1]
                        for op in report_ops
                        if op.get("op") in {"REBIND_FIELD", "REMOVE_FIELD"}
                    }
                    if targeted_vids and vid not in targeted_vids:
                        return False, {"check": "pbir", "code": "UNPLANNED_PBIR_CHANGE", "message": f"Visual {rel} changed outside planned visuals."}
                for path, _, _ in leafs:
                    if not path.startswith(allowed_visual_prefixes) and path != "parentGroupName":
                        return False, {"check": "pbir", "code": "UNPLANNED_PBIR_CHANGE", "message": f"Unplanned property {path} in {rel}."}
            elif rel.endswith("/page.json"):
                if not (has_page_copy or has_visual_delete or has_rebind):
                    return False, {"check": "pbir", "code": "UNPLANNED_PBIR_CHANGE", "message": f"{rel} changed without page/rebind operation."}
                for path, _, _ in leafs:
                    if not path.startswith(allowed_page_prefixes):
                        return False, {"check": "pbir", "code": "UNPLANNED_PBIR_CHANGE", "message": f"Unplanned property {path} in {rel}."}
            else:
                return False, {"check": "pbir", "code": "UNPLANNED_PBIR_CHANGE", "message": f"Unplanned change in {rel}."}

        return True, None
