"""Read the connection ID from a `connection.json` marker.

The marker key was `session_id` in old versions. The app now writes
`connection_id` only, because a "session" is a merge session in the
Development Center. The app still reads the old key.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

KEY = "connection_id"
OLD_KEY = "session_id"


def marker_connection_id(payload: Any) -> str | None:
    """Return the connection ID of a marker payload, or None if it has no ID."""
    if not isinstance(payload, Mapping):
        return None
    value = payload.get(KEY, payload.get(OLD_KEY))
    return value if isinstance(value, str) and value else None
