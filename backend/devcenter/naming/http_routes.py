"""HTTP read routes of build step S4: ``GET naming-rules`` and ``POST name-propose`` (section 14.1).

``POST name-propose`` is a read-only calculation with a request body. It
changes no session state and no file.
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from backend.devcenter.errors import DevCenterError
from backend.devcenter.http_routes import route
from backend.devcenter.naming import service


def _json(body: Any) -> Any:
    if isinstance(body, Mapping):
        return dict(body)
    if body in (None, b"", ""):
        return {}
    try:
        return json.loads(body.decode("utf-8") if isinstance(body, bytes) else body)
    except (UnicodeDecodeError, ValueError) as exc:
        raise DevCenterError("invalid_payload", "The request body is not valid JSON.", {"reason": "invalid_json"}) from exc


@route("GET", "naming-rules", contract="http/naming-rules.reply.json")
def get_naming_rules(devcenter: Any, query: Mapping[str, Sequence[str]], body: Any) -> Mapping[str, Any]:
    return service.rules_view(devcenter)


@route("POST", "name-propose", contract="http/name-propose.reply.json")
def post_name_propose(devcenter: Any, query: Mapping[str, Sequence[str]], body: Any) -> Mapping[str, Any]:
    return service.name_propose(devcenter, _json(body))
