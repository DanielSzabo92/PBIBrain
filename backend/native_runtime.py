"""Locate the application-owned native runtime without machine configuration."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_dll_directories: dict[str, object] = {}


def configure_native_runtime() -> Path | None:
    """Prefer bundled runtime libraries when present.

    Trail graph persistence is pure Python/JSON and does not require a native
    graph database shared library. On Windows packaged builds, register the
    bundled native directory (OpenSSL / WebView2 helpers) if it exists.
    """
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    directory = base / "runtime" / "native"
    if not directory.is_dir():
        return None
    key = str(directory)
    if sys.platform == "win32" and hasattr(os, "add_dll_directory") and key not in _dll_directories:
        _dll_directories[key] = os.add_dll_directory(key)
    return directory
