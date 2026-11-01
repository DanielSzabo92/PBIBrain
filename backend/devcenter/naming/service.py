"""Naming rules of the open merge session (technical design sections 5 and 14, UC16, UC18, UC19, UC34).

The reads (``rules_view``, ``name_propose``) change nothing. The changes
(``confirm``, ``reject``, ``edit``, ``copy``) exist only in the pywebview JS
API (ADR 0003). Each change writes the rule file of the target model, stores
the rule file path and hash in the session, and adds one log entry.

This module uses the session frame of ``DevCenterSessions`` (lock, open
session, source records, and ``_change``) so that a rule change follows the
same revision and log rules as each other state change.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from backend.devcenter import contracts
from backend.devcenter.errors import DevCenterError, not_allowed
from backend.devcenter.naming.detector import NamingSettings, detect
from backend.devcenter.naming.objects import RULE_OBJECT_TYPES, NamedObject, format_kind, model_objects, report_objects
from backend.devcenter.naming.proposer import breaks, clash_with, propose
from backend.devcenter.naming.rules import (
    CHECK_KINDS,
    CONFIRMED,
    ORIGIN_USER,
    PROPOSED,
    REJECTED,
    identity_key,
    make_rule,
    rule_id_for,
    rule_text,
    signature,
    support,
    validate_rule,
)
from backend.devcenter.naming.store import local_rule_file, read_rule_set, write_rule_set
from backend.devcenter.sources.kinds import LocalSource

NAME_PROPOSE_REQUEST = "http/name-propose.request.json"


@dataclass
class _Target:
    record: Mapping[str, Any]
    source: LocalSource
    path: Path
    rule_set: dict[str, Any]
    objects: list[NamedObject]
    report_objects: list[NamedObject]
    detected: list[dict[str, Any]] | None = None

    @property
    def settings(self) -> NamingSettings:
        return NamingSettings.from_mapping(self.rule_set.get("settings"))

    @property
    def stored(self) -> list[dict[str, Any]]:
        return self.rule_set["rules"]

    def offered(self) -> list[dict[str, Any]]:
        """The detected rules that the file does not have. A rejected rule is not offered again."""

        if self.detected is None:
            self.detected = detect(self.objects, self.settings)
        return offered_rules(self.stored, self.detected)

    def all_rules(self) -> list[dict[str, Any]]:
        return [*self.stored, *self.offered()]


def offered_rules(stored: list[Mapping[str, Any]], detected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    signatures = {signature(rule) for rule in stored}
    keys = {identity_key(rule) for rule in stored if rule["status"] != REJECTED}
    return [rule for rule in detected if signature(rule) not in signatures and identity_key(rule) not in keys]


def _sort_key(rule: Mapping[str, Any]) -> tuple[int, int, str]:
    return (RULE_OBJECT_TYPES.index(rule["object_type"]), CHECK_KINDS.index(rule["check"]["kind"]), rule["rule_id"])


def rule_view(rule: Mapping[str, Any], objects: list[NamedObject]) -> dict[str, Any]:
    found = support(rule, objects)
    return {**copy.deepcopy(dict(rule)), "text": rule_text(rule), "support": found, "breaks": found["total"] - found["count"]}


def _model_source(devcenter: Any, record: Mapping[str, Any]) -> LocalSource | None:
    """Load a source with a model. A missing or damaged source gives None."""

    if not record.get("model_path"):
        return None
    try:
        source = devcenter._load(record)
    except (DevCenterError, OSError, ValueError):
        return None
    return source if source.model_dir is not None and source.model_format is not None else None


def _load_target(devcenter: Any, document: Mapping[str, Any], *, required: bool) -> _Target | None:
    model = (document.get("target") or {}).get("model") or {}
    source_id = model.get("source_id")
    if not source_id:
        if required:
            raise not_allowed("Select a target model first.", "no_target")
        return None
    record = devcenter._source(document, source_id)
    source = _model_source(devcenter, record)
    if source is None:
        raise not_allowed("The app cannot read the target model.", "target_unreadable", source_id=source_id)
    assert source.model_dir is not None
    path = local_rule_file(devcenter.project_root, source.model_dir)
    report_source = None
    report = (document.get("target") or {}).get("report") or {}
    if report.get("mode") == "existing" and report.get("source_id"):
        try:
            report_source = devcenter._load(devcenter._source(document, report["source_id"]))
        except (DevCenterError, OSError, ValueError):
            report_source = None
    return _Target(record, source, path, read_rule_set(path, source.model_dir.name), model_objects(source),
                   report_objects(report_source))


def _source_rules(devcenter: Any, record: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The rule set of one session source model: the rules of its file (not rejected) and its detected rules."""

    source = _model_source(devcenter, record)
    if source is None:
        return []
    assert source.model_dir is not None
    try:
        rule_set = read_rule_set(local_rule_file(devcenter.project_root, source.model_dir), source.model_dir.name)
    except DevCenterError:
        return []
    stored = rule_set["rules"]
    detected = detect(model_objects(source), NamingSettings.from_mapping(rule_set.get("settings")))
    return [rule for rule in stored if rule["status"] != REJECTED] + offered_rules(stored, detected)


