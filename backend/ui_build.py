"""Tell whether the built web UI (frontend/dist) is older than its sources.

A source checkout serves ``frontend/dist``. ``git pull`` updates ``frontend/src``
but not the build, so without a rebuild the app keeps running the old UI. The
start scripts call ``python -m backend.ui_build`` and rebuild when it exits 1.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"

# Inputs of `npm run build`. node_modules and dist are outputs, not inputs.
_INPUT_FILES = ("index.html", "package.json", "package-lock.json", "vite.config.js", "vite.config.mjs",
                "vite.config.ts", "tailwind.config.js", "postcss.config.js", "jsconfig.json")
_INPUT_DIRS = ("src", "public", "vite-plugins")


def _newest_input(frontend: Path) -> tuple[float, Path | None]:
    newest, newest_path = 0.0, None
    candidates = [frontend / name for name in _INPUT_FILES]
    for folder in _INPUT_DIRS:
        root = frontend / folder
        if root.is_dir():
            candidates.extend(path for path in root.rglob("*") if path.is_file())
    for path in candidates:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime > newest:
            newest, newest_path = mtime, path
    return newest, newest_path


def stale_reason(frontend: Path = FRONTEND) -> str | None:
    """Give why the build must be made again, or None when it is current.

    A checkout without sources (an installed package) is never stale.
    """

    built = frontend / "dist" / "index.html"
    if not (frontend / "src").is_dir():
        return None
    if not built.is_file():
        return "the UI build is missing"
    newest, path = _newest_input(frontend)
    if path is not None and newest > built.stat().st_mtime:
        return f"{path.relative_to(frontend).as_posix()} is newer than the UI build"
    return None


def ensure_current(frontend: Path = FRONTEND) -> str | None:
    """Rebuild a stale UI with npm when npm is on PATH. Give the reason it is still stale, or None."""

    reason = stale_reason(frontend)
    if reason is None:
        return None
    npm = shutil.which("npm")
    if npm is None:
        return f"{reason}, and npm is not on PATH to build it (cd frontend && npm install && npm run build)"
    print(f"[PBIBrain] Building the web UI: {reason}.", file=sys.stderr, flush=True)
    try:
        if not (frontend / "node_modules").is_dir() or reason.startswith("package"):
            subprocess.run([npm, "install"], cwd=frontend, check=True)
        subprocess.run([npm, "run", "build"], cwd=frontend, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        return f"{reason}, and the build failed: {exc}"
    return stale_reason(frontend)


def main() -> int:
    reason = stale_reason()
    if reason is None:
        return 0
    print(reason)
    return 1


if __name__ == "__main__":
    sys.exit(main())
