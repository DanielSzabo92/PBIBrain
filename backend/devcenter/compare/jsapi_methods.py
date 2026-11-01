"""JS API methods of build step S3: alignment overrides and the compare mode."""

from __future__ import annotations

from typing import Any, Mapping

from backend.devcenter.compare import service
from backend.devcenter.jsapi import register

S3_METHODS = ("alignment_override", "compare_mode_set")


@register("alignment_override")
def alignment_override(devcenter: Any, request: Mapping[str, Any]) -> Mapping[str, Any]:
    return service.alignment_override(devcenter, request)


@register("compare_mode_set")
def compare_mode_set(devcenter: Any, request: Mapping[str, Any]) -> Mapping[str, Any]:
    return service.compare_mode_set(devcenter, request)
