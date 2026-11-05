"""The one open merge session of the app, and its state changes (technical design sections 11 and 14).

Only the pywebview JS API calls the change methods of this class (ADR 0003). The
HTTP read routes call ``sessions_list`` and ``session_summary`` only.
"""

from __future__ import annotations

import copy
import os
from pathlib import Path
import shutil
import threading
import uuid
from typing import Any, Callable, Mapping

from backend.devcenter.errors import DevCenterError, not_allowed
from backend.devcenter.session.proposals import session_lists
from backend.devcenter.session.secrets import check_secrets
from backend.devcenter.session.store import (
    LOCK_FREE,
    SCHEMA_DAMAGED,
    SCHEMA_OK,
    SCHEMA_VERSION,
    SessionFiles,
    SessionLock,
    SessionReadError,
    ensure_gitignore,
    migrate,
    session_folders,
    sessions_dir,
    require_writable,
    utc_now,
    valid_session_id,
)
from backend.devcenter.sources.fingerprint import source_fingerprint
from backend.devcenter.sources.kinds import CLOUD_MODEL, CLOUD_REPORT, LocalSource, detect_local_source, require_model_target, require_report_target
from backend.devcenter.sources.objects import object_index
from backend.devcenter.sources.targets import copy_source, prepare_empty_folder, remove_children, write_empty_target

LOCATION_PROJECT = "project"
LOCATION_APP_DATA = "app_data"
ROLE_DONOR = "donor"
ROLE_TARGET = "target"

MARK_SOURCE_CHANGED = "source_changed"
MARK_OBJECT_MISSING = "source_object_missing"
MARK_NEW_SINCE_START = "new_since_start"
MARK_KINDS = (MARK_SOURCE_CHANGED, MARK_OBJECT_MISSING, MARK_NEW_SINCE_START)

STATUS_OK = "ok"
STATUS_MISSING = "missing"
STATUS_UNREADABLE = "unreadable"
FINGERPRINT_SAME = "same"
FINGERPRINT_CHANGED = "changed"
FINGERPRINT_NOT_CHECKED = "not_checked"

REPORT_NEW_EMPTY = {"mode": "new_empty"}
CLOUD_KINDS = (CLOUD_MODEL, CLOUD_REPORT)


def default_app_data_dir() -> Path | None:
    value = os.environ.get("APPDATA")
    return Path(value) / "PBIBrain" if value else None


def new_document(session_id: str, display_name: str, location: str) -> dict[str, Any]:
    now = utc_now()
    return {
        "schema_version": SCHEMA_VERSION,
        "session_id": session_id,
        "display_name": display_name,
        "location": location,
        "created_at": now,
        "updated_at": now,
        "revision": 1,
        "next_source_number": 1,
        "sources": [],
        "target": {"model": None, "report": dict(REPORT_NEW_EMPTY)},
        "compare_mode": "default",
        "alignment_overrides": {},
        "merge_choices": {},
        "removal_policies": {},
        "prerequisite_mappings": {},
        "need_mappings": {},
        "item_actions": {},
        "selected_offers": [],
        "naming_rules": {"path": None, "hash": None},
        "proposals": [],
        "questions": [],
        "source_fingerprints": {},
        "row_hashes": {},
        "source_marks": [],
        "source_status": {},
        "checked_at": None,
    }


class _OpenSession:
    def __init__(self, files: SessionFiles, document: dict[str, Any], lock: SessionLock, read_only: bool, location: str) -> None:
        self.files = files
        self.document = document
        self.lock = lock
        self.read_only = read_only
        self.location = location


