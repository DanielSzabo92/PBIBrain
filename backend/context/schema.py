"""Small JSON contract for context responses."""

from __future__ import annotations

from typing import Any, Mapping


CONTEXT_KEYS = (
    "target",
    "scope",
    "semantics",
    "relationships",
    "dependencies",
    "controls",
    "usage",
    "constraints",
    "evidence",
    "confidence",
    "warnings",
)

# This is intentionally descriptive.  Runtime validation below stays stdlib
# only and accepts extensible object/edge records.
CONTEXT_SCHEMA: dict[str, Any] = {
    "target": "object",
    "scope": {"model_ids": "string[]", "report_ids": "string[]"},
    "semantics": "assertion[]",
    "relationships": "edge[]",
    "dependencies": "object[]",
    "controls": "edge[]",
    "usage": "edge[]",
    "constraints": "edge[]",
    "evidence": "evidence[]",
    "confidence": "number map",
    "warnings": "warning[]",
}


def empty_context() -> dict[str, Any]:
    """Return a complete empty package with stable section names."""

    return {
        "target": {},
        "scope": {"model_ids": [], "report_ids": []},
        "semantics": [],
        "relationships": [],
        "dependencies": [],
        "controls": [],
        "usage": [],
        "constraints": [],
        "evidence": [],
        "confidence": {},
        "warnings": [],
    }


def validate_context(value: Mapping[str, Any]) -> list[str]:
    """Return contract errors; an empty list means the shape is valid."""

    if not isinstance(value, Mapping):
        return ["context must be an object"]
    errors = [f"missing section: {key}" for key in CONTEXT_KEYS if key not in value]
    scope = value.get("scope")
    if not isinstance(scope, Mapping):
        errors.append("scope must be an object")
    else:
        for key in ("model_ids", "report_ids"):
            if not isinstance(scope.get(key), list):
                errors.append(f"scope.{key} must be an array")
    for key in CONTEXT_KEYS[2:]:
        if key == "confidence":
            if not isinstance(value.get(key), Mapping):
                errors.append("confidence must be an object")
        elif key != "target" and not isinstance(value.get(key), list):
            errors.append(f"{key} must be an array")
    return errors


__all__ = ["CONTEXT_KEYS", "CONTEXT_SCHEMA", "empty_context", "validate_context"]
