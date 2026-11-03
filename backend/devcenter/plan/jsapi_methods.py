"""JS API methods of build step S5: Merge Choices on rows."""

from __future__ import annotations

from typing import Any, Mapping

from backend.devcenter.jsapi import register


@register("merge_choice_set")
def merge_choice_set(devcenter: Any, request: Mapping[str, Any]) -> Mapping[str, Any]:
    return devcenter.merge_choice_set(request)


@register("merge_choice_bulk_set", long=True)
def merge_choice_bulk_set(devcenter: Any, request: Mapping[str, Any]) -> Mapping[str, Any]:
    return devcenter.merge_choice_bulk_set(request)
