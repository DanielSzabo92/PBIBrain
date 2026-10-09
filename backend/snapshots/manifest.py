from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Any, Mapping

SCHEMA_VERSION = 1
SCANNER_VERSION = "guarded-2"
SOURCE_SUFFIXES = {".pbip", ".tmdl", ".pbir", ".json", ".bim"}
OPAQUE_RESOURCE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff", ".woff2"}
EXCLUDED_DIRECTORIES = {".git", ".pbi", ".pbibrain", ".pbi-guard"}


class SourceIntegrityError(ValueError):
    code = "SOURCE_INTEGRITY"


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def content_hash(value: Any) -> str:
    data = value if isinstance(value, bytes) else canonical_json(value).encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_path(root: Path, relative: str, *, must_exist: bool = False) -> Path:
    root = root.absolute()
    part = Path(relative)
    reserved = {"CON", "PRN", "AUX", "NUL", *("COM" + str(i) for i in range(1, 10)), *("LPT" + str(i) for i in range(1, 10))}
    if not relative or part.is_absolute() or part.drive or any(
        p in {"..", "."} or p.endswith((".", " ")) or p.split(".")[0].upper() in reserved
        or any(ord(c) < 32 or c in '<>"|?*' for c in p) for p in part.parts
    ) or ":" in relative:
        raise SourceIntegrityError("Unsafe relative path")
    target = root / part
    for current in [root, *target.parents, target]:
        if current.exists() or current.is_symlink():
            info = current.lstat()
            if current.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
                raise SourceIntegrityError("Links/reparse points are forbidden")
    if not target.resolve().is_relative_to(root.resolve()):
        raise SourceIntegrityError("Path escapes project")
    if must_exist and not target.is_file():
        raise SourceIntegrityError("Source file missing")
    return target


def source_manifest(root: str | Path) -> list[dict[str, Any]]:
    root = Path(root).absolute()
    if not root.is_dir() or root.is_symlink():
        raise SourceIntegrityError("Project root must be a real directory")
    records, seen = [], set()
    for directory, directories, files in os.walk(root, followlinks=False):
        for name in list(directories):
            path = Path(directory) / name
            safe_path(root, path.relative_to(root).as_posix())
            if name in EXCLUDED_DIRECTORIES:
                directories.remove(name)
        for name in sorted(files):
            relative = (Path(directory) / name).relative_to(root).as_posix()
            path = safe_path(root, relative, must_exist=True)
            marker = relative.casefold()
            if marker in seen or path.stat().st_nlink > 1:
                raise SourceIntegrityError("Aliased source file")
            seen.add(marker)
            opaque = path.suffix.casefold() in OPAQUE_RESOURCE_SUFFIXES and "StaticResources" in path.parts
            if path.suffix.casefold() not in SOURCE_SUFFIXES and name not in {".platform", ".gitignore", ".gitattributes"} and not opaque:
                raise SourceIntegrityError(f"Unsupported/protected source file: {relative}")
            data = path.read_bytes()
            if not opaque:
                data.decode("utf-8-sig")
            records.append({"path": relative, "hash": content_hash(data), "size": len(data)})
    if not records:
        raise SourceIntegrityError("Source manifest is empty")
    return sorted(records, key=lambda item: item["path"])


@dataclass(frozen=True)
class Snapshot:
    """Canonical JSON prevents mutable dictionaries from altering a captured state."""
    document: str

    def to_dict(self) -> dict[str, Any]:
        return json.loads(self.document)

    @property
    def snapshot_id(self) -> str:
        return self.to_dict()["snapshot_id"]

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Snapshot":
        snapshot = cls(canonical_json(dict(payload)))
        if snapshot.snapshot_id != content_hash(snapshot.to_dict()["identity_inputs"]):
            raise SourceIntegrityError("Snapshot identity mismatch")
        values = snapshot.to_dict()
        if any(values.get(key) != value for key, value in values["identity_inputs"].items()):
            raise SourceIntegrityError("Snapshot manifest/configuration binding mismatch")
        return snapshot


def capture_snapshot(root: str | Path, project_id: str, *, configuration: Mapping[str, Any] | None = None,
                     identity_manifest: Mapping[str, Any] | None = None, kind: str = "BASELINE",
                     analysis: Mapping[str, Any] | None = None) -> Snapshot:
    if kind not in {"BASELINE", "CANDIDATE", "PROMOTED"} or not project_id:
        raise ValueError("Invalid snapshot kind/project")
    manifest = source_manifest(root)
    identities = dict(identity_manifest or {"version": 1, "mappings": {}})
    if identities.get("version") != 1 or not isinstance(identities.get("mappings"), dict):
        raise SourceIntegrityError("Invalid identity manifest")
    values = list(identities["mappings"].values())
    if any(not isinstance(item, str) or not item for item in values) or len(values) != len(set(values)):
        raise SourceIntegrityError("Invalid/colliding identity mappings")
    inputs = {"project_id": project_id, "source_manifest": manifest, "configuration": dict(configuration or {}),
              "identity_manifest": identities, "scanner_version": SCANNER_VERSION, "schema_version": SCHEMA_VERSION}
    revision = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=False)
    analyzed = dict(analysis or {})
    payload = {**inputs, "identity_inputs": inputs, "snapshot_id": content_hash(inputs), "kind": kind,
               "identity_manifest_hash": content_hash(identities), "source_revision": revision.stdout.strip() if revision.returncode == 0 else None,
               "created_at": utc_now(), "model_ids": analyzed.get("model_ids", []), "report_ids": analyzed.get("report_ids", []),
               "completeness": analyzed.get("completeness", {"status": "UNKNOWN", "blocking": ["SCAN_NOT_RUN"]}),
               "validation_status": analyzed.get("validation_status", "NOT_RUN"), "analysis": analyzed}
    return Snapshot(canonical_json(payload))
