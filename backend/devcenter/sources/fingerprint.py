"""Source Fingerprint: one hash over the files of a local source (technical design section 11)."""

from __future__ import annotations

import os
from pathlib import Path

from backend.devcenter.errors import DevCenterError
from backend.devcenter.sources.kinds import LocalSource
from backend.snapshots.manifest import SourceIntegrityError, content_hash, source_manifest


def _relative(path: Path, base: Path) -> str:
    return Path(os.path.relpath(path, base)).as_posix()


def source_files(source: LocalSource) -> list[dict[str, object]]:
    """Give the file records (path, hash, size) of the source, sorted by path.

    Each path is relative to the folder that holds the source, so that the same
    files at a new place give the same fingerprint.
    """

    base = source.root.parent
    records: list[dict[str, object]] = []
    try:
        for item in source.artifact_paths():
            if item.is_file():
                data = item.read_bytes()
                records.append({"path": _relative(item, base), "hash": content_hash(data), "size": len(data)})
                continue
            prefix = _relative(item, base)
            for record in source_manifest(item):
                records.append({**record, "path": f"{prefix}/{record['path']}"})
    except (SourceIntegrityError, ValueError) as exc:
        raise DevCenterError("invalid_payload", "The app cannot read the files of this source.", {"reason": "source_unreadable"}) from exc
    return sorted(records, key=lambda record: str(record["path"]))


def source_fingerprint(source: LocalSource) -> str:
    return content_hash(source_files(source))

