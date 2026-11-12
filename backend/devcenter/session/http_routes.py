"""HTTP routes of build step S10: the agent proposal routes and ``GET log`` (sections 14.1 and 14.3).

The proposal routes write only proposals and questions. They never change
accepted state (ADR 0003).
"""

from __future__ import annotations

from typing import Any
from collections.abc import Mapping, Sequence

from backend.devcenter.http_routes import PROPOSAL, route
from backend.devcenter.session import proposals
from backend.devcenter.http_routes import json_body as _json


@route("POST", "proposals", kind=PROPOSAL, contract="http/proposals.reply.json")
def post_proposal(devcenter: Any, query: Mapping[str, Sequence[str]], body: Any) -> Mapping[str, Any]:
    return proposals.proposal_submit(devcenter, _json(body))


@route("POST", "questions", kind=PROPOSAL, contract="http/questions.reply.json")
def post_question(devcenter: Any, query: Mapping[str, Sequence[str]], body: Any) -> Mapping[str, Any]:
    return proposals.question_ask(devcenter, _json(body))


@route("GET", "log", contract="http/log.reply.json")
def get_log(devcenter: Any, query: Mapping[str, Sequence[str]], body: Any) -> Mapping[str, Any]:
    return proposals.log_page(devcenter, query)