# Reads -----------------------------------------------------------------------


def rules_view(devcenter: Any) -> dict[str, Any]:
    """``GET naming-rules``: the rules with status, origin, support, and break counts (UC18)."""

    with devcenter._lock:
        current = devcenter._require_open()
        document = current.document
        target = _load_target(devcenter, document, required=False)
        target_id = target.record["source_id"] if target else None
        counts = {
            item["source_id"]: len(_source_rules(devcenter, item))
            for item in document["sources"]
            if item["source_id"] != target_id and item.get("model_path")
        }
        if target is None:
            return {"revision": document["revision"], "target": None, "settings": NamingSettings().view(), "rules": [],
                    "source_rule_counts": counts}
        rules = sorted(target.all_rules(), key=_sort_key)
        return {
            "revision": document["revision"],
            "target": {"source_id": target_id, "model_name": target.record["display_name"],
                       "rule_file": devcenter._relative(target.path)},
            "settings": target.settings.view(),
            "rules": [rule_view(rule, target.objects) for rule in rules],
            "source_rule_counts": counts,
        }


def name_propose(devcenter: Any, body: Any) -> dict[str, Any]:
    """``POST name-propose``: a read-only calculation (UC19)."""

    problems = contracts.errors(NAME_PROPOSE_REQUEST, body)
    if problems:
        raise DevCenterError("invalid_payload", "The request is not valid.", {"errors": problems[:20]})
    with devcenter._lock:
        current = devcenter._require_open()
        document = current.document
        target = _load_target(devcenter, document, required=True)
        assert target is not None
        donor = None
        if body.get("source_id"):
            donor = devcenter._source(document, body["source_id"])["display_name"]
        context = {"table": body.get("table"), "display_folder": body.get("display_folder"),
                   "format_kind": format_kind(body.get("format_string"))}
        existing = target.objects + target.report_objects
        rules = target.stored
        result = propose(body["name"], body["object_type"], context, rules, existing, donor)
        checked = body.get("candidate") or result["name"]
        check_context = context if body.get("candidate") else {**context, "table": result["table"], "display_folder": result["display_folder"]}
        clash = clash_with(checked, body["object_type"], check_context["table"], existing)
        return {
            "revision": document["revision"],
            "name": result["name"],
            "rule_ids": result["rule_ids"],
            "table": result["table"],
            "display_folder": result["display_folder"],
            "resolved_clash": result["clash"],
            "checked_name": checked,
            "breaks": breaks(checked, body["object_type"], check_context, rules),
            "clash": clash.view() if clash is not None else None,
        }


# Changes (JS API only) ---------------------------------------------------------


def _find(target: _Target, rule_id: Any) -> tuple[dict[str, Any], bool]:
    """Give (rule, is_stored). Raise ``not_found`` for an unknown rule ID."""

    for rule in target.stored:
        if rule["rule_id"] == rule_id:
            return rule, True
    for rule in target.offered():
        if rule["rule_id"] == rule_id:
            return rule, False
    raise DevCenterError("not_found", "The naming rule does not exist.", {"rule_id": rule_id})


def _change(devcenter: Any, request: Mapping[str, Any], action: str,
            work: Callable[[_Target], tuple[Any, Any, dict[str, Any]]]) -> dict[str, Any]:
    """Run one rule change in the session frame. ``work`` changes ``target.rule_set`` and gives (before, after, reply)."""

    with devcenter._lock:
        current = devcenter._require_open()
        target = _load_target(devcenter, current.document, required=True)
        assert target is not None
        reply: dict[str, Any] = {}

        def mutate(draft: dict[str, Any]) -> tuple[Any, Any]:
            before, after, result = work(target)
            digest = write_rule_set(target.path, target.rule_set)
            draft["naming_rules"] = {"path": devcenter._relative(target.path), "hash": digest}
            reply.update(result)
            return before, after

        log_target = request.get("rule_id") or request.get("source_id")
        document = devcenter._change(request, action, log_target, mutate)
        return {"revision": document["revision"], **reply}


def _replace(target: _Target, rule: dict[str, Any]) -> None:
    rules = [item for item in target.stored if item["rule_id"] != rule["rule_id"]]
    rules.append(rule)
    target.rule_set["rules"] = sorted(rules, key=lambda item: item["rule_id"])


