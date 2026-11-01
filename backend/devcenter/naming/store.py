"""Naming rule files (technical design section 5).

Local target: ``<project root>/.pbibrain/naming-rules/<model folder name>.json``.
Cloud-only target: ``%APPDATA%/PBIBrain/naming-rules/<workspace ID>/<model ID>.json``.
The file is outside the model ``definition`` folder and outside the guard
scope. It is canonical JSON (sorted keys, 2-space indent, LF), so it moves
through git with the project.

The file keeps the rules that the user acted on: confirmed and rejected
detected rules, user rules, and copied rules. The detector gives the other
proposed rules again on each read.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from backend.devcenter.errors import DevCenterError
from backend.devcenter.naming.objects import RULE_OBJECT_TYPES
from backend.devcenter.naming.rules import (
    CHECK_KINDS,
    CONFIRMED,
    ORIGIN_DETECTED,
    ORIGIN_USER,
    PROPOSED,
    REJECTED,
    SCOPE_KEYS,
)
from backend.devcenter.session.secrets import check_secrets
from backend.devcenter.session.store import canonical_bytes, write_atomic
from backend.snapshots.manifest import content_hash

RULES_SCHEMA_VERSION = 1
RULES_DIR = "naming-rules"


def local_rule_file(project_root: Path, model_dir: Path) -> Path:
    return project_root / ".pbibrain" / RULES_DIR / f"{model_dir.name}.json"


def cloud_rule_file(app_data_dir: Path, workspace_id: str, model_id: str) -> Path:
    for part in (workspace_id, model_id):
        if not part or any(char in part for char in '\\/:*?"<>|') or part in {".", ".."}:
            raise DevCenterError("invalid_payload", "The cloud item ID is not valid.", {"reason": "invalid_item_id"})
    return app_data_dir / RULES_DIR / workspace_id / f"{model_id}.json"


def empty_rule_set(model: str) -> dict[str, Any]:
    return {"schema_version": RULES_SCHEMA_VERSION, "model": model, "settings": {}, "rules": []}


def read_rule_set(path: Path, model: str) -> dict[str, Any]:
    """Read a rule file. A missing file gives an empty rule set."""

    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return empty_rule_set(model)
    try:
        document = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise DevCenterError("action_not_allowed", "The naming rule file is not valid JSON.", {"reason": "rules_file_damaged"}) from exc
    if not isinstance(document, dict) or not isinstance(document.get("rules"), list):
        raise DevCenterError("action_not_allowed", "The naming rule file is not valid.", {"reason": "rules_file_damaged"})
    if not isinstance(document.get("schema_version"), int) or document["schema_version"] > RULES_SCHEMA_VERSION:
        raise DevCenterError("action_not_allowed", "The naming rule file is from a newer app version.", {"reason": "rules_file_newer"})
    if not all(_valid_rule(rule) for rule in document["rules"]) or not isinstance(document.get("settings", {}), dict):
        raise DevCenterError("action_not_allowed", "The naming rule file is not valid.", {"reason": "rules_file_damaged"})
    document.setdefault("settings", {})
    document.setdefault("model", model)
    return document


def _valid_rule(rule: Any) -> bool:
    """Check the shape of one stored rule. A hand edit can break it."""

    if not isinstance(rule, dict) or not isinstance(rule.get("rule_id"), str):
        return False
    check, scope = rule.get("check"), rule.get("scope", {})
    if not isinstance(check, dict) or check.get("kind") not in CHECK_KINDS or not isinstance(check.get("value"), str):
        return False
    if scope is not None and (not isinstance(scope, dict) or any(key not in SCOPE_KEYS for key in scope)):
        return False
    return (rule.get("object_type") in RULE_OBJECT_TYPES and rule.get("origin") in (ORIGIN_DETECTED, ORIGIN_USER)
            and rule.get("status") in (PROPOSED, CONFIRMED, REJECTED))


def _ordered(document: Mapping[str, Any]) -> dict[str, Any]:
    return {**document, "rules": sorted(document["rules"], key=lambda rule: rule["rule_id"])}


def rule_set_hash(document: Mapping[str, Any]) -> str:
    """The hash of the file bytes that ``write_rule_set`` writes for this rule set."""

    return content_hash(canonical_bytes(_ordered(document)))


def write_rule_set(path: Path, document: Mapping[str, Any]) -> str:
    """Write the rule file atomically. Give the hash of the rule set."""

    ordered = _ordered(document)
    check_secrets(ordered)
    write_atomic(path, canonical_bytes(ordered))
    return rule_set_hash(ordered)
