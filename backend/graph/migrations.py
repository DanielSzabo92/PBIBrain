"""Schema bootstrap and forward migration, kept separate from graph business logic."""

from __future__ import annotations

from typing import Any
from collections.abc import Callable, Mapping

from .schema import GRAPH_SCHEMA_VERSION


def _version_1_to_2(payload: dict[str, Any]) -> dict[str, Any]:
    # Version 2 only adds node types. The node and edge records of version 1
    # stay valid. A rescan adds the new nodes.
    return payload


# Each step changes a payload of version N into a payload of version N + 1.
MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {1: _version_1_to_2}


def payload_version(payload: Mapping[str, Any]) -> int:
    # A graph file without a version is a version 1 file.
    value = payload.get("schema_version", 1)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("The graph file has an incorrect schema version")
    return value


def migrate_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Move a stored graph payload forward to GRAPH_SCHEMA_VERSION.

    A payload from a newer version stops the load, because an old app must
    not write over data that it cannot read.
    """

    result = dict(payload)
    version = payload_version(result)
    if version > GRAPH_SCHEMA_VERSION:
        raise ValueError(f"The graph file has schema version {version}. This app reads version {GRAPH_SCHEMA_VERSION} or older")
    while version < GRAPH_SCHEMA_VERSION:
        result = MIGRATIONS[version](result)
        version += 1
    result["schema_version"] = version
    return result
