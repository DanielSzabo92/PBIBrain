"""HTTP read routes of build step S5: Change Plan and plan validation (technical design section 14.1).

``POST plan-validate`` is a read-only calculation with a request body (section 14.1).
It changes no session state and no file.
"""

from __future__ import annotations

from typing import Any
from collections.abc import Mapping, Sequence

from backend.devcenter.http_routes import READ, route
from backend.devcenter.plan import service
from backend.devcenter.http_routes import json_body as _json


@route("GET", "plan", contract="http/plan.reply.json")
def get_plan(devcenter: Any, query: Mapping[str, Sequence[str]], body: Any) -> Mapping[str, Any]:
    return service.get_plan(devcenter, query)


@route("POST", "plan-validate", kind=READ, contract="http/plan-validate.reply.json")
def post_plan_validate(devcenter: Any, query: Mapping[str, Sequence[str]], body: Any) -> Mapping[str, Any]:
    return service.validate_plan(devcenter, _json(body))


@route("POST", "edit-preview", kind=READ, contract="http/edit-preview.reply.json")
def post_edit_preview(devcenter: Any, query: Mapping[str, Sequence[str]], body: Any) -> Mapping[str, Any]:
    from backend.devcenter.plan import edits

    return edits.preview(devcenter, _json(body))
