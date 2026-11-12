"""JS API methods of build step S11: cloud sign-in, cloud item lists, cloud connect, pull to local PBIP.

These calls exist in the pywebview JS API only. No HTTP route gives cloud data
(UC13): the HTTP API has no authentication, so a local agent must not see
tenant data through it.
"""

from __future__ import annotations

from typing import Any
from collections.abc import Mapping

from backend.devcenter.jsapi import register

S11_METHODS = (
    "cloud_sign_in",
    "cloud_items_list",
    "cloud_connect",
    "pull_to_local",
)


@register("cloud_sign_in", long=True)
def cloud_sign_in(devcenter: Any, request: Mapping[str, Any]) -> Mapping[str, Any]:
    return devcenter.cloud_service().sign_in(devcenter.revision, request)


@register("cloud_items_list")
def cloud_items_list(devcenter: Any, request: Mapping[str, Any]) -> Mapping[str, Any]:
    return devcenter.cloud_service().items(devcenter.revision, request)


@register("cloud_connect", long=True)
def cloud_connect(devcenter: Any, request: Mapping[str, Any]) -> Mapping[str, Any]:
    return devcenter.cloud_service().connect(devcenter, request)


@register("pull_to_local", long=True)
def pull_to_local(devcenter: Any, request: Mapping[str, Any]) -> Mapping[str, Any]:
    return devcenter.cloud_service().pull_to_local(devcenter, request)
