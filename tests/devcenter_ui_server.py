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
    "cloud_items_list",
)
# Calls that read only: they do not change the revision.
JSAPI_READS = frozenset({"cloud_items_list"})
# Calls that work with no open session.
NO_SESSION_METHODS = frozenset({"session_create", "session_open", "cloud_sign_in", "cloud_items_list"})
# Calls that a read-only (locked) session still permits.
LOCKED_METHODS = frozenset({"session_close", "session_open", "cloud_items_list", "cloud_sign_in"})
# The existing desktop host methods that frontend/src/desktop.js and App.jsx use (old reply shape).
DESKTOP_METHODS = ("get_session", "choose_folder", "choose_sources", "open_project", "add_sources", "close_project")

ERROR_STATUS = {
    "invalid_payload": 400, "not_found": 404, "session_not_open": 409, "stale_revision": 409,
    "action_not_allowed": 409, "source_changed": 409, "user_choice_exists": 409,
    "confidence_below_threshold": 422, "reason_required": 422, "naming_rule_violation": 422,
    "unknown": 500, "network": 503,
}
PROPOSAL_MIN_CONFIDENCE = 0.9


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


def _generate_large(files: dict[str, Any], plan: dict[str, int]) -> None:
    """Make the large-5000-rows data in memory, so that the repository has no large fixture file."""
    session = files["session"]
    source_ids = [f"src-{index + 1}" for index in range(plan["sources"])]
    session["sources"] = [
        {"id": source_id, "display_name": f"Model {index + 1}", "kind": "pbip_folder", "role": "donor", "access_type": "local",
         "path": f"sources/Model{index + 1}.SemanticModel", "status": "ok", "fingerprint_state": "same"}
        for index, source_id in enumerate(source_ids)
    ]
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
    severities = ("critical", "high", "low", "not_checked")
    files["impact"] = {
        **files["impact"],
        "items": [
            {"id": f"imp-{index:05d}", "object_id": f"visual-{index:05d}", "object_name": f"Visual {index:05d}", "object_type": "visual",
             "direction": "downstream", "severity": severities[index % len(severities)], "certainty": "certain",
             "reason_id": "impact.reason.measure_changed", "blocking": False}
            for index in range(plan["impact_items"])
        ],
    }
    session["counts"] = {**session["counts"], "rows": plan["compare_rows"]}


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

    def agent_proposal(self, body: dict[str, Any]) -> dict[str, Any]:
        """Add a proposal as an agent would, with no revision check. For the poll test (A19)."""
        with self.lock:
            session = self._require_session()
            proposal = self._add_proposal(session, body)
            return {"revision": self.revision, "proposal": proposal}

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

    def _call_session_open(self, payload: dict[str, Any]) -> dict[str, Any]:
        session_id = payload.get("session_id")
        item = next((entry for entry in self.files["sessions"]["sessions"] if entry["id"] == session_id), None)
        if item is None:
            raise FakeError("not_found", f"The session {session_id} does not exist.")
        if item["schema_state"] != "ok":
            raise FakeError("action_not_allowed", "This session file cannot open.", {"reason": item["schema_state"]})
        _, default_files = load_scenario_files("default", self.fixtures)
        session = copy.deepcopy(default_files["session"])
        session.update({"id": item["id"], "display_name": item["display_name"], "lock": item["lock_state"], "read_only": item["lock_state"] == "locked"})
        self.session = session
        return {"session": session}

    def _call_session_create(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = payload.get("display_name")
        if not isinstance(name, str) or not name.strip():
            raise FakeError("invalid_payload", "The session needs a display name.", {"field": "display_name"})
        _, default_files = load_scenario_files("default", self.fixtures)
        session = copy.deepcopy(default_files["session"])
        session.update({"id": f"s-{len(self.files['sessions']['sessions']) + 1}", "display_name": name.strip(), "open_proposals": []})
        self.session = session
        self.files["sessions"]["sessions"].insert(0, {
            "id": session["id"], "display_name": session["display_name"], "updated_utc": "2026-10-31T10:00:00Z",
            "target_model_name": session["target"]["model_name"], "target_report_name": session["target"]["report_name"],
            "source_count": len(session["sources"]), "plan_status": None, "lock_state": "free", "schema_state": "ok",
        })
        return {"session": session}

    def _call_session_close(self, _payload: dict[str, Any]) -> None:
        self.session = None

    def _call_merge_choice_set(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = self._row(payload.get("row_key"))
        row["merge_choice"] = payload.get("choice")
        return {"row_key": row["row_key"]}

    def _call_merge_choice_bulk_set(self, payload: dict[str, Any]) -> dict[str, Any]:
        keys = payload.get("row_keys")
        if not isinstance(keys, list) or not keys:
            raise FakeError("invalid_payload", "The bulk call needs a list of row keys.", {"field": "row_keys"})
        rows = [self._row(key) for key in keys]
        for row in rows:
            row["merge_choice"] = payload.get("choice")
        return {"changed": len(rows)}

    def _call_row_confirm(self, payload: dict[str, Any]) -> dict[str, Any]:
        keys = payload.get("row_keys")
        if not isinstance(keys, list) or not keys:
            raise FakeError("invalid_payload", "The confirm call needs a list of row keys.", {"field": "row_keys"})
        rows = [self._row(key) for key in keys]
        for row in rows:
            row["marks"] = []
        self.session["counts"]["marks"] = sum(1 for row in self._rows() if row["marks"])
        return {"confirmed": len(rows)}

    def _take_proposal(self, proposal_id: Any) -> dict[str, Any]:
        proposals = self.session["open_proposals"]
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
        for proposal in self.session["open_proposals"]:
            if proposal.get("blocked"):
                skipped.append({"id": proposal["id"], "reason": proposal["blocked"]})
                kept.append(proposal)
            else:
                accepted.append(proposal["id"])
        self.session["open_proposals"] = kept
        return {"accepted_ids": accepted, "skipped": skipped}

    def _call_cloud_items_list(self, payload: dict[str, Any]) -> dict[str, Any]:
        kind = payload.get("kind", "workspaces")
        if kind not in {"workspaces", "models", "reports"}:
            raise FakeError("invalid_payload", "The kind must be workspaces, models, or reports.", {"field": "kind"})
        return {"kind": kind, "items": self.files["cloud-items"][kind]}

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
        session["open_proposals"] = [item for item in session["open_proposals"]
                                     if (item["target_id"], item["kind"]) != (proposal["target_id"], proposal["kind"])]
        session["open_proposals"].append(proposal)
        session["counts"]["open_proposals"] = len(session["open_proposals"])
        self._step("proposal_submit", {"target_id": proposal["target_id"], "proposal_id": proposal["id"], "reason": proposal["reason"]}, author)
        return proposal

    # HTTP reads and proposal endpoints

    def read(self, method: str, path: str, query: dict[str, list[str]], body: dict[str, Any]) -> dict[str, Any]:
        parts = [unquote(part) for part in path.split("/") if part][2:]
        self.before_reply(path)
        self.before_reply(f"{method} {path}")
        with self.lock:
            if method == "GET" and parts == ["sessions"]:
                return self._reply(self.files["sessions"])
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
                simple = {
                    ("plan",): "plan", ("impact",): "impact", ("naming-rules",): "naming-rules", ("apply", "preview"): "apply-preview",
                    ("apply", "progress"): "apply-progress", ("apply", "last"): "apply-last", ("display-folders",): "display-folders",
                }
                if tuple(parts) in simple:
                    value = self.files[simple[tuple(parts)]]
                    if parts == ["impact"]:
                        value = self._page(value, "items", query)
                    return self._reply(value)
                if parts == ["log"]:
                    return self._reply(self._page(self.files["log"], "entries", query))
                if len(parts) == 3 and parts[:2] == ["impact", "removal"]:
                    return self._reply({**self.files["removal"], "object": parts[2]})
                if len(parts) == 2 and parts[0] == "wireframe":
                    return self._reply({**self.files["wireframe"], "report": parts[1]})
            if method == "POST" and parts == ["name-propose"]:
                candidate = body.get("candidate") or body.get("name") or "New measure"
                return self._reply({"name": str(candidate).strip().title(), "rule_ids": ["rule-1"], "breaks": [], "clash": None})
            if method == "POST" and parts == ["plan-validate"]:
                mode = body.get("mode", "quick")
                if mode not in {"quick", "full"}:
                    raise FakeError("invalid_payload", "The mode must be quick or full.", {"field": "mode"})
                plan = self.files["plan"]
                return self._reply({"mode": mode, "status": plan["status"], "blocking": plan["blocking"], "warnings": plan["warnings"]})
        raise FakeError("not_found", f"The route {method} {path} does not exist.")

    def _submit(self, kind: str, body: dict[str, Any]) -> dict[str, Any]:
        session = self._require_session()
        if body.get("base_revision") != self.revision:
            raise FakeError("stale_revision", "The session changed after the base revision.", {"base_revision": body.get("base_revision"), "revision": self.revision})
        if not str(body.get("reason") or "").strip():
            raise FakeError("reason_required", "A proposal needs a reason.")
        if kind == "questions":
            question = {"id": f"q-test-{self.next_proposal}", "target_id": body.get("target_id"), "text": body.get("text"),
                        "options": body.get("options", []), "recommended": body.get("recommended"), "reason": body.get("reason")}
            self.next_proposal += 1
            session["open_questions"].append(question)
            self._step("question_ask", {"target_id": question["target_id"], "reason": question["reason"]}, "agent")
            return self._reply({"question": question})
        if float(body.get("confidence", 0)) < PROPOSAL_MIN_CONFIDENCE:
            raise FakeError("confidence_below_threshold", "The confidence is below 0.9.", {"minimum": PROPOSAL_MIN_CONFIDENCE})
        return self._reply({"proposal": self._add_proposal(session, body)})

    def _reply(self, value: dict[str, Any]) -> dict[str, Any]:
        return {**value, "revision": self.revision}

    def _page(self, value: dict[str, Any], key: str, query: dict[str, list[str]]) -> dict[str, Any]:
        items = value[key]
        limit, offset = _int(query, "limit", 200), _int(query, "offset", 0)
        page = items[offset:offset + limit]
        return {**value, key: page, "total": len(items), "has_more": offset + len(page) < len(items)}

    def _compare_rows(self, query: dict[str, list[str]]) -> dict[str, Any]:
        rows = self._rows()
        filters = {"type": "object_type", "table": "table", "folder": "display_folder", "state": "row_state"}
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
        return {**self._page({"rows": rows}, "rows", query), "state_counts": counts}


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
                    "delay": lambda: state.set_delay(body), "agent-proposal": lambda: state.agent_proposal(body)}
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
            return {"ok": True, "sources": ["sources/Sales.SemanticModel"]}
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
