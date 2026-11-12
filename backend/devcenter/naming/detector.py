"""Rule detection from the target model (technical design section 5).

The detector offers a rule only when its scope has at least ``min_objects``
objects and at least ``min_support`` of them obey the rule. Both limits are
settings. The detector is a pure function: the same objects and settings give
the same rules with the same rule IDs.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any
from collections.abc import Iterable, Mapping

from backend.devcenter.naming.objects import COLUMN_TYPES, FORMAT_KINDS, MEASURE, RULE_OBJECT_TYPES, NamedObject
from backend.devcenter.naming.rules import (
    FOLDER_BY_TYPE,
    LETTER_CASE,
    ORIGIN_DETECTED,
    PREFIX,
    PROPOSED,
    SEPARATOR,
    SUFFIX,
    UNIT_WORD,
    make_rule,
    rule_id_for,
    signature,
    support,
)
from backend.devcenter.naming.tokens import CASE_STYLES, SEPARATOR_CHARS, SEPARATORS, separator_chunks, used_separators, words

DEFAULT_MIN_OBJECTS = 5
DEFAULT_MIN_SUPPORT = 0.8


@dataclass(frozen=True)
class NamingSettings:
    """The detection limits (settings, not fixed code)."""

    min_objects: int = DEFAULT_MIN_OBJECTS
    min_support: float = DEFAULT_MIN_SUPPORT

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> NamingSettings:
        value = value or {}
        objects = value.get("min_objects", DEFAULT_MIN_OBJECTS)
        ratio = value.get("min_support", DEFAULT_MIN_SUPPORT)
        if isinstance(objects, bool) or not isinstance(objects, int) or objects < 1:
            objects = DEFAULT_MIN_OBJECTS
        if isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or not 0 < ratio <= 1:
            ratio = DEFAULT_MIN_SUPPORT
        return cls(objects, float(ratio))

    def view(self) -> dict[str, Any]:
        return {"min_objects": self.min_objects, "min_support": self.min_support}

    def passes(self, count: int, total: int) -> bool:
        # Integer compare: 80 of 100 passes 0.8, 79 of 100 does not.
        return total >= self.min_objects and count * 1000 >= round(self.min_support * 1000) * total


def detected_rule_id(rule: Mapping[str, Any]) -> str:
    return rule_id_for(["detected", list(signature(rule))])


def _prefix(name: str) -> str | None:
    """The first word and the separator after it, or the first case token of a name with no separator."""

    if used_separators(name):
        for index, char in enumerate(name):
            if char in SEPARATOR_CHARS:
                return name[: index + 1] if index > 0 else None
        return None
    parts = words(name)
    return parts[0] if len(parts) > 1 else None


def _suffix(name: str) -> str | None:
    if used_separators(name):
        for index in range(len(name) - 1, -1, -1):
            if name[index] in SEPARATOR_CHARS:
                return name[index:] if index < len(name) - 1 else None
        return None
    parts = words(name)
    return parts[-1] if len(parts) > 1 else None


def _last_word(name: str) -> str | None:
    chunks = separator_chunks(name)
    return chunks[-1] if chunks else None


class _Collector:
    def __init__(self, objects: list[NamedObject], settings: NamingSettings) -> None:
        self.objects = objects
        self.settings = settings
        self.rules: list[dict[str, Any]] = []

    def offer(self, object_type: str, scope: Mapping[str, Any], check: Mapping[str, Any]) -> bool:
        rule = make_rule("", object_type, scope, check, ORIGIN_DETECTED, PROPOSED)
        found = support(rule, self.objects)
        if not self.settings.passes(found["count"], found["total"]):
            return False
        rule["rule_id"] = detected_rule_id(rule)
        self.rules.append(rule)
        return True

    def best(self, object_type: str, scope: Mapping[str, Any], kind: str, candidates: Iterable[Any], **extra: Any) -> None:
        """Offer the candidate with the most support, in candidate order for a tie."""

        scored = []
        for position, value in enumerate(candidates):
            rule = make_rule("", object_type, scope, {"kind": kind, "value": value, **extra}, ORIGIN_DETECTED, PROPOSED)
            found = support(rule, self.objects)
            if self.settings.passes(found["count"], found["total"]):
                scored.append((-found["count"], position, value))
        if scored:
            self.offer(object_type, scope, {"kind": kind, "value": sorted(scored)[0][2], **extra})


def _common(values: Iterable[str | None]) -> list[str]:
    counts = Counter(value for value in values if value)
    return [value for value, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]


def detect(objects: Iterable[NamedObject], settings: NamingSettings | None = None) -> list[dict[str, Any]]:
    """Give the detected rules (status proposed), sorted by rule ID."""

    settings = settings or NamingSettings()
    items = [item for item in objects if item.object_type in RULE_OBJECT_TYPES]
    collector = _Collector(items, settings)
    for object_type in RULE_OBJECT_TYPES:
        group = [item for item in items if item.object_type == object_type]
        if len(group) < settings.min_objects:
            continue
        names = [item.name for item in group]
        model: dict[str, Any] = {}
        collector.best(object_type, model, LETTER_CASE, CASE_STYLES)
        multi = [name for name in names if len(words(name)) > 1]
        used = {"space": any(" " in name for name in multi), "underscore": any("_" in name for name in multi),
                "none": any(not used_separators(name) for name in multi)}
        collector.best(object_type, model, SEPARATOR, [value for value in SEPARATORS if used[value]])
        collector.best(object_type, model, PREFIX, _common(_prefix(name) for name in names)[:3])
        collector.best(object_type, model, SUFFIX, _common(_suffix(name) for name in names)[:3])
        if object_type == MEASURE or object_type in COLUMN_TYPES:
            for kind in FORMAT_KINDS:
                scoped = [item for item in group if item.format_kind == kind]
                collector.best(object_type, {"format_kind": kind}, UNIT_WORD, _common(_last_word(item.name) for item in scoped)[:3])
        if object_type == MEASURE:
            # Folder rules are for measures only: no folder rules for columns.
            collector.best(object_type, model, FOLDER_BY_TYPE, _common(item.table for item in group)[:3], folder="table")
            for prefix in _common(_prefix(name) for name in names):
                scoped = [item for item in group if item.name.startswith(prefix)]
                if len(scoped) < settings.min_objects:
                    continue
                collector.best(object_type, {"name_prefix": prefix}, FOLDER_BY_TYPE,
                               _common(item.display_folder for item in scoped)[:3], folder="display_folder")
    return sorted(collector.rules, key=lambda rule: rule["rule_id"])

