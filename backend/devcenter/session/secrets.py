"""Secret check before each save (technical design section 11).

The check refuses token-like strings, absolute paths, user names in paths, and
e-mail addresses in a session document or a log entry. The refusal names the
JSON pointer of the value, never the value itself.
"""

from __future__ import annotations

import re
from typing import Any, Iterator

from backend.devcenter.errors import DevCenterError

_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")
_JWT = re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}")
_PREFIXED = re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|xox[abprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,})")
_SECRET_PAIR = re.compile(r"(?i)\b(?:password|passwd|pwd|secret|client_secret|api[_-]?key|access[_-]?token|refresh[_-]?token)\s*[=:]\s*\S+")
_LONG_RUN = re.compile(r"[A-Za-z0-9+/_=-]{40,}")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
_WINDOWS_ABSOLUTE = re.compile(r"(?:^|[\s\"'=(])[A-Za-z]:[\\/]")
_UNC = re.compile(r"(?:^|[\s\"'=(])\\\\[^\\\s]+\\")
_POSIX_HOME = re.compile(r"(?:^|[\s\"'=(])/(?:Users|home|root)/")
_USER_PROFILE = re.compile(r"(?i)%(?:USERPROFILE|APPDATA|LOCALAPPDATA|HOMEPATH)%|\$HOME\b")


def _strings(value: Any, pointer: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(value, str):
        yield pointer or "/", value
    elif isinstance(value, dict):
        for key, item in value.items():
            escaped = str(key).replace("~", "~0").replace("/", "~1")
            yield f"{pointer}/{escaped}#key", str(key)
            yield from _strings(item, f"{pointer}/{escaped}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            yield from _strings(item, f"{pointer}/{index}")


def _token_like(text: str) -> bool:
    if _JWT.search(text) or _BEARER.search(text) or _PREFIXED.search(text) or _SECRET_PAIR.search(text):
        return True
    for match in _LONG_RUN.finditer(text):
        run = match.group(0)
        # A lowercase hex run is a hash or an ID. A run with mixed case and digits is a token.
        if any(c.isupper() for c in run) and any(c.islower() for c in run) and any(c.isdigit() for c in run):
            return True
    return False


def _absolute_path(text: str) -> bool:
    return bool(_WINDOWS_ABSOLUTE.search(text) or _UNC.search(text) or _POSIX_HOME.search(text) or _USER_PROFILE.search(text)
                or text.startswith("/"))


def find_secrets(value: Any) -> list[dict[str, str]]:
    """Give each finding as ``{pointer, kind}``. The kinds are ``token``, ``absolute_path``, and ``email``."""

    findings: list[dict[str, str]] = []
    for pointer, text in _strings(value):
        if _HASH.match(text):
            continue
        if _token_like(text):
            findings.append({"pointer": pointer, "kind": "token"})
        elif _absolute_path(text):
            findings.append({"pointer": pointer, "kind": "absolute_path"})
        elif _EMAIL.search(text):
            findings.append({"pointer": pointer, "kind": "email"})
    return findings


def check_secrets(value: Any) -> None:
    findings = find_secrets(value)
    if findings:
        raise DevCenterError(
            "invalid_payload",
            "The app did not save, because the data contains a secret, an e-mail address, or a full path.",
            {"reason": "secret_found", "findings": findings},
        )
