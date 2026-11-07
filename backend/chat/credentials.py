"""Where the chat keeps the provider API key: the OS credential store, never ``brain.json``.

On Windows the key is a generic credential in Windows Credential Manager (``advapi32``
through ``ctypes``, no extra package). Elsewhere the ``keyring`` package is used when it is
installed. Without either, the key lives in memory until the app closes, and the settings
say so (``persistent: false``).

Each key is stored under its provider *and* its exact endpoint URL (``credential_name``). A
changed base URL therefore has no key until the user types one: the local API has no
authentication, and this is what stops a local process from redirecting a saved key to a
server of its own by editing the base URL.
"""

from __future__ import annotations

import sys
import threading
from typing import Protocol

SERVICE = "PBIBrain"


def credential_name(provider: str, base_url: str) -> str:
    return f"{SERVICE}/ai/{provider}/{base_url.rstrip('/')}"


class CredentialStore(Protocol):
    label: str
    persistent: bool

    def get(self, name: str) -> str | None: ...

    def set(self, name: str, secret: str) -> None: ...

    def delete(self, name: str) -> None: ...


class MemoryStore:
    label = "memory (until PBIBrain closes)"
    persistent = False

    def __init__(self) -> None:
        self._values: dict[str, str] = {}
        self._lock = threading.Lock()

    def get(self, name: str) -> str | None:
        with self._lock:
            return self._values.get(name)

    def set(self, name: str, secret: str) -> None:
        with self._lock:
            self._values[name] = secret

    def delete(self, name: str) -> None:
        with self._lock:
            self._values.pop(name, None)


class WindowsCredentialStore:
    """Generic credentials in Windows Credential Manager (CredReadW / CredWriteW / CredDeleteW)."""

    label = "Windows Credential Manager"
    persistent = True
    _GENERIC = 1
    _PERSIST_LOCAL_MACHINE = 2
    _NOT_FOUND = 1168

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        class FILETIME(ctypes.Structure):
            _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]

        class CREDENTIAL(ctypes.Structure):
            _fields_ = [
                ("Flags", wintypes.DWORD), ("Type", wintypes.DWORD), ("TargetName", wintypes.LPWSTR),
                ("Comment", wintypes.LPWSTR), ("LastWritten", FILETIME), ("CredentialBlobSize", wintypes.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)), ("Persist", wintypes.DWORD),
                ("AttributeCount", wintypes.DWORD), ("Attributes", ctypes.c_void_p),
                ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR),
            ]

        self._ctypes = ctypes
        self._CREDENTIAL = CREDENTIAL
        advapi = ctypes.WinDLL("advapi32", use_last_error=True)
        self._read = advapi.CredReadW
        self._read.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.POINTER(CREDENTIAL))]
        self._read.restype = wintypes.BOOL
        self._write = advapi.CredWriteW
        self._write.argtypes = [ctypes.POINTER(CREDENTIAL), wintypes.DWORD]
        self._write.restype = wintypes.BOOL
        self._delete = advapi.CredDeleteW
        self._delete.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        self._delete.restype = wintypes.BOOL
        self._free = advapi.CredFree
        self._free.argtypes = [ctypes.c_void_p]

    def get(self, name: str) -> str | None:
        ctypes = self._ctypes
        pointer = ctypes.POINTER(self._CREDENTIAL)()
        if not self._read(name, self._GENERIC, 0, ctypes.byref(pointer)):
            if ctypes.get_last_error() == self._NOT_FOUND:
                return None
            raise OSError("Windows Credential Manager could not read the API key")
        try:
            item = pointer.contents
            return bytes(item.CredentialBlob[: item.CredentialBlobSize]).decode("utf-8")
        finally:
            self._free(pointer)

    def set(self, name: str, secret: str) -> None:
        ctypes = self._ctypes
        blob = secret.encode("utf-8")
        buffer = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
        item = self._CREDENTIAL()
        item.Type = self._GENERIC
        item.TargetName = name
        item.UserName = SERVICE
        item.CredentialBlobSize = len(blob)
        item.CredentialBlob = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
        item.Persist = self._PERSIST_LOCAL_MACHINE
        if not self._write(ctypes.byref(item), 0):
            raise OSError("Windows Credential Manager could not save the API key")

    def delete(self, name: str) -> None:
        if not self._delete(name, self._GENERIC, 0) and self._ctypes.get_last_error() != self._NOT_FOUND:
            raise OSError("Windows Credential Manager could not remove the API key")


class KeyringStore:
    label = "system keyring"
    persistent = True

    def __init__(self) -> None:
        import keyring  # optional; raises ImportError when absent

        self._keyring = keyring

    def get(self, name: str) -> str | None:
        return self._keyring.get_password(SERVICE, name)

    def set(self, name: str, secret: str) -> None:
        self._keyring.set_password(SERVICE, name, secret)

    def delete(self, name: str) -> None:
        try:
            self._keyring.delete_password(SERVICE, name)
        except self._keyring.errors.PasswordDeleteError:
            pass


def default_store() -> CredentialStore:
    if sys.platform == "win32":
        try:
            return WindowsCredentialStore()
        except (OSError, AttributeError):
            pass
    try:
        return KeyringStore()
    except ImportError:
        return MemoryStore()
