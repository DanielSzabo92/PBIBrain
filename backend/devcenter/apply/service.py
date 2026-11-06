"""The local apply sequence of the open merge session (technical design section 13, build step S9).

``ApplyService`` runs the 12 steps of section 13 for ``apply``, the format only
apply, and the undo. It keeps the progress of the current run (UC5) and the
record of the last apply (UC7). It gives the Apply dialog data (UC6). Only the
pywebview JS API calls ``apply``, ``format_only_apply``, ``undo_apply``, and
``change_report_write`` (ADR 0003). The HTTP API reads the preview, the
progress, and the last apply only.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace
from typing import Any, Callable, Mapping, Sequence
import uuid

from backend.devcenter.apply import desktop as desktop_states
from backend.devcenter.apply import rescan
from backend.devcenter.apply.desktop import DesktopBridge
from backend.devcenter.apply.pipeline import ApplyJob, GuardPipeline
from backend.devcenter.apply.report import change_report
from backend.devcenter.apply.steps import (APPROVAL, BACKUP_CHECK, CANONICAL_CHECK, CHANGE_REPORT, DESKTOP_CHECK, FINGERPRINT,
                                           GUARD, PLAN_STATUS, PROMOTION, RESCAN, SOURCE_CHECK, STEPS_BY_KIND, VALIDATION,
                                           WRITE, ApplyFailure)
from backend.devcenter.compare import service as compare_service
from backend.devcenter.errors import DevCenterError
from backend.devcenter.plan import service as plan_service
from backend.devcenter.session.store import utc_now
from backend.devcenter.sources.kinds import MODEL_TMDL, LocalSource
from backend.devcenter.sources.objects import object_index

APPLY_FOLDER = "apply"
GUARD_FOLDER = "apply/guard"
LAST_FILE = "apply/last.json"

HIGH_RISK = "HIGH_RISK_PROMOTION"
UNCHECKED = "UNCHECKED_IMPACT"
# The regression limit of a full apply of the merge lab (S9 acceptance test, seconds).
APPLY_BUDGET_SECONDS = 300.0


def service(devcenter: Any) -> "ApplyService":
    """Give the apply service of a session owner. The first call makes it."""

    current = getattr(devcenter, "apply_service", None)
    if current is None:
        current = ApplyService(devcenter)
        devcenter.apply_service = current
    return current


def _revision(devcenter: Any) -> int | None:
    # No lock: a read of the progress must not wait for a running apply.
    current = getattr(devcenter, "_open", None)
    return current.document["revision"] if current is not None else None


# Risk and approvals (the merge policy, section 8) -------------------------------------------

def _risk(operations: Sequence[Mapping[str, Any]]) -> str:
    from change_guard.merge import _mutation
    from change_guard.policy.engine import MERGE_CRITICAL_TYPES, classify_risk, merge_policy

    if not operations:
        return "LOW"
    pairs = [_mutation(item) for item in operations]
    payload = {"targets": [pair[0] for pair in pairs], "allowed_mutations": [pair[1] for pair in pairs]}
    risk = classify_risk(SimpleNamespace(to_dict=lambda: payload), merge_policy())
    if any(pair[0]["object_type"] in MERGE_CRITICAL_TYPES for pair in pairs):
        risk = "CRITICAL"
    return risk


def not_checked(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    items = []
    for item in plan.get("warnings") or []:
        if item.get("kind") == "not_checked":
            view = item.get("object") or {}
            items.append({"object_id": item.get("row_key") or item.get("item_id"), "object_name": view.get("name") or item.get("row_key") or ""})
    return items


def approvals_needed(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Give the approval purposes of the one Apply dialog: HIGH and CRITICAL risk, and the items that are not checked."""

    operations = list(plan.get("operations") or [])
    needed = []
    risk = _risk(operations)
    if risk in {"HIGH", "CRITICAL"}:
        keys = sorted({str(item.get("row_key")) for item in operations if _risk([item]) in {"HIGH", "CRITICAL"}})
        needed.append({"purpose": HIGH_RISK, "risk": risk, "row_keys": keys})
    unchecked = not_checked(plan)
    if unchecked:
        needed.append({"purpose": UNCHECKED, "risk": None, "row_keys": sorted({str(item["object_id"]) for item in unchecked})})
    return needed


