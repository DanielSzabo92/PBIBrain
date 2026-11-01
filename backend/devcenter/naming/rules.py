"""The shape of a Naming Rule and the rule checker (technical design section 5).

A rule has a rule ID, an object type, a scope (optional table, display
folder, format kind, and name prefix filters), one check, an origin
(``detected`` or ``user``), and a status (``proposed``, ``confirmed``, or
``rejected``). Only a confirmed rule marks a name. A user rule is confirmed
when the user makes it.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable, Mapping

from backend.devcenter.errors import DevCenterError
from backend.devcenter.naming.objects import NamedObject, rule_type
from backend.devcenter.naming.tokens import CASE_TEXT, SEPARATOR_VALUES, is_case, used_separators

PREFIX = "prefix"
SUFFIX = "suffix"
LETTER_CASE = "letter_case"
SEPARATOR = "separator"
UNIT_WORD = "unit_word"
FOLDER_BY_TYPE = "folder_by_type"
REGEX = "regex"
CHECK_KINDS = (PREFIX, SUFFIX, LETTER_CASE, SEPARATOR, UNIT_WORD, FOLDER_BY_TYPE, REGEX)

ORIGIN_DETECTED = "detected"
ORIGIN_USER = "user"
PROPOSED = "proposed"
CONFIRMED = "confirmed"
REJECTED = "rejected"

SCOPE_KEYS = ("table", "display_folder", "format_kind", "name_prefix")

_LABELS = {
    "table": ("Table", "Tables"),
    "data_column": ("Data column", "Data columns"),
    "calculated_column": ("Calculated column", "Calculated columns"),
    "calculated_table": ("Calculated table", "Calculated tables"),
    "measure": ("Measure", "Measures"),
    "hierarchy": ("Hierarchy", "Hierarchies"),
    "calculation_group": ("Calculation group", "Calculation groups"),
}
_FORMAT_WORDS = {"percent": "Percent", "currency": "Currency"}
_SEPARATOR_TEXT = {"space": "a space between words", "underscore": "an underscore between words", "none": "no separator between words"}


def normal_scope(scope: Mapping[str, Any] | None) -> dict[str, Any]:
    scope = scope or {}
    return {key: (scope.get(key) if scope.get(key) not in ("", None) else None) for key in SCOPE_KEYS}


def normal_check(check: Mapping[str, Any]) -> dict[str, Any]:
    result = {"kind": check["kind"], "value": check["value"]}
    if check["kind"] == FOLDER_BY_TYPE:
        result["folder"] = check.get("folder") or "display_folder"
    return result


def make_rule(rule_id: str, object_type: str, scope: Mapping[str, Any] | None, check: Mapping[str, Any],
              origin: str, status: str, copied_from: str | None = None) -> dict[str, Any]:
    return {
        "rule_id": rule_id,
        "object_type": object_type,
        "scope": normal_scope(scope),
        "check": normal_check(check),
        "origin": origin,
        "status": status,
        "copied_from": copied_from,
    }


def identity_key(rule: Mapping[str, Any]) -> tuple[Any, ...]:
    """Two rules with the same object type, scope, and check kind are the same rule (UC34)."""

    scope = normal_scope(rule.get("scope"))
    return (rule["object_type"], tuple(scope[key] for key in SCOPE_KEYS), rule["check"]["kind"])


def signature(rule: Mapping[str, Any]) -> tuple[Any, ...]:
    """The identity key plus the check value. A rejected rule is matched by its signature."""

    check = normal_check(rule["check"])
    return identity_key(rule) + (check["value"], check.get("folder"))


def rule_id_for(seed: Any, used: Iterable[str] = ()) -> str:
    """A stable rule ID from a seed. A number goes after the seed when the ID is in use."""

    taken = set(used)
    number = 0
    while True:
        data = json.dumps([seed, number], ensure_ascii=False, sort_keys=True).encode("utf-8")
        candidate = "nr-" + hashlib.sha256(data).hexdigest()[:12]
        if candidate not in taken:
            return candidate
        number += 1


def validate_rule(rule: Mapping[str, Any]) -> None:
    """Check the values that the JSON Schema cannot check. Raise ``invalid_payload``."""

    check = rule["check"]
    if check["kind"] == REGEX:
        try:
            re.compile(check["value"])
        except re.error as exc:
            raise DevCenterError("invalid_payload", "The regular expression is not valid.", {"reason": "invalid_regex", "position": exc.pos}) from exc
        if rule["origin"] != ORIGIN_USER:
            raise DevCenterError("action_not_allowed", "Only a user rule can use a regular expression.",
                                 {"reason": "regex_user_only"})
    elif check["kind"] == LETTER_CASE and check["value"] not in CASE_TEXT:
        raise DevCenterError("invalid_payload", "The letter case is not valid.", {"reason": "invalid_letter_case"})
    elif check["kind"] == SEPARATOR and check["value"] not in SEPARATOR_VALUES:
        raise DevCenterError("invalid_payload", "The separator is not valid.", {"reason": "invalid_separator"})
    elif check["kind"] == UNIT_WORD and normal_scope(rule.get("scope"))["format_kind"] is None:
        raise DevCenterError("invalid_payload", "A unit word rule needs a format kind in its scope.", {"reason": "format_kind_required"})
    elif not str(check["value"]):
        raise DevCenterError("invalid_payload", "The rule needs a value.", {"reason": "value_required"})


def in_scope(rule: Mapping[str, Any], item: NamedObject) -> bool:
    """Give True when the rule applies to the object."""

    if rule_type(item.object_type) != rule["object_type"]:
        return False
    scope = normal_scope(rule.get("scope"))
    if scope["table"] is not None and item.table != scope["table"]:
        return False
    if scope["display_folder"] is not None and item.display_folder != scope["display_folder"]:
        return False
    if scope["format_kind"] is not None and item.format_kind != scope["format_kind"]:
        return False
    if scope["name_prefix"] is not None and not item.name.startswith(scope["name_prefix"]):
        return False
    return True


def obeys(rule: Mapping[str, Any], item: NamedObject) -> bool:
    """Give True when the object obeys the check of the rule. Call ``in_scope`` first."""

    check = rule["check"]
    kind, value, name = check["kind"], check["value"], item.name
    if kind == PREFIX:
        return name.startswith(value)
    if kind in {SUFFIX, UNIT_WORD}:
        return name.endswith(value)
    if kind == LETTER_CASE:
        return is_case(name, value)
    if kind == SEPARATOR:
        allowed = {SEPARATOR_VALUES[value]} - {""}
        return used_separators(name) <= allowed
    if kind == FOLDER_BY_TYPE:
        found = item.table if check.get("folder") == "table" else item.display_folder
        return found == value
    if kind == REGEX:
        try:
            return re.fullmatch(value, name) is not None
        except re.error:
            return False
    raise ValueError(f"Unknown check kind: {kind}")


def support(rule: Mapping[str, Any], objects: Iterable[NamedObject]) -> dict[str, int]:
    """The objects in scope (total) and the objects that obey the rule (count)."""

    scoped = [item for item in objects if in_scope(rule, item)]
    count = sum(1 for item in scoped if obeys(rule, item))
    return {"count": count, "total": len(scoped)}


def _quoted(value: str) -> str:
    return f'"{value}"'


def rule_text(rule: Mapping[str, Any]) -> str:
    """One plain sentence for the rule."""

    single, plural = _LABELS[rule["object_type"]]
    scope = normal_scope(rule.get("scope"))
    check = rule["check"]
    kind, value = check["kind"], check["value"]
    subject = plural
    if scope["format_kind"] is not None:
        subject = f"{_FORMAT_WORDS[scope['format_kind']]} {plural.lower()}"
    names = f"{single} names" if subject == plural else f"The names of {subject.lower()}"
    if kind == PREFIX:
        text = f"{names} start with {_quoted(value)}"
    elif kind == SUFFIX:
        text = f"{names} end with {_quoted(value)}"
    elif kind == UNIT_WORD:
        text = f"{subject} end with the unit word {_quoted(value)}"
    elif kind == LETTER_CASE:
        text = f"{names} use {CASE_TEXT[value]}"
    elif kind == SEPARATOR:
        text = f"{names} use {_SEPARATOR_TEXT[value]}"
    elif kind == FOLDER_BY_TYPE:
        place = "the table" if check.get("folder") == "table" else "the display folder"
        text = f"{subject} are in {place} {_quoted(value)}"
    else:
        text = f"{names} match the pattern {_quoted(value)}"
    filters = []
    if scope["name_prefix"] is not None:
        filters.append(f"with the prefix {_quoted(scope['name_prefix'])}")
    if scope["table"] is not None:
        filters.append(f"in the table {_quoted(scope['table'])}")
    if scope["display_folder"] is not None:
        filters.append(f"in the display folder {_quoted(scope['display_folder'])}")
    if filters:
        text += " (" + ", ".join(filters) + ")"
    return text + "."


def is_active(rule: Mapping[str, Any]) -> bool:
    """Only a confirmed rule marks a name. A user rule is confirmed when the user makes it."""

    return rule["status"] == CONFIRMED