class DevCenterSessions:
    """Owner of the open merge session. Thread safe."""

    def __init__(self, *, app_data_dir: Path | None | Callable[[], Path | None] = default_app_data_dir, owner: str | None = None,
                 cloud: Any = None) -> None:
        self._app_data = app_data_dir
        # The cloud service (build step S11, ``backend.devcenter.sources.cloud``). It starts at the first cloud call.
        self.cloud = cloud
        self.owner = owner or uuid.uuid4().hex
        self._lock = threading.RLock()
        self._project_root: Path | None = None
        self._open: _OpenSession | None = None
        self._cached_plan: dict[str, Any] | None = None
        self._plan_state: str | None = None

    # Project and locations -------------------------------------------------

    def attach_project(self, root: str | Path | None) -> None:
        """Set the project root. A change of project closes the open session."""

        with self._lock:
            new_root = Path(root).resolve() if root is not None else None
            if new_root != self._project_root:
                self._close()
            self._project_root = new_root

    @property
    def project_root(self) -> Path:
        if self._project_root is None:
            raise not_allowed("Open a project first.", "no_project")
        return self._project_root

    def _app_data_dir(self) -> Path | None:
        value = self._app_data() if callable(self._app_data) else self._app_data
        return Path(value) if value is not None else None

    def _bases(self) -> list[tuple[str, Path]]:
        bases = [(LOCATION_PROJECT, self.project_root / ".pbibrain")]
        app_data = self._app_data_dir()
        if app_data is not None:
            bases.append((LOCATION_APP_DATA, app_data))
        return bases

    def _relative(self, path: Path) -> str:
        try:
            return Path(os.path.relpath(path, self.project_root)).as_posix()
        except ValueError as exc:
            raise not_allowed("The source must be on the same drive as the project.", "other_drive") from exc

    def _absolute(self, relative: str) -> Path:
        return (self.project_root / relative).resolve()

    def relative_path(self, path: Path) -> str:
        return self._relative(path)

    # Cloud sources (build step S11) ------------------------------------------

    def cloud_service(self) -> Any:
        if self.cloud is None:
            from backend.devcenter.sources.cloud import CloudService

            self.cloud = CloudService()
        return self.cloud

    def session_folder(self) -> Path:
        return self._require_open().files.folder

    def source_record(self, source_id: Any) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._source(self._require_open().document, source_id))

    def add_prepared_source(self, request: Mapping[str, Any], action: str, record: Mapping[str, Any],
                            prepare: Callable[[], LocalSource]) -> dict[str, Any]:
        """Add a source record that a different module made (a cloud source).

        ``prepare`` gives the baseline source. It runs only after the duplicate check.
        """

        with self._lock:
            added: dict[str, Any] = {}

            def mutate(document: dict[str, Any]) -> tuple[Any, Any]:
                item_id = (record.get("cloud") or {}).get("item_id")
                if item_id and any((item.get("cloud") or {}).get("item_id") == item_id for item in document["sources"]):
                    raise not_allowed("This source is already in the session.", "duplicate_source")
                source_id = f"src-{document['next_source_number']}"
                document["next_source_number"] += 1
                added.update({"source_id": source_id, **copy.deepcopy(dict(record))})
                self._record_baseline(document, source_id, prepare())
                document["sources"].append(added)
                return None, copy.deepcopy(added)

            document = self._change(request, action, None, mutate)
            return {"revision": document["revision"], "source": self._source_view(document, added)}

    # Reads -----------------------------------------------------------------

    @property
    def revision(self) -> int | None:
        with self._lock:
            return self._open.document["revision"] if self._open else None

    def _require_open(self) -> _OpenSession:
        if self._open is None:
            raise DevCenterError("session_not_open", "No merge session is open.")
        return self._open

    def sessions_list(self) -> dict[str, Any]:
        """``GET sessions`` (UC1): each session of the project and of the app data folder."""

        with self._lock:
            rows: list[dict[str, Any]] = []
            for location, base in self._bases():
                for folder in session_folders(base):
                    rows.append(self._list_row(location, folder))
            rows.sort(key=lambda row: (row["updated_at"] or "", row["session_id"]), reverse=True)
            return {"revision": self.revision, "sessions": rows}

    def _list_row(self, location: str, folder: Path) -> dict[str, Any]:
        files = SessionFiles(folder)
        is_open = self._open is not None and self._open.files.folder == folder
        row: dict[str, Any] = {
            "session_id": folder.name,
            "location": location,
            "display_name": None,
            "updated_at": None,
            "target_model_name": None,
            "target_report_name": None,
            "source_count": 0,
            "plan_status": None,
            "lock_state": LOCK_FREE if is_open else SessionLock(folder, self.owner).state(),
            "schema_state": SCHEMA_OK,
            "is_open": is_open,
        }
        try:
            document = self._open.document if is_open else files.read()
        except SessionReadError as exc:
            row["schema_state"] = exc.schema_state
            return row
        except DevCenterError:
            row["schema_state"] = SCHEMA_DAMAGED
            return row
        try:
            sources = {item["source_id"]: item for item in document.get("sources", [])}
            target = document.get("target") or {}
            model = target.get("model") or {}
            report = target.get("report") or {}
            row.update({
                "display_name": str(document.get("display_name") or ""),
                "updated_at": document.get("updated_at"),
                "source_count": len(sources),
                "target_model_name": sources.get(model.get("source_id"), {}).get("display_name"),
                "target_report_name": sources.get(report.get("source_id"), {}).get("display_name"),
            })
        except (AttributeError, KeyError, TypeError):
            row["schema_state"] = SCHEMA_DAMAGED
        return row

    def session_summary(self) -> dict[str, Any]:
        """``GET session``: the summary of the open session. It never runs a source check or a plan."""

        with self._lock:
            current = self._require_open()
            document = current.document
            marks = document["source_marks"]
            by_kind = {kind: sum(1 for mark in marks if mark["mark"] == kind) for kind in MARK_KINDS}
            sources = [self._source_view(document, item) for item in document["sources"]]
            plan_status = self._cached_plan["status"] if self._cached_plan is not None else None
            plan_state = "ready" if self._cached_plan is not None else self._plan_state
            return {
                "revision": document["revision"],
                "session_id": document["session_id"],
                "display_name": document["display_name"],
                "location": current.location,
                "read_only": current.read_only,
                "created_at": document["created_at"],
                "updated_at": document["updated_at"],
                "checked_at": document["checked_at"],
                "sources": sources,
                "target": copy.deepcopy(document["target"]),
                "compare_mode": document["compare_mode"],
                "plan_status": plan_status,
                "plan_state": plan_state,
                "counts": {
                    "sources": len(sources),
                    "donors": sum(1 for item in sources if item["role"] == ROLE_DONOR),
                    "merge_choices": len(document["merge_choices"]),
                    "marks": len(marks),
                    "marks_by_kind": by_kind,
                },
                # UC9: each field of each open proposal and question, with the blocked state.
                **session_lists(document),
            }

    @staticmethod
    def _source_view(document: Mapping[str, Any], item: Mapping[str, Any]) -> dict[str, Any]:
        source_id = item["source_id"]
        status = document["source_status"].get(source_id, STATUS_OK)
        marks = sum(1 for mark in document["source_marks"] if mark["source_id"] == source_id)
        if status != STATUS_OK:
            fingerprint_state = FINGERPRINT_NOT_CHECKED
        else:
            fingerprint_state = FINGERPRINT_CHANGED if marks else FINGERPRINT_SAME
        return {**copy.deepcopy(dict(item)), "status": status, "fingerprint_state": fingerprint_state, "mark_count": marks}

    def marks(self) -> list[dict[str, Any]]:
        with self._lock:
            return copy.deepcopy(self._require_open().document["source_marks"])

    # Change frame ------------------------------------------------------------

    def _change(self, request: Mapping[str, Any], action: str, target: Any,
                mutate: Callable[[dict[str, Any]], tuple[Any, Any]], *,
                log: Callable[[], list[Mapping[str, Any]]] | None = None) -> dict[str, Any]:
        """Run one state change: check the revision, change a copy, save it, then log it.

        ``log`` gives the log entries after ``mutate`` ran (build step S10). Each
        entry replaces fields of the default entry. With no ``log``, the change
        writes one user entry.
        """

        current = self._require_open()
        require_writable(current.read_only)
        revision = current.document["revision"]
        if request.get("base_revision") != revision:
            raise DevCenterError("stale_revision", "The session changed. Load it again.", {"revision": revision})
        draft = copy.deepcopy(current.document)
        before, after = mutate(draft)
        return self._commit(current, draft, action, target, before, after, log() if log is not None else None)

    def _commit(self, current: _OpenSession, draft: dict[str, Any], action: str, target: Any, before: Any, after: Any,
                log: list[Mapping[str, Any]] | None = None) -> dict[str, Any]:
        draft["revision"] = current.document["revision"] + 1
        draft["updated_at"] = utc_now()
        self._cached_plan = None
        self._plan_state = "computing"
        default = {
            "time": draft["updated_at"],
            "author": "user",
            "mcp_client": None,
            "action": action,
            "target": target,
            "before": before,
            "after": after,
            "reason": None,
            "proposal_id": None,
            "revision": draft["revision"],
        }
        entries = [{**default, **dict(item)} for item in log] if log is not None else [default]
        for entry in entries:
            check_secrets(entry)
        current.files.save(draft)
        current.document = draft
        try:
            for entry in entries:
                current.files.append_log(entry)
        except OSError:
            # The state is saved. A lost log line must not undo it.
            pass
        return draft

    # Sessions ----------------------------------------------------------------

    def create(self, request: Mapping[str, Any]) -> dict[str, Any]:
        with self._lock:
            name = str(request.get("display_name") or "").strip()
            if not name:
                raise DevCenterError("invalid_payload", "Type a session name.", {"reason": "name_required"})
            location = request.get("location") or LOCATION_PROJECT
            bases = dict(self._bases())
            if location not in bases:
                raise DevCenterError("invalid_payload", "The session location is not available.", {"reason": "location_unavailable"})
            session_id = uuid.uuid4().hex
            document = new_document(session_id, name, location)
            check_secrets(document)
            folder = sessions_dir(bases[location]) / session_id
            folder.mkdir(parents=True)
            try:
                ensure_gitignore(self.project_root / ".pbibrain")
                files = SessionFiles(folder)
                files.save(document)
                lock = SessionLock(folder, self.owner)
                lock.acquire()
                files.append_log({"time": document["created_at"], "author": "user", "mcp_client": None, "action": "session_create",
                                  "target": session_id, "before": None, "after": {"display_name": name}, "reason": None,
                                  "proposal_id": None, "revision": 1})
            except BaseException:
                shutil.rmtree(folder, ignore_errors=True)
                raise
            self._close()
            self._open = _OpenSession(files, document, lock, False, location)
            return {"revision": 1, "session_id": session_id, "read_only": False}

    def _find(self, session_id: str) -> tuple[str, Path]:
        for location, base in self._bases():
            folder = sessions_dir(base) / session_id
            if (folder / "session.json").is_file():
                return location, folder
        raise DevCenterError("not_found", "The session does not exist.", {"session_id": session_id})

    def open(self, request: Mapping[str, Any]) -> dict[str, Any]:
        with self._lock:
            session_id = valid_session_id(request.get("session_id"))
            if self._open is not None and self._open.files.session_id == session_id:
                current = self._open
                return {"revision": current.document["revision"], "session_id": session_id, "read_only": current.read_only,
                        "migrated": False, "mark_count": len(current.document["source_marks"])}
            location, folder = self._find(session_id)
            files = SessionFiles(folder)
            raw = files.read()
            document, migrated = migrate(raw)
            lock = SessionLock(folder, self.owner)
            read_only = not lock.acquire()
            try:
                if migrated and not read_only:
                    files.backup(raw["schema_version"])
                    files.save(document)
                self._close()
                self._open = _OpenSession(files, document, lock, read_only, location)
                if not read_only:
                    draft = copy.deepcopy(document)
                    if self._check_sources(draft):
                        self._commit(self._open, draft, "sources_check", session_id, None, self._marks_summary(draft))
                else:
                    self._check_sources(self._open.document)
            except BaseException:
                if not read_only and (self._open is None or self._open.files.folder != folder):
                    lock.release()
                raise
            current = self._open
            return {"revision": current.document["revision"], "session_id": session_id, "read_only": read_only,
                    "migrated": migrated, "mark_count": len(current.document["source_marks"])}

    def close(self, request: Mapping[str, Any] | None = None) -> dict[str, Any]:
        with self._lock:
            current = self._open
            reply = {"revision": current.document["revision"] if current else None,
                     "session_id": current.files.session_id if current else None}
            self._close()
            return reply

    def _close(self) -> None:
        current, self._open = self._open, None
        self._cached_plan = None
        self._plan_state = None
        if current is not None and not current.read_only:
            current.lock.release()

    # Sources -----------------------------------------------------------------

    def _source_record(self, document: dict[str, Any], source: LocalSource, role: str) -> dict[str, Any]:
        source_id = f"src-{document['next_source_number']}"
        document["next_source_number"] += 1
        return {
            "source_id": source_id,
            "kind": source.kind,
            "role": role,
            "display_name": source.display_name,
            "path": self._relative(source.root),
            "model_path": self._relative(source.model_dir) if source.model_dir else None,
            "model_format": source.model_format,
            "report_path": self._relative(source.report_dir) if source.report_dir else None,
            "report_format": source.report_format,
            "access_type": None,
        }

    def _record_baseline(self, document: dict[str, Any], source_id: str, source: LocalSource) -> None:
        document["source_fingerprints"][source_id] = source_fingerprint(source)
        document["row_hashes"][source_id] = object_index(source)
        document["source_status"][source_id] = STATUS_OK
        document["source_marks"] = [mark for mark in document["source_marks"] if mark["source_id"] != source_id]
        document["checked_at"] = utc_now()

    def _add(self, document: dict[str, Any], source: LocalSource, role: str) -> dict[str, Any]:
        path = self._relative(source.root)
        if any((item["path"] or "").casefold() == path.casefold() for item in document["sources"]):
            raise not_allowed("This source is already in the session.", "duplicate_source", path=path)
        record = self._source_record(document, source, role)
        self._record_baseline(document, record["source_id"], source)
        document["sources"].append(record)
        return record

    @staticmethod
    def _source(document: Mapping[str, Any], source_id: Any) -> dict[str, Any]:
        for item in document["sources"]:
            if item["source_id"] == source_id:
                return item
        raise DevCenterError("not_found", "The source is not in the session.", {"source_id": source_id})

    def _load(self, record: Mapping[str, Any]) -> LocalSource:
        if record["kind"] in CLOUD_KINDS:
            return self.cloud_service().load(self, record)
        return detect_local_source(self._absolute(record["path"]))

    def _load_target(self, record: Mapping[str, Any]) -> LocalSource:
        if record["kind"] in CLOUD_KINDS:
            raise not_allowed("Pull to local PBIP first.", "cloud_target")
        return self._load(record)

    def source_add(self, request: Mapping[str, Any]) -> dict[str, Any]:
        with self._lock:
            source = detect_local_source(str(request.get("path") or ""))
            added: dict[str, Any] = {}

            def mutate(document: dict[str, Any]) -> tuple[Any, Any]:
                added.update(self._add(document, source, ROLE_DONOR))
                return None, added

            document = self._change(request, "source_add", None, mutate)
            return {"revision": document["revision"], "source": self._source_view(document, added)}

    def source_remove(self, request: Mapping[str, Any]) -> dict[str, Any]:
        with self._lock:
            source_id = request.get("source_id")
            count = {"value": 0}

            def mutate(document: dict[str, Any]) -> tuple[Any, Any]:
                record = self._source(document, source_id)
                document["sources"].remove(record)
                for key in ("source_fingerprints", "row_hashes", "source_status"):
                    document[key].pop(source_id, None)
                document["source_marks"] = [mark for mark in document["source_marks"] if mark["source_id"] != source_id]
                target = document["target"]
                if (target.get("model") or {}).get("source_id") == source_id:
                    target["model"] = None
                if (target.get("report") or {}).get("source_id") == source_id:
                    target["report"] = dict(REPORT_NEW_EMPTY)
                # Merge Choices that take from the source stay (UC33). The plan step blocks them.
                count["value"] = sum(1 for choice in document["merge_choices"].values()
                                     if isinstance(choice, Mapping) and choice.get("source_id") == source_id)
                return record, None

            document = self._change(request, "source_remove", source_id, mutate)
            return {"revision": document["revision"], "source_id": source_id, "choice_count": count["value"]}

    def source_relink(self, request: Mapping[str, Any]) -> dict[str, Any]:
        with self._lock:
            source_id = request.get("source_id")
            source = detect_local_source(str(request.get("path") or ""))
            changed: dict[str, Any] = {}

            def mutate(document: dict[str, Any]) -> tuple[Any, Any]:
                record = self._source(document, source_id)
                if source.kind != record["kind"]:
                    raise not_allowed("The new place has a different source kind.", "kind_changed", kind=source.kind)
                path = self._relative(source.root)
                if any((item["path"] or "").casefold() == path.casefold() and item["source_id"] != source_id for item in document["sources"]):
                    raise not_allowed("This source is already in the session.", "duplicate_source", path=path)
                before = copy.deepcopy(record)
                record.update({
                    "path": path,
                    "model_path": self._relative(source.model_dir) if source.model_dir else None,
                    "model_format": source.model_format,
                    "report_path": self._relative(source.report_dir) if source.report_dir else None,
                    "report_format": source.report_format,
                })
                # The baseline stays. The check marks the rows that differ at the new place.
                self._check_one(document, record)
                changed.update(record)
                return before, copy.deepcopy(record)

            document = self._change(request, "source_relink", source_id, mutate)
            return {"revision": document["revision"], "source": self._source_view(document, changed)}

    # Target ------------------------------------------------------------------

    def target_set(self, request: Mapping[str, Any]) -> dict[str, Any]:
        with self._lock:
            model = request.get("model")
            report = request.get("report") or dict(REPORT_NEW_EMPTY)
            if not isinstance(model, Mapping):
                raise DevCenterError("invalid_payload", "Select a target model.", {"reason": "model_required"})
            current = self._require_open()
            require_writable(current.read_only)
            if request.get("base_revision") != current.document["revision"]:
                raise DevCenterError("stale_revision", "The session changed. Load it again.", {"revision": current.document["revision"]})
            document = current.document
            mode = model.get("mode")
            # Check everything first, so that a refusal leaves nothing on disk.
            folder: Path | None = None
            original: LocalSource | None = None
            if mode == "existing":
                require_model_target(self._load_target(self._source(document, model.get("source_id"))))
            elif mode == "copy_of":
                original = self._load_target(self._source(document, model.get("source_id")))
                require_model_target(original)
                folder = prepare_empty_folder(str(model.get("path") or ""))
            elif mode == "empty":
                folder = prepare_empty_folder(str(model.get("path") or ""))
                self._relative(folder)
            else:
                raise DevCenterError("invalid_payload", "The target model mode is not valid.", {"reason": "invalid_mode"})
            if report.get("mode") == "existing":
                require_report_target(self._load_target(self._source(document, report.get("source_id"))))
            elif report.get("mode") != "new_empty":
                raise DevCenterError("invalid_payload", "The target report mode is not valid.", {"reason": "invalid_mode"})

            created_folder = folder is not None and not folder.exists()
            added: list[dict[str, Any]] = []
            try:
                created: LocalSource | None = None
                if mode == "empty":
                    assert folder is not None
                    created = detect_local_source(write_empty_target(folder, str(model.get("name") or "Merged")))
                elif mode == "copy_of":
                    assert folder is not None and original is not None
                    created = detect_local_source(copy_source(original, folder))

                def mutate(draft: dict[str, Any]) -> tuple[Any, Any]:
                    before = copy.deepcopy(draft["target"])
                    model_target: dict[str, Any] = {"mode": mode, "source_id": model.get("source_id")}
                    report_target: dict[str, Any] = dict(report)
                    if created is not None:
                        record = self._add(draft, created, ROLE_TARGET)
                        added.append(record)
                        model_target["source_id"] = record["source_id"]
                        if mode == "copy_of":
                            model_target["copy_of"] = model.get("source_id")
                        if mode == "empty" and report_target.get("mode") == "new_empty":
                            report_target = {"mode": "existing", "source_id": record["source_id"]}
                    draft["target"] = {"model": model_target, "report": report_target}
                    targets = {model_target.get("source_id"), report_target.get("source_id")}
                    for item in draft["sources"]:
                        item["role"] = ROLE_TARGET if item["source_id"] in targets else ROLE_DONOR
                    return before, copy.deepcopy(draft["target"])

                draft = copy.deepcopy(document)
                before, after = mutate(draft)
                saved = self._commit(current, draft, "target_set", "target", before, after)
            except BaseException:
                if folder is not None and mode in {"empty", "copy_of"}:
                    if created_folder:
                        shutil.rmtree(folder, ignore_errors=True)
                    else:
                        remove_children(folder)
                raise
            return {"revision": saved["revision"], "target": copy.deepcopy(saved["target"]),
                    "sources_added": [self._source_view(saved, item) for item in added]}

    # Merge Choices -----------------------------------------------------------

    def merge_choice_set(self, request: Mapping[str, Any]) -> dict[str, Any]:
        with self._lock:
            row_key = request.get("row_key")
            if not row_key or not isinstance(row_key, str):
                raise DevCenterError("invalid_payload", "The row key is required.", {"reason": "row_key_required"})
            choice = request.get("choice")
            if isinstance(choice, str):
                choice = {"kind": choice}
            elif choice is not None and not isinstance(choice, Mapping):
                raise DevCenterError("invalid_payload", "The choice must be an object, string, or null.", {"reason": "invalid_choice"})
            if choice is not None:
                choice = dict(choice)

            def mutate(document: dict[str, Any]) -> tuple[Any, Any]:
                before = copy.deepcopy(document["merge_choices"].get(row_key))
                if choice is None:
                    document["merge_choices"].pop(row_key, None)
                    after = None
                else:
                    document["merge_choices"][row_key] = copy.deepcopy(choice)
                    after = copy.deepcopy(choice)
                return before, after

            document = self._change(request, "merge_choice_set", row_key, mutate)
            return {"revision": document["revision"], "row_key": row_key, "choice": choice}

    def merge_choice_bulk_set(self, request: Mapping[str, Any]) -> dict[str, Any]:
        with self._lock:
            row_keys = list(request.get("row_keys") or [])
            single_choice = request.get("choice")
            items = list(request.get("items") or [])
            if not row_keys and not items:
                raise DevCenterError("invalid_payload", "No rows specified.", {"reason": "row_keys_required"})

            assignments: list[tuple[str, Any]] = []
            if row_keys:
                c = {"kind": single_choice} if isinstance(single_choice, str) else dict(single_choice) if isinstance(single_choice, Mapping) else None
                for key in row_keys:
                    assignments.append((key, c))
            for item in items:
                if isinstance(item, Mapping):
                    k = item.get("row_key")
                    c = item.get("choice")
                    c = {"kind": c} if isinstance(c, str) else dict(c) if isinstance(c, Mapping) else None
                    if k:
                        assignments.append((k, c))

            updated_keys: list[str] = []

            def mutate(document: dict[str, Any]) -> tuple[Any, Any]:
                before = {key: copy.deepcopy(document["merge_choices"].get(key)) for key, _ in assignments}
                after = {}
                for key, ch in assignments:
                    updated_keys.append(key)
                    if ch is None:
                        document["merge_choices"].pop(key, None)
                        after[key] = None
                    else:
                        document["merge_choices"][key] = copy.deepcopy(ch)
                        after[key] = copy.deepcopy(ch)
                return before, after

            document = self._change(request, "merge_choice_bulk_set", None, mutate)
            return {"revision": document["revision"], "count": len(updated_keys), "row_keys": updated_keys}


    # Source check and marks --------------------------------------------------

    @staticmethod
    def _marks_summary(document: Mapping[str, Any]) -> dict[str, Any]:
        return {"mark_count": len(document["source_marks"]), "status": dict(document["source_status"])}

    def _check_one(self, document: dict[str, Any], record: dict[str, Any]) -> None:
        source_id = record["source_id"]
        others = [mark for mark in document["source_marks"] if mark["source_id"] != source_id]
        has_marks = len(others) != len(document["source_marks"])
        if record["kind"] in CLOUD_KINDS:
            # A cloud check is silent: no sign-in window. No token gives "unreadable".
            try:
                cloud_source = self.cloud_service().check_source(self, record, has_marks)
                fingerprint = source_fingerprint(cloud_source) if cloud_source is not None else None
            except DevCenterError:
                document["source_status"][source_id] = STATUS_UNREADABLE
                return
            document["source_status"][source_id] = STATUS_OK
            if cloud_source is None:
                return
            source = cloud_source
        else:
            path = self._absolute(record["path"])
            if not path.exists():
                document["source_status"][source_id] = STATUS_MISSING
                return
            try:
                source = detect_local_source(path)
                fingerprint = source_fingerprint(source)
            except DevCenterError:
                document["source_status"][source_id] = STATUS_UNREADABLE
                return
            document["source_status"][source_id] = STATUS_OK
        if fingerprint == document["source_fingerprints"].get(source_id) and not has_marks:
            return
        marks = self._diff(source_id, document["row_hashes"].get(source_id, {}), object_index(source))
        document["source_marks"] = sorted(others + marks, key=lambda mark: (mark["source_id"], mark["row_key"]))
        if not marks:
            # The files changed outside the indexed objects. No row needs a confirm.
            document["source_fingerprints"][source_id] = fingerprint

    @staticmethod
    def _diff(source_id: str, baseline: Mapping[str, str], current: Mapping[str, str]) -> list[dict[str, Any]]:
        marks = []
        for key in sorted(set(baseline) | set(current)):
            if key not in current:
                marks.append({"source_id": source_id, "row_key": key, "mark": MARK_OBJECT_MISSING})
            elif key not in baseline:
                marks.append({"source_id": source_id, "row_key": key, "mark": MARK_NEW_SINCE_START})
            elif baseline[key] != current[key]:
                marks.append({"source_id": source_id, "row_key": key, "mark": MARK_SOURCE_CHANGED})
        return marks

    def _check_sources(self, document: dict[str, Any]) -> bool:
        """Check each source. Give True when the stored state changed."""

        before = (copy.deepcopy(document["source_marks"]), dict(document["source_status"]), dict(document["source_fingerprints"]))
        for record in document["sources"]:
            self._check_one(document, record)
        changed = before != (document["source_marks"], document["source_status"], document["source_fingerprints"])
        if changed:
            document["checked_at"] = utc_now()
        return changed

    def sources_check(self, request: Mapping[str, Any]) -> dict[str, Any]:
        with self._lock:
            current = self._require_open()
            if current.read_only:
                self._check_sources(current.document)
                document = current.document
            else:
                if request.get("base_revision") != current.document["revision"]:
                    raise DevCenterError("stale_revision", "The session changed. Load it again.", {"revision": current.document["revision"]})
                draft = copy.deepcopy(current.document)
                document = (self._commit(current, draft, "sources_check", "sources", None, self._marks_summary(draft))
                            if self._check_sources(draft) else current.document)
            return {
                "revision": document["revision"],
                "sources": [{"source_id": item["source_id"], "status": document["source_status"].get(item["source_id"], STATUS_OK)}
                            for item in document["sources"]],
                "mark_count": len(document["source_marks"]),
            }

    def row_confirm(self, request: Mapping[str, Any]) -> dict[str, Any]:
        """UC27: confirm each marked row of the list in one revision step (all or nothing)."""

        with self._lock:
            keys = request.get("row_keys")
            if not isinstance(keys, list) or not keys:
                raise DevCenterError("invalid_payload", "Select at least one row.", {"reason": "row_keys_required"})
            wanted = list(dict.fromkeys(keys))

            def mutate(document: dict[str, Any]) -> tuple[Any, Any]:
                marked = {mark["row_key"] for mark in document["source_marks"]}
                unknown = [key for key in wanted if key not in marked]
                if unknown:
                    raise DevCenterError("not_found", "These rows have no mark to confirm.", {"row_keys": unknown})
                selected = set(wanted)
                before = [mark for mark in document["source_marks"] if mark["row_key"] in selected]
                for source_id in sorted({mark["source_id"] for mark in before}):
                    record = self._source(document, source_id)
                    source = self._load(record)
                    current = object_index(source)
                    baseline = document["row_hashes"].setdefault(source_id, {})
                    for mark in before:
                        if mark["source_id"] != source_id:
                            continue
                        key = mark["row_key"]
                        if key in current:
                            baseline[key] = current[key]
                        else:
                            baseline.pop(key, None)
                    document["row_hashes"][source_id] = dict(sorted(baseline.items()))
                    remaining = [mark for mark in self._diff(source_id, baseline, current) if mark["row_key"] not in selected]
                    others = [mark for mark in document["source_marks"] if mark["source_id"] != source_id]
                    document["source_marks"] = sorted(others + remaining, key=lambda item: (item["source_id"], item["row_key"]))
                    if not remaining:
                        document["source_fingerprints"][source_id] = source_fingerprint(source)
                return before, None

            document = self._change(request, "row_confirm", wanted, mutate)
            return {"revision": document["revision"], "confirmed": wanted, "mark_count": len(document["source_marks"])}

    def apply_source_check(self) -> dict[str, Any]:
        """Step 1 of a local apply (section 13): check the sources, then report the blocking state."""

        with self._lock:
            current = self._require_open()
            self.sources_check({"base_revision": current.document["revision"]})
            document = self._require_open().document
            missing = [item["source_id"] for item in document["sources"]
                       if document["source_status"].get(item["source_id"], STATUS_OK) != STATUS_OK]
            row_keys = sorted({mark["row_key"] for mark in document["source_marks"]})
            items = []
            if row_keys:
                items.append({"kind": "unconfirmed_marks", "row_keys": row_keys})
            if missing:
                items.append({"kind": "source_not_available", "source_ids": missing})
            return {"revision": document["revision"], "blocking": bool(items), "items": items}
