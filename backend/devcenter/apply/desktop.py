"""Desktop-open check of a local apply (technical design section 13 step 3, home ticket 05).

The check uses the Power BI Desktop bridge CLI (``powerbi-desktop status``,
``docs/powerbi-desktop-bridge-cli.md``). The CLI gives each running Desktop
instance with its current file and its unsaved-change flag.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any, Callable, Iterable, Mapping

NOT_OPEN = "not_open"
OPEN_SAVED = "open_saved"
OPEN_UNSAVED = "open_unsaved"
NOT_REACHABLE = "not_reachable"
STATES = (NOT_OPEN, OPEN_SAVED, OPEN_UNSAVED, NOT_REACHABLE)

# The notice for each state that does not block (section 13 step 3).
NOTICES = {OPEN_SAVED: "apply_external_changes", NOT_REACHABLE: "desktop_not_checked"}


def _inside(path: Path, root: Path) -> bool:
    try:
        return os.path.normcase(str(path.resolve())) == os.path.normcase(str(root.resolve())) or root.resolve() in path.resolve().parents
    except OSError:
        return False


def state_of(instances: Iterable[Mapping[str, Any]], target_root: Path) -> str:
    """Give the Desktop state of a target from the instance list of ``powerbi-desktop status``."""

    state = NOT_OPEN
    for instance in instances:
        current = instance.get("currentFilePath")
        if not isinstance(current, str) or not current or not _inside(Path(current), target_root):
            continue
        if instance.get("hasUnsavedChanges") is True:
            return OPEN_UNSAVED
        state = OPEN_SAVED
    return state


Runner = Callable[[list[str]], subprocess.CompletedProcess]


def _run(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=20, check=False)


class DesktopBridge:
    """The client of the Power BI Desktop bridge CLI. Each failure gives ``not_reachable``."""

    def __init__(self, executable: str | None = None, runner: Runner = _run) -> None:
        self.executable = executable
        self.runner = runner

    def state(self, target_root: Path) -> str:
        executable = self.executable or shutil.which("powerbi-desktop")
        if not executable:
            return NOT_REACHABLE
        try:
            result = self.runner([executable, "status"])
            payload = json.loads(result.stdout or "")
        except (OSError, ValueError, subprocess.SubprocessError):
            return NOT_REACHABLE
        instances = payload.get("instances") if isinstance(payload, dict) else None
        if result.returncode or not isinstance(instances, list):
            return NOT_REACHABLE
        return state_of([item for item in instances if isinstance(item, dict)], Path(target_root))
