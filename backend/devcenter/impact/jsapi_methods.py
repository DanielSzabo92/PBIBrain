"""JS API state mutation methods for Dev Center S6 impact data (technical design section 14.2).

Registers the 4 state-changing methods for pywebview JS API:
- impact_action_apply
- removal_policy_set
- need_mapping_set
- offer_select
"""

from __future__ import annotations

from typing import Any, Mapping

from backend.devcenter.impact import service
from backend.devcenter.jsapi import register


@register("impact_action_apply")
def impact_action_apply(devcenter: Any, request: Mapping[str, Any]) -> Mapping[str, Any]:
    return service.impact_action_apply(devcenter, request)


@register("removal_policy_set")
def removal_policy_set(devcenter: Any, request: Mapping[str, Any]) -> Mapping[str, Any]:
    return service.removal_policy_set(devcenter, request)


@register("need_mapping_set")
def need_mapping_set(devcenter: Any, request: Mapping[str, Any]) -> Mapping[str, Any]:
    return service.need_mapping_set(devcenter, request)


@register("offer_select")
def offer_select(devcenter: Any, request: Mapping[str, Any]) -> Mapping[str, Any]:
    return service.offer_select(devcenter, request)
