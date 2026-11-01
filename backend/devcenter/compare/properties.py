"""The properties that count for each object type, and their phrase IDs (technical design section 4.2).

Each property has one fixed phrase ID (``<property>_changed``). The text of
each phrase ID is in ``backend/devcenter/contracts/phrases.json`` (UC31).
"""

from __future__ import annotations

from typing import Any

from backend.devcenter.compare.extract import CompareObject
from backend.devcenter.compare.normalize import NO_RENAMES, RenameMap, dax_equal, exact_text
from backend.snapshots.manifest import canonical_json

DAX = "dax"
TEXT = "text"
VALUE = "value"
JSON = "json"
DAX_MAP = "dax_map"

_MEASURE = (("expression", DAX), ("format_string", TEXT), ("format_string_expression", DAX), ("display_folder", TEXT),
            ("description", TEXT), ("hidden", VALUE), ("data_category", VALUE))
_DATA_COLUMN = (("data_type", VALUE), ("source_column", VALUE), ("format_string", TEXT), ("display_folder", TEXT),
                ("description", TEXT), ("hidden", VALUE), ("summarize_by", VALUE), ("sort_by_column", VALUE),
                ("data_category", VALUE), ("key", VALUE))
_TABLE = (("description", TEXT), ("hidden", VALUE), ("data_category", VALUE))

PROPERTIES: dict[str, tuple[tuple[str, str], ...]] = {
    "measure": _MEASURE,
    "data_column": _DATA_COLUMN,
    "calculated_column": _DATA_COLUMN + (("expression", DAX),),
    "table": _TABLE,
    "calculation_group": _TABLE,
    "calculated_table": _TABLE + (("expression", DAX),),
    "relationship": (("cardinality", VALUE), ("cross_filter_direction", VALUE), ("active", VALUE),
                     ("security_filter_direction", VALUE), ("referential_integrity", VALUE)),
    "hierarchy": (("levels", JSON), ("display_folder", TEXT), ("description", TEXT), ("hidden", VALUE)),
    "role": (("model_permission", VALUE), ("role_filters", DAX_MAP), ("ols", JSON)),
    "partition": (("mode", VALUE), ("m_text", TEXT), ("partition_source", JSON)),
    "calculation_item": (("expression", DAX), ("order", VALUE), ("format_string_expression", DAX)),
    "expression": (("m_text", TEXT), ("expression_kind", VALUE)),
    "function": (("expression", DAX), ("description", TEXT), ("hidden", VALUE)),
    "report_measure": (("expression", DAX), ("format_string", TEXT), ("display_folder", TEXT)),
    "page": (("display_name", VALUE), ("page_size", JSON), ("filters", JSON), ("formatting", JSON)),
    "visual": (("position", JSON), ("visual_type", VALUE), ("fields", JSON), ("filters", JSON), ("formatting", JSON)),
    "visual_group": (("position", JSON), ("visual_type", VALUE), ("fields", JSON), ("filters", JSON), ("formatting", JSON)),
}
# Strict compare also compares these (annotations, lineageTags, and other metadata such as changedProperty lines).
STRICT_PROPERTIES = (("annotations", JSON), ("lineage_tag", VALUE), ("metadata", JSON))

PROPERTY_IDS = tuple(sorted({prop for spec in PROPERTIES.values() for prop, _ in spec} | {prop for prop, _ in STRICT_PROPERTIES}))
PROPERTY_PHRASE_IDS = tuple(f"{prop}_changed" for prop in PROPERTY_IDS)

# A value longer than this, or with a line break, shows only the phrase.
SHORT_VALUE = 40


def _short(value: Any, kind: str) -> bool:
    if kind in {DAX, DAX_MAP}:
        return False
    if value is None or isinstance(value, (bool, int, float)):
        return True
    if isinstance(value, str):
        return len(value) <= SHORT_VALUE and "\n" not in value
    return False


def _equal(kind: str, target: Any, donor: Any, *, strict: bool, renames: RenameMap) -> tuple[bool, bool]:
    """Give (equal, equal only through the rename map)."""

    if kind == DAX:
        return dax_equal(target, donor, strict=strict, renames=renames)
    if kind == TEXT:
        return exact_text(target, strict=strict) == exact_text(donor, strict=strict), False
    if kind == DAX_MAP:
        target, donor = dict(target or {}), dict(donor or {})
        if set(target) != set(donor):
            return False, False
        results = [dax_equal(target[key], donor[key], strict=strict, renames=renames) for key in sorted(target)]
        return all(equal for equal, _ in results), any(through for _, through in results) and all(equal for equal, _ in results)
    return canonical_json(target) == canonical_json(donor), False


def compare_properties(target: CompareObject, donor: CompareObject, *, strict: bool,
                       renames: RenameMap = NO_RENAMES) -> tuple[list[dict[str, Any]], bool]:
    """Compare the properties that count. Give the phrases and True when a value is equal only after rename."""

    spec = PROPERTIES.get(target.subtype, ())
    phrases: list[dict[str, Any]] = []
    after_rename = False
    checks = [(prop, kind, target.props, donor.props) for prop, kind in spec]
    if strict:
        checks += [(prop, kind, target.strict_props, donor.strict_props) for prop, kind in STRICT_PROPERTIES]
    for prop, kind, target_values, donor_values in checks:
        before, after = target_values.get(prop), donor_values.get(prop)
        equal, through = _equal(kind, before, after, strict=strict, renames=renames)
        if not equal:
            short = _short(before, kind) and _short(after, kind)
            phrases.append({"phrase_id": f"{prop}_changed", "property": prop,
                            "old": before if short else None, "new": after if short else None, "short": short})
        elif through:
            after_rename = True
    return phrases, after_rename
