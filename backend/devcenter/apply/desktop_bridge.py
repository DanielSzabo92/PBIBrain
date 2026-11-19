"""Desktop-open status bridge for local Development Center apply (section 13 step 3, UC6)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

DESKTOP_NOT_OPEN = "not_open"
DESKTOP_OPEN_SAVED = "open_saved"
DESKTOP_OPEN_UNSAVED = "open_unsaved"
DESKTOP_NOT_REACHABLE = "not_reachable"

DESKTOP_STATES = frozenset({
    DESKTOP_NOT_OPEN,
    DESKTOP_OPEN_SAVED,
    DESKTOP_OPEN_UNSAVED,
    DESKTOP_NOT_REACHABLE,
})

_WARNINGS = {
    DESKTOP_OPEN_SAVED: (
        "Power BI Desktop has this project open with no unsaved changes. "
        "After applying, select Apply external changes in Power BI Desktop."
    ),
    DESKTOP_NOT_REACHABLE: "Could not check whether Power BI Desktop has this project open.",
}


class DefaultDesktopBridge:
    """Default local bridge returning not_open without probing external processes."""

    def check(self, target_root: Path | None) -> str:
        return DESKTOP_NOT_OPEN


def warning_for_desktop_state(state: str) -> str | None:
    return _WARNINGS.get(state)


def check_desktop_state(devcenter: Any, target_root: Path | None) -> tuple[str, str | None]:
    """Query the configured Desktop bridge, falling back to not_reachable on failure."""
    bridge = getattr(devcenter, "_desktop_bridge", None)
    if bridge is None:
        return DESKTOP_NOT_OPEN, None

    try:
        raw: Any
        if callable(bridge):
            raw = bridge(target_root)
        elif hasattr(bridge, "check"):
            raw = bridge.check(target_root)
        elif hasattr(bridge, "state"):
            state_attr = bridge.state
            raw = state_attr(target_root) if callable(state_attr) else state_attr
        elif hasattr(bridge, "get_state"):
            raw = bridge.get_state(target_root)
        else:
            raw = DESKTOP_NOT_REACHABLE
    except Exception:
        return DESKTOP_NOT_REACHABLE, _WARNINGS[DESKTOP_NOT_REACHABLE]

    if isinstance(raw, Mapping):
        raw = raw.get("desktop_state") or raw.get("state") or raw.get("status")
    state = str(raw or "").strip()
    if state not in DESKTOP_STATES:
        state = DESKTOP_NOT_REACHABLE
    return state, warning_for_desktop_state(state)
