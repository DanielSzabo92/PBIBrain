"""Fake Development Center server for UI tests (UI design section 10, step U0).

Run from the repository root: python -m tests.devcenter_ui_server --port 8766

The server keeps one in-memory scenario state. It serves the /api/devcenter
reads from that state, a mock of the pywebview JS API at
POST /__test__/jsapi/<method>, the test controls under /__test__, and the
built frontend (frontend/dist) with the test shim tag in index.html.

The shim and the /__test__ routes are test code only. Do not import this
module from backend/: backend/api/app.py and backend/desktop/host.py must
never serve them.
"""

from __future__ import annotations

import argparse
import copy
import json
import mimetypes
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "devcenter_ui"
DIST = ROOT / "frontend" / "dist"
SHIM = ROOT / "frontend" / "src" / "devcenter" / "mock" / "pywebviewShim.js"
DEFAULT_PORT = 8766
SHIM_PATH = "/__test__/pywebview-shim.js"
SHIM_TAG = f'<script src="{SHIM_PATH}"></script>'

SCENARIOS = (
    "default", "no-project", "no-sessions", "locked", "newer-schema", "damaged",
    "sources-changed", "source-missing", "plan-invalid", "apply-ready", "large-5000-rows",
)

# Technical design section 14.2, plus the new JS API call of section 14.4 (UC13).
JSAPI_METHODS = (
    "session_create", "session_open", "session_close", "source_add", "source_remove", "source_relink",
    "target_set", "compare_mode_set", "alignment_override", "merge_choice_set", "merge_choice_bulk_set",
    "removal_policy_set", "need_mapping_set", "impact_action_apply", "offer_select", "row_confirm",
    "sources_check", "naming_rule_confirm", "naming_rule_reject", "naming_rule_edit", "naming_rules_copy",
    "proposal_accept", "proposal_reject", "proposal_accept_all", "question_answer", "format_only_apply",
    "apply", "undo_apply", "change_report_write", "cloud_sign_in", "cloud_connect", "pull_to_local",
    "cloud_items_list", "target_edit_apply", "target_convert_tmdl", "merge_template_save", "merge_template_list", "merge_template_apply",
)
# Calls that read only: they do not change the revision.
JSAPI_READS = frozenset({"cloud_items_list", "merge_template_list", "merge_template_save"})
# Calls that work with no open session.
NO_SESSION_METHODS = frozenset({"session_create", "session_open", "cloud_sign_in", "cloud_items_list"})
# Calls that a read-only (locked) session still permits.
LOCKED_METHODS = frozenset({"session_close", "session_open", "cloud_items_list", "cloud_sign_in", "merge_template_list"})
# The existing desktop host methods that frontend/src/desktop.js and App.jsx use (old reply shape).
DESKTOP_METHODS = ("get_session", "choose_folder", "choose_sources", "open_project", "add_sources", "close_project")

ERROR_STATUS = {
    "invalid_payload": 400, "not_found": 404, "session_not_open": 409, "stale_revision": 409,
    "action_not_allowed": 409, "source_changed": 409, "user_choice_exists": 409,
    "confidence_below_threshold": 422, "reason_required": 422, "naming_rule_violation": 422,
    "unknown": 500, "network": 503,
}
PROPOSAL_MIN_CONFIDENCE = 0.9
# The Impact sort order of severities (UI design 4.5: blocking, severity, name).
IMPACT_SEVERITY_RANK = {name: rank for rank, name in enumerate((
    "breaks", "missing", "name_clash", "changes_value", "needs_review", "will_be_added", "mapped", "not_changed_by_this_plan"))}
# The paths that the fake native source picker gives, in turn.
SOURCE_PICKS = ("sources/Sales.SemanticModel", "sources/Finance.SemanticModel", "sources/Budget.SemanticModel")


