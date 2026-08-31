"""Helpers that keep acceptance tests readable across record containers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from typing import Any, Iterable


def as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    for method_name in ("to_dict", "model_dump", "dict"):
        method = getattr(value, method_name, None)
        if callable(method):
            result = method()
            if isinstance(result, Mapping):
                return dict(result)
    if is_dataclass(value):
        return asdict(value)
    raise TypeError(f"Expected canonical record, got {type(value)!r}")


def records(value: Any, *keys: str) -> list[Any]:
    """Extract records from a list or a canonical model container."""

    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    if isinstance(value, Mapping):
        if "id" in value and "type" in value:
            return [value]
        for key in keys or ("nodes", "objects", "records", "items"):
            if key in value:
                return records(value[key])
    for key in keys or ("nodes", "objects", "records", "items"):
        child = getattr(value, key, None)
        if child is not None:
            return records(child)
    return [value]


def dictionaries(values: Iterable[Any]) -> list[dict[str, Any]]:
    return [as_mapping(value) for value in values]


def by_type(values: Iterable[Any]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for value in dictionaries(values):
        result.setdefault(str(value["type"]).upper(), []).append(value)
    return result

