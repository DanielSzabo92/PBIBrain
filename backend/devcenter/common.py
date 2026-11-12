"""Helpers shared by the Development Center services."""

from __future__ import annotations

import copy
from typing import Any
from collections.abc import Mapping, Sequence


def query_value(query: Mapping[str, Sequence[str]], name: str) -> str | None:
    """The last value of a query parameter, or None when it is absent."""
    values = list(query.get(name) or [])
    return str(values[-1]) if values else None


def session_snapshot(devcenter: Any) -> dict[str, Any]:
    """A deep copy of the open session document, taken under the session lock."""
    with devcenter._lock:
        return copy.deepcopy(devcenter._require_open().document)
