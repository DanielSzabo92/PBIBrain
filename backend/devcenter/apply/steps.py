"""Step IDs of a local apply (technical design section 13) and guard check names (UC5, UC32)."""

from __future__ import annotations

from typing import Any
from collections.abc import Iterable, Mapping

from backend.devcenter.errors import DevCenterError

# The 12 steps of section 13, in order.
SOURCE_CHECK = "source_check"
PLAN_STATUS = "plan_status"
DESKTOP_CHECK = "desktop_check"
CANONICAL_CHECK = "canonical_check"
VALIDATION = "validation"
APPROVAL = "approval"
WRITE = "write"
GUARD = "guard"
PROMOTION = "promotion"
RESCAN = "rescan"
FINGERPRINT = "fingerprint"
CHANGE_REPORT = "change_report"
# Undo only: the check of the backup and of the target files before the restore.
BACKUP_CHECK = "backup_check"

APPLY_STEPS = (SOURCE_CHECK, PLAN_STATUS, DESKTOP_CHECK, CANONICAL_CHECK, VALIDATION, APPROVAL,
               WRITE, GUARD, PROMOTION, RESCAN, FINGERPRINT, CHANGE_REPORT)
FORMAT_ONLY_STEPS = (DESKTOP_CHECK, CANONICAL_CHECK, WRITE, GUARD, PROMOTION, RESCAN, FINGERPRINT)
UNDO_STEPS = (DESKTOP_CHECK, BACKUP_CHECK, PROMOTION, RESCAN, FINGERPRINT)
STEPS_BY_KIND = {"apply": APPLY_STEPS, "format_only": FORMAT_ONLY_STEPS, "undo": UNDO_STEPS}

# UC32: the guard check of a failure.
CHECKS = ("scope", "canonical", "tree_compare", "pbir", "policy", "approval", "write", "rescan")

_CHECK_OF_CODE = {
    "WRITE_RECORD_MISSING": "write",
    "WRITE_RECORD_HASH_MISMATCH": "write",
    "WRITE_RECORD_FILE_MISMATCH": "write",
    "APP_WRITE_FAILED": "write",
    "PROMOTION_FAILED": "write",
    "NON_CANONICAL_BASELINE_FILE": "canonical",
    "NON_CANONICAL_MODEL_FILE": "canonical",
    "MODEL_NOT_PLAN_OUTPUT": "canonical",
    "MODEL_LOAD_FAILED": "tree_compare",
    "UNPLANNED_MODEL_CHANGE": "tree_compare",
    "REQUIRED_MODEL_CHANGE_MISSING": "tree_compare",
    "UNPLANNED_IDENTITY_ENTRY": "tree_compare",
    "UNPLANNED_IDENTITY_REMOVAL": "tree_compare",
    "RENAME_PAIR_PROPERTY_CHANGED": "tree_compare",
    "FORMAT_ONLY_MODEL_CHANGED": "tree_compare",
    "UNPLANNED_REPORT_PROPERTY": "pbir",
    "REQUIRED_REPORT_CHANGE_MISSING": "pbir",
    "REPORT_FILE_CONTENT_MISMATCH": "pbir",
    "UNPLANNED_FILE_CREATED": "scope",
    "UNPLANNED_FILE_DELETED": "scope",
    "UNPLANNED_FILE_CHANGED": "scope",
    "SCOPE_VIOLATION": "scope",
    "MISSING_APPROVAL": "approval",
    "APPROVAL_CANNOT_BYPASS_GATES": "policy",
    "PROFILE_MISMATCH": "policy",
    "POST_PROMOTION_MISMATCH": "rescan",
    "RESCAN_FAILED": "rescan",
}

_CHECK_OF_GATE = {"security": "write", "source": "canonical", "scope": "scope", "static": "policy", "policy": "policy"}


def check_of(code: str | None, gate: str | None = None) -> str:
    """Give the UC32 check of a guard code. An unknown code is a policy rejection."""

    if code in _CHECK_OF_CODE:
        return _CHECK_OF_CODE[code]
    if gate in _CHECK_OF_GATE:
        return _CHECK_OF_GATE[gate]
    return "policy"


def first_check(codes: Iterable[tuple[str | None, str | None]]) -> str:
    """Give the check of the first code in the fixed check order (the most specific check first)."""

    found = [check_of(code, gate) for code, gate in codes]
    order = ("write", "canonical", "tree_compare", "pbir", "scope", "approval", "policy", "rescan")
    return next((check for check in order if check in found), "policy")


class ApplyFailure(Exception):
    """A step of an apply stopped. The service gives it as the error shape with ``details.step``."""

    def __init__(self, step: str, reason: str, message: str, *, check: str | None = None,
                 code: str = "action_not_allowed", **details: Any) -> None:
        super().__init__(message)
        if check is not None and check not in CHECKS:
            raise ValueError(f"Unknown guard check: {check}")
        self.step = step
        self.reason = reason
        self.message = message
        self.check = check
        self.code = code
        self.details = details

    def error(self) -> DevCenterError:
        details: dict[str, Any] = {"reason": self.reason, "step": self.step, **self.details}
        if self.check is not None:
            details["check"] = self.check
        return DevCenterError(self.code, self.message, details)


def guard_failure(step: str, codes: Iterable[Mapping[str, Any]], message: str) -> ApplyFailure:
    """Give the failure of a guard rejection. ``codes`` are the violations and blocking reasons."""

    items = [dict(item) for item in codes]
    pairs = [(item.get("code"), item.get("gate")) for item in items]
    return ApplyFailure(step, "guard_rejected", message, check=first_check(pairs),
                        guard_codes=sorted({str(code) for code, _ in pairs if code}))
