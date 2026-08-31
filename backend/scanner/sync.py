"""Scanner-facing aliases for the Phase 5 incremental sync seam."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .pipeline import Scanner


# Keep one implementation.  These names make the scanner seam discoverable to
# integrations without duplicating synchronization logic.
IncrementalScanner = Scanner
IncrementalSync = Scanner
SyncEngine = Scanner
IncrementalSynchronizer = Scanner


def sync(
    model_source: Any,
    report_source: Any = None,
    *,
    repository: Any = None,
    database_path: str | Path | None = None,
    identity_path: str | Path | None = None,
    use_native: bool | None = None,
    overrides_path: str | Path | None = None,
    override_store: Any = None,
):
    """Run one incremental scan through :class:`Scanner`."""

    return Scanner(
        repository,
        database_path=database_path,
        identity_path=identity_path,
        use_native=use_native,
        overrides_path=overrides_path,
        override_store=override_store,
    ).scan_incremental(model_source, report_source)


synchronize = sync
incremental_scan = sync


__all__ = [
    "IncrementalScanner",
    "IncrementalSync",
    "IncrementalSynchronizer",
    "SyncEngine",
    "incremental_scan",
    "sync",
    "synchronize",
]
