"""Session folder, ``session.json``, ``log.jsonl``, lock, and migration (technical design section 11)."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any, Callable, Mapping

from backend.devcenter.errors import DevCenterError, not_allowed
from backend.devcenter.session.secrets import check_secrets

SCHEMA_VERSION = 1
SESSION_FILE = "session.json"
LOG_FILE = "log.jsonl"
LOCK_FILE = "session.lock"
SESSIONS_FOLDER = "sessions"
_SESSION_ID = re.compile(r"^[0-9a-f]{32}$")
_CONFLICT_MARKER = re.compile(r"^(?:<{7}|={7}|>{7}|\|{7})(?:\s|$)", re.MULTILINE)

# Runtime files in ".pbibrain" that must not go into git (technical design section 11).
GITIGNORE_ENTRIES = (
    "connection.json",
    "*.lbug",
    "*.lbug.*",
    "*.wal",
    "*.lock",
    "*.bak",
    "*.tmp",
    "backups/",
    "tmp/",
)

# Migrations from one schema version to the next: {old version: function}.
MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {}

SCHEMA_OK = "ok"
SCHEMA_NEWER = "newer"
SCHEMA_DAMAGED = "damaged"
LOCK_FREE = "free"
LOCK_LOCKED = "locked"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def canonical_bytes(document: Mapping[str, Any]) -> bytes:
    """Sorted keys, 2-space indent, LF line ends, one final LF."""

    return (json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def write_atomic(path: Path, data: bytes) -> None:
    """Write a temp file in the same folder, then replace the file in one step."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def ensure_gitignore(pbibrain_dir: Path) -> Path:
    """Make sure that ``.pbibrain/.gitignore`` has each runtime entry. Keep the lines of the user."""

    path = pbibrain_dir / ".gitignore"
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else ["# PBIBrain runtime files"]
    missing = [entry for entry in GITIGNORE_ENTRIES if entry not in {line.strip() for line in lines}]
    if missing or not path.is_file():
        write_atomic(path, ("\n".join(lines + missing) + "\n").encode("utf-8"))
    return path


class SessionReadError(DevCenterError):
    """A session file that the app cannot open: ``schema_state`` is ``newer`` or ``damaged``."""

    def __init__(self, schema_state: str, message: str, **details: Any) -> None:
        super().__init__("action_not_allowed", message, {"reason": f"schema_{schema_state}", "schema_state": schema_state, **details})
        self.schema_state = schema_state


def parse_session(raw: bytes) -> dict[str, Any]:
    """Read session bytes. Refuse conflict markers, invalid JSON, and a newer schema version."""

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SessionReadError(SCHEMA_DAMAGED, "The session file is not UTF-8 text.") from exc
    if _CONFLICT_MARKER.search(text):
        raise SessionReadError(SCHEMA_DAMAGED, "The session file has git conflict markers. Fix the conflict first.", cause="conflict_markers")
    try:
        document = json.loads(text)
    except ValueError as exc:
        raise SessionReadError(SCHEMA_DAMAGED, "The session file is not valid JSON.", cause="invalid_json") from exc
    if not isinstance(document, dict):
        raise SessionReadError(SCHEMA_DAMAGED, "The session file is not a JSON object.", cause="invalid_json")
    version = document.get("schema_version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise SessionReadError(SCHEMA_DAMAGED, "The session file has no valid schema version.", cause="invalid_schema_version")
    if version > SCHEMA_VERSION:
        raise SessionReadError(SCHEMA_NEWER, "This session needs a newer PBIBrain.", schema_version=version)
    return document


def migrate(document: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Migrate forward to the current schema version. Give the document and True when it changed."""

    version = document["schema_version"]
    migrated = copy.deepcopy(document)
    while version < SCHEMA_VERSION:
        step = MIGRATIONS.get(version)
        if step is None:
            raise SessionReadError(SCHEMA_DAMAGED, f"The app has no migration from schema version {version}.", cause="no_migration")
        migrated = step(migrated)
        version += 1
        migrated["schema_version"] = version
    return migrated, version != document["schema_version"]


def _process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            # Access denied means that the process exists.
            return ctypes.get_last_error() == 5
        try:
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return True
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class SessionLock:
    """Lock file with the process ID. A second open of a locked session is read-only."""

    def __init__(self, folder: Path, owner: str) -> None:
        self.path = folder / LOCK_FILE
        self.owner = owner

    def holder(self) -> dict[str, Any] | None:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return value if isinstance(value, dict) else None

    def state(self) -> str:
        holder = self.holder()
        if holder is None or holder.get("owner") == self.owner:
            return LOCK_FREE
        pid = holder.get("pid")
        return LOCK_LOCKED if isinstance(pid, int) and _process_alive(pid) else LOCK_FREE

    def acquire(self) -> bool:
        """Take the lock. Give False when another live process or app instance has it."""

        if self.state() == LOCK_LOCKED:
            return False
        payload = canonical_bytes({"pid": os.getpid(), "owner": self.owner})
        try:
            descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        except FileExistsError:
            # The old lock is stale or is ours: replace it.
            write_atomic(self.path, payload)
            return True
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
        return True

    def release(self) -> None:
        holder = self.holder()
        if holder is not None and holder.get("owner") == self.owner:
            self.path.unlink(missing_ok=True)


class SessionFiles:
    """Read and write the files of one session folder."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.session_path = folder / SESSION_FILE
        self.log_path = folder / LOG_FILE

    @property
    def session_id(self) -> str:
        return self.folder.name

    def read(self) -> dict[str, Any]:
        try:
            raw = self.session_path.read_bytes()
        except FileNotFoundError as exc:
            raise DevCenterError("not_found", "The session does not exist.", {"session_id": self.session_id}) from exc
        return parse_session(raw)

    def backup(self, version: int) -> Path:
        path = self.folder / f"{SESSION_FILE}.v{version}.bak"
        write_atomic(path, self.session_path.read_bytes())
        return path

    def save(self, document: Mapping[str, Any]) -> None:
        check_secrets(document)
        write_atomic(self.session_path, canonical_bytes(document))

    def append_log(self, entry: Mapping[str, Any]) -> None:
        check_secrets(entry)
        line = json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        with open(self.log_path, "ab") as handle:
            handle.write(line.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())


def sessions_dir(base: Path) -> Path:
    return base / SESSIONS_FOLDER


def session_folders(base: Path) -> list[Path]:
    folder = sessions_dir(base)
    if not folder.is_dir():
        return []
    return sorted(path for path in folder.iterdir() if path.is_dir() and _SESSION_ID.match(path.name))


def valid_session_id(value: Any) -> str:
    if not isinstance(value, str) or not _SESSION_ID.match(value):
        raise DevCenterError("invalid_payload", "The session ID is not valid.", {"reason": "invalid_session_id"})
    return value


def require_writable(read_only: bool) -> None:
    if read_only:
        raise not_allowed("This session is open in another window. It opens read-only.", "read_only")
