"""The one error shape of the Development Center (technical design section 12)."""

from __future__ import annotations

from typing import Any
from collections.abc import Mapping

ERROR_CODES = (
    "not_found",
    "session_not_open",
    "stale_revision",
    "confidence_below_threshold",
    "reason_required",
    "user_choice_exists",
    "naming_rule_violation",
    "invalid_payload",
    "action_not_allowed",
    "source_changed",
)


class DevCenterError(Exception):
    """An error that the JS API and the HTTP reads send as ``{error: {code, message, details}}``."""

    def __init__(self, code: str, message: str, details: Mapping[str, Any] | None = None) -> None:
        if code not in ERROR_CODES:
            raise ValueError(f"Unknown error code: {code}")
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})

    def reply(self) -> dict[str, Any]:
        return error_reply(self.code, self.message, self.details)


def error_reply(code: str, message: str, details: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": dict(details or {})}}


def not_allowed(message: str, reason: str, **details: Any) -> DevCenterError:
    return DevCenterError("action_not_allowed", message, {"reason": reason, **details})
