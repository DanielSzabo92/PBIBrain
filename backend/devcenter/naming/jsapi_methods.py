"""JS API methods of build step S4: naming rule confirm, reject, edit, and copy (UC16, UC34)."""

from __future__ import annotations

from typing import Any, Mapping

from backend.devcenter.jsapi import register
from backend.devcenter.naming import service

S4_METHODS = (
    "naming_rule_confirm",
    "naming_rule_reject",
    "naming_rule_edit",
    "naming_rules_copy",
)


@register("naming_rule_confirm")
def naming_rule_confirm(devcenter: Any, request: Mapping[str, Any]) -> Mapping[str, Any]:
    return service.confirm(devcenter, request)


@register("naming_rule_reject")
def naming_rule_reject(devcenter: Any, request: Mapping[str, Any]) -> Mapping[str, Any]:
    return service.reject(devcenter, request)


@register("naming_rule_edit")
def naming_rule_edit(devcenter: Any, request: Mapping[str, Any]) -> Mapping[str, Any]:
    return service.edit(devcenter, request)


@register("naming_rules_copy", long=True)
def naming_rules_copy(devcenter: Any, request: Mapping[str, Any]) -> Mapping[str, Any]:
    return service.copy_rules(devcenter, request)