def _summary(plan: Mapping[str, Any]) -> dict[str, int]:
    summary = plan.get("summary") or {}
    total = {"add": 0, "change": 0, "remove": 0, "rename": 0}
    for domain in ("model", "report"):
        part = summary.get(domain) or {}
        for change, name in (("created", "add"), ("modified", "change"), ("deleted", "remove"), ("renamed", "rename")):
            total[name] += int((part.get(change) or {}).get("total") or 0)
    return total


def _failed_checks(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [{"check": item.get("kind"), "object": item.get("row_key"), "message": item.get("message") or ""}
            for item in plan.get("blocking") or []]


class _Target(SimpleNamespace):
    """The target of an apply: the source record, the loaded source, and the paths relative to its root."""


class ApplyService:
    """Owner of the apply runs of one ``DevCenterSessions``. One run at a time."""

    def __init__(self, devcenter: Any, *, pipeline: Any = None, desktop: Any = None,
                 plan_builder: Callable[..., dict[str, Any]] | None = None) -> None:
        self.devcenter = devcenter
        self.pipeline = pipeline or GuardPipeline()
        self.desktop = desktop or DesktopBridge()
        self.plan_builder = plan_builder or plan_service.build_plan
        self._lock = threading.Lock()
        self._busy = False
        self._progress: dict[str, Any] = {"apply_id": None, "kind": None, "step": None, "step_index": 0,
                                          "step_count": len(STEPS_BY_KIND["apply"]), "state": "done"}

    # Progress (UC5) -----------------------------------------------------------------------

    def progress(self) -> dict[str, Any]:
        revision = _revision(self.devcenter)
        if revision is None:
            raise DevCenterError("session_not_open", "No merge session is open.")
        with self._lock:
            value = {key: self._progress[key] for key in ("apply_id", "step", "step_index", "step_count", "state")}
        return {"revision": revision, **value}

    def _set(self, **values: Any) -> None:
        with self._lock:
            self._progress.update(values)

    def _start(self, kind: str) -> str:
        with self._lock:
            if self._busy:
                raise DevCenterError("action_not_allowed", "An apply runs now. Wait until it stops.", {"reason": "apply_running"})
            self._busy = True
            apply_id = "apl-" + uuid.uuid4().hex[:16]
            self._progress = {"apply_id": apply_id, "kind": kind, "step": None, "step_index": 0,
                              "step_count": len(STEPS_BY_KIND[kind]), "state": "running"}
            return apply_id

    def _step(self, kind: str, step: str) -> None:
        steps = STEPS_BY_KIND[kind]
        self._set(step=step, step_index=steps.index(step) + 1, state="running")

    def _finish(self, state: str) -> None:
        with self._lock:
            self._progress["state"] = state
            self._busy = False

    def _run(self, kind: str, body: Callable[[str], dict[str, Any]]) -> dict[str, Any]:
        apply_id = self._start(kind)
        try:
            reply = body(apply_id)
        except ApplyFailure as failure:
            self._finish("failed")
            raise failure.error() from failure
        except DevCenterError as exc:
            # UC32: each failure names the step where it stopped.
            exc.details.setdefault("step", self._progress["step"])
            self._finish("failed")
            raise
        except BaseException:
            self._finish("failed")
            raise
        self._finish("done")
        return reply

    # Session parts -------------------------------------------------------------------------

    def _document(self) -> dict[str, Any]:
        with self.devcenter._lock:
            return copy.deepcopy(self.devcenter._require_open().document)

    def _folder(self) -> Path:
        return Path(self.devcenter.session_folder())

    def _target(self, document: Mapping[str, Any], step: str) -> _Target:
        model_id, report_id = compare_service.targets(document)
        if model_id is None:
            raise ApplyFailure(step, "no_target_model", "The session has no target model.")
        record = self.devcenter._source(document, model_id)
        source: LocalSource = self.devcenter._load_target(record)
        # A PBIP source has the ``.pbip`` file as its root. The guard works on the folder of the project.
        root = source.root if source.root.is_dir() else source.root.parent
        if source.model_dir is None or source.model_format != MODEL_TMDL:
            raise ApplyFailure(step, "target_not_tmdl", "The app can write a target model in TMDL format only.")
        report_path = None
        if report_id is not None:
            report: LocalSource = source if report_id == model_id else self.devcenter._load_target(self.devcenter._source(document, report_id))
            if report.report_dir is None:
                raise ApplyFailure(step, "target_report_missing", "The target report is not available.")
            if report.report_dir.resolve().parent != root.resolve():
                raise ApplyFailure(step, "target_roots_differ", "The target model and the target report must be in the same PBIP folder.")
            report_path = report.report_dir.resolve().relative_to(root.resolve()).as_posix()
        if source.model_dir.resolve().parent != root.resolve():
            raise ApplyFailure(step, "target_layout_not_supported", "The target model must be in the folder of the project.")
        model_path = (source.model_dir.resolve() / "definition").relative_to(root.resolve()).as_posix()
        donors = {}
        for item in document["sources"]:
            if item["source_id"] in {model_id, report_id} or not item.get("report_path"):
                continue
            donors[item["source_id"]] = str(self.devcenter._absolute(item["report_path"]))
        return _Target(record=record, source=source, root=root.resolve(), model_path=model_path, report_path=report_path,
                       donors=donors, source_id=model_id)

    def _job(self, apply_id: str, kind: str, document: Mapping[str, Any], target: _Target, plan: Mapping[str, Any],
             approvals: Sequence[str] = ()) -> ApplyJob:
        state_root = self._folder() / GUARD_FOLDER
        if apply_id != "preview":  # A preview is a read: it makes no folder.
            state_root.mkdir(parents=True, exist_ok=True)
        unchecked = [{"item_id": item["object_id"], "row_key": item["object_id"]} for item in not_checked(plan)]
        return ApplyJob(apply_id=apply_id, kind=kind, project_id=document["session_id"], target_root=Path(target.root), state_root=state_root,
                        model_path=target.model_path, report_path=target.report_path, plan=plan, donor_paths=target.donors,
                        unchecked_items=unchecked, approvals=list(approvals))

    def _desktop(self, target: _Target, step: str) -> str:
        state = self.desktop.state(Path(target.root))
        if state not in desktop_states.STATES:
            state = desktop_states.NOT_REACHABLE
        if state == desktop_states.OPEN_UNSAVED:
            raise ApplyFailure(step, "desktop_unsaved_changes",
                               "Power BI Desktop has unsaved changes in the target. Save or close the file first.", desktop_state=state)
        return state

    def _commit(self, action: str, target_id: str, before: Any, after: Any) -> int:
        """Step 11: the new target fingerprint and row hashes, and one log entry."""

        devcenter = self.devcenter
        with devcenter._lock:
            current = devcenter._require_open()
            draft = copy.deepcopy(current.document)
            record = devcenter._source(draft, target_id)
            devcenter._record_baseline(draft, target_id, devcenter._load_target(record))
            document = devcenter._commit(current, draft, action, target_id, before, after)
            return document["revision"]

    def _load_last(self) -> dict[str, Any] | None:
        path = self._folder() / LAST_FILE
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _save_last(self, record: Mapping[str, Any]) -> None:
        path = self._folder() / LAST_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(path)

    def _check_revision(self, request: Mapping[str, Any], step: str) -> None:
        revision = _revision(self.devcenter)
        if request.get("base_revision") != revision:
            raise ApplyFailure(step, "stale_revision", "The session changed. Load it again.", code="stale_revision", revision=revision)

    def _writable(self, step: str) -> None:
        if self.devcenter._require_open().read_only:
            raise ApplyFailure(step, "read_only", "The session is open as read-only.")

    # Reads (UC6, UC7) --------------------------------------------------------------------------

    def preview(self) -> dict[str, Any]:
        """``GET apply/preview``: the Apply dialog data and the blocks of steps 1 to 5. It changes no state."""

        devcenter = self.devcenter
        with devcenter._lock:
            document = copy.deepcopy(devcenter._require_open().document)
            checked = copy.deepcopy(document)
            devcenter._check_sources(checked)
        plan = self.plan_builder(devcenter, document)
        row_keys = sorted({mark["row_key"] for mark in checked["source_marks"]})
        missing = [item["source_id"] for item in checked["sources"] if checked["source_status"].get(item["source_id"], "ok") != "ok"]
        failed = _failed_checks(plan)
        desktop_state = desktop_states.NOT_REACHABLE
        non_canonical: list[str] = []
        try:
            target = self._target(document, PLAN_STATUS)
        except (ApplyFailure, DevCenterError) as exc:
            failed.append({"check": getattr(exc, "reason", None) or "target", "object": None, "message": str(exc.message)})
            target = None
        if target is not None:
            desktop_state = self.desktop.state(Path(target.root))
            if desktop_state not in desktop_states.STATES:
                desktop_state = desktop_states.NOT_REACHABLE
            try:
                non_canonical = self.pipeline.canonical_files(self._job("preview", "apply", document, target, plan))
            except ApplyFailure as failure:
                failed.append({"check": failure.reason, "object": None, "message": failure.message})
        if missing:
            failed.append({"check": "source_not_available", "object": None, "message": "A source is not available."})
        status = plan.get("status")
        ready = (not row_keys and not failed and status != "invalid" and bool(plan.get("operations"))
                 and desktop_state != desktop_states.OPEN_UNSAVED and not non_canonical)
        return {
            "revision": document["revision"],
            "ready": ready,
            "plan_hash": plan.get("plan_hash"),
            "summary": _summary(plan),
            "unconfirmed_marks": {"count": len(row_keys), "row_keys": row_keys},
            "desktop_state": desktop_state,
            "non_canonical_files": non_canonical,
            "validation": {"status": status, "failed_checks": failed},
            "approvals_needed": approvals_needed(plan),
            "not_checked": not_checked(plan),
        }

    def last(self) -> dict[str, Any]:
        """``GET apply/last``: the last apply, the backup state, the target changes, and the rescan differences."""

        revision = _revision(self.devcenter)
        if revision is None:
            raise DevCenterError("session_not_open", "No merge session is open.")
        record = self._load_last()
        if record is None:
            return {"revision": revision, "apply_id": None, "kind": None, "finished_utc": None, "file_count": 0,
                    "backup_present": False, "target_changed": False, "changed_files": [], "rescan_differences": [], "undone": False}
        state_root = self._folder() / GUARD_FOLDER
        changed = self.pipeline.changed_files(state_root, record["operation_id"])
        backup = not record.get("undone") and self.pipeline.backup_present(state_root, record["operation_id"])
        return {"revision": revision, "apply_id": record["apply_id"], "kind": record["kind"], "finished_utc": record["finished_utc"],
                "file_count": len(record.get("files") or []), "backup_present": bool(backup), "target_changed": bool(changed),
                "changed_files": changed, "rescan_differences": record.get("rescan_differences") or [], "undone": bool(record.get("undone"))}

    # Apply (section 13) ------------------------------------------------------------------------

    def apply(self, request: Mapping[str, Any]) -> dict[str, Any]:
        return self._run("apply", lambda apply_id: self._apply(apply_id, request))

    def _apply(self, apply_id: str, request: Mapping[str, Any]) -> dict[str, Any]:
        kind = "apply"
        devcenter = self.devcenter
        started = time.monotonic()
        self._step(kind, SOURCE_CHECK)
        self._writable(SOURCE_CHECK)
        self._check_revision(request, SOURCE_CHECK)
        check = devcenter.apply_source_check()
        for item in check["items"]:
            if item["kind"] == "unconfirmed_marks":
                raise ApplyFailure(SOURCE_CHECK, "unconfirmed_marks", "Rows changed in their source. Confirm them first.",
                                   row_keys=item["row_keys"], count=len(item["row_keys"]))
            raise ApplyFailure(SOURCE_CHECK, "source_not_available", "A source is not available.", source_ids=item["source_ids"])

        self._step(kind, PLAN_STATUS)
        # The accepted state only: an agent proposal that the user did not accept has no effect (ADR 0003).
        document = self._document()
        plan = self.plan_builder(devcenter, document)
        if plan.get("status") == "invalid":
            raise ApplyFailure(PLAN_STATUS, "plan_invalid", "The plan has blocking items.", count=len(plan.get("blocking") or []))
        if request.get("plan_hash") != plan.get("plan_hash"):
            raise ApplyFailure(PLAN_STATUS, "plan_changed", "The plan changed. Open the Apply dialog again.", plan_hash=plan.get("plan_hash"))
        if not plan.get("operations"):
            raise ApplyFailure(PLAN_STATUS, "plan_empty", "The plan has no change to apply.")
        target = self._target(document, PLAN_STATUS)

        self._step(kind, DESKTOP_CHECK)
        desktop_state = self._desktop(target, DESKTOP_CHECK)

        self._step(kind, CANONICAL_CHECK)
        approvals = sorted({str(item) for item in request.get("approvals") or []})
        job = self._job(apply_id, kind, document, target, plan, approvals)
        files = self.pipeline.canonical_files(job)
        if files:
            raise ApplyFailure(CANONICAL_CHECK, "non_canonical_files", "Some model files do not have the canonical format. Use format only first.",
                               check="canonical", files=files)

        self._step(kind, VALIDATION)
        if plan.get("blocking"):
            raise ApplyFailure(VALIDATION, "validation_failed", "The full validation found blocking items.", failed_checks=_failed_checks(plan))

        self._step(kind, APPROVAL)
        needed = sorted(item["purpose"] for item in approvals_needed(plan))
        if approvals != needed:
            raise ApplyFailure(APPROVAL, "approval_missing", "Give the approvals of the Apply dialog.", check="approval", purposes=needed)

        before = object_index(target.source)
        self._step(kind, WRITE)
        self.pipeline.write(job)
        self._step(kind, GUARD)
        self.pipeline.guard(job)
        self._step(kind, PROMOTION)
        written = self.pipeline.promote(job)

        record = {"apply_id": apply_id, "kind": kind, "operation_id": job.operation_id, "plan_hash": plan.get("plan_hash"),
                  "target_id": target.source_id, "files": list(written), "approvals": approvals, "desktop_state": desktop_state,
                  "before_index": before, "rescan_differences": [], "undone": False, "finished_utc": None}
        self._save_last(record)
        return self._after_write(kind, record, target, plan, document, started)

    def _after_write(self, kind: str, record: dict[str, Any], target: _Target, plan: Mapping[str, Any],
                     document: Mapping[str, Any], started: float) -> dict[str, Any]:
        self._step(kind, RESCAN)
        try:
            after = object_index(self.devcenter._load_target(target.record))
        except Exception as exc:
            raise ApplyFailure(RESCAN, "rescan_failed", "The app could not read the target again.", check="rescan") from exc
        operations = [] if kind == "format_only" else list(plan.get("operations") or [])
        record["rescan_differences"] = rescan.differences(operations, record["before_index"], after)
        self._save_last(record)

        self._step(kind, FINGERPRINT)
        revision = self._commit("format_only_apply" if kind == "format_only" else "apply", target.source_id, None,
                                {"apply_id": record["apply_id"], "plan_hash": record["plan_hash"], "file_count": len(record["files"])})
        record["finished_utc"] = utc_now()
        if kind == "apply":
            self._step(kind, CHANGE_REPORT)
            sources = {item["source_id"]: item.get("display_name") or item["source_id"] for item in document["sources"]}
            record["change_report"] = change_report(record, plan, target_name=target.source.display_name, sources=sources)
        else:
            record["change_report"] = change_report(record, plan, target_name=target.source.display_name, sources={})
        record["seconds"] = round(time.monotonic() - started, 3)
        self._save_last(record)
        notices = [desktop_states.NOTICES[record["desktop_state"]]] if record["desktop_state"] in desktop_states.NOTICES else []
        return {"revision": revision, "apply_id": record["apply_id"], "kind": kind, "file_count": len(record["files"]),
                "files": record["files"], "desktop_state": record["desktop_state"], "notices": notices,
                "rescan_differences": record["rescan_differences"]}

    def format_only_apply(self, request: Mapping[str, Any]) -> dict[str, Any]:
        return self._run("format_only", lambda apply_id: self._format_only(apply_id, request))

    def _format_only(self, apply_id: str, request: Mapping[str, Any]) -> dict[str, Any]:
        kind = "format_only"
        started = time.monotonic()
        self._step(kind, DESKTOP_CHECK)
        self._writable(DESKTOP_CHECK)
        self._check_revision(request, DESKTOP_CHECK)
        document = self._document()
        target = self._target(document, DESKTOP_CHECK)
        desktop_state = self._desktop(target, DESKTOP_CHECK)
        self._step(kind, CANONICAL_CHECK)
        plan = {"plan_hash": "format-only", "operations": [], "steps": [], "summary": {}, "warnings": [], "blocking": []}
        job = self._job(apply_id, kind, document, target, plan)
        if not self.pipeline.canonical_files(job):
            raise ApplyFailure(CANONICAL_CHECK, "already_canonical", "All model files have the canonical format.", check="canonical")
        before = object_index(target.source)
        self._step(kind, WRITE)
        self.pipeline.write(job)
        self._step(kind, GUARD)
        self.pipeline.guard(job)
        self._step(kind, PROMOTION)
        written = self.pipeline.promote(job)
        record = {"apply_id": apply_id, "kind": kind, "operation_id": job.operation_id, "plan_hash": None, "target_id": target.source_id,
                  "files": list(written), "approvals": [], "desktop_state": desktop_state, "before_index": before,
                  "rescan_differences": [], "undone": False, "finished_utc": None}
        self._save_last(record)
        return self._after_write(kind, record, target, plan, document, started)

    # Undo (section 13) -------------------------------------------------------------------------

    def undo_apply(self, request: Mapping[str, Any]) -> dict[str, Any]:
        return self._run("undo", lambda apply_id: self._undo(apply_id, request))

    def _undo(self, apply_id: str, request: Mapping[str, Any]) -> dict[str, Any]:
        kind = "undo"
        self._step(kind, DESKTOP_CHECK)
        self._writable(DESKTOP_CHECK)
        self._check_revision(request, DESKTOP_CHECK)
        record = self._load_last()
        if record is None or record.get("undone"):
            raise ApplyFailure(DESKTOP_CHECK, "no_apply_to_undo", "No apply is available to undo.", code="not_found")
        if request.get("apply_id") not in (None, record["apply_id"]):
            raise ApplyFailure(DESKTOP_CHECK, "not_last_apply", "Only the last apply can be undone.", code="not_found")
        document = self._document()
        target = self._target(document, DESKTOP_CHECK)
        desktop_state = self._desktop(target, DESKTOP_CHECK)

        self._step(kind, BACKUP_CHECK)
        state_root = self._folder() / GUARD_FOLDER
        changed = self.pipeline.changed_files(state_root, record["operation_id"])
        if changed:
            raise ApplyFailure(BACKUP_CHECK, "target_changed", "The target files changed after the apply. The app cannot undo it.",
                               check="write", files=changed)
        if not self.pipeline.backup_present(state_root, record["operation_id"]):
            raise ApplyFailure(BACKUP_CHECK, "backup_missing", "The backup of the apply is not available.", check="write")

        self._step(kind, PROMOTION)
        files = self.pipeline.undo(state_root, record["operation_id"])

        self._step(kind, RESCAN)
        try:
            after = object_index(self.devcenter._load_target(target.record))
        except Exception as exc:
            raise ApplyFailure(RESCAN, "rescan_failed", "The app could not read the target again.", check="rescan") from exc
        before = record.get("before_index") or {}
        differences = [{"object": key, "expected": "restored", "found": "different"}
                       for key in sorted(set(before) | set(after)) if before.get(key) != after.get(key)]

        self._step(kind, FINGERPRINT)
        revision = self._commit("undo_apply", target.source_id, {"apply_id": record["apply_id"]}, {"undo_id": apply_id})
        record.update(undone=True, undo_id=apply_id, undo_finished_utc=utc_now(), undo_differences=differences)
        self._save_last(record)
        notices = [desktop_states.NOTICES[desktop_state]] if desktop_state in desktop_states.NOTICES else []
        return {"revision": revision, "apply_id": record["apply_id"], "undo_id": apply_id, "file_count": len(files), "files": files,
                "desktop_state": desktop_state, "notices": notices, "rescan_differences": differences}

    # Change report (section 13 step 12) ---------------------------------------------------------

    def change_report_write(self, request: Mapping[str, Any]) -> dict[str, Any]:
        """Write the Markdown change report of the last apply into the session folder. The app never commits."""

        revision = _revision(self.devcenter)
        if request.get("base_revision") != revision:
            raise DevCenterError("stale_revision", "The session changed. Load it again.", {"revision": revision})
        record = self._load_last()
        if record is None or not record.get("change_report"):
            raise DevCenterError("not_found", "No apply has a change report.", {"reason": "no_apply"})
        if request.get("apply_id") not in (None, record["apply_id"]):
            raise DevCenterError("not_found", "Only the last apply has a change report.", {"reason": "not_last_apply"})
        file_name = request.get("file_name") or f"change-report-{record['apply_id']}.md"
        if file_name.startswith(".") or "\\" in file_name or Path(file_name).name != file_name:
            raise DevCenterError("invalid_payload", "The file name must be a plain file name.", {"field": "file_name"})
        path = self._folder() / APPLY_FOLDER / file_name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(record["change_report"], encoding="utf-8", newline="\n")
        return {"revision": revision, "apply_id": record["apply_id"], "path": self.devcenter.relative_path(path),
                "markdown": record["change_report"]}
