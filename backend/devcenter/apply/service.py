"""Local Development Center apply service (technical design section 13, S9, UC5/UC6/UC7/UC32)."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
import getpass
import json
from pathlib import Path
import shutil
import tempfile
import threading
import uuid
from typing import Any, Callable, Mapping, Sequence

from backend.adapters.pbir import PBIRWriteError, write_report
from backend.adapters.tabular_metadata import (
    CanonicalCheckFailed,
    MetadataUnavailable,
    ModelWriteFailed,
    TabularMetadataAdapter,
)
from backend.devcenter.apply.change_report import build_change_report, write_change_report
from backend.devcenter.apply.desktop_bridge import (
    DESKTOP_OPEN_SAVED,
    DESKTOP_OPEN_UNSAVED,
    DESKTOP_NOT_REACHABLE,
    check_desktop_state,
)
from backend.devcenter.compare import service as compare_service
from backend.devcenter.compare.extract import MODEL, REPORT, CompareObject, load_objects
from backend.devcenter.compare.rows import fold
from backend.devcenter.errors import DevCenterError
from backend.devcenter.impact import service as impact_service
from backend.devcenter.plan import service as plan_service
from backend.devcenter.session.store import write_atomic

STATUS_OK = "ok"
from backend.devcenter.sources.fingerprint import source_fingerprint
from backend.devcenter.sources.kinds import LocalSource, MODEL_TMDL, REPORT_PBIR, detect_local_source
from backend.devcenter.sources.objects import object_index
from backend.snapshots.manifest import canonical_json, content_hash
from change_guard.audit.records import durable_write
from change_guard.contracts import authorize_contract
from change_guard.merge import (
    MergeGuard,
    MergeGuardError,
    _is_minimal_empty_model_tmdl,
    build_merge_contract,
    build_write_record,
    dir_file_hashes,
)
from change_guard.policy.engine import MERGE_POLICY, classify_risk

APPLY_STEPS: tuple[str, ...] = (
    "source_check",
    "plan_check",
    "desktop_check",
    "canonical_check",
    "full_validation",
    "approval",
    "write_candidate",
    "guard_verify",
    "backup",
    "promote",
    "rescan",
    "update_fingerprints",
)

FORMAT_ONLY_STEPS: tuple[str, ...] = (
    "source_check",
    "desktop_check",
    "write_candidate",
    "guard_verify",
    "backup",
    "promote",
    "update_fingerprints",
)

UNDO_STEPS: tuple[str, ...] = (
    "check_backup",
    "verify_target",
    "restore_files",
    "verify_restored",
    "update_fingerprints",
)

_SCALAR_CREATE_PROPS = (
    "format_string",
    "display_folder",
    "is_hidden",
    "data_type",
    "description",
    "data_category",
)

_CHECK_REMAP = {
    "write_record": "scope",
    "scope": "scope",
    "canonical": "canonical",
    "tree_compare": "tree_compare",
    "identity_map": "tree_compare",
    "static": "tree_compare",
    "pbir": "pbir",
    "policy": "policy",
    "baseline": "policy",
    "source": "policy",
    "approval": "approval",
    "write": "write",
    "rescan": "rescan",
}


@dataclass(frozen=True)
class _TargetPaths:
    session_dir: Path
    model_sid: str | None
    model_source: LocalSource | None
    model_def_dir: Path | None
    model_format: str | None
    report_sid: str | None
    report_source: LocalSource | None
    report_dir: Path | None
    report_format: str | None
    desktop_root: Path | None
    donor_report_paths: dict[str, Path]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _model_def_dir(model_dir: Path | None) -> Path | None:
    if model_dir is None:
        return None
    definition = model_dir / "definition"
    return definition if definition.is_dir() else model_dir


def _resolve_targets(devcenter: Any, document: Mapping[str, Any], open_session: Any) -> _TargetPaths:
    target = document.get("target") or {}
    model_entry = target.get("model") if isinstance(target.get("model"), Mapping) else None
    report_entry = target.get("report") if isinstance(target.get("report"), Mapping) else None

    model_sid = str(model_entry.get("source_id")) if model_entry and model_entry.get("source_id") else None
    report_sid = str(report_entry.get("source_id")) if report_entry and report_entry.get("source_id") else None

    model_source = devcenter._load(devcenter._source(document, model_sid)) if model_sid else None
    report_source = devcenter._load(devcenter._source(document, report_sid)) if report_sid else None

    donor_report_paths: dict[str, Path] = {}
    for rec in document.get("sources") or ():
        if not isinstance(rec, Mapping):
            continue
        try:
            loaded = devcenter._load(rec)
        except Exception:
            continue
        if loaded.report_dir is not None and loaded.report_dir.is_dir():
            donor_report_paths[str(rec["source_id"])] = loaded.report_dir

    desktop_root = None
    if model_source is not None:
        desktop_root = model_source.root
    elif report_source is not None:
        desktop_root = report_source.root

    return _TargetPaths(
        session_dir=open_session.files.folder,
        model_sid=model_sid,
        model_source=model_source,
        model_def_dir=_model_def_dir(model_source.model_dir) if model_source else None,
        model_format=model_source.model_format if model_source else None,
        report_sid=report_sid,
        report_source=report_source,
        report_dir=report_source.report_dir if report_source else None,
        report_format=report_source.report_format if report_source else None,
        desktop_root=desktop_root,
        donor_report_paths=donor_report_paths,
    )


def _tabular_adapter(devcenter: Any) -> TabularMetadataAdapter:
    adapter = getattr(devcenter, "_tabular_adapter", None)
    if adapter is None:
        adapter = TabularMetadataAdapter()
        devcenter._tabular_adapter = adapter
    return adapter


def _ensure_locks(devcenter: Any) -> tuple[threading.RLock, threading.RLock]:
    with devcenter._lock:
        if not hasattr(devcenter, "_progress_lock"):
            devcenter._progress_lock = threading.RLock()
        if not hasattr(devcenter, "_apply_lock"):
            devcenter._apply_lock = threading.RLock()
        return devcenter._progress_lock, devcenter._apply_lock


def _progress_snapshot(devcenter: Any, revision: int, session_id: str | None) -> dict[str, Any]:
    lock, _ = _ensure_locks(devcenter)
    with lock:
        state = getattr(devcenter, "_apply_progress", None) or {}
        if state.get("session_id") != session_id:
            return {
                "revision": revision,
                "apply_id": None,
                "step": None,
                "step_index": 0,
                "step_count": len(APPLY_STEPS),
                "state": "done",
            }
        return {
            "revision": revision,
            "apply_id": state.get("apply_id"),
            "step": state.get("step"),
            "step_index": int(state.get("step_index", 0)),
            "step_count": int(state.get("step_count", len(APPLY_STEPS))),
            "state": str(state.get("state") or "done"),
        }


def _set_progress(
    devcenter: Any,
    *,
    session_id: str,
    apply_id: str | None,
    step: str | None,
    step_index: int,
    step_count: int,
    state: str,
) -> None:
    lock, _ = _ensure_locks(devcenter)
    payload = {
        "session_id": session_id,
        "apply_id": apply_id,
        "step": step,
        "step_index": step_index,
        "step_count": step_count,
        "state": state,
    }
    with lock:
        devcenter._apply_progress = payload

    hook = getattr(devcenter, "_on_apply_progress", None)
    if callable(hook):
        hook({
            "apply_id": apply_id,
            "step": step,
            "step_index": step_index,
            "step_count": step_count,
            "state": state,
        })


def _non_canonical_files(adapter: TabularMetadataAdapter, model_def_dir: Path | None) -> list[str]:
    if model_def_dir is None or not model_def_dir.is_dir():
        return []
    result = adapter.canonical_check(model_def_dir)
    out = []
    for item in result.get("non_canonical_files") or ():
        rel = str(item.get("file") or "")
        if rel and not _is_minimal_empty_model_tmdl(model_def_dir, rel):
            out.append(rel)
    return sorted(out)


def _plan_summary(plan: Mapping[str, Any]) -> dict[str, int]:
    raw = plan.get("summary") or {}
    add = change = remove = rename = 0
    for domain in ("model", "report"):
        part = raw.get(domain)
        if not isinstance(part, Mapping):
            continue
        add += int((part.get("created") or {}).get("total", 0))
        change += int((part.get("modified") or {}).get("total", 0))
        remove += int((part.get("deleted") or {}).get("total", 0))
        rename += int((part.get("renamed") or {}).get("total", 0))
    return {"add": add, "change": change, "remove": remove, "rename": rename}


def _not_checked_items(devcenter: Any, document: Mapping[str, Any], plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for w in plan.get("warnings") or ():
        if not isinstance(w, Mapping):
            continue
        if w.get("kind") in {"opaque_expression", "not_checked", "unsupported_reference", "partial_coverage"}:
            obj = w.get("object") if isinstance(w.get("object"), Mapping) else {}
            oid = str(w.get("row_key") or w.get("item_id") or "")
            if oid and oid not in seen_ids:
                seen_ids.add(oid)
                items.append({
                    "object_id": oid,
                    "object_name": str(obj.get("name") or oid),
                    "reason": str(w.get("message") or w.get("kind")),
                })
    try:
        imp = impact_service.get_impact(devcenter, {"target": ["plan"]})
    except Exception:
        imp = None
    if isinstance(imp, Mapping):
        comp = imp.get("completeness") if isinstance(imp.get("completeness"), Mapping) else {}
        for otype in comp.get("not_checked_object_types") or ():
            oid = f"type:{otype}"
            if oid not in seen_ids:
                seen_ids.add(oid)
                items.append({
                    "object_id": oid,
                    "object_name": str(otype),
                    "reason": str(comp.get("reason") or "not_checked"),
                })
    return items


def _approvals_needed(
    document: Mapping[str, Any],
    plan: Mapping[str, Any],
    not_checked: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    spec = build_merge_contract(
        project_id=str(document.get("display_name") or document["session_id"]),
        session_id=document["session_id"],
        baseline_snapshot_id=f"rev-{document['revision']}",
        plan=plan,
        mode="apply",
        not_checked_items=not_checked,
    )
    principal = getpass.getuser() or "local-user"
    contract_obj = authorize_contract(spec["contract"], principal, MERGE_POLICY.version, objects=None)
    risk = classify_risk(contract_obj, MERGE_POLICY)
    needed: list[dict[str, Any]] = []
    if risk in {"HIGH", "CRITICAL"}:
        needed.append({
            "kind": "HIGH_RISK_PROMOTION",
            "risk": risk,
            "message": "This plan contains high-risk changes such as creating, deleting, or renaming objects.",
        })
    if not_checked:
        needed.append({
            "kind": "NOT_CHECKED_ITEMS",
            "count": len(not_checked),
            "message": "Some objects could not be checked completely during impact analysis.",
        })
    return needed


def _expected_created_definitions(plan: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    expected: dict[str, dict[str, Any]] = {}
    for op in plan.get("operations") or ():
        if op.get("domain") != "model" or op.get("op") != "CREATE":
            continue
        rk = str(op.get("row_key") or "")
        raw_props = op.get("properties") if isinstance(op.get("properties"), Mapping) else {}
        checked_props = {k: raw_props[k] for k in _SCALAR_CREATE_PROPS if k in raw_props}
        expected[rk] = {
            "object_type": str(op.get("object_type") or ""),
            "table": op.get("table"),
            "name": str(op.get("name") or ""),
            "properties": checked_props,
        }
    return expected


def _read_only_unconfirmed_marks(devcenter: Any, document: Mapping[str, Any]) -> list[str]:
    """Return unconfirmed row keys without mutating session revision (safe for GET preview)."""
    row_keys: set[str] = {str(m["row_key"]) for m in document.get("source_marks") or () if m.get("row_key")}
    for rec in document.get("sources") or ():
        if not isinstance(rec, Mapping):
            continue
        sid = str(rec["source_id"])
        try:
            source = devcenter._load(rec)
            fp = source_fingerprint(source)
        except Exception:
            continue
        recorded_fp = (document.get("source_fingerprints") or {}).get(sid)
        if recorded_fp is not None and fp != recorded_fp:
            baseline = (document.get("row_hashes") or {}).get(sid) or {}
            try:
                current = object_index(source)
            except Exception:
                continue
            for mark in devcenter._diff(sid, baseline, current):
                row_keys.add(str(mark["row_key"]))
    return sorted(row_keys)


def get_apply_preview(devcenter: Any) -> dict[str, Any]:
    """UC6: compute Section 13 steps 1-5 preview without mutating target files or session revision."""
    with devcenter._lock:
        open_sess = devcenter._require_open()
        document = copy.deepcopy(open_sess.document)
        revision = int(document["revision"])
        targets = _resolve_targets(devcenter, document, open_sess)

    unconfirmed_keys = _read_only_unconfirmed_marks(devcenter, document)
    unconfirmed = {"count": len(unconfirmed_keys), "row_keys": unconfirmed_keys}

    plan = plan_service.build_plan(devcenter, document, include_proposals=False)
    desktop_state, desktop_warning = check_desktop_state(devcenter, targets.desktop_root)

    non_canonical: list[str] = []
    canon_error: dict[str, Any] | None = None
    if targets.model_def_dir is not None and targets.model_format == MODEL_TMDL:
        try:
            adapter = _tabular_adapter(devcenter)
            non_canonical = _non_canonical_files(adapter, targets.model_def_dir)
        except (MetadataUnavailable, CanonicalCheckFailed) as exc:
            canon_error = {"check": "canonical", "object": "model", "message": str(exc)}

    failed_checks: list[dict[str, Any]] = []
    if canon_error is not None:
        failed_checks.append(canon_error)
    for b in plan.get("blocking") or ():
        obj = b.get("object") if isinstance(b.get("object"), Mapping) else None
        failed_checks.append({
            "check": str(b.get("kind") or "plan"),
            "object": str((obj or {}).get("name") or b.get("row_key") or "plan"),
            "message": str(b.get("message") or b.get("kind") or "Plan check failed."),
        })
    if desktop_state == DESKTOP_OPEN_UNSAVED:
        failed_checks.append({
            "check": "desktop",
            "object": "desktop",
            "message": "Power BI Desktop has unsaved changes on the target project.",
        })
    if non_canonical:
        failed_checks.append({
            "check": "canonical",
            "object": non_canonical[0],
            "message": f"{len(non_canonical)} target TMDL file(s) need canonical formatting.",
        })

    not_checked = _not_checked_items(devcenter, document, plan)
    approvals = _approvals_needed(document, plan, not_checked)

    missing_sources = [
        rec["source_id"]
        for rec in document.get("sources") or ()
        if (document.get("source_status") or {}).get(rec["source_id"], STATUS_OK) != STATUS_OK
    ]
    if missing_sources:
        failed_checks.append({
            "check": "source",
            "object": missing_sources[0],
            "message": f"Source {missing_sources[0]} is unavailable.",
        })

    val_status = plan["status"]
    if failed_checks and val_status != "invalid":
        val_status = "invalid"

    ready = (
        unconfirmed["count"] == 0
        and not missing_sources
        and plan["status"] != "invalid"
        and desktop_state != DESKTOP_OPEN_UNSAVED
        and not non_canonical
        and canon_error is None
    )

    return {
        "revision": revision,
        "ready": ready,
        "plan_hash": plan["plan_hash"],
        "summary": _plan_summary(plan),
        "unconfirmed_marks": unconfirmed,
        "desktop_state": desktop_state,
        "desktop_warning": desktop_warning,
        "non_canonical_files": non_canonical,
        "validation": {"status": val_status, "failed_checks": failed_checks},
        "not_checked": not_checked,
        "approvals_needed": approvals,
    }


def get_apply_progress(devcenter: Any) -> dict[str, Any]:
    """UC5: read live progress snapshot without acquiring long-running apply locks."""
    with devcenter._lock:
        open_sess = devcenter._require_open()
        revision = int(open_sess.document["revision"])
        session_id = str(open_sess.document["session_id"])
    return _progress_snapshot(devcenter, revision, session_id)


def _last_apply_path(session_dir: Path) -> Path:
    return session_dir / "last_apply.json"


def _read_last_apply(session_dir: Path) -> dict[str, Any] | None:
    path = _last_apply_path(session_dir)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _write_last_apply(session_dir: Path, record: Mapping[str, Any]) -> None:
    write_atomic(_last_apply_path(session_dir), canonical_json(record).encode("utf-8"))


def _live_diff_against_hashes(roots: Mapping[str, Mapping[str, Any]]) -> tuple[bool, list[str]]:
    changed: list[str] = []
    multi = len(roots) > 1
    for root_name, info in sorted(roots.items()):
        root_dir = Path(info["target_dir"])
        expected = dict(info.get("after_hashes") or {})
        actual = dir_file_hashes(root_dir)
        all_keys = sorted(set(expected) | set(actual))
        for rel in all_keys:
            if expected.get(rel) != actual.get(rel):
                changed.append(f"{root_name}/{rel}" if multi else rel)
    return bool(changed), changed


def get_apply_last(devcenter: Any) -> dict[str, Any]:
    """UC7: report latest apply status, live target_changed drift, backup availability, and rescan diffs."""
    with devcenter._lock:
        open_sess = devcenter._require_open()
        revision = int(open_sess.document["revision"])
        session_dir = open_sess.files.folder

    record = _read_last_apply(session_dir)
    if not record or not record.get("apply_id"):
        return {
            "revision": revision,
            "apply_id": None,
            "kind": None,
            "finished_utc": None,
            "file_count": 0,
            "backup_present": False,
            "target_changed": False,
            "changed_files": [],
            "rescan_differences": [],
            "desktop_warning": None,
            "plan_hash": None,
            "undone": False,
            "change_report_path": None,
        }

    apply_id = str(record["apply_id"])
    undone = bool(record.get("undone", False))
    manifest_path = session_dir / "backups" / apply_id / "manifest.json"
    backup_present = (not undone) and manifest_path.is_file()

    target_changed = False
    drift_files: list[str] = []
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        roots = manifest.get("roots") or {}
        if not undone:
            target_changed, drift_files = _live_diff_against_hashes(roots)

    reported_files = drift_files if target_changed else list(record.get("changed_files") or ())
    return {
        "revision": revision,
        "apply_id": apply_id,
        "kind": record.get("kind"),
        "finished_utc": record.get("finished_utc"),
        "file_count": int(record.get("file_count", 0)),
        "backup_present": backup_present,
        "target_changed": target_changed,
        "changed_files": reported_files,
        "rescan_differences": list(record.get("rescan_differences") or ()),
        "desktop_warning": record.get("desktop_warning"),
        "plan_hash": record.get("plan_hash"),
        "undone": undone,
        "change_report_path": record.get("change_report_path"),
    }


def _check_base_revision(devcenter: Any, request: Mapping[str, Any]) -> tuple[Any, dict[str, Any]]:
    with devcenter._lock:
        open_sess = devcenter._require_open()
        document = open_sess.document
        if open_sess.read_only:
            raise DevCenterError(
                "action_not_allowed",
                "This session is open in another window and cannot modify the target.",
                {"step": "source_check", "check": "policy", "reason": "read_only"},
            )
        if request.get("base_revision") != document["revision"]:
            raise DevCenterError(
                "stale_revision",
                "The session changed. Load it again.",
                {"revision": document["revision"]},
            )
        return open_sess, copy.deepcopy(document)


def _check_sources_and_block(devcenter: Any) -> tuple[Any, dict[str, Any]]:
    result = devcenter.apply_source_check()
    if result.get("blocking"):
        for item in result.get("items") or ():
            if item.get("kind") == "unconfirmed_marks":
                keys = list(item.get("row_keys") or ())
                raise DevCenterError(
                    "source_changed",
                    "Sources have unconfirmed changes. Review and confirm them before applying.",
                    {"step": "source_check", "check": "scope", "reason": "unconfirmed_marks", "row_keys": keys},
                )
            if item.get("kind") == "source_not_available":
                sids = list(item.get("source_ids") or ())
                raise DevCenterError(
                    "action_not_allowed",
                    "One or more sources are unavailable.",
                    {"step": "source_check", "check": "scope", "reason": "source_not_available", "source_ids": sids},
                )
    with devcenter._lock:
        open_sess = devcenter._require_open()
        return open_sess, copy.deepcopy(open_sess.document)


def _guard_check_name(raw_check: str | None) -> str:
    return _CHECK_REMAP.get(str(raw_check or "").strip().lower(), "policy")


def _stage_backup_and_promote(
    *,
    devcenter: Any,
    session_dir: Path,
    apply_id: str,
    kind: str,
    plan_hash: str,
    root_pairs: Sequence[tuple[str, Path, Path]],
) -> tuple[list[str], int]:
    """Back up modified/removed target files, promote candidate changes atomically, or roll back all-or-nothing."""
    backup_dir = session_dir / "backups" / apply_id
    backup_dir.mkdir(parents=True, exist_ok=True)

    manifest_roots: dict[str, dict[str, Any]] = {}
    ops_per_root: list[tuple[str, Path, Path, list[str], list[str], list[str], dict[str, str]]] = []
    multi = len(root_pairs) > 1
    changed_summary: list[str] = []

    for root_name, target_dir, cand_dir in root_pairs:
        before = dir_file_hashes(target_dir)
        after = dir_file_hashes(cand_dir)
        added = sorted(rel for rel in after if rel not in before)
        removed = sorted(rel for rel in before if rel not in after)
        modified = sorted(rel for rel in before if rel in after and before[rel] != after[rel])

        for rel in modified + removed:
            src_file = target_dir / rel
            raw = src_file.read_bytes()
            if content_hash(raw) != before[rel]:
                raise DevCenterError(
                    "action_not_allowed",
                    f"Target file changed unexpectedly during backup: {rel}",
                    {"step": "backup", "check": "scope", "reason": "backup_hash_mismatch"},
                )
            b_file = backup_dir / root_name / rel
            b_file.parent.mkdir(parents=True, exist_ok=True)
            durable_write(b_file, raw)

        manifest_roots[root_name] = {
            "target_dir": str(target_dir),
            "before_hashes": before,
            "after_hashes": after,
            "added": added,
            "modified": modified,
            "removed": removed,
        }
        ops_per_root.append((root_name, target_dir, cand_dir, added, modified, removed, before))
        for rel in added + modified + removed:
            changed_summary.append(f"{root_name}/{rel}" if multi else rel)

    manifest = {
        "apply_id": apply_id,
        "kind": kind,
        "plan_hash": plan_hash,
        "created_utc": _utc_now(),
        "roots": manifest_roots,
    }
    write_atomic(backup_dir / "manifest.json", canonical_json(manifest).encode("utf-8"))

    fault_hook = getattr(devcenter, "_promotion_fault", None)
    try:
        for root_name, target_dir, cand_dir, added, modified, removed, _before in ops_per_root:
            for rel in added + modified:
                if callable(fault_hook):
                    fault_hook(root_name, rel)
                dest = target_dir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                durable_write(dest, (cand_dir / rel).read_bytes())
            for rel in removed:
                if callable(fault_hook):
                    fault_hook(root_name, rel)
                victim = target_dir / rel
                victim.unlink(missing_ok=True)
            _prune_empty_dirs(target_dir)
    except Exception as exc:
        _rollback_from_manifest(backup_dir, manifest_roots)
        raise DevCenterError(
            "action_not_allowed",
            f"Apply failed while writing target files and was rolled back: {exc}",
            {"step": "promote", "check": "write", "reason": "promotion_failed"},
        ) from exc

    return changed_summary, len(changed_summary)


def _prune_empty_dirs(root: Path) -> None:
    if not root.is_dir():
        return
    for d in sorted((p for p in root.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        if any(part in {".pbi", ".pbibrain", ".git"} for part in d.relative_to(root).parts):
            continue
        try:
            if not any(d.iterdir()):
                d.rmdir()
        except OSError:
            pass


def _rollback_from_manifest(backup_dir: Path, manifest_roots: Mapping[str, Mapping[str, Any]]) -> None:
    for root_name, info in manifest_roots.items():
        target_dir = Path(info["target_dir"])
        for rel in info.get("added") or ():
            (target_dir / rel).unlink(missing_ok=True)
        for rel in list(info.get("modified") or ()) + list(info.get("removed") or ()):
            b_file = backup_dir / root_name / rel
            if b_file.is_file():
                dest = target_dir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                durable_write(dest, b_file.read_bytes())
        _prune_empty_dirs(target_dir)


def _norm_compare_val(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, bool):
        return "True" if val else "False"
    lines = str(val).replace("\r\n", "\n").replace("\r", "\n").splitlines()
    return "\n".join(line.strip() for line in lines).strip()


def _extract_target_objects(
    targets: _TargetPaths,
    adapter: TabularMetadataAdapter,
) -> tuple[dict[tuple[str, str, str], CompareObject], dict[tuple[str, str, str], CompareObject]]:
    model_objs: dict[tuple[str, str, str], CompareObject] = {}
    report_objs: dict[tuple[str, str, str], CompareObject] = {}
    seen_roots: set[Path] = set()
    for src in (targets.model_source, targets.report_source):
        if src is None:
            continue
        resolved_root = src.root.resolve()
        if resolved_root in seen_roots:
            continue
        seen_roots.add(resolved_root)
        fresh_source = detect_local_source(src.root)
        extracted = load_objects(fresh_source, adapter=adapter)
        for obj in extracted.model:
            model_objs[(obj.kind, fold(obj.table or ""), fold(obj.name))] = obj
        for obj in extracted.report:
            report_objs[(obj.kind, fold(obj.table or ""), fold(obj.name))] = obj
    return model_objs, report_objs


def _rescan_target(
    devcenter: Any,
    *,
    targets: _TargetPaths,
    plan: Mapping[str, Any],
    report_write: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    """Step 10: reload target from disk and compare each planned operation against actual objects."""
    model_objs, report_objs = _extract_target_objects(targets, _tabular_adapter(devcenter))
    differences: list[dict[str, Any]] = []
    page_name_map = dict((report_write or {}).get("page_name_map") or {})
    visual_page_map = dict((report_write or {}).get("visual_page_map") or {})

    # Track effective (table, name) for renamed objects across ordered ops.
    renamed_to: dict[str, tuple[str | None, str]] = {}
    for op in plan.get("operations") or ():
        domain = op.get("domain")
        otype = str(op.get("object_type") or "")
        rk = str(op.get("row_key") or "")
        table = op.get("table")
        name = str(op.get("name") or "")
        kind = str(op.get("op") or "")
        pool = model_objs if domain == MODEL else report_objs

        if kind in {"DELETE", "DELETE_PAGE", "DELETE_VISUAL", "DELETE_REPORT_MEASURE"}:
            lookup_table, lookup_name = renamed_to.get(rk, (table, name))
            if kind == "DELETE_PAGE":
                found_obj = next(
                    (o for o in pool.values() if o.kind == "page" and (
                        o.extra.get("page_id") == (op.get("page_id") or lookup_name)
                        or fold(o.name) == fold(lookup_name)
                    )),
                    None,
                )
            elif kind == "DELETE_VISUAL":
                target_vid = op.get("visual_id") or (rk.split("/")[-1] if "/" in rk else "")
                found_obj = next(
                    (o for o in pool.values() if o.kind == "visual" and o.extra.get("visual_id") == target_vid),
                    pool.get((otype, fold(lookup_table or ""), fold(lookup_name))),
                )
            else:
                found_obj = pool.get((otype, fold(lookup_table or ""), fold(lookup_name)))
            if found_obj is not None:
                differences.append({"object": rk, "expected": "deleted", "found": found_obj.name})
            continue

        if kind in {"RENAME", "RENAME_PAIR"}:
            old_name = str(op.get("old_name") or name)
            new_name = str(op.get("new_name") or name)
            renamed_to[rk] = (table, new_name)
            if otype != "page":
                if fold(old_name) != fold(new_name) and (otype, fold(table or ""), fold(old_name)) in pool:
                    differences.append({"object": rk, "expected": f"absent:{old_name}", "found": old_name})
                if (otype, fold(table or ""), fold(new_name)) not in pool:
                    differences.append({"object": rk, "expected": new_name, "found": "missing"})
            continue

        if kind == "CREATE":
            found_obj = pool.get((otype, fold(table or ""), fold(name)))
            if found_obj is None:
                differences.append({"object": rk, "expected": name, "found": "missing"})
                continue
            props = op.get("properties") if isinstance(op.get("properties"), Mapping) else {}
            for key in ("expression", "format_string", "display_folder"):
                if key in props and props[key] is not None and key in found_obj.props:
                    exp_v = _norm_compare_val(props[key])
                    act_v = _norm_compare_val(found_obj.props.get(key))
                    if exp_v != act_v:
                        differences.append({"object": f"{rk}.{key}", "expected": exp_v, "found": act_v})
            continue

        if kind in {"CREATE_REPORT_MEASURE", "REPLACE_REPORT_MEASURE"}:
            found_obj = pool.get(("report_measure", fold(table or ""), fold(name)))
            if found_obj is None:
                differences.append({"object": rk, "expected": name, "found": "missing"})
            continue

        if kind == "COPY_PAGE":
            src_page = str(op.get("page_id") or (str(op.get("source_key") or "").split(":", 1)[-1]))
            mapped_page = page_name_map.get(src_page, src_page)
            if not any(o.kind == "page" and o.extra.get("page_id") == mapped_page for o in pool.values()):
                differences.append({"object": rk, "expected": mapped_page, "found": "missing"})
            continue

        if kind == "COPY_VISUAL":
            src_page = str(op.get("page_id") or "")
            mapped_page = page_name_map.get(src_page, src_page)
            src_vid = str(op.get("visual_id") or "")
            mapped_vid = visual_page_map.get(f"{src_page}/{src_vid}", src_vid)
            if not any(
                o.kind == "visual" and o.extra.get("visual_id") in {mapped_vid, src_vid}
                and (not mapped_page or fold(o.table or "") == fold(mapped_page))
                for o in pool.values()
            ):
                differences.append({"object": rk, "expected": mapped_vid or src_vid, "found": "missing"})
            continue

        if kind in {"SET_PROPERTIES", "REPLACE", "REWRITE_EXPRESSION"}:
            lookup_table, lookup_name = renamed_to.get(rk, (table, name))
            found_obj = pool.get((otype, fold(lookup_table or ""), fold(lookup_name)))
            if found_obj is None:
                differences.append({"object": rk, "expected": lookup_name, "found": "missing"})
                continue
            if kind == "REWRITE_EXPRESSION":
                prop = str(op.get("property") or "expression")
                if prop in found_obj.props:
                    exp_v = _norm_compare_val(op.get("new_text"))
                    act_v = _norm_compare_val(found_obj.props.get(prop))
                    if exp_v != act_v:
                        differences.append({"object": f"{rk}.{prop}", "expected": exp_v, "found": act_v})
            else:
                props = op.get("properties") if isinstance(op.get("properties"), Mapping) else {}
                for key in ("expression", "format_string", "display_folder"):
                    if key in props and props[key] is not None and key in found_obj.props:
                        exp_v = _norm_compare_val(props[key])
                        act_v = _norm_compare_val(found_obj.props.get(key))
                        if exp_v != act_v:
                            differences.append({"object": f"{rk}.{key}", "expected": exp_v, "found": act_v})

    hook = getattr(devcenter, "_rescan_hook", None)
    if callable(hook):
        extra = hook(plan=plan, differences=list(differences), model_objects=model_objs, report_objects=report_objs)
        if isinstance(extra, list):
            differences = extra
    return differences


def _refresh_target_fingerprints_and_commit(
    devcenter: Any,
    *,
    target_sids: Sequence[str],
    action: str,
    target_payload: Any,
    before_payload: Any,
    after_payload: Any,
    after_commit: Callable[[], None] | None = None,
) -> dict[str, Any]:
    with devcenter._lock:
        current = devcenter._require_open()
        draft = copy.deepcopy(current.document)
        target_set = {sid for sid in target_sids if sid}
        for sid in sorted(target_set):
            rec = devcenter._source(draft, sid)
            source = devcenter._load(rec)
            draft["source_fingerprints"][sid] = source_fingerprint(source)
            draft["row_hashes"][sid] = object_index(source)
            draft["source_status"][sid] = STATUS_OK
        draft["source_marks"] = [
            mark for mark in draft.get("source_marks") or () if mark.get("source_id") not in target_set
        ]
        if after_commit is not None:
            after_commit()
        return devcenter._commit(current, draft, action, target_payload, before_payload, after_payload)


def _target_sids(targets: _TargetPaths) -> list[str]:
    return [sid for sid in dict.fromkeys((targets.model_sid, targets.report_sid)) if sid]


def format_only_apply(devcenter: Any, request: Mapping[str, Any]) -> dict[str, Any]:
    """Canonicalize target TMDL files without any semantic change."""
    _, apply_lock = _ensure_locks(devcenter)
    with apply_lock:
        return _format_only_impl(devcenter, request)


def _format_only_impl(devcenter: Any, request: Mapping[str, Any]) -> dict[str, Any]:
    _open_sess, document = _check_base_revision(devcenter, request)
    session_id = str(document["session_id"])
    apply_id = f"fmt-{uuid.uuid4().hex[:12]}"
    count = len(FORMAT_ONLY_STEPS)

    def _prog(idx: int, state: str = "running") -> None:
        _set_progress(
            devcenter,
            session_id=session_id,
            apply_id=apply_id,
            step=FORMAT_ONLY_STEPS[idx - 1],
            step_index=idx,
            step_count=count,
            state=state,
        )

    try:
        _prog(1)
        open_sess, document = _check_sources_and_block(devcenter)
        targets = _resolve_targets(devcenter, document, open_sess)

        if targets.model_def_dir is None or targets.model_format != MODEL_TMDL:
            raise DevCenterError(
                "action_not_allowed",
                "Format-only apply requires a local TMDL target model.",
                {"step": "source_check", "check": "canonical", "reason": "no_tmdl_target"},
            )

        _prog(2)
        desktop_state, desktop_warning = check_desktop_state(devcenter, targets.desktop_root)
        if desktop_state == DESKTOP_OPEN_UNSAVED:
            raise DevCenterError(
                "action_not_allowed",
                "Power BI Desktop has unsaved changes on the target project. Save or close Desktop first.",
                {"step": "desktop_check", "check": "policy", "reason": "desktop_unsaved"},
            )

        adapter = _tabular_adapter(devcenter)
        with tempfile.TemporaryDirectory(prefix="pbibrain-format-") as tmp:
            cand_model_dir = Path(tmp) / "candidate_model"
            _prog(3)
            try:
                base_hashes = dir_file_hashes(targets.model_def_dir)
                model_write = adapter.write_model(targets.model_def_dir, cand_model_dir, [])
            except (ModelWriteFailed, MetadataUnavailable) as exc:
                raise DevCenterError(
                    "action_not_allowed",
                    f"Could not write formatted TMDL candidate: {exc}",
                    {"step": "write_candidate", "check": "write", "reason": "model_write_failed"},
                ) from exc

            empty_plan = {
                "status": "valid",
                "summary": {},
                "steps": [],
                "operations": [],
                "blocking": [],
                "warnings": [],
                "sources": [],
                "plan_hash": "sha256:" + content_hash({"mode": "format_only", "session_id": session_id}),
            }
            spec = build_merge_contract(
                project_id=str(document.get("display_name") or session_id),
                session_id=session_id,
                baseline_snapshot_id=f"rev-{document['revision']}",
                plan=empty_plan,
                mode="format_only",
            )
            write_record = build_write_record(
                contract_hash=spec["contract_hash"],
                plan_hash=empty_plan["plan_hash"],
                mode="format_only",
                baseline_model_hashes=base_hashes,
                candidate_model_hashes=dir_file_hashes(cand_model_dir),
                model_write=model_write,
            )

            _prog(4)
            guard = MergeGuard(targets.session_dir / "guard", adapter=adapter)
            try:
                guard_res = guard.validate(
                    merge_spec=spec,
                    write_record=write_record,
                    baseline_model_dir=targets.model_def_dir,
                    candidate_model_dir=cand_model_dir,
                    operation_id=apply_id,
                )
            except MergeGuardError as exc:
                raise DevCenterError(
                    "action_not_allowed",
                    str(exc),
                    {"step": "guard_verify", "check": _guard_check_name(exc.check), "reason": exc.code},
                ) from exc

            if not guard_res.get("eligible_for_promotion"):
                failures = list(guard_res.get("failures") or ())
                first = failures[0] if failures else {}
                raise DevCenterError(
                    "action_not_allowed",
                    str(first.get("message") or "Change Guard rejected format-only apply."),
                    {"step": "guard_verify", "check": _guard_check_name(first.get("check")), "reason": str(first.get("code") or "guard_rejected")},
                )

            _prog(5)
            _prog(6)
            changed_files, file_count = _stage_backup_and_promote(
                devcenter=devcenter,
                session_dir=targets.session_dir,
                apply_id=apply_id,
                kind="format_only",
                plan_hash=empty_plan["plan_hash"],
                root_pairs=[("model", targets.model_def_dir, cand_model_dir)],
            )

        _prog(7)
        last_record = {
            "apply_id": apply_id,
            "kind": "format_only",
            "finished_utc": _utc_now(),
            "file_count": file_count,
            "changed_files": changed_files,
            "rescan_differences": [],
            "desktop_warning": desktop_warning,
            "plan_hash": empty_plan["plan_hash"],
            "undone": False,
            "change_report_path": None,
        }
        updated_doc = _refresh_target_fingerprints_and_commit(
            devcenter,
            target_sids=_target_sids(targets),
            action="format_only_apply",
            target_payload=apply_id,
            before_payload=None,
            after_payload={"file_count": file_count, "changed_files": changed_files},
            after_commit=lambda: _write_last_apply(targets.session_dir, last_record),
        )
        _prog(7, state="done")
        return {
            "revision": int(updated_doc["revision"]),
            "apply_id": apply_id,
            "file_count": file_count,
            "changed_files": changed_files,
            "backup_present": True,
            "desktop_warning": desktop_warning,
        }
    except DevCenterError as exc:
        cur = _progress_snapshot(devcenter, int(document["revision"]), session_id)
        _set_progress(
            devcenter,
            session_id=session_id,
            apply_id=apply_id,
            step=cur.get("step") or exc.details.get("step") or FORMAT_ONLY_STEPS[0],
            step_index=max(1, int(cur.get("step_index") or 1)),
            step_count=count,
            state="failed",
        )
        raise


def apply(devcenter: Any, request: Mapping[str, Any]) -> dict[str, Any]:
    """Execute the full local apply pipeline of Section 13 with Guard verification, atomic promotion, rescan, and undo backup."""
    _, apply_lock = _ensure_locks(devcenter)
    with apply_lock:
        return _apply_impl(devcenter, request)


def _apply_impl(devcenter: Any, request: Mapping[str, Any]) -> dict[str, Any]:
    _open_sess, document = _check_base_revision(devcenter, request)
    session_id = str(document["session_id"])
    apply_id = f"apply-{uuid.uuid4().hex[:12]}"
    count = len(APPLY_STEPS)

    def _prog(idx: int, state: str = "running") -> None:
        _set_progress(
            devcenter,
            session_id=session_id,
            apply_id=apply_id,
            step=APPLY_STEPS[idx - 1],
            step_index=idx,
            step_count=count,
            state=state,
        )

    try:
        # 1. Source check
        _prog(1)
        open_sess, document = _check_sources_and_block(devcenter)
        targets = _resolve_targets(devcenter, document, open_sess)

        # 2. Plan status (unaccepted agent proposals never enter applied files)
        _prog(2)
        plan = plan_service.build_plan(devcenter, document, include_proposals=False)
        expected_hash = request.get("expected_plan_hash")
        if expected_hash and expected_hash != plan["plan_hash"]:
            raise DevCenterError(
                "action_not_allowed",
                "The change plan changed since preview. Refresh the plan and try again.",
                {"step": "plan_check", "check": "policy", "reason": "plan_hash_mismatch"},
            )
        if plan["status"] == "invalid":
            raise DevCenterError(
                "action_not_allowed",
                "The change plan has blocking items that must be resolved before applying.",
                {"step": "plan_check", "check": "policy", "reason": "plan_invalid", "blocking": plan["blocking"]},
            )

        # 3. Desktop-open check
        _prog(3)
        desktop_state, desktop_warning = check_desktop_state(devcenter, targets.desktop_root)
        if desktop_state == DESKTOP_OPEN_UNSAVED:
            raise DevCenterError(
                "action_not_allowed",
                "Power BI Desktop has unsaved changes on the target project. Save or close Desktop before applying.",
                {"step": "desktop_check", "check": "policy", "reason": "desktop_unsaved", "desktop_state": desktop_state},
            )

        model_ops = [op for op in plan["operations"] if op.get("domain") == MODEL]
        report_ops = [op for op in plan["operations"] if op.get("domain") == REPORT]

        if model_ops and targets.model_format != MODEL_TMDL:
            raise DevCenterError(
                "action_not_allowed",
                "Target model must be in local TMDL format before applying model changes.",
                {"step": "canonical_check", "check": "write", "reason": "unsupported_target_format"},
            )
        if report_ops and targets.report_format != REPORT_PBIR:
            raise DevCenterError(
                "action_not_allowed",
                "Target report must be in PBIR format before applying report changes.",
                {"step": "canonical_check", "check": "pbir", "reason": "unsupported_target_format"},
            )

        # 4. Canonical check
        _prog(4)
        adapter = _tabular_adapter(devcenter)
        if targets.model_def_dir is not None and targets.model_format == MODEL_TMDL:
            try:
                non_canonical = _non_canonical_files(adapter, targets.model_def_dir)
            except (MetadataUnavailable, CanonicalCheckFailed) as exc:
                raise DevCenterError(
                    "action_not_allowed",
                    f"Canonical check failed: {exc}",
                    {"step": "canonical_check", "check": "canonical", "reason": "canonical_check_failed"},
                ) from exc
            if non_canonical:
                raise DevCenterError(
                    "action_not_allowed",
                    "Target TMDL files are not in canonical format. Run Format only apply first.",
                    {"step": "canonical_check", "check": "canonical", "reason": "non_canonical_target", "files": non_canonical},
                )

        # 5. Full validation
        _prog(5)
        not_checked = _not_checked_items(devcenter, document, plan)
        needed_approvals = _approvals_needed(document, plan, not_checked)
        required_approval_kinds = {item["kind"] for item in needed_approvals}

        # 6. Approval
        _prog(6)
        provided_approvals = set(request.get("approvals") or ())
        if request.get("approved") is True:
            provided_approvals |= required_approval_kinds
        missing_approvals = sorted(required_approval_kinds - provided_approvals)
        if missing_approvals:
            raise DevCenterError(
                "action_not_allowed",
                "Review and approve the plan risks before applying.",
                {
                    "step": "approval",
                    "check": "approval",
                    "reason": "approval_required",
                    "approvals_needed": missing_approvals,
                },
            )

        # 7. Write to candidate folder (model + report together before touching target)
        _prog(7)
        spec = build_merge_contract(
            project_id=str(document.get("display_name") or session_id),
            session_id=session_id,
            baseline_snapshot_id=f"rev-{document['revision']}",
            plan=plan,
            mode="apply",
            not_checked_items=not_checked,
            expected_created_definitions=_expected_created_definitions(plan),
        )

        with tempfile.TemporaryDirectory(prefix="pbibrain-apply-") as tmp:
            tmp_dir = Path(tmp)
            cand_model_dir: Path | None = None
            cand_report_dir: Path | None = None
            base_model_dir: Path | None = None
            base_report_dir: Path | None = None
            base_model_hashes: dict[str, str] = {}
            cand_model_hashes: dict[str, str] = {}
            base_report_hashes: dict[str, str] = {}
            cand_report_hashes: dict[str, str] = {}
            model_write: dict[str, Any] | None = None
            report_write: dict[str, Any] | None = None
            root_pairs: list[tuple[str, Path, Path]] = []

            if model_ops and targets.model_def_dir is not None:
                base_model_dir = targets.model_def_dir
                cand_model_dir = tmp_dir / "candidate_model"
                base_model_hashes = dir_file_hashes(base_model_dir)
                try:
                    model_write = adapter.write_model(base_model_dir, cand_model_dir, model_ops)
                except (ModelWriteFailed, MetadataUnavailable) as exc:
                    raise DevCenterError(
                        "action_not_allowed",
                        f"Could not write candidate model files: {exc}",
                        {"step": "write_candidate", "check": "write", "reason": getattr(exc, "code", "model_write_failed")},
                    ) from exc
                cand_model_hashes = dir_file_hashes(cand_model_dir)
                root_pairs.append(("model", base_model_dir, cand_model_dir))

            if report_ops and targets.report_dir is not None:
                base_report_dir = targets.report_dir
                cand_report_dir = tmp_dir / "candidate_report"
                base_report_hashes = dir_file_hashes(base_report_dir)
                try:
                    report_write = write_report(
                        base_report_dir,
                        cand_report_dir,
                        report_ops,
                        donor_paths=targets.donor_report_paths,
                    )
                except PBIRWriteError as exc:
                    raise DevCenterError(
                        "action_not_allowed",
                        f"Could not write candidate report files: {exc}",
                        {"step": "write_candidate", "check": "pbir" if "schema" in exc.code else "write", "reason": exc.code},
                    ) from exc
                cand_report_hashes = dir_file_hashes(cand_report_dir)
                root_pairs.append(("report", base_report_dir, cand_report_dir))

            write_record = build_write_record(
                contract_hash=spec["contract_hash"],
                plan_hash=plan["plan_hash"],
                mode="apply",
                baseline_model_hashes=base_model_hashes,
                candidate_model_hashes=cand_model_hashes,
                model_write=model_write,
                baseline_report_hashes=base_report_hashes,
                candidate_report_hashes=cand_report_hashes,
                report_write=report_write,
            )

            # 8. Guard verification on candidate folders
            _prog(8)
            guard = MergeGuard(targets.session_dir / "guard", adapter=adapter)
            try:
                guard_res = guard.validate(
                    merge_spec=spec,
                    write_record=write_record,
                    baseline_model_dir=base_model_dir,
                    candidate_model_dir=cand_model_dir,
                    baseline_report_dir=base_report_dir,
                    candidate_report_dir=cand_report_dir,
                    approvals=sorted(provided_approvals),
                    operation_id=apply_id,
                )
            except MergeGuardError as exc:
                raise DevCenterError(
                    "action_not_allowed",
                    str(exc),
                    {"step": "guard_verify", "check": _guard_check_name(exc.check), "reason": exc.code},
                ) from exc

            if not guard_res.get("eligible_for_promotion"):
                failures = list(guard_res.get("failures") or ())
                approval_reasons = list(guard_res.get("approval_reasons") or ())
                blocking_reasons = list(guard_res.get("blocking_reasons") or ())
                if failures:
                    first = failures[0]
                    check = _guard_check_name(first.get("check"))
                    msg = str(first.get("message") or "Change Guard rejected apply.")
                    reason = str(first.get("code") or "guard_rejected")
                elif approval_reasons:
                    check = "approval"
                    msg = "Change Guard requires explicit approval before applying."
                    reason = approval_reasons[0]
                else:
                    check = "policy"
                    msg = "Change Guard policy rejected apply."
                    reason = blocking_reasons[0] if blocking_reasons else "policy_rejected"
                raise DevCenterError(
                    "action_not_allowed",
                    msg,
                    {"step": "guard_verify", "check": check, "reason": reason},
                )

            # 9. Backup and atomic all-or-nothing promotion
            _prog(9)
            _prog(10)
            changed_files, file_count = _stage_backup_and_promote(
                devcenter=devcenter,
                session_dir=targets.session_dir,
                apply_id=apply_id,
                kind="apply",
                plan_hash=plan["plan_hash"],
                root_pairs=root_pairs,
            )

        # 10. Rescan target and compare with plan
        _prog(11)
        try:
            rescan_differences = _rescan_target(
                devcenter,
                targets=targets,
                plan=plan,
                report_write=report_write,
            )
        except Exception as exc:
            raise DevCenterError(
                "action_not_allowed",
                f"Target rescan after apply failed: {exc}",
                {"step": "rescan", "check": "rescan", "reason": "rescan_failed"},
            ) from exc

        # 11. Re-fingerprint target, clear caches, persist last_apply, log
        _prog(12)
        last_record = {
            "apply_id": apply_id,
            "kind": "apply",
            "finished_utc": _utc_now(),
            "file_count": file_count,
            "changed_files": changed_files,
            "rescan_differences": rescan_differences,
            "desktop_warning": desktop_warning,
            "plan_hash": plan["plan_hash"],
            "plan_snapshot": {
                "plan_hash": plan["plan_hash"],
                "status": plan["status"],
                "summary": plan["summary"],
                "steps": plan["steps"],
                "warnings": plan["warnings"],
            },
            "undone": False,
            "change_report_path": None,
        }
        updated_doc = _refresh_target_fingerprints_and_commit(
            devcenter,
            target_sids=_target_sids(targets),
            action="apply",
            target_payload=apply_id,
            before_payload=None,
            after_payload={
                "plan_hash": plan["plan_hash"],
                "file_count": file_count,
                "changed_files": changed_files,
                "rescan_differences": len(rescan_differences),
            },
            after_commit=lambda: _write_last_apply(targets.session_dir, last_record),
        )
        _prog(12, state="done")
        return {
            "revision": int(updated_doc["revision"]),
            "apply_id": apply_id,
            "plan_hash": plan["plan_hash"],
            "file_count": file_count,
            "changed_files": changed_files,
            "backup_present": True,
            "rescan_differences": rescan_differences,
            "desktop_warning": desktop_warning,
        }
    except DevCenterError as exc:
        cur = _progress_snapshot(devcenter, int(document["revision"]), session_id)
        _set_progress(
            devcenter,
            session_id=session_id,
            apply_id=apply_id,
            step=cur.get("step") or exc.details.get("step") or APPLY_STEPS[0],
            step_index=max(1, int(cur.get("step_index") or 1)),
            step_count=count,
            state="failed",
        )
        raise


def undo_apply(devcenter: Any, request: Mapping[str, Any]) -> dict[str, Any]:
    """Restore every file modified/added/removed by the last apply from its Guard backup."""
    _, apply_lock = _ensure_locks(devcenter)
    with apply_lock:
        return _undo_impl(devcenter, request)


def _undo_impl(devcenter: Any, request: Mapping[str, Any]) -> dict[str, Any]:
    open_sess, document = _check_base_revision(devcenter, request)
    session_id = str(document["session_id"])
    targets = _resolve_targets(devcenter, document, open_sess)
    record = _read_last_apply(targets.session_dir)
    requested_id = str(request.get("apply_id") or (record or {}).get("apply_id") or "")
    count = len(UNDO_STEPS)

    def _prog(idx: int, state: str = "running") -> None:
        _set_progress(
            devcenter,
            session_id=session_id,
            apply_id=requested_id or "undo",
            step=UNDO_STEPS[idx - 1],
            step_index=idx,
            step_count=count,
            state=state,
        )

    try:
        # 1. Check backup presence
        _prog(1)
        if not record or not requested_id or record.get("undone"):
            raise DevCenterError(
                "action_not_allowed",
                "No apply backup is available to undo.",
                {"step": "check_backup", "check": "scope", "reason": "no_backup"},
            )
        if request.get("apply_id") and str(request["apply_id"]) != str(record.get("apply_id")):
            raise DevCenterError(
                "not_found",
                "The requested apply backup was not found.",
                {"step": "check_backup", "check": "scope", "reason": "apply_id_mismatch"},
            )

        backup_dir = targets.session_dir / "backups" / requested_id
        manifest_path = backup_dir / "manifest.json"
        if not manifest_path.is_file():
            raise DevCenterError(
                "action_not_allowed",
                "The apply backup files are missing.",
                {"step": "check_backup", "check": "scope", "reason": "backup_missing"},
            )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_roots = manifest.get("roots") or {}

        # 2. Verify target wasn't externally modified since apply
        _prog(2)
        target_changed, drift_files = _live_diff_against_hashes(manifest_roots)
        if target_changed:
            raise DevCenterError(
                "action_not_allowed",
                "Target files changed since the last apply. Undo refused to avoid overwriting newer edits.",
                {"step": "verify_target", "check": "scope", "reason": "target_changed", "changed_files": drift_files},
            )

        # Verify backup integrity before modifying target
        for root_name, info in manifest_roots.items():
            before_hashes = dict(info.get("before_hashes") or {})
            for rel in list(info.get("modified") or ()) + list(info.get("removed") or ()):
                b_file = backup_dir / root_name / rel
                if not b_file.is_file() or content_hash(b_file.read_bytes()) != before_hashes.get(rel):
                    raise DevCenterError(
                        "action_not_allowed",
                        f"Backup file integrity check failed for {rel}.",
                        {"step": "verify_target", "check": "scope", "reason": "backup_corrupted"},
                    )

        # 3. Restore modified/removed files and delete added files
        _prog(3)
        multi = len(manifest_roots) > 1
        restored_files: list[str] = []
        removed_files: list[str] = []
        for root_name, info in sorted(manifest_roots.items()):
            target_dir = Path(info["target_dir"])
            for rel in info.get("added") or ():
                (target_dir / rel).unlink(missing_ok=True)
                removed_files.append(f"{root_name}/{rel}" if multi else rel)
            for rel in list(info.get("modified") or ()) + list(info.get("removed") or ()):
                b_file = backup_dir / root_name / rel
                dest = target_dir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                durable_write(dest, b_file.read_bytes())
                restored_files.append(f"{root_name}/{rel}" if multi else rel)
            _prune_empty_dirs(target_dir)

        # 4. Verify byte-for-byte match with pre-apply baseline
        _prog(4)
        for root_name, info in manifest_roots.items():
            target_dir = Path(info["target_dir"])
            before_hashes = dict(info.get("before_hashes") or {})
            if dir_file_hashes(target_dir) != before_hashes:
                raise DevCenterError(
                    "action_not_allowed",
                    "Restored files do not match the pre-apply backup hashes.",
                    {"step": "verify_restored", "check": "write", "reason": "undo_hash_mismatch"},
                )

        # 5. Update fingerprints, clear caches, update last_apply, log
        _prog(5)
        updated_record = {**record, "undone": True}
        total = len(restored_files) + len(removed_files)
        updated_doc = _refresh_target_fingerprints_and_commit(
            devcenter,
            target_sids=_target_sids(targets),
            action="undo_apply",
            target_payload=requested_id,
            before_payload=None,
            after_payload={"restored_files": restored_files, "removed_files": removed_files, "file_count": total},
            after_commit=lambda: _write_last_apply(targets.session_dir, updated_record),
        )
        _prog(5, state="done")
        return {
            "revision": int(updated_doc["revision"]),
            "apply_id": requested_id,
            "restored_files": restored_files,
            "removed_files": removed_files,
            "file_count": total,
        }
    except DevCenterError as exc:
        cur = _progress_snapshot(devcenter, int(document["revision"]), session_id)
        _set_progress(
            devcenter,
            session_id=session_id,
            apply_id=requested_id or "undo",
            step=cur.get("step") or exc.details.get("step") or UNDO_STEPS[0],
            step_index=max(1, int(cur.get("step_index") or 1)),
            step_count=count,
            state="failed",
        )
        raise


def change_report_write(devcenter: Any, request: Mapping[str, Any]) -> dict[str, Any]:
    """Generate and write a Markdown change report for the current plan and latest apply."""
    open_sess, document = _check_base_revision(devcenter, request)
    targets = _resolve_targets(devcenter, document, open_sess)
    last_record = _read_last_apply(targets.session_dir)
    if (
        last_record is not None
        and not last_record.get("undone")
        and isinstance(last_record.get("plan_snapshot"), Mapping)
    ):
        plan = dict(last_record["plan_snapshot"])
    else:
        plan = plan_service.build_plan(devcenter, document, include_proposals=False)

    warnings: list[str] = []
    if last_record and last_record.get("desktop_warning"):
        warnings.append(str(last_record["desktop_warning"]))

    markdown = build_change_report(
        session=document,
        plan=plan,
        last_apply=last_record,
        warnings=warnings,
    )
    out_path = write_change_report(
        targets.session_dir,
        markdown,
        output_path=request.get("output_path"),
    )

    def _after() -> None:
        if last_record is not None:
            _write_last_apply(targets.session_dir, {**last_record, "change_report_path": str(out_path)})

    with devcenter._lock:
        current = devcenter._require_open()
        draft = copy.deepcopy(current.document)
        _after()
        updated = devcenter._commit(
            current,
            draft,
            "change_report_write",
            out_path.name,
            None,
            {"plan_hash": plan["plan_hash"]},
        )

    return {
        "revision": int(updated["revision"]),
        "path": str(out_path),
        "markdown": markdown,
        "plan_hash": plan["plan_hash"],
    }