def confirm(devcenter: Any, request: Mapping[str, Any]) -> dict[str, Any]:
    def work(target: _Target) -> tuple[Any, Any, dict[str, Any]]:
        rule, _ = _find(target, request["rule_id"])
        if rule["status"] == CONFIRMED:
            raise not_allowed("The rule is already confirmed.", "already_confirmed", rule_id=rule["rule_id"])
        changed = {**copy.deepcopy(rule), "status": CONFIRMED}
        _replace(target, changed)
        return rule, changed, {"rule": rule_view(changed, target.objects)}

    return _change(devcenter, request, "naming_rule_confirm", work)


def reject(devcenter: Any, request: Mapping[str, Any]) -> dict[str, Any]:
    """UC16: reject of a user rule removes it; reject of a detected rule keeps it as rejected."""

    def work(target: _Target) -> tuple[Any, Any, dict[str, Any]]:
        rule, _ = _find(target, request["rule_id"])
        if rule["origin"] == ORIGIN_USER:
            target.rule_set["rules"] = [item for item in target.stored if item["rule_id"] != rule["rule_id"]]
            return rule, None, {"rule_id": rule["rule_id"], "removed": True, "rule": None}
        if rule["status"] == REJECTED:
            raise not_allowed("The rule is already rejected.", "already_rejected", rule_id=rule["rule_id"])
        changed = {**copy.deepcopy(rule), "status": REJECTED}
        _replace(target, changed)
        return rule, changed, {"rule_id": rule["rule_id"], "removed": False, "rule": rule_view(changed, target.objects)}

    return _change(devcenter, request, "naming_rule_reject", work)


def _duplicate(target: _Target, rule: Mapping[str, Any]) -> None:
    """UC34: refuse a rule with the same object type, scope, and check kind as a rule that is not rejected."""

    key = identity_key(rule)
    for other in target.all_rules():
        if other["rule_id"] != rule["rule_id"] and other["status"] != REJECTED and identity_key(other) == key:
            raise not_allowed("The same rule exists.", "duplicate_rule", existing_rule_id=other["rule_id"])


def edit(devcenter: Any, request: Mapping[str, Any]) -> dict[str, Any]:
    """UC16: edit with no rule ID creates a confirmed user rule; edit of a proposed rule confirms it."""

    def work(target: _Target) -> tuple[Any, Any, dict[str, Any]]:
        rule_id = request.get("rule_id")
        if rule_id is None:
            before = None
            used = [rule["rule_id"] for rule in target.all_rules()]
            changed = make_rule("", request["object_type"], request.get("scope"), request["check"], ORIGIN_USER, CONFIRMED)
            changed["rule_id"] = rule_id_for(["user", list(signature(changed))], used)
        else:
            before, _ = _find(target, rule_id)
            changed = make_rule(rule_id, request["object_type"], request.get("scope"), request["check"], before["origin"],
                                CONFIRMED, before.get("copied_from"))
        validate_rule(changed)
        _duplicate(target, changed)
        _replace(target, changed)
        return before, changed, {"rule": rule_view(changed, target.objects)}

    return _change(devcenter, request, "naming_rule_edit", work)


def copy_rules(devcenter: Any, request: Mapping[str, Any]) -> dict[str, Any]:
    """Copy the rule set of a different session model. The copied rules arrive as "proposed"."""

    def work(target: _Target) -> tuple[Any, Any, dict[str, Any]]:
        document = devcenter._require_open().document
        record = devcenter._source(document, request["source_id"])
        if record["source_id"] == target.record["source_id"]:
            raise not_allowed("Select a model that is not the target.", "same_model")
        if _model_source(devcenter, record) is None:
            raise not_allowed("The app cannot read the model of this source.", "source_unreadable", source_id=record["source_id"])
        rejected = {signature(rule) for rule in target.stored if rule["status"] == REJECTED}
        used = [rule["rule_id"] for rule in target.all_rules()]
        copied: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        for rule in sorted(_source_rules(devcenter, record), key=_sort_key):
            existing = next((other for other in target.all_rules()
                             if other["status"] != REJECTED and identity_key(other) == identity_key(rule)), None)
            if existing is not None:
                skipped.append({"rule_id": rule["rule_id"], "reason": "duplicate_rule", "existing_rule_id": existing["rule_id"]})
                continue
            if signature(rule) in rejected:
                skipped.append({"rule_id": rule["rule_id"], "reason": "rejected_rule", "existing_rule_id": None})
                continue
            new = make_rule("", rule["object_type"], rule["scope"], rule["check"], rule["origin"], PROPOSED, record["display_name"])
            new["rule_id"] = rule_id_for(["copy", list(signature(new))], used)
            used.append(new["rule_id"])
            _replace(target, new)
            copied.append(new)
        after = {"source_id": record["source_id"], "copied": [rule["rule_id"] for rule in copied]}
        return None, after, {"copied": [rule_view(rule, target.objects) for rule in copied], "skipped": skipped}

    return _change(devcenter, request, "naming_rules_copy", work)
