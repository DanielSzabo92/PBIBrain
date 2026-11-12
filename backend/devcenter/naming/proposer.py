"""Deterministic name proposer and name check (technical design section 5).

The proposer applies the confirmed rules in a fixed order: letter case,
separator, prefix, suffix and unit word, folder. For a name clash it adds the
donor source name in parentheses and checks the result again. The output is
the name and the IDs of the rules that it used.

The clash check is built in and compares names case-insensitively.
"""

from __future__ import annotations

from typing import Any
from collections.abc import Iterable, Mapping

from backend.devcenter.naming.objects import (
    COLUMN_TYPES,
    HIERARCHY,
    MEASURE,
    REPORT_MEASURE,
    TABLE_TYPES,
    NamedObject,
    rule_type,
)
from backend.devcenter.naming.rules import (
    FOLDER_BY_TYPE,
    LETTER_CASE,
    PREFIX,
    SCOPE_KEYS,
    SEPARATOR,
    SUFFIX,
    UNIT_WORD,
    in_scope,
    is_active,
    normal_scope,
    obeys,
    rule_text,
)
from backend.devcenter.naming.tokens import SEPARATOR_CHARS, SEPARATOR_VALUES, main_separator, render, words

# The fixed order of the proposer.
ORDER = (LETTER_CASE, SEPARATOR, PREFIX, SUFFIX, UNIT_WORD, FOLDER_BY_TYPE)
MAX_CLASH_TRIES = 100


def _specific_first(rule: Mapping[str, Any]) -> tuple[int, str]:
    scope = normal_scope(rule.get("scope"))
    return (-sum(1 for key in SCOPE_KEYS if scope[key] is not None), rule["rule_id"])


def _pick(rules: Iterable[Mapping[str, Any]], kind: str, item: NamedObject) -> Mapping[str, Any] | None:
    """The most specific active rule of one check kind that applies to the object."""

    found = sorted((rule for rule in rules if is_active(rule) and rule["check"]["kind"] == kind and in_scope(rule, item)),
                   key=_specific_first)
    return found[0] if found else None


def _strip_start(name: str, value: str) -> str:
    return name[len(value):] if value and name.casefold().startswith(value.casefold()) else name


def _strip_end(name: str, value: str) -> str:
    return name[: len(name) - len(value)] if value and name.casefold().endswith(value.casefold()) else name


def _item(name: str, object_type: str, context: Mapping[str, Any]) -> NamedObject:
    return NamedObject(object_type, name, context.get("table"), context.get("display_folder"), context.get("format_kind"))


def clash_with(name: str, object_type: str, table: str | None, existing: Iterable[NamedObject]) -> NamedObject | None:
    """The object that has the same name (case-insensitive) in the same name space, or None."""

    folded = name.casefold()
    for item in existing:
        if item.name.casefold() != folded:
            continue
        if object_type in TABLE_TYPES:
            if item.object_type in TABLE_TYPES:
                return item
        elif object_type in (MEASURE, REPORT_MEASURE):
            if item.object_type in (MEASURE, REPORT_MEASURE):
                return item
            if table is not None and item.object_type in COLUMN_TYPES and item.table == table:
                return item
        elif object_type in COLUMN_TYPES:
            same_table = table is None or item.table == table
            if same_table and (item.object_type in COLUMN_TYPES or (table is not None and item.object_type == MEASURE)):
                return item
        elif object_type == HIERARCHY:
            if item.object_type == HIERARCHY and (table is None or item.table == table):
                return item
    return None


def breaks(name: str, object_type: str, context: Mapping[str, Any], rules: Iterable[Mapping[str, Any]]) -> list[dict[str, str]]:
    """The confirmed rules that the name breaks. A folder rule counts only when the location is given."""

    item = _item(name, object_type, context)
    found = []
    for rule in sorted(rules, key=lambda value: value["rule_id"]):
        if not is_active(rule) or rule["object_type"] != rule_type(object_type) or not in_scope(rule, item):
            continue
        check = rule["check"]
        if check["kind"] == FOLDER_BY_TYPE and context.get("table" if check.get("folder") == "table" else "display_folder") is None:
            continue
        if not obeys(rule, item):
            found.append({"rule_id": rule["rule_id"], "text": rule_text(rule)})
    return found


