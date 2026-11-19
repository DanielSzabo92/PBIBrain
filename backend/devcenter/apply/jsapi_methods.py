"""JS API methods for local apply, format-only apply, undo, and change report (S9)."""

from __future__ import annotations

from typing import Any, Mapping

from backend.devcenter.apply import service
from backend.devcenter.jsapi import register


@register("format_only_apply", long=True)
def format_only_apply(devcenter: Any, request: Mapping[str, Any]) -> Mapping[str, Any]:
    return service.format_only_apply(devcenter, request)


@register("apply", long=True)
def apply(devcenter: Any, request: Mapping[str, Any]) -> Mapping[str, Any]:
    return service.apply(devcenter, request)


@register("undo_apply", long=True)
def undo_apply(devcenter: Any, request: Mapping[str, Any]) -> Mapping[str, Any]:
    return service.undo_apply(devcenter, request)


@register("change_report_write")
def change_report_write(devcenter: Any, request: Mapping[str, Any]) -> Mapping[str, Any]:
    return service.change_report_write(devcenter, request)
