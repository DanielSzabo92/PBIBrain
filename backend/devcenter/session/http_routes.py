"""HTTP read routes for session log inspection (technical design section 14.1, UC8)."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from backend.devcenter.http_routes import route


@route("GET", "log", contract="http/log.reply.json")
def get_log(devcenter: Any, query: Mapping[str, Sequence[str]], body: Any) -> Mapping[str, Any]:
    return devcenter.session_log(query)
