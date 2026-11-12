"""One registry of the Development Center JS API methods (technical design section 14.2).

Each area module registers its methods with ``register``. To add an area, add
its module name to ``AREA_MODULES``. ``DevCenterJSAPI`` is a mixin of the
pywebview JS API object (``backend.desktop.host.DesktopController``): it gets
one public method for each registered name. These methods are the only path
for accepted-state writes (ADR 0003). No HTTP route calls them.

Each call takes one request object and gives one reply object, or the error
shape ``{error: {code, message, details}}``. The request and the reply are
checked against ``contracts/jsapi/<method>.request.json`` and ``.reply.json``.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import logging
import traceback
from typing import Any
from collections.abc import Callable, Mapping

from backend.devcenter import contracts
from backend.devcenter.errors import DevCenterError, error_reply

LOGGER = logging.getLogger(__name__)

# One line for each area. Later build steps add their modules here.
AREA_MODULES = (
    "backend.devcenter.session.jsapi_methods",
    "backend.devcenter.compare.jsapi_methods",
    "backend.devcenter.naming.jsapi_methods",
    "backend.devcenter.sources.cloud_jsapi_methods",
    "backend.devcenter.plan.jsapi_methods",
    "backend.devcenter.impact.jsapi_methods",
    "backend.devcenter.session.proposal_jsapi_methods",
    "backend.devcenter.apply.jsapi_methods",
    "backend.devcenter.session.migration_jsapi_methods",
)

Handler = Callable[[Any, Mapping[str, Any]], Mapping[str, Any]]


@dataclass(frozen=True)
class JSAPIMethod:
    name: str
    handler: Handler
    long: bool = False


METHODS: dict[str, JSAPIMethod] = {}


def register(name: str, *, long: bool = False) -> Callable[[Handler], Handler]:
    """Register a handler ``handler(devcenter, request) -> reply`` for one JS API method."""

    def decorator(handler: Handler) -> Handler:
        if name in METHODS:
            raise ValueError(f"JS API method {name} is registered two times")
        METHODS[name] = JSAPIMethod(name, handler, long)
        return handler

    return decorator


def call(devcenter: Any, name: str, request: Any = None) -> dict[str, Any]:
    """Run one JS API method with contract checks. Never raise: give the error shape."""

    method = METHODS.get(name)
    if method is None:
        return error_reply("not_found", "The method does not exist.", {"method": name})
    payload = {} if request is None else request
    problems = contracts.errors(contracts.jsapi_request(name), payload)
    if problems:
        return error_reply("invalid_payload", "The request is not valid.", {"errors": problems[:20]})
    try:
        reply = dict(method.handler(devcenter, payload))
    except DevCenterError as exc:
        return exc.reply()
    except Exception as exc:  # The reply must keep the error shape; the log keeps the cause.
        # Only the type and the code lines: an exception text can hold an account name or a token.
        LOGGER.error("Development Center method %s failed: %s\n%s", name, type(exc).__name__,
                     "".join(traceback.format_tb(exc.__traceback__)))
        return error_reply("action_not_allowed", "The app could not do this action.", {"reason": "internal_error"})
    problems = contracts.errors(contracts.jsapi_reply(name), reply)
    if problems:
        # Only the JSON pointers: a schema message holds the value, for example an account name.
        pointers = sorted({"/" + "/".join(str(part) for part in item.absolute_path)
                           for item in contracts.validator(contracts.jsapi_reply(name)).iter_errors(reply)})
        LOGGER.error("Development Center method %s gave a reply that is not valid at: %s", name, pointers)
        return error_reply("action_not_allowed", "The app could not do this action.", {"reason": "internal_error"})
    return reply


class DevCenterJSAPI:
    """Mixin for the pywebview JS API object. The object sets ``_devcenter``."""

    _devcenter: Any = None


def _bind(name: str) -> None:
    def method(self: DevCenterJSAPI, request: Any = None) -> dict[str, Any]:
        return call(self._devcenter, name, request)

    method.__name__ = name
    method.__qualname__ = f"DevCenterJSAPI.{name}"
    method.__doc__ = f"Development Center JS API method {name}."
    setattr(DevCenterJSAPI, name, method)


def load_areas() -> None:
    for module in AREA_MODULES:
        importlib.import_module(module)
    for name in METHODS:
        if not hasattr(DevCenterJSAPI, name):
            _bind(name)


load_areas()
