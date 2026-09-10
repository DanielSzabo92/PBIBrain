"""Locate the application-owned native runtime without machine configuration."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_dll_directories: dict[str, object] = {}


def configure_native_runtime() -> Path | None:
    """Prefer bundled libraries; retain developer overrides outside packaged builds.

    Keep add_dll_directory handles alive for delayed native dependencies. Never
    search the working directory, which belongs to the opened Power BI project.
    """
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    directory = base / "runtime" / "native"
    library = directory / "lbug_shared.dll"
    if not library.is_file():
        if getattr(sys, "frozen", False) and sys.platform == "win32":
            raise RuntimeError("PBIBrain's database runtime is missing. Reinstall PBIBrain.")
        return None
    os.environ["LBUG_C_API_LIB_PATH"] = str(library)
    # Use the runtime we ship. Ladybug's optional pybind extension otherwise
    # takes precedence and can fail while inserting the project's edges.
    os.environ["LBUG_PYTHON_BACKEND"] = "capi"
    key = str(directory)
    if sys.platform == "win32" and key not in _dll_directories:
        _dll_directories[key] = os.add_dll_directory(key)
    return library