class FakeError(Exception):
    """An error reply in the shape {error: {code, message, details}}."""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None, status: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.status = status or ERROR_STATUS.get(code, 500)

    def body(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_scenario_files(name: str, fixtures: Path = FIXTURES) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (scenario.json, files) for one scenario. A file that the scenario does not have comes from its base."""
    if name not in SCENARIOS:
        raise FakeError("not_found", f"The scenario {name} does not exist.", {"scenarios": list(SCENARIOS)})
    folder = fixtures / name
    meta = _read_json(folder / "scenario.json")
    files: dict[str, Any] = {}
    if meta.get("base"):
        _, files = load_scenario_files(meta["base"], fixtures)
    for path in sorted(folder.glob("*.json")):
        if path.name != "scenario.json":
            files[path.stem] = _read_json(path)
    return meta, files


def _generate_log(files: dict[str, Any], count: int) -> None:
    """Step U9: add older user log entries after the fixture entries, so that the Log tab has more than one page."""
    entries = files.setdefault("log", {"entries": []}).setdefault("entries", [])
    for index in range(count):
        entries.append({
            "time_utc": "2026-10-30T08:00:00Z", "author": "user", "mcp_client": None, "action": "merge_choice_set",
            "target": f"row-old-{index:03d}", "before": None, "after": {"choice": "keep"}, "reason": None,
            "proposal_id": None, "revision_after": max(1, 10 - index // 10),
        })


def _generate_large(files: dict[str, Any], plan: dict[str, int]) -> None:
    """Make the large-5000-rows data in memory, so that the repository has no large fixture file."""
    session = files["session"]
    source_ids = [f"src-{index + 1}" for index in range(plan["sources"])]
    session["sources"] = [_local_source(source_id, f"sources/Model{index + 1}.SemanticModel") for index, source_id in enumerate(source_ids)]
    session["target"] = {"model": {"mode": "existing", "source_id": "src-1"}, "report": {"mode": "new_empty"}}
    states = ("same", "different", "missing", "renamed", "conflict")
    types = ("measure", "column", "table", "relationship")
    rows = []
    for index in range(plan["compare_rows"]):
        state = states[index % len(states)]
        rows.append({
            "row_key": f"row-{index:05d}", "object_type": types[index % len(types)], "name": f"Object {index:05d}",
            "table": f"Table {index % 40:02d}", "display_folder": None, "row_state": state,
            "cells": {source_id: {"state": state if position == index % plan["sources"] else "same", "changed": state != "same"}
                      for position, source_id in enumerate(source_ids)},
            "notes": [], "properties": [], "merge_choice": None, "proposal_status": None, "marks": [],
        })
    files["compare-rows"] = {"rows": rows}
    # Step U8: S6-shaped items. Each 50th item is possible; these 100 items have 125 graph nodes (budget P5).
    severities = ("breaks", "changes_value", "needs_review", "missing")
    items = []
    for index in range(plan["impact_items"]):
        possible = index % 50 == 0
        needs = not possible and index % 4 == 3
        severity = "needs_review" if possible else severities[index % len(severities)]
        measure = {"object_id": f"measure:M{index % 25:02d}", "name": f"Measure {index % 25:02d}", "type": "measure",
                   "edge_phrase_id": "reference", "edge_phrase": "reference"}
        visual = {"object_id": f"visual-{index:05d}", "name": f"Visual {index:05d}", "type": "visual",
                  "edge_phrase_id": "uses", "edge_phrase": "uses"}
        items.append({
            "id": f"imp-{index:05d}", "direction": "needs" if needs else "breaks", "cause": f"row-{index % 25:05d}",
            "impacted_object": {"source_id": "src-1", "object_id": visual["object_id"], "object_type": "visual",
                                "name": visual["name"], "domain": "report"},
            "severity": severity, "certainty": "possible" if possible else "certain",
            "reason_id": "modified_object", "reason_text": "Uses a changed object", "path": [measure, visual],
            "other_paths_count": 0, "blocking": severity in {"breaks", "missing"} and not possible,
            "allowed_actions": ["add_from_donor", "map_to_target", "drop_added_object"] if needs else ["include_in_rewrite"],
        })
    files["impact"] = {**files["impact"], "items": items, "proposal_items": []}
    session["counts"] = {**session["counts"], "sources": len(source_ids), "donors": len(source_ids)}


# Source kinds of the fake native picker paths (technical design section 11).
_KIND_BY_SUFFIX = (
    (".semanticmodel", "tmdl_folder"), (".bim", "model_bim"), (".report", "pbir_report"), (".pbip", "pbip"),
)


def _source_kind(path: str) -> str | None:
    lowered = path.lower().rstrip("/")
    for suffix, kind in _KIND_BY_SUFFIX:
        if lowered.endswith(suffix):
            return kind
    return None


def _local_source(source_id: str, path: str, role: str = "donor", kind: str | None = None) -> dict[str, Any]:
    """A local source record in the S2 shape (defs.json#/$defs/source)."""
    kind = kind or _source_kind(path) or "pbip"
    name = path.replace("\\", "/").rstrip("/").split("/")[-1]
    for suffix in (".SemanticModel", ".Report", ".pbip", ".bim"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    is_report = kind in {"pbir_report", "pbir_legacy_report"}
    return {
        "source_id": source_id, "kind": kind, "role": role, "display_name": f"{name} report" if is_report else f"{name} model",
        "path": path, "model_path": None if is_report else path, "model_format": None if is_report else ("tmsl" if kind == "model_bim" else "tmdl"),
        "report_path": path if is_report else None, "report_format": "pbir" if is_report else None,
        "access_type": None, "status": "ok", "fingerprint_state": "same", "mark_count": 0,
    }


def _empty_session(session_id: str, name: str, revision: int) -> dict[str, Any]:
    """A new session in the S2 GET session shape: no sources and no target model."""
    return {
        "session_id": session_id, "display_name": name, "location": "project", "read_only": False, "revision": revision,
        "created_at": "2026-10-31T10:00:00Z", "updated_at": "2026-10-31T10:00:00Z", "checked_at": None, "sources": [],
        "target": {"model": None, "report": {"mode": "new_empty"}}, "compare_mode": "default", "plan_status": None,
        "plan_state": None,
        "counts": {"sources": 0, "donors": 0, "merge_choices": 0, "marks": 0,
                   "marks_by_kind": {"source_changed": 0, "source_object_missing": 0, "new_since_start": 0}},
        "questions": {"open": [], "answered": []}, "proposals": {"open": []},
    }


class FakeDevCenter:
    """The in-memory scenario state. Thread-safe: each public method takes the lock."""

    def __init__(self, fixtures: Path = FIXTURES, *, sleep: Any = time.sleep) -> None:
        self.fixtures = fixtures
        self.sleep = sleep
        self.lock = threading.RLock()
        self.load("default")

    # Test controls

    def load(self, name: str) -> dict[str, Any]:
        meta, files = load_scenario_files(name, self.fixtures)
        files = copy.deepcopy(files)
        if meta.get("generate"):
            _generate_large(files, meta["generate"])
        with self.lock:
            self.scenario = name
            self.meta = meta
            self.files = files
            self.session = files.get("session")
            self.revision = int(meta.get("revision", (self.session or {}).get("revision", 0)))
            self.faults: dict[str, list[dict[str, Any]]] = {}
            self.delays: dict[str, dict[str, Any]] = {}
            self.next_proposal = 1
            self.picks = 0
            return self.health()

    def health(self) -> dict[str, Any]:
        with self.lock:
            return {"ok": True, "scenario": self.scenario, "revision": self.revision, "scenarios": list(SCENARIOS)}

    def set_fault(self, body: dict[str, Any]) -> dict[str, Any]:
        key = body.get("method") or body.get("path")
        if not isinstance(key, str) or not key:
            raise FakeError("invalid_payload", "A fault needs a method or a path.")
        with self.lock:
            if body.get("code") is None:
                self.faults.pop(key, None)
                return {"ok": True, "cleared": key}
            fault = {
                "code": str(body["code"]), "message": str(body.get("message") or f"Injected {body['code']} fault."),
                "details": body.get("details") or {}, "once": bool(body.get("once", True)), "status": body.get("status"),
                "skip": int(body.get("skip", 0)),
            }
            self.faults.setdefault(key, []).append(fault)
            return {"ok": True, "fault": {key: fault}}

    def set_delay(self, body: dict[str, Any]) -> dict[str, Any]:
        key = body.get("method") or body.get("path")
        if not isinstance(key, str) or not key:
            raise FakeError("invalid_payload", "A delay needs a method or a path.")
        milliseconds = body.get("ms", 0)
        if not isinstance(milliseconds, (int, float)) or milliseconds < 0:
            raise FakeError("invalid_payload", "The delay ms must be a number of 0 or more.")
        with self.lock:
            if milliseconds == 0:
                self.delays.pop(key, None)
            else:
                self.delays[key] = {"ms": milliseconds, "once": bool(body.get("once", False))}
            return {"ok": True, "delay": {key: milliseconds}}

    def agent_review(self, _body: dict[str, Any]) -> dict[str, Any]:
        """Step U9: load the default scenario, then put the files of default/agent-review.json over it."""
        with self.lock:
            self.load("default")
            bundle = copy.deepcopy(self.files["agent-review"])
            self.files.update(bundle["files"])
            _generate_log(self.files, int(bundle.get("log_entries", 0)))
            self.session = self.files["session"]
            self.scenario = "default+agent-review"
            return self.health()

    def agent_proposal(self, body: dict[str, Any]) -> dict[str, Any]:
        """Add a proposal as an agent would, with no revision check. For the poll test (A19)."""
        with self.lock:
            session = self._require_session()
            proposal = self._add_proposal(session, body)
            return {"revision": self.revision, "proposal": proposal}

    def set_rules(self, body: dict[str, Any]) -> dict[str, Any]:
        """Change naming rules test fixtures in memory."""
        with self.lock:
            rules_file = self.files.setdefault("naming-rules", {})
            if "rules" in body:
                rules_file["rules"] = copy.deepcopy(body["rules"])
            if "target" in body:
                if body["target"] is None:
                    if self.session and "target" in self.session:
                        self.session["target"]["model"] = None
                    rules_file["target"] = None
                else:
                    rules_file["target"] = copy.deepcopy(body["target"])
            if "source_rule_counts" in body:
                rules_file["source_rule_counts"] = copy.deepcopy(body["source_rule_counts"])
            return {"ok": True}

    def set_plan(self, body: dict[str, Any]) -> dict[str, Any]:
        """Change plan and apply-preview test fixtures in memory."""
        with self.lock:
            plan_file = self.files.setdefault("plan", {})
            for key in ("status", "plan_hash", "summary", "steps", "operations", "blocking", "warnings"):
                if key in body:
                    plan_file[key] = copy.deepcopy(body[key])
            if "status" in body and self.session is not None:
                self.session["plan_status"] = body["status"]
            if "plan_state" in body and self.session is not None:
                self.session["plan_state"] = body["plan_state"]
            if "marks" in body and self.session is not None:
                self.session.setdefault("counts", {})["marks"] = int(body["marks"])
            if "apply_preview" in body and isinstance(body["apply_preview"], dict):
                preview = self.files.setdefault("apply-preview", {})
                preview.update(copy.deepcopy(body["apply_preview"]))
                plan_file["apply_preview"] = copy.deepcopy(body["apply_preview"])
            return {"ok": True}

    def set_apply(self, body: dict[str, Any]) -> dict[str, Any]:
        """Step U10: change GET apply/last, apply/progress, apply/preview, and the extra reply fields of the apply calls in memory."""
        with self.lock:
            for key in ("apply-last", "apply-progress", "apply-preview"):
                if isinstance(body.get(key), dict):
                    self.files[key] = {**self.files.get(key, {}), **copy.deepcopy(body[key])}
            if isinstance(body.get("replies"), dict):
                self.files.setdefault("apply-replies", {}).update(copy.deepcopy(body["replies"]))
            return {"ok": True}

    def set_compare_rows(self, body: dict[str, Any]) -> dict[str, Any]:
        """Change compare-rows, removal, and display-folders test fixtures in memory."""
        with self.lock:
            if "rows" in body and isinstance(body["rows"], list):
                self.files.setdefault("compare-rows", {})["rows"] = copy.deepcopy(body["rows"])
            if "removal" in body and isinstance(body["removal"], dict):
                self.files.setdefault("removal", {}).update(copy.deepcopy(body["removal"]))
                # A test removal reply wins over the removal replies of each object.
                self.files["removals"] = {}
            if "folders" in body and isinstance(body["folders"], dict):
                self.files.setdefault("display-folders", {})["folders"] = copy.deepcopy(body["folders"])
            return {"ok": True}

    def set_impact(self, body: dict[str, Any]) -> dict[str, Any]:
        """Step U8: change the impact, removal, and wireframe test fixtures in memory."""
        with self.lock:
            impact = self.files.setdefault("impact", {})
            for key in ("items", "completeness", "offers", "proposal_items"):
                if key in body:
                    impact[key] = copy.deepcopy(body[key])
            for key in ("removals", "wireframes", "impact-paths"):
                if isinstance(body.get(key), dict):
                    self.files.setdefault(key, {}).update(copy.deepcopy(body[key]))
            return {"ok": True}

    def before_reply(self, key: str) -> None:
        """Wait for an injected delay, then raise an injected fault. Each one is for the next call of the key."""
        with self.lock:
            delay = self.delays.get(key)
            if delay and delay["once"]:
                self.delays.pop(key, None)
        if delay:
            self.sleep(delay["ms"] / 1000)
        with self.lock:
            queue = self.faults.get(key)
            if not queue:
                return
            fault = queue[0]
            if fault.get("skip", 0) > 0:
                fault["skip"] -= 1
                return
            if fault["once"]:
                queue.pop(0)
                if not queue:
                    self.faults.pop(key, None)
        raise FakeError(fault["code"], fault["message"], fault["details"], fault["status"])

    # Mock JS API

    def call(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        if method not in JSAPI_METHODS:
            raise FakeError("not_found", f"The JS API has no method {method}.")
        self.before_reply(method)
        with self.lock:
            if self.session is None and method not in NO_SESSION_METHODS:
                raise FakeError("session_not_open", "No session is open.")
            if self.session is not None:
                base = payload.get("base_revision")
                if base != self.revision:
                    raise FakeError("stale_revision", "The session changed after the base revision.", {"base_revision": base, "revision": self.revision})
                if self.session.get("read_only") and method not in LOCKED_METHODS:
                    raise FakeError("action_not_allowed", "The session is read-only, because another window has it open.", {"reason": "session_locked"})
            handler = getattr(self, f"_call_{method}", None)
            extra = handler(payload) if handler else {}
            if method not in JSAPI_READS:
                self._step(method, payload)
            return {"revision": self.revision, **(extra or {})}

    def _step(self, action: str, payload: dict[str, Any], author: str = "user") -> None:
        self.revision += 1
        if self.session is not None:
            self.session["revision"] = self.revision
        self.files.setdefault("log", {"entries": []}).setdefault("entries", []).insert(0, {
            "time_utc": "2026-10-31T10:00:00Z", "author": author, "mcp_client": "Test agent" if author == "agent" else None,
            "action": action, "target": payload.get("row_key") or payload.get("proposal_id") or payload.get("target_id"),
            "before": None, "after": None, "reason": payload.get("reason"), "proposal_id": payload.get("proposal_id"),
            "revision_after": self.revision,
        })

    def _require_session(self) -> dict[str, Any]:
        if self.session is None:
            raise FakeError("session_not_open", "No session is open.")
        return self.session

    def _rows(self) -> list[dict[str, Any]]:
        return self.files["compare-rows"]["rows"]

    def _row(self, row_key: Any) -> dict[str, Any]:
        for row in self._rows():
            if row["row_key"] == row_key:
                return row
        raise FakeError("not_found", f"The row {row_key} does not exist.", {"row_key": row_key})

    # The S2 session_open and session_create replies have no session field (jsapi/session_*.reply.json).

    def _call_session_open(self, payload: dict[str, Any]) -> dict[str, Any]:
        session_id = payload.get("session_id")
        item = next((entry for entry in self.files["sessions"]["sessions"] if entry["session_id"] == session_id), None)
        if item is None:
            raise FakeError("not_found", f"The session {session_id} does not exist.")
        if item["schema_state"] != "ok":
            raise FakeError("action_not_allowed", "This session file cannot open.", {"reason": item["schema_state"]})
        _, default_files = load_scenario_files("default", self.fixtures)
        session = copy.deepcopy(default_files["session"])
        session.update({"session_id": item["session_id"], "display_name": item["display_name"], "read_only": item["lock_state"] == "locked"})
        self.session = session
        return {"session_id": session["session_id"], "read_only": session["read_only"], "migrated": False,
                "mark_count": session["counts"]["marks"]}

    def _call_session_create(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = payload.get("display_name")
        if not isinstance(name, str) or not name.strip():
            raise FakeError("invalid_payload", "The session needs a display name.", {"field": "display_name"})
        session_id = f"{len(self.files['sessions']['sessions']) + 1:032x}"
        self.session = _empty_session(session_id, name.strip(), self.revision + 1)
        self.files["sessions"]["sessions"].insert(0, {
            "session_id": session_id, "location": "project", "display_name": name.strip(), "updated_at": "2026-10-31T10:00:00Z",
            "target_model_name": None, "target_report_name": None, "source_count": 0, "plan_status": None,
            "lock_state": "free", "schema_state": "ok", "is_open": False,
        })
        return {"session_id": session_id, "read_only": False}

    def _call_session_close(self, _payload: dict[str, Any]) -> dict[str, Any]:
        session_id = self.session["session_id"] if self.session else None
        self.session = None
        return {"session_id": session_id}

    def _list_entry(self) -> dict[str, Any] | None:
        session_id = (self.session or {}).get("session_id")
        return next((entry for entry in self.files["sessions"]["sessions"] if entry["session_id"] == session_id), None)

    def _source_changed(self) -> None:
        """Keep the counts and the session list row the same as the source list (UC1)."""
        session = self.session
        sources = {item["source_id"]: item for item in session["sources"]}
        session["counts"]["sources"] = len(sources)
        session["counts"]["donors"] = sum(1 for item in sources.values() if item["role"] == "donor")
        entry = self._list_entry()
        if entry is not None:
            target = session["target"]
            entry["source_count"] = len(sources)
            entry["target_model_name"] = sources.get((target.get("model") or {}).get("source_id"), {}).get("display_name")
            entry["target_report_name"] = sources.get((target.get("report") or {}).get("source_id"), {}).get("display_name")

    def _next_source_id(self) -> str:
        numbers = [int(item["source_id"].split("-")[1]) for item in self.session["sources"]]
        return f"src-{max(numbers, default=0) + 1}"

    def _call_source_add(self, payload: dict[str, Any]) -> dict[str, Any]:
        path = payload.get("path")
        if not isinstance(path, str) or not path.strip():
            raise FakeError("invalid_payload", "The source needs a path.", {"field": "path"})
        if path.lower().endswith(".pbix"):
            raise FakeError("action_not_allowed", "PBIBrain cannot read a PBIX file.", {"reason": "pbix"})
        if any(item["path"] == path for item in self.session["sources"]):
            raise FakeError("action_not_allowed", "This source is already in the session.", {"reason": "duplicate_source"})
        source = _local_source(self._next_source_id(), path)
        self.session["sources"].append(source)
        self._source_changed()
        return {"source": source}

    def _call_source_remove(self, payload: dict[str, Any]) -> dict[str, Any]:
        source_id = payload.get("source_id")
        source = next((item for item in self.session["sources"] if item["source_id"] == source_id), None)
        if source is None:
            raise FakeError("not_found", f"The source {source_id} does not exist.", {"kind": "source", "source_id": source_id})
        self.session["sources"].remove(source)
        choices = [row for row in self.files.get("compare-rows", {}).get("rows", [])
                   if (row.get("merge_choice") or {}).get("source") == source_id]
        if choices:
            plan = self.files.setdefault("plan", {})
            blocking = plan.setdefault("blocking", [])
            for row in choices:
                item_id = f"choice_source_removed:{row['row_key']}"
                if not any(item.get("item_id") == item_id for item in blocking):
                    blocking.append({
                        "item_id": item_id,
                        "kind": "choice_source_removed",
                        "row_key": row["row_key"],
                        "row_id": "row_0000000000000004",
                        "step_id": None,
                        "object": {
                            "name": row["name"],
                            "object_type": row["object_type"],
                            "table": row.get("table"),
                        },
                        "message": f"The Merge Choice for {row['name']} uses removed source {source['display_name']}.",
                        "params": {"source_id": source_id, "source_name": source["display_name"]},
                        "actions": [],
                    })
            plan["status"] = "invalid"
            self.session["plan_status"] = "invalid"
        self._source_changed()
        return {"source_id": source_id, "choice_count": len(choices)}

    def _call_source_relink(self, payload: dict[str, Any]) -> dict[str, Any]:
        source_id = payload.get("source_id")
        source = next((item for item in self.session["sources"] if item["source_id"] == source_id), None)
        if source is None or not isinstance(payload.get("path"), str):
            raise FakeError("not_found", f"The source {source_id} does not exist.", {"kind": "source", "source_id": source_id})
        source.update({"status": "ok", "fingerprint_state": "same"})
        return {"source": source}

    def _call_target_set(self, payload: dict[str, Any]) -> dict[str, Any]:
        model = payload.get("model")
        if not isinstance(model, dict) or model.get("mode") not in {"existing", "copy_of", "empty"}:
            raise FakeError("invalid_payload", "The target needs a model mode.", {"field": "model"})
        added = []
        if model["mode"] == "existing":
            target_model = {"mode": "existing", "source_id": model.get("source_id")}
        else:
            source = _local_source(self._next_source_id(), str(model.get("path") or "target"), role="target", kind="tmdl_folder")
            if model["mode"] == "empty" and model.get("name"):
                source["display_name"] = str(model["name"])
            self.session["sources"].append(source)
            added.append(source)
            target_model = {"mode": model["mode"], "source_id": source["source_id"]}
            if model["mode"] == "copy_of":
                target_model["copy_of"] = model.get("source_id")
        report = payload.get("report") or {"mode": "new_empty"}
        self.session["target"] = {"model": target_model, "report": report}
        self._source_changed()
        return {"target": self.session["target"], "sources_added": added}

    def _call_sources_check(self, _payload: dict[str, Any]) -> dict[str, Any]:
        self.session["checked_at"] = "2026-10-31T10:00:00Z"
        return {"sources": [{"source_id": item["source_id"], "status": item["status"]} for item in self.session["sources"]],
                "mark_count": self.session["counts"]["marks"]}

    def _call_compare_mode_set(self, payload: dict[str, Any]) -> dict[str, Any]:
        mode = payload.get("compare_mode") or payload.get("mode")
        if mode:
            self.session["compare_mode"] = mode
        return {"compare_mode": self.session.get("compare_mode", "default")}

    def _call_merge_choice_set(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = self._row(payload.get("row_key"))
        choice = payload.get("choice")
        row["merge_choice"] = choice
        return {"row_key": row["row_key"], "choice": choice}

    def _call_removal_policy_set(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = self._row(payload.get("row_key"))
        policy = payload.get("policy")
        if policy not in {"block", "cascade", "repoint"}:
            raise FakeError("invalid_payload", "The policy must be block, cascade, or repoint.", {"field": "policy"})
        repoint_target = payload.get("repoint_target")
        if policy == "repoint" and (not isinstance(repoint_target, str) or not repoint_target.strip()):
            raise FakeError("invalid_payload", "Repoint needs a repoint_target.", {"field": "repoint_target"})
        row["removal_policy"] = {"policy": policy, "repoint_target": repoint_target if policy == "repoint" else None}
        self._set_removal_blocking(row["row_key"], policy)
        return {"row_key": row["row_key"], "policy": policy, "repoint_target": repoint_target if policy == "repoint" else None}

    def _set_removal_blocking(self, row_key: Any, policy: str) -> None:
        """Items of a removed row block only under the Block policy (S6 blocking rule 1)."""
        for item in self._impact_items(True):
            if item["cause"] == row_key and "set_policy_block" in item["allowed_actions"]:
                item["blocking"] = policy == "block"

    def _call_impact_action_apply(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Step U8: one revision step for all items (UC28). An item that does not permit the action fails."""
        action = payload.get("action")
        item_ids = payload.get("item_ids") or []
        if not isinstance(item_ids, list) or not item_ids:
            raise FakeError("invalid_payload", "No items specified.", {"reason": "item_ids_required"})
        known = {item["id"]: item for item in self._impact_items(True)}
        applied: list[str] = []
        failed: list[dict[str, str]] = []
        for item_id in item_ids:
            item = known.get(item_id)
            if item is None:
                failed.append({"item_id": item_id, "reason": "item_not_found"})
            elif action not in item["allowed_actions"]:
                failed.append({"item_id": item_id, "reason": "action_not_allowed"})
            else:
                applied.append(item_id)
        for item_id in applied:
            item = known[item_id]
            if action in {"set_policy_block", "set_policy_cascade", "set_policy_repoint"}:
                self._set_removal_blocking(item["cause"], action.replace("set_policy_", ""))
            elif action == "add_from_donor":
                item.update(blocking=False, severity="will_be_added")
            elif action == "map_to_target":
                item.update(blocking=False, severity="mapped")
            else:
                item["blocking"] = False
        return {"applied": applied, "failed": failed}

    def _call_need_mapping_set(self, payload: dict[str, Any]) -> dict[str, Any]:
        item = self._impact_item(payload.get("need_id"))
        action = payload.get("action")
        item.update(blocking=False, severity="mapped" if action == "map_to_target" else "will_be_added")
        return {"need_id": item["id"], "action": action, "target_object": payload.get("target_object")}

    def _call_offer_select(self, payload: dict[str, Any]) -> dict[str, Any]:
        offer_id = payload.get("offer_id")
        offer = next((offer for offer in self.files["impact"].get("offers", []) if offer["id"] == offer_id), None)
        if offer is None:
            raise FakeError("not_found", f"The offer {offer_id} does not exist.", {"offer_id": offer_id})
        if offer.get("information_only"):
            raise FakeError("action_not_allowed", "A bookmark is information only.", {"reason": "information_only"})
        offer["selected"] = bool(payload.get("selected"))
        return {"offer_id": offer_id, "selected": offer["selected"]}

    def _call_alignment_override(self, payload: dict[str, Any]) -> dict[str, Any]:
        action = payload.get("action")
        source_id = payload.get("source_id")
        row_key = payload.get("row_key")
        other_row_key = payload.get("other_row_key")
        if action not in {"confirm", "break", "reject_rename", "clear"} or not source_id or not row_key:
            raise FakeError("invalid_payload", "The alignment override needs action, source_id, and row_key.")
        if action in {"confirm", "reject_rename"} and not other_row_key:
            raise FakeError("invalid_payload", "confirm and reject_rename need other_row_key.")
        row = self._row(row_key)
        rows = self._rows()
        removed_choices: list[str] = []

        if action == "break":
            if row.get("merge_choice") is not None:
                removed_choices.append(row["row_key"])
                row["merge_choice"] = None
            cells = row.get("cells")
            if isinstance(cells, dict):
                donor_cell = copy.deepcopy(cells.get(source_id, {"state": "same", "changed": False}))
                cells[source_id] = {"state": "missing", "changed": False}
            elif isinstance(cells, list):
                donor_cell = next((copy.deepcopy(c) for c in cells if c.get("source_id") == source_id), {"source_id": source_id, "state": "same", "changed": False})
                for c in cells:
                    if c.get("source_id") == source_id:
                        c.update({"present": False, "state": "missing", "changed": False, "phrases": [], "notes": []})
            else:
                donor_cell = {"state": "same", "changed": False}
            split_key = f"{row['row_key']}@{source_id}"
            donor_name = (donor_cell.get("name") if isinstance(donor_cell, dict) else None) or row["name"]
            new_row = {
                "row_key": split_key,
                "object_type": row["object_type"],
                "name": donor_name,
                "table": row.get("table"),
                "display_folder": row.get("display_folder"),
                "row_state": "missing",
                "cells": {
                    "src-3": {"state": "missing", "changed": False},
                    source_id: {"state": "same", "changed": False, "name": donor_name},
                },
                "notes": [],
                "properties": [],
                "merge_choice": None,
                "proposal_status": None,
                "marks": [],
            }
            if not any(r["row_key"] == split_key for r in rows):
                idx = rows.index(row)
                rows.insert(idx + 1, new_row)
            return {"action": action, "row_keys": [row["row_key"], split_key], "removed_choices": removed_choices}

        if action == "confirm":
            other = self._row(other_row_key)
            for r in (row, other):
                if r.get("merge_choice") is not None:
                    removed_choices.append(r["row_key"])
                    r["merge_choice"] = None
            cells = row.get("cells")
            if isinstance(cells, dict):
                cells[source_id] = {
                    "state": "renamed" if other["name"] != row["name"] else "different",
                    "changed": True,
                    "name": other["name"],
                    "step": "manual",
                }
            elif isinstance(cells, list):
                for c in cells:
                    if c.get("source_id") == source_id:
                        c.update({
                            "present": True,
                            "name": other["name"],
                            "state": "renamed" if other["name"] != row["name"] else "different",
                            "changed": True,
                            "step": "manual",
                            "notes": [n for n in c.get("notes", []) if n.get("note_id") != "possible_rename"],
                        })
            row["notes"] = [
                n for n in row.get("notes", [])
                if (n.get("note_id") or n.get("phrase_id")) not in {"possible_rename", "compare.note.possible_rename"}
            ]
            row["alignment_step"] = "manual"
            if other["name"] != row["name"]:
                row["row_state"] = "renamed"
            if other in rows:
                rows.remove(other)
            return {"action": action, "row_keys": [row["row_key"]], "removed_choices": removed_choices}

        if action == "reject_rename":
            try:
                other = self._row(other_row_key)
            except FakeError:
                other = None
            targets = [row] if other is None else [row, other]
            for r in targets:
                r["notes"] = [
                    n for n in r.get("notes", [])
                    if (n.get("note_id") or n.get("phrase_id")) not in {"possible_rename", "compare.note.possible_rename"}
                ]
                if isinstance(r.get("cells"), list):
                    for c in r["cells"]:
                        c["notes"] = [n for n in c.get("notes", []) if n.get("note_id") != "possible_rename"]
                elif isinstance(r.get("cells"), dict):
                    for c in r["cells"].values():
                        if isinstance(c, dict) and "notes" in c:
                            c["notes"] = [n for n in c["notes"] if n.get("note_id") != "possible_rename"]
            return {"action": action, "row_keys": [r["row_key"] for r in targets], "removed_choices": removed_choices}

        return {"action": action, "row_keys": [row["row_key"]], "removed_choices": removed_choices}

    def _call_merge_choice_bulk_set(self, payload: dict[str, Any]) -> dict[str, Any]:
        keys = payload.get("row_keys")
        if not isinstance(keys, list) or not keys:
            raise FakeError("invalid_payload", "The bulk call needs a list of row keys.", {"field": "row_keys"})
        rows = [self._row(key) for key in keys]
        for row in rows:
            row["merge_choice"] = payload.get("choice")
        return {"changed": len(rows)}

    def _call_target_edit_apply(self, payload: dict[str, Any]) -> dict[str, Any]:
        scope = payload.get("scope") or {}
        keys = scope.get("row_keys") or [row["row_key"] for row in self._rows()]
        rows = [self._row(key) for key in keys]
        for row in rows:
            row["merge_choice"] = {"kind": "edit"}
        return {"count": len(rows), "row_keys": [row["row_key"] for row in rows], "skipped": []}

    def _call_target_convert_tmdl(self, payload: dict[str, Any]) -> dict[str, Any]:
        source = next((item for item in self.session["sources"] if item["source_id"] == payload.get("source_id")), self.session["sources"][0])
        source["model_format"] = "tmdl"
        return {"source": source, "backup_path": ".pbibrain/sessions/fake/apply/tmsl-backup/model.bim"}

    def _call_merge_template_save(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.templates = getattr(self, "templates", {})
        name = str(payload.get("name") or "Template")
        self.templates[name] = {row["row_key"]: row["merge_choice"] for row in self._rows() if row.get("merge_choice")}
        return {"name": name, "path": f".pbibrain/templates/{name}.json", "choice_count": len(self.templates[name])}

    def _call_merge_template_list(self, payload: dict[str, Any]) -> dict[str, Any]:
        templates = getattr(self, "templates", {})
        return {"templates": [{"name": name, "saved_utc": "2026-11-07T10:00:00Z", "choice_count": len(choices), "source_names": []}
                              for name, choices in sorted(templates.items())]}

    def _call_merge_template_apply(self, payload: dict[str, Any]) -> dict[str, Any]:
        choices = getattr(self, "templates", {}).get(payload.get("name"))
        if choices is None:
            raise FakeError("not_found", "The template does not exist.", {"reason": "template_not_found"})
        for key, choice in choices.items():
            self._row(key)["merge_choice"] = choice
        return {"name": str(payload.get("name")), "applied": sorted(choices), "skipped": []}

    def _call_row_confirm(self, payload: dict[str, Any]) -> dict[str, Any]:
        keys = payload.get("row_keys")
        if not isinstance(keys, list) or not keys:
            raise FakeError("invalid_payload", "The confirm call needs a list of row keys.", {"field": "row_keys"})
        rows = [self._row(key) for key in keys]
        for row in rows:
            row["marks"] = []
        confirmed = {row["row_key"] for row in rows}
        for proposal in self.session.get("proposals", {}).get("open", []):
            if proposal.get("target_id") in confirmed and proposal.get("blocked") == "source_changed":
                proposal["blocked"] = None
        marks = sum(1 for row in self._rows() if row["marks"])
        self.session["counts"]["marks"] = marks
        self.session["counts"]["marks_by_kind"]["source_changed"] = marks
        return {"confirmed": [row["row_key"] for row in rows], "mark_count": marks}

    def _take_proposal(self, proposal_id: Any) -> dict[str, Any]:
        proposals = self.session["proposals"]["open"]
        for index, proposal in enumerate(proposals):
            if proposal["id"] == proposal_id:
                if proposal.get("blocked") == "source_changed":
                    raise FakeError("source_changed", "The source of this proposal changed. Confirm the row first.", {"proposal_id": proposal_id})
                return proposals.pop(index)
        raise FakeError("not_found", f"The proposal {proposal_id} does not exist.", {"proposal_id": proposal_id})

    def _call_proposal_accept(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"accepted_ids": [self._take_proposal(payload.get("proposal_id"))["id"]]}

    def _call_proposal_reject(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"rejected_ids": [self._take_proposal(payload.get("proposal_id"))["id"]]}

    def _call_proposal_accept_all(self, _payload: dict[str, Any]) -> dict[str, Any]:
        accepted, skipped, kept = [], [], []
        for proposal in self.session["proposals"]["open"]:
            if proposal.get("blocked"):
                skipped.append({"id": proposal["id"], "reason": proposal["blocked"]})
                kept.append(proposal)
            else:
                accepted.append(proposal["id"])
        self.session["proposals"]["open"] = kept
        return {"accepted_ids": accepted, "skipped": skipped}

    def _call_question_answer(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Step U9: move the question to answered, as S10 does."""
        questions = self.session["questions"]
        question = next((item for item in questions["open"] if item["id"] == payload.get("question_id")), None)
        if question is None:
            raise FakeError("not_found", "The question does not exist.", {"question_id": payload.get("question_id")})
        if payload.get("option_id") not in {option["id"] for option in question.get("options", [])}:
            raise FakeError("not_found", "The option does not exist.", {"option_id": payload.get("option_id")})
        if question.get("blocked") == "source_changed":
            raise FakeError("source_changed", "The source of this row changed. Confirm the row first.", {"question_id": question["id"]})
        questions["open"].remove(question)
        question.update(status="answered", selected_option=payload["option_id"], answered_utc="2026-10-31T10:00:00Z")
        questions["answered"].append(question)
        return {"question_id": question["id"], "option_id": payload["option_id"], "applied": True}

    # Step U10: the apply calls. The test route /__test__/apply can change the extra reply fields.

    def _apply_reply(self, method: str) -> dict[str, Any]:
        reply = {"apply_id": "apl-00000000000000a1", "file_count": 2,
                 "files": ["Sales.SemanticModel/definition/tables/Sales.tmdl", "Sales.Report/definition/report.json"],
                 "desktop_state": "not_open", "notices": [], "rescan_differences": []}
        reply.update(copy.deepcopy((self.files.get("apply-replies") or {}).get(method) or {}))
        return reply

    def _record_last(self, reply: dict[str, Any], kind: str) -> None:
        finished = reply.get("finished_utc") or datetime.now(timezone.utc).isoformat()
        self.files["apply-last"] = {"apply_id": reply["apply_id"], "kind": kind, "finished_utc": finished,
                                    "file_count": reply["file_count"], "backup_present": True, "target_changed": False,
                                    "changed_files": [], "rescan_differences": reply["rescan_differences"], "undone": False}

    def _call_apply(self, _payload: dict[str, Any]) -> dict[str, Any]:
        reply = {"kind": "apply", **self._apply_reply("apply")}
        self._record_last(reply, "apply")
        return reply

    def _call_format_only_apply(self, _payload: dict[str, Any]) -> dict[str, Any]:
        reply = {"kind": "format_only", **self._apply_reply("format_only_apply")}
        self._record_last(reply, "format_only")
        self.files.setdefault("apply-preview", {})["non_canonical_files"] = []
        return reply

    def _call_undo_apply(self, _payload: dict[str, Any]) -> dict[str, Any]:
        last = self.files.get("apply-last") or {}
        reply = {**self._apply_reply("undo_apply"), "apply_id": last.get("apply_id") or "apl-00000000000000a1",
                 "undo_id": "apl-00000000000000b2"}
        self.files["apply-last"] = {**last, "undone": True, "backup_present": False}
        return reply

    def _call_change_report_write(self, payload: dict[str, Any]) -> dict[str, Any]:
        last = self.files.get("apply-last") or {}
        name = payload.get("file_name") or "change-report.md"
        return {"apply_id": last.get("apply_id") or "apl-00000000000000a1",
                "path": f".pbibrain/sessions/apply/{name}", "markdown": "# Change report\n"}

    def _call_cloud_items_list(self, payload: dict[str, Any]) -> dict[str, Any]:
        kind = payload.get("kind", "workspaces")
        if kind not in {"workspaces", "models", "reports"}:
            raise FakeError("invalid_payload", "The kind must be workspaces, models, or reports.", {"field": "kind"})
        return {"kind": kind, "items": self.files["cloud-items"][kind]}

    def _find_rule(self, rule_id: Any) -> dict[str, Any]:
        rules = self.files.get("naming-rules", {}).get("rules", [])
        for rule in rules:
            if rule["rule_id"] == rule_id:
                return rule
        raise FakeError("not_found", f"The rule {rule_id} does not exist.", {"rule_id": rule_id})

    def _call_naming_rule_confirm(self, payload: dict[str, Any]) -> dict[str, Any]:
        rule = self._find_rule(payload.get("rule_id"))
        if rule["status"] == "confirmed":
            raise FakeError("action_not_allowed", "The rule is already confirmed.", {"reason": "already_confirmed", "rule_id": rule["rule_id"]})
        rule["status"] = "confirmed"
        return {"rule": rule}

    def _call_naming_rule_reject(self, payload: dict[str, Any]) -> dict[str, Any]:
        rule = self._find_rule(payload.get("rule_id"))
        rules = self.files.get("naming-rules", {}).get("rules", [])
        if rule.get("origin") == "user":
            rules.remove(rule)
            return {"rule_id": rule["rule_id"], "removed": True, "rule": None}
        if rule["status"] == "rejected":
            raise FakeError("action_not_allowed", "The rule is already rejected.", {"reason": "already_rejected", "rule_id": rule["rule_id"]})
        rule["status"] = "rejected"
        return {"rule_id": rule["rule_id"], "removed": False, "rule": rule}

    def _call_naming_rule_edit(self, payload: dict[str, Any]) -> dict[str, Any]:
        rules = self.files.get("naming-rules", {}).get("rules", [])
        rule_id = payload.get("rule_id")
        object_type = payload.get("object_type")
        check = payload.get("check")
        if not object_type or not check:
            raise FakeError("invalid_payload", "The rule edit needs object_type and check.", {"field": "object_type"})

        if check.get("kind") == "regex":
            try:
                re.compile(check.get("value", ""))
            except re.error as exc:
                raise FakeError("invalid_payload", "The regular expression is not valid.", {"reason": "invalid_regex", "field": "pattern", "position": exc.pos, "detail": str(exc)})

        raw_scope = payload.get("scope") or {}
        norm_scope = {
            "table": raw_scope.get("table"),
            "display_folder": raw_scope.get("display_folder"),
            "format_kind": raw_scope.get("format_kind"),
            "name_prefix": raw_scope.get("name_prefix"),
        }
        for other in rules:
            if other["rule_id"] != rule_id and other["status"] != "rejected":
                other_scope = {
                    "table": other["scope"].get("table"),
                    "display_folder": other["scope"].get("display_folder"),
                    "format_kind": other["scope"].get("format_kind"),
                    "name_prefix": other["scope"].get("name_prefix"),
                }
                if (other["object_type"], other_scope, other["check"]["kind"]) == (object_type, norm_scope, check["kind"]):
                    raise FakeError("action_not_allowed", "The same rule exists.", {"reason": "duplicate_rule", "existing_rule_id": other["rule_id"]})

        if rule_id:
            rule = self._find_rule(rule_id)
            rule["object_type"] = object_type
            rule["scope"] = norm_scope
            rule["check"] = check
            rule["status"] = "confirmed"
            rule["text"] = f"{object_type} {check['kind']} rule."
            return {"rule": rule}
        else:
            new_id = f"nr-{len(rules) + 1:012x}"
            new_rule = {
                "rule_id": new_id,
                "object_type": object_type,
                "scope": norm_scope,
                "check": check,
                "origin": "user",
                "status": "confirmed",
                "copied_from": None,
                "text": f"{object_type} {check['kind']} rule.",
                "support": {"count": 0, "total": 0},
                "breaks": 0,
            }
            rules.append(new_rule)
            return {"rule": new_rule}

    def _call_naming_rules_copy(self, payload: dict[str, Any]) -> dict[str, Any]:
        source_id = payload.get("source_id")
        target_source_id = (self.session.get("target", {}).get("model") or {}).get("source_id")
        if source_id == target_source_id:
            raise FakeError("action_not_allowed", "Select a model that is not the target.", {"reason": "same_model"})
        source = next((s for s in self.session.get("sources", []) if s["source_id"] == source_id), None)
        if source is None:
            raise FakeError("not_found", f"The source {source_id} does not exist.")
        counts = self.files.get("naming-rules", {}).get("source_rule_counts", {})
        count = counts.get(source_id, 0)
        rules = self.files.get("naming-rules", {}).get("rules", [])
        copied = []
        if count > 0:
            for idx in range(count):
                copied_id = f"nr-{len(rules) + 100 + idx:012x}"
                copied_rule = {
                    "rule_id": copied_id,
                    "object_type": "measure",
                    "scope": {"table": None, "display_folder": None, "format_kind": None, "name_prefix": None},
                    "check": {"kind": "prefix", "value": f"Copied{idx + 1}"},
                    "origin": "detected",
                    "status": "proposed",
                    "copied_from": source["display_name"],
                    "text": f"Copied rule {idx + 1} from {source['display_name']}.",
                    "support": {"count": 5, "total": 5},
                    "breaks": 0,
                }
                rules.append(copied_rule)
                copied.append(copied_rule)
        return {"copied": copied, "skipped": []}


    def _add_proposal(self, session: dict[str, Any], body: dict[str, Any], author: str = "agent") -> dict[str, Any]:
        proposal = {
            "id": body.get("id") or f"p-test-{self.next_proposal}", "kind": body.get("kind", "merge_choice"),
            "target_id": body.get("target_id", "row-customer"), "target_name": body.get("target_name", "Customer"),
            "summary": body.get("summary", "Take from Finance model"), "payload": body.get("payload", {}),
            "confidence": body.get("confidence", 0.95), "reason": body.get("reason", "The agent found a match."),
            "mcp_client": body.get("mcp_client", "Test agent"), "created_utc": "2026-10-31T10:00:00Z",
            "blocked": body.get("blocked"), "status": "proposed",
        }
        self.next_proposal += 1
        # A new agent proposal for the same target and kind replaces the older one.
        session["proposals"]["open"] = [item for item in session["proposals"]["open"]
                                        if (item["target_id"], item["kind"]) != (proposal["target_id"], proposal["kind"])]
        session["proposals"]["open"].append(proposal)
        self._step("proposal_submit", {"target_id": proposal["target_id"], "proposal_id": proposal["id"], "reason": proposal["reason"]}, author)
        return proposal

    # HTTP reads and proposal endpoints

    def read(self, method: str, path: str, query: dict[str, list[str]], body: dict[str, Any]) -> dict[str, Any]:
        parts = [unquote(part) for part in path.split("/") if part][2:]
        self.before_reply(path)
        self.before_reply(f"{method} {path}")
        with self.lock:
            if method == "GET" and parts == ["sessions"]:
                return self._sessions()
            if method == "POST" and parts in (["proposals"], ["questions"]):
                return self._submit(parts[0], body)
            session = self._require_session()
            if method == "GET":
                if parts == ["session"]:
                    return self._reply(session)
                if parts == ["compare-rows"]:
                    return self._reply(self._compare_rows(query))
                if len(parts) == 3 and parts[0] == "compare-rows" and parts[2] == "diff":
                    source = _one(query, "source")
                    diff = self.files["row-diffs"].get(parts[1], {}).get(source) if source else None
                    if diff is None:
                        self._row(parts[1])
                        diff = {"language": "tmdl", "target": "", "source": ""}
                    return self._reply({"row_key": parts[1], "source": source, **diff})
                if parts == ["display-folders"]:
                    return self._reply(self._display_folders(query))
                simple = {
                    ("plan",): "plan", ("impact",): "impact", ("apply", "preview"): "apply-preview",
                    ("apply", "progress"): "apply-progress", ("apply", "last"): "apply-last",
                }
                if tuple(parts) in simple:
                    value = self.files[simple[tuple(parts)]]
                    if parts == ["impact"]:
                        value = self._impact(query)
                    if parts == ["plan"] and _one(query, "include_proposals") in {"true", "ready"}:
                        value = self.files.get("plan-proposals", value)
                    return self._reply(value)
                if parts == ["naming-rules"]:
                    value = copy.deepcopy(self.files["naming-rules"])
                    target_model = (self.session or {}).get("target", {}).get("model")
                    if target_model is None:
                        value["target"] = None
                        value["rules"] = []
                    return self._reply(value)
                if parts == ["log"]:
                    page = self._page(self._log(query), "entries", query)
                    return self._reply({**page, "limit": _int(query, "limit", 200), "offset": _int(query, "offset", 0)})
                if len(parts) == 3 and parts[:2] == ["impact", "removal"]:
                    removal = (self.files.get("removals") or {}).get(parts[2]) or self.files["removal"]
                    return self._reply({**copy.deepcopy(removal), "object": parts[2]})
                if len(parts) == 3 and parts[0] == "impact" and parts[2] == "paths":
                    return self._reply(self._impact_paths(parts[1], query))
                if len(parts) == 2 and parts[0] == "wireframe":
                    wireframe = (self.files.get("wireframes") or {}).get(parts[1]) or self.files["wireframe"]
                    return self._reply({**copy.deepcopy(wireframe), "report": parts[1]})
            if method == "POST" and parts == ["name-propose"]:
                return self._reply(self._name_propose(body))
            if method == "POST" and parts == ["plan-validate"]:
                mode = body.get("mode", "quick")
                if mode not in {"quick", "full"}:
                    raise FakeError("invalid_payload", "The mode must be quick or full.", {"field": "mode"})
                plan = self.files["plan"]
                return self._reply({"mode": mode, "plan_hash": plan["plan_hash"], "status": plan["status"],
                                    "blocking": plan["blocking"], "warnings": plan["warnings"]})
        raise FakeError("not_found", f"The route {method} {path} does not exist.")

    def _submit(self, kind: str, body: dict[str, Any]) -> dict[str, Any]:
        session = self._require_session()
        if body.get("base_revision") != self.revision:
            raise FakeError("stale_revision", "The session changed after the base revision.", {"base_revision": body.get("base_revision"), "revision": self.revision})
        if not str(body.get("reason") or "").strip():
            raise FakeError("reason_required", "A proposal needs a reason.")
        if kind == "questions":
            question = {"id": f"q-test-{self.next_proposal}", "target_id": body.get("target_id"),
                        "target_name": body.get("target_name", body.get("target_id")), "text": body.get("text"),
                        "options": body.get("options", []), "recommended_option": body.get("recommended_option"),
                        "reason": body.get("reason"), "mcp_client": body.get("mcp_client", "Test agent"), "author": "agent",
                        "created_utc": "2026-10-31T10:00:00Z", "status": "open", "blocked": None,
                        "selected_option": None, "answered_utc": None}
            self.next_proposal += 1
            session["questions"]["open"].append(question)
            self._step("question_ask", {"target_id": question["target_id"], "reason": question["reason"]}, "agent")
            return self._reply({"question": question})
        if float(body.get("confidence", 0)) < PROPOSAL_MIN_CONFIDENCE:
            raise FakeError("confidence_below_threshold", "The confidence is below 0.9.", {"minimum": PROPOSAL_MIN_CONFIDENCE})
        return self._reply({"proposal": self._add_proposal(session, body)})

    def _reply(self, value: dict[str, Any]) -> dict[str, Any]:
        return {**value, "revision": self.revision}

    def _display_folders(self, query: dict[str, list[str]]) -> dict[str, Any]:
        source = _one(query, "source")
        obj_type = _one(query, "object_type")
        target_model_id = ((self.session or {}).get("target", {}).get("model") or {}).get("source_id")
        source_id = source or target_model_id
        raw = self.files.get("display-folders", {})
        folders_map = raw.get("folders", {})
        if isinstance(folders_map, dict):
            if source_id and source_id in folders_map:
                folders = list(folders_map[source_id])
            elif "src-1" in folders_map:
                folders = list(folders_map["src-1"])
            else:
                folders = [item for sub in folders_map.values() if isinstance(sub, list) for item in sub]
        elif isinstance(folders_map, list):
            folders = list(folders_map)
        else:
            folders = []
        types = [obj_type] if obj_type else ["measure", "column", "hierarchy"]
        return {"source_id": source_id, "types": types, "folders": sorted(set(folders))}

    def _name_propose(self, body: dict[str, Any]) -> dict[str, Any]:
        raw_name = str(body.get("name") or body.get("candidate") or "New measure").strip()
        candidate = str(body["candidate"]).strip() if body.get("candidate") else None
        obj_type = str(body.get("object_type") or "measure")
        if obj_type == "column":
            obj_type = "data_column"
        table = body.get("table")
        display_folder = body.get("display_folder")
        source_id = body.get("source_id")
        donor_name = None
        if source_id and self.session:
            src_obj = next((s for s in self.session.get("sources", []) if s["source_id"] == source_id), None)
            if src_obj:
                donor_name = src_obj["display_name"]

        rules = [
            r for r in self.files.get("naming-rules", {}).get("rules", [])
            if r.get("status") == "confirmed"
            and (r.get("object_type") == obj_type or (obj_type == "report_measure" and r.get("object_type") == "measure"))
        ]
        used_rule_ids: list[str] = []
        proposed = raw_name
        for r in rules:
            scope = r.get("scope") or {}
            if scope.get("table") and scope["table"] != table:
                continue
            if scope.get("display_folder") and scope["display_folder"] != display_folder:
                continue
            kind = r.get("check", {}).get("kind")
            val = r.get("check", {}).get("value", "")
            if kind == "letter_case" and val == "title":
                proposed = " ".join(w.capitalize() if w.islower() else w for w in proposed.split())
                used_rule_ids.append(r["rule_id"])
            elif kind == "prefix" and val and not proposed.startswith(val):
                proposed = f"{val}{proposed}"
                used_rule_ids.append(r["rule_id"])
            elif kind == "suffix" and val and not proposed.endswith(val):
                proposed = f"{proposed} {val}".strip()
                used_rule_ids.append(r["rule_id"])
        if not used_rule_ids:
            proposed = " ".join(w.capitalize() if w.islower() else w for w in proposed.split()) or "New Measure"
            used_rule_ids = ["nr-000000000002"]

        def _row_key_for(ot: str, tbl: str | None, nm: str) -> str:
            if ot in {"table", "calculated_table", "calculation_group"}:
                return f"table:{nm}"
            prefix = "column" if ot in {"data_column", "calculated_column", "column"} else ot
            return f"{prefix}:{tbl or 'Table'}/{nm}"

        target_rows = [
            r for r in self._rows()
            if (r.get("cells", {}).get("src-1", {}).get("state") if isinstance(r.get("cells"), dict) else "same") != "missing"
        ]

        def _find_clash(nm: str) -> dict[str, Any] | None:
            folded = nm.casefold()
            for r in target_rows:
                if r["name"].casefold() == folded:
                    r_type = r.get("object_type", "measure")
                    if r_type == "column":
                        r_type = "data_column"
                    return {
                        "object_type": r_type,
                        "name": r["name"],
                        "table": r.get("table"),
                        "row_key": _row_key_for(r_type, r.get("table"), r["name"]),
                    }
            return None

        resolved_clash = _find_clash(proposed)
        if resolved_clash is not None:
            suffix = donor_name or "2"
            proposed = f"{proposed} ({suffix})"

        checked = candidate if candidate is not None else proposed
        clash = _find_clash(checked)
        rule_breaks: list[dict[str, str]] = []
        for r in rules:
            scope = r.get("scope") or {}
            if scope.get("table") and scope["table"] != table:
                continue
            if scope.get("display_folder") and scope["display_folder"] != display_folder:
                continue
            kind = r.get("check", {}).get("kind")
            val = r.get("check", {}).get("value", "")
            if kind == "letter_case" and val == "title":
                words = checked.split()
                if any(w and w[0].islower() for w in words) or "_" in checked:
                    rule_breaks.append({"rule_id": r["rule_id"], "text": r.get("text", "Measure names use Title Case.")})
            elif kind == "prefix" and val and not checked.startswith(val):
                rule_breaks.append({"rule_id": r["rule_id"], "text": r.get("text", f"Names start with {val}.")})
            elif kind == "suffix" and val and not checked.endswith(val):
                rule_breaks.append({"rule_id": r["rule_id"], "text": r.get("text", f"Names end with {val}.")})
            elif kind == "separator" and val == "space" and "_" in checked:
                rule_breaks.append({"rule_id": r["rule_id"], "text": r.get("text", "Table names use space separator.")})
            elif kind == "regex" and val:
                try:
                    if re.fullmatch(val, checked) is None:
                        rule_breaks.append({"rule_id": r["rule_id"], "text": r.get("text", f"Names match {val}.")})
                except re.error:
                    pass

        return {
            "name": proposed,
            "rule_ids": used_rule_ids,
            "table": table,
            "display_folder": display_folder,
            "resolved_clash": resolved_clash,
            "checked_name": checked,
            "breaks": rule_breaks,
            "clash": clash,
        }

    def _sessions(self) -> dict[str, Any]:
        """GET sessions as the real backend gives it (UC1, UC2).

        With no project, the real backend refuses with the reason no_project. With no open session,
        the revision is null. The row of the open session has is_open true.
        """
        if self.meta.get("no_project"):
            raise FakeError("action_not_allowed", "Open a project first.", {"reason": "no_project"})
        open_id = (self.session or {}).get("session_id")
        rows = [{**row, "is_open": row["session_id"] == open_id} for row in self.files["sessions"]["sessions"]]
        return {"sessions": rows, "revision": self.revision if self.session is not None else None}

    def _log(self, query: dict[str, list[str]]) -> dict[str, Any]:
        """Step U9: the GET log filters of S10 (author, action, target, proposal_id) before the paging."""
        entries = self.files["log"]["entries"]
        for key in ("author", "action", "target", "proposal_id"):
            wanted = _one(query, key)
            if wanted:
                entries = [entry for entry in entries if str(entry.get(key)) == wanted]
        return {**self.files["log"], "entries": entries}

    def _page(self, value: dict[str, Any], key: str, query: dict[str, list[str]]) -> dict[str, Any]:
        items = value[key]
        limit, offset = _int(query, "limit", 200), _int(query, "offset", 0)
        page = items[offset:offset + limit]
        return {**value, key: page, "total": len(items), "has_more": offset + len(page) < len(items)}

    # Step U8: GET impact as S6 gives it (UC29): filters, then facets and total before paging.

    def _impact_items(self, include_proposals: bool = False) -> list[dict[str, Any]]:
        impact = self.files["impact"]
        items = list(impact.get("items", []))
        if include_proposals:
            items += list(impact.get("proposal_items", []))
        return items

    def _impact(self, query: dict[str, list[str]]) -> dict[str, Any]:
        impact = self.files["impact"]
        items = self._impact_items(_one(query, "include_proposals") in {"true", "1"})
        for name, read in (("direction", lambda it: it["direction"]), ("severity", lambda it: it["severity"]),
                           ("certainty", lambda it: it["certainty"]),
                           ("source", lambda it: it["impacted_object"].get("source_id")),
                           ("object_type", lambda it: it["impacted_object"]["object_type"])):
            wanted = _one(query, name)
            if wanted:
                items = [it for it in items if read(it) == wanted]
        blocking = _one(query, "blocking")
        if blocking is not None:
            items = [it for it in items if it["blocking"] == (blocking.lower() in {"true", "1"})]
        text = (_one(query, "q") or "").lower()
        if text:
            items = [it for it in items if text in it["impacted_object"]["name"].lower() or text in it.get("reason_text", "").lower()]
        items.sort(key=lambda it: (not it["blocking"], IMPACT_SEVERITY_RANK.get(it["severity"], 99), it["impacted_object"]["name"].lower()))
        facets: dict[str, dict[str, int]] = {"direction": {"breaks": 0, "needs": 0}, "blocking": {"true": 0, "false": 0},
                                             "severity": {}, "certainty": {"certain": 0, "possible": 0}, "object_type": {}}
        for it in items:
            for facet, value in (("direction", it["direction"]), ("blocking", "true" if it["blocking"] else "false"),
                                 ("severity", it["severity"]), ("certainty", it["certainty"]),
                                 ("object_type", it["impacted_object"]["object_type"])):
                facets[facet][value] = facets[facet].get(value, 0) + 1
        limit, offset = _int(query, "limit", 50), _int(query, "offset", 0)
        page = items[offset:offset + limit]
        return {"target": _one(query, "target") or "plan", "total": len(items), "limit": limit, "offset": offset,
                "has_more": offset + len(page) < len(items), "facets": facets, "items": copy.deepcopy(page),
                "completeness": copy.deepcopy(impact.get("completeness", {"status": "complete"})),
                "offers": copy.deepcopy(impact.get("offers", []))}

    def _impact_item(self, item_id: Any) -> dict[str, Any]:
        for item in self._impact_items(True):
            if item["id"] == item_id:
                return item
        raise FakeError("not_found", f"The impact item {item_id} does not exist.", {"item_id": item_id})

    def _impact_paths(self, item_id: str, query: dict[str, list[str]]) -> dict[str, Any]:
        item = self._impact_item(item_id)
        paths = (self.files.get("impact-paths") or {}).get(item_id) or ([item["path"]] if item["path"] else [])
        limit, offset = _int(query, "limit", 50), _int(query, "offset", 0)
        page = paths[offset:offset + limit]
        return {"item_id": item_id, "total": len(paths), "limit": limit, "offset": offset,
                "has_more": offset + len(page) < len(paths), "paths": copy.deepcopy(page)}

    def _compare_rows(self, query: dict[str, list[str]]) -> dict[str, Any]:
        rows = self._rows()
        state = _one(query, "state")
        if state in {"not_same", "notsame"}:
            rows = [row for row in rows if row.get("row_state") != "same"]
        elif state:
            rows = [row for row in rows if row.get("row_state") == state]
        filters = {"type": "object_type", "table": "table", "folder": "display_folder"}
        for name, field in filters.items():
            wanted = _one(query, name)
            if wanted:
                rows = [row for row in rows if row.get(field) == wanted]
        source = _one(query, "source")
        if source:
            rows = [row for row in rows if source in row["cells"]]
        if _one(query, "changed") == "true":
            rows = [row for row in rows if any(cell["changed"] for cell in row["cells"].values())]
        if _one(query, "marks") == "true":
            rows = [row for row in rows if row["marks"]]
        if _one(query, "proposal") == "true":
            rows = [row for row in rows if row.get("proposal_status")]
        page_val = _one(query, "page")
        if page_val:
            rows = [row for row in rows if row.get("page") == page_val]
        text = (_one(query, "q") or "").casefold()
        if text:
            rows = [row for row in rows if text in row["name"].casefold()]
        sort = _one(query, "sort")
        if sort:
            field, _, direction = sort.partition(":")
            key = {"state": "row_state", "name": "name", "type": "object_type", "table": "table"}.get(field)
            if key is None:
                raise FakeError("invalid_payload", "The sort must be state, name, type, or table.", {"field": "sort"})
            rows = sorted(rows, key=lambda row: str(row.get(key) or ""), reverse=direction == "desc")
        counts: dict[str, int] = {}
        for row in rows:
            counts[row["row_state"]] = counts.get(row["row_state"], 0) + 1
        return {**self._page({"rows": rows}, "rows", query), "state_counts": counts, "compare_mode": (self.session or {}).get("compare_mode", "default")}


def _one(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    return values[0] if values else None


def _int(query: dict[str, list[str]], key: str, default: int) -> int:
    value = _one(query, key)
    try:
        number = int(value) if value is not None else default
    except ValueError as exc:
        raise FakeError("invalid_payload", f"The parameter {key} must be an integer.", {"field": key}) from exc
    if number < 0:
        raise FakeError("invalid_payload", f"The parameter {key} must be 0 or more.", {"field": key})
    return number


def shim_script() -> bytes:
    """The shim with the method lists in front of it, so that the shim has no import."""
    lists = json.dumps({"jsapi": list(JSAPI_METHODS), "desktop": list(DESKTOP_METHODS)})
    return f"self.__DEVCENTER_FAKE_METHODS__ = {lists};\n".encode("utf-8") + SHIM.read_bytes()


def index_with_shim(html: str) -> str:
    """Put the shim tag before the first module script, so that the shim runs before the app."""
    marker = '<script type="module"'
    position = html.find(marker)
    if position < 0:
        position = html.find("</head>")
    return html[:position] + SHIM_TAG + "\n    " + html[position:] if position >= 0 else SHIM_TAG + html


class FakeDevCenterHandler(BaseHTTPRequestHandler):
    server_version = "DevCenterFake/1"
    state: FakeDevCenter
    dist: Path

    def log_message(self, *_args: Any) -> None:
        pass

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def _dispatch(self, method: str) -> None:
        parsed = urlsplit(self.path)
        path, query = parsed.path, parse_qs(parsed.query, keep_blank_values=True)
        try:
            body = self._body() if method == "POST" else {}
            if path.startswith("/__test__/"):
                self._test_route(method, path[len("/__test__/"):], body)
            elif path.startswith("/api/devcenter/"):
                self._json(200, self.state.read(method, path, query, body))
            elif path == "/api/overview":
                self._json(200, {"models": [], "reports": [], "counts": {}, "candidate_count": 0, "warning_count": 0, "validation_state": "passed", "scan_state": "idle", "last_scan": None})
            elif path == "/api/config":
                if method == "POST":
                    self.state.files.setdefault("legacy_config", {}).update(body)
                    self._json(200, self.state.files.get("legacy_config", body))
                else:
                    cfg = self.state.files.get("legacy_config", {"name": "Power BI Brain", "sources": [], "graph_colors": {}})
                    self._json(200, cfg)
            elif path == "/api/scan":
                self._json(200, {"overview": {"models": [], "reports": [], "counts": {}, "candidate_count": 0, "warning_count": 0, "validation_state": "passed", "scan_state": "idle", "last_scan": "2026-11-03T20:00:00Z"}, "source_count": len(self.state.files.get("legacy_config", {}).get("sources", []))})
            elif path.startswith("/api/"):
                raise FakeError("not_found", f"The fake server has no route {path}.")
            elif method == "GET":
                self._static(path)
            else:
                raise FakeError("not_found", f"The fake server has no route {method} {path}.")
        except FakeError as error:
            self._json(error.status, error.body())

    def _test_route(self, method: str, route: str, body: dict[str, Any]) -> None:
        state = self.state
        if method == "GET" and route == "health":
            return self._json(200, state.health())
        if method == "GET" and route == "pywebview-shim.js":
            return self._send(200, shim_script(), "text/javascript; charset=utf-8")
        if method == "POST" and route.startswith("jsapi/"):
            try:
                reply = state.call(route[len("jsapi/"):], body)
            except FakeError as error:
                # The real host returns an error dict, not an HTTP failure. A network fault is an HTTP failure.
                if error.code == "network":
                    raise
                return self._json(200, error.body())
            return self._json(200, reply)
        if method == "POST" and route.startswith("desktop/"):
            return self._json(200, self._desktop(route[len("desktop/"):]))
        controls = {"scenario": lambda: state.load(str(body.get("name", ""))), "fault": lambda: state.set_fault(body),
                    "delay": lambda: state.set_delay(body), "agent-proposal": lambda: state.agent_proposal(body),
                    "agent-review": lambda: state.agent_review(body),
                    "rules": lambda: state.set_rules(body), "plan": lambda: state.set_plan(body),
                    "compare-rows": lambda: state.set_compare_rows(body), "impact": lambda: state.set_impact(body),
                    "apply": lambda: state.set_apply(body)}
        if method == "POST" and route in controls:
            return self._json(200, controls[route]())
        raise FakeError("not_found", f"The test route {method} /__test__/{route} does not exist.")

    def _desktop(self, method: str) -> dict[str, Any]:
        if method not in DESKTOP_METHODS:
            return {"ok": False, "error": f"The desktop host has no method {method}."}
        with self.state.lock:
            session = copy.deepcopy(self.state.files["desktop-session"])
        if method == "choose_folder":
            return {"ok": True, "folder": "merge-lab"}
        if method == "choose_sources":
            # Each pick gives the next source, so that a create flow can add more than one source.
            with self.state.lock:
                index = self.state.picks
                self.state.picks += 1
            return {"ok": True, "sources": [SOURCE_PICKS[index % len(SOURCE_PICKS)]]}
        return session

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length > 1024 * 1024:
            raise FakeError("invalid_payload", "The request body is larger than 1 MiB.")
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise FakeError("invalid_payload", "The request body is not valid JSON.") from exc
        if not isinstance(value, dict):
            raise FakeError("invalid_payload", "The request body must be a JSON object.")
        return value

    def _static(self, path: str) -> None:
        dist = self.dist.resolve()
        asset = (dist / unquote(path).lstrip("/")).resolve()
        if not asset.is_relative_to(dist):
            raise FakeError("not_found", "The path is not in the frontend build.")
        if path == "/" or not asset.is_file():
            index = dist / "index.html"
            if not index.is_file():
                return self._send(503, b"Build the frontend first: npm run build in frontend/.", "text/plain; charset=utf-8")
            return self._send(200, index_with_shim(index.read_text(encoding="utf-8")).encode("utf-8"), "text/html; charset=utf-8")
        self._send(200, asset.read_bytes(), mimetypes.guess_type(asset.name)[0] or "application/octet-stream")

    def _json(self, status: int, value: Any) -> None:
        self._send(status, json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8"), "application/json")

    def _send(self, status: int, raw: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)


def create_server(port: int = DEFAULT_PORT, *, state: FakeDevCenter | None = None, dist: Path = DIST) -> ThreadingHTTPServer:
    """Make the server on 127.0.0.1. Port 0 picks a free port (for unit tests)."""
    handler = type("BoundFakeDevCenterHandler", (FakeDevCenterHandler,), {"state": state or FakeDevCenter(), "dist": dist})
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    server.daemon_threads = True
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="Fake Development Center server for UI tests.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--scenario", default="default", choices=SCENARIOS)
    args = parser.parse_args()
    state = FakeDevCenter()
    state.load(args.scenario)
    with create_server(args.port, state=state) as server:
        print(f"Development Center fake server ready at http://127.0.0.1:{args.port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