def _join_word(name: str, word: str, separator: str | None) -> str:
    if not name or word[:1] in SEPARATOR_CHARS:
        return name + word
    value = SEPARATOR_VALUES[separator] if separator is not None else SEPARATOR_VALUES.get(main_separator(name), " ")
    return name + (value if value or separator == "none" else " ") + word


def propose(name: str, object_type: str, context: Mapping[str, Any], rules: Iterable[Mapping[str, Any]],
            existing: Iterable[NamedObject], donor_name: str | None = None) -> dict[str, Any]:
    """Give ``{name, rule_ids, table, display_folder, clash}``.

    ``context`` has the optional keys ``table``, ``display_folder``, and
    ``format_kind`` of the new object. ``clash`` is the object that the first
    proposal had the same name as (before the donor name was added), or None.
    """

    rules = list(rules)
    existing = list(existing)
    used: list[str] = []
    core = name.strip()
    item = _item(core, object_type, context)
    picked = {kind: _pick(rules, kind, item) for kind in (LETTER_CASE, SEPARATOR, PREFIX, SUFFIX, UNIT_WORD)}
    if picked[PREFIX] is not None:
        core = _strip_start(core, picked[PREFIX]["check"]["value"])
    for kind in (SUFFIX, UNIT_WORD):
        if picked[kind] is not None:
            core = _strip_end(core, picked[kind]["check"]["value"])
    core = core.strip("".join(SEPARATOR_CHARS)) or core
    style = picked[LETTER_CASE]["check"]["value"] if picked[LETTER_CASE] else None
    separator = picked[SEPARATOR]["check"]["value"] if picked[SEPARATOR] else None
    core = render(words(core), style, separator, core)
    for kind in (LETTER_CASE, SEPARATOR):
        if picked[kind] is not None:
            used.append(picked[kind]["rule_id"])
    if picked[PREFIX] is not None:
        core = picked[PREFIX]["check"]["value"] + core
        used.append(picked[PREFIX]["rule_id"])
    if picked[SUFFIX] is not None:
        core = core + picked[SUFFIX]["check"]["value"]
        used.append(picked[SUFFIX]["rule_id"])
    if picked[UNIT_WORD] is not None:
        core = _join_word(core, picked[UNIT_WORD]["check"]["value"], separator)
        used.append(picked[UNIT_WORD]["rule_id"])
    location = {"table": context.get("table"), "display_folder": context.get("display_folder")}
    placed: set[str] = set()
    final = _item(core, object_type, context)
    for folder_rule in sorted((rule for rule in rules if is_active(rule) and rule["check"]["kind"] == FOLDER_BY_TYPE
                               and in_scope(rule, final)), key=_specific_first):
        field = "table" if folder_rule["check"].get("folder") == "table" else "display_folder"
        if field not in placed:
            location[field] = folder_rule["check"]["value"]
            placed.add(field)
            used.append(folder_rule["rule_id"])
    table, display_folder = location["table"], location["display_folder"]
    first_clash = clash_with(core, object_type, table, existing)
    proposed = core
    if first_clash is not None:
        label = (donor_name or "").strip()
        for number in range(1, MAX_CLASH_TRIES + 1):
            if label:
                suffix = label if number == 1 else f"{label} {number}"
            else:
                suffix = str(number + 1)
            proposed = f"{core} ({suffix})"
            if clash_with(proposed, object_type, table, existing) is None:
                break
    return {
        "name": proposed,
        "rule_ids": used,
        "table": table,
        "display_folder": display_folder,
        "clash": first_clash.view() if first_clash is not None else None,
    }
