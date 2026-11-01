"""JS API methods of build step S2: sessions, sources, target, source check, row confirm."""

from __future__ import annotations

from typing import Any, Mapping

from backend.devcenter.jsapi import register
from backend.devcenter.session.manager import DevCenterSessions

S2_METHODS = (
    "session_create",
    "session_open",
    "session_close",
    "source_add",
    "source_remove",
    "source_relink",
    "target_set",
    "sources_check",
    "row_confirm",
)


@register("session_create", long=True)
def session_create(devcenter: DevCenterSessions, request: Mapping[str, Any]) -> Mapping[str, Any]:
    return devcenter.create(request)


@register("session_open", long=True)
def session_open(devcenter: DevCenterSessions, request: Mapping[str, Any]) -> Mapping[str, Any]:
    return devcenter.open(request)


@register("session_close")
def session_close(devcenter: DevCenterSessions, request: Mapping[str, Any]) -> Mapping[str, Any]:
    return devcenter.close(request)


@register("source_add")
def source_add(devcenter: DevCenterSessions, request: Mapping[str, Any]) -> Mapping[str, Any]:
    return devcenter.source_add(request)


@register("source_remove")
def source_remove(devcenter: DevCenterSessions, request: Mapping[str, Any]) -> Mapping[str, Any]:
    return devcenter.source_remove(request)


@register("source_relink")
def source_relink(devcenter: DevCenterSessions, request: Mapping[str, Any]) -> Mapping[str, Any]:
    return devcenter.source_relink(request)


@register("target_set")
def target_set(devcenter: DevCenterSessions, request: Mapping[str, Any]) -> Mapping[str, Any]:
    return devcenter.target_set(request)


@register("sources_check", long=True)
def sources_check(devcenter: DevCenterSessions, request: Mapping[str, Any]) -> Mapping[str, Any]:
    return devcenter.sources_check(request)


@register("row_confirm")
def row_confirm(devcenter: DevCenterSessions, request: Mapping[str, Any]) -> Mapping[str, Any]:
    return devcenter.row_confirm(request)
