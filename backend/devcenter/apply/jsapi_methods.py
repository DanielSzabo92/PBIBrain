"""JS API methods of build step S9: local apply, format only apply, undo, and the change report (section 14.2).

These methods exist only in the pywebview JS API (ADR 0003). No HTTP route and no MCP tool calls them.
"""

from __future__ import annotations

from typing import Any
from collections.abc import Mapping

from backend.devcenter.apply.service import service
from backend.devcenter.jsapi import register


@register("apply", long=True)
def apply(devcenter: Any, request: Mapping[str, Any]) -> Mapping[str, Any]:
    return service(devcenter).apply(request)


@register("format_only_apply", long=True)
def format_only_apply(devcenter: Any, request: Mapping[str, Any]) -> Mapping[str, Any]:
    return service(devcenter).format_only_apply(request)


@register("undo_apply", long=True)
def undo_apply(devcenter: Any, request: Mapping[str, Any]) -> Mapping[str, Any]:
    return service(devcenter).undo_apply(request)


@register("change_report_write")
def change_report_write(devcenter: Any, request: Mapping[str, Any]) -> Mapping[str, Any]:
    return service(devcenter).change_report_write(request)
