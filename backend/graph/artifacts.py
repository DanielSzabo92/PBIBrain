"""Presentation groups for canonical objects; ownership is never changed."""

from typing import Any, Mapping
from .schema import OBJECT_TYPES

REPORT_TYPES = frozenset({"REPORT", "PAGE", "VISUAL", "VISUAL_CALCULATION", "VISUAL_FILTER", "PAGE_FILTER", "REPORT_FILTER"})
MODEL_TYPES = frozenset({
    "MODEL", "TABLE", "COLUMN", "MEASURE", "RELATIONSHIP", "FIELD_PARAMETER",
    "SHARED_EXPRESSION", "USER_DEFINED_FUNCTION", "CALCULATION_GROUP", "CALCULATION_ITEM",
})


def artifact_group(node: Mapping[str, Any]) -> str:
    kind = node.get("type")
    if kind in REPORT_TYPES:
        return "report"
    if kind in MODEL_TYPES:
        return "model"
    if kind in OBJECT_TYPES or kind in {"ALIAS", "ROLE", "BEHAVIOR"}:
        return "other"
    # Report objects can carry BOTH IDs. Report ownership takes precedence.
    if node.get("report_id") or node.get("source") == "report_metadata":
        return "report"
    if node.get("model_id"):
        return "model"
    return "other"
