"""JS API methods of build step S10: the user decisions on agent proposals and questions (ADR 0003)."""

from __future__ import annotations

from typing import Any
from collections.abc import Mapping

from backend.devcenter.jsapi import register
from backend.devcenter.session import proposals

S10_METHODS = ("proposal_accept", "proposal_reject", "proposal_accept_all", "question_answer")


@register("proposal_accept")
def proposal_accept(devcenter: Any, request: Mapping[str, Any]) -> Mapping[str, Any]:
    return proposals.proposal_accept(devcenter, request)


@register("proposal_reject")
def proposal_reject(devcenter: Any, request: Mapping[str, Any]) -> Mapping[str, Any]:
    return proposals.proposal_reject(devcenter, request)


@register("proposal_accept_all", long=True)
def proposal_accept_all(devcenter: Any, request: Mapping[str, Any]) -> Mapping[str, Any]:
    return proposals.proposal_accept_all(devcenter, request)


@register("question_answer")
def question_answer(devcenter: Any, request: Mapping[str, Any]) -> Mapping[str, Any]:
    return proposals.question_answer(devcenter, request)
