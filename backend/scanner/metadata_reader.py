"""Source loading helpers kept at the Power BI adapter boundary."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


def load_metadata(source: Any) -> Any:
    """Load a mapping, JSON document, or simple API model object."""

    if isinstance(source, Mapping):
        return dict(source)
    if isinstance(source, (bytes, bytearray)):
        value = json.loads(bytes(source).decode("utf-8"))
        if isinstance(value, Mapping):
            return dict(value)
        if isinstance(value, list):
            return value
        raise TypeError("Metadata JSON root must be an object or array")
    if isinstance(source, Path):
        return _load_path(source)
    if isinstance(source, str):
        path = Path(source)
        if path.exists():
            return _load_path(path)
        value = json.loads(source)
        if isinstance(value, Mapping):
            return dict(value)
        if isinstance(value, list):
            return value
        raise TypeError("Metadata JSON root must be an object or array")
    for method_name in ("model_dump", "dict", "to_dict"):
        method = getattr(source, method_name, None)
        if callable(method):
            value = method()
            if isinstance(value, Mapping):
                return dict(value)
    if isinstance(source, (list, tuple)):
        return list(source)
    raise TypeError("Source must be a mapping, JSON path/text, or mapping-like object")


def _load_path(path: Path) -> Any:
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, list):
        return value
    raise TypeError(f"Metadata JSON root must be an object or array: {path}")


def pick(value: Any, *names: str, default: Any = None) -> Any:
    """Read common Power BI casing variants without adding source leakage."""

    if not isinstance(value, Mapping):
        return default
    available = {_key_name(str(key)): item for key, item in value.items()}
    for name in names:
        key = _key_name(name)
        if key in available:
            return available[key]
    return default


def key_name(value: str) -> str:
    return _key_name(value)


def _key_name(value: str) -> str:
    return "".join(char for char in value.casefold() if char.isalnum())


def collection(value: Any, *names: str) -> list[Any]:
    result: list[Any] = []
    seen_names: set[str] = set()
    for name in names:
        normalized_name = _key_name(name)
        if normalized_name in seen_names:
            continue
        seen_names.add(normalized_name)
        item = pick(value, name)
        if item is None:
            continue
        if isinstance(item, list):
            result.extend(item)
        elif isinstance(item, tuple):
            result.extend(item)
        elif isinstance(item, Mapping):
            # Some metadata APIs return a keyed object instead of an array.
            result.extend(item.values())
    return [item for item in result if item is not None]


def source_id(value: Any) -> str | None:
    item = pick(
        value,
        "source_id",
        "sourceId",
        "object_id",
        "objectId",
        "id",
        "guid",
        "lineage_tag",
        "lineageTag",
        "queryName",
    )
    if item is None or isinstance(item, (Mapping, list, tuple, dict)):
        return None
    text = str(item).strip()
    return text or None


def display_name(value: Any, default: str = "") -> str:
    item = pick(value, "name", "display_name", "displayName", "caption", "title", default=default)
    return default if item is None else str(item)


def description(value: Any) -> str | None:
    item = pick(value, "description", "display_description", "displayDescription", "comment")
    if item is None:
        return None
    return str(item)


def expression(value: Any) -> str | None:
    item = pick(value, "expression", "formula", "dax", "expressionText", "code")
    if item is None:
        return None
    if isinstance(item, (list, tuple)):
        return "\n".join(str(part) for part in item)
    return str(item)
