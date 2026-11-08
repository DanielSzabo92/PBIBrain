"""Read-only agent snapshot, so MCP answers while the app is closed (issue #18).

Each project scan writes ``agent-snapshot.json`` next to the project configuration: the
canonical graph (nodes and edges) and a SHA-256 hash of every source file it was scanned
from. The native graph database has one owner, so the MCP process never opens it. When no
app is running, :class:`SnapshotClient` answers the read-only ``brain_*`` routes from this
file instead. :func:`freshness` compares the recorded hashes with the files on disk, live
or not, so every reply can say whether the graph is older than the sources.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import urlencode

LOGGER = logging.getLogger(__name__)

SNAPSHOT_NAME = "agent-snapshot.json"
SNAPSHOT_VERSION = 1
# Files a source walk reads at most. A PBIP project has a few hundred; this only stops a
# source that points at a huge folder from stalling every reply.
MAX_SOURCE_FILES = 20_000
# Changed files listed in a reply; the count is always exact.
MAX_CHANGED_LISTED = 10
# Hidden folders (.pbi cache, .git, .pbibrain) change without a source change.
_SKIPPED_FILES = {"cache.abf", "localsettings.json"}

# Routes the snapshot answers. Everything else needs the running app.
SNAPSHOT_GET_ROUTES = ("overview", "search", "objects/", "context", "graph", "commonality")
SNAPSHOT_POST_ROUTES = ("impact",)

_hash_cache: dict[str, tuple[int, int, str]] = {}


def snapshot_path(config_path: str | Path) -> Path:
    return Path(config_path).resolve().parent / SNAPSHOT_NAME


def _file_hash(path: Path) -> str:
    """SHA-256 of one file; unchanged files (same size and mtime) are not read again."""

    stat = path.stat()
    key = str(path)
    cached = _hash_cache.get(key)
    if cached and cached[0] == stat.st_mtime_ns and cached[1] == stat.st_size:
        return cached[2]
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    value = digest.hexdigest()
    _hash_cache[key] = (stat.st_mtime_ns, stat.st_size, value)
    return value


def _source_files(source: Path) -> Iterable[Path]:
    """The files one configured source is read from.

    A folder is walked; a ``.pbip`` file stands for the project folder around it; any other
    file (a metadata JSON) is that file.
    """

    if source.is_file() and source.suffix.casefold() != ".pbip":
        yield source
        return
    root = source.parent if source.is_file() else source
    if not root.is_dir():
        return
    for folder, directories, files in os.walk(root):
        directories[:] = sorted(name for name in directories if not name.startswith("."))
        for name in sorted(files):
            if name.startswith(".") or name.casefold() in _SKIPPED_FILES:
                continue
            yield Path(folder) / name


def _display(path: Path, base: Path) -> str:
    try:
        return Path(os.path.relpath(path, base)).as_posix()
    except ValueError:  # another drive on Windows
        return path.as_posix()


def _own_files(config_path: Path) -> tuple[set[Path], tuple[str, ...]]:
    """The files PBIBrain writes for this project, and the name prefixes of the database files (WAL, lock)."""

    base = config_path.resolve().parent
    files = {config_path.resolve(), snapshot_path(config_path), (base / "connection.json").resolve()}
    prefixes: list[str] = []
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        from backend.projects import _project_paths

        paths = _project_paths(config, base)
    except (OSError, ValueError, KeyError, TypeError):
        paths = {}
    for key, path in paths.items():
        files.add(Path(path).resolve())
        if key == "database":
            prefixes.append(Path(path).name)
    return files, tuple(prefixes)


def source_fingerprint(config_path: str | Path, source_paths: Iterable[Path]) -> dict[str, str]:
    """``{file: sha256}`` for every file of the configured sources, paths relative to the config folder."""

    base = Path(config_path).resolve().parent
    own_files, own_prefixes = _own_files(Path(config_path))
    hashes: dict[str, str] = {}
    for source in source_paths:
        source = Path(source)
        root = (source.parent if source.suffix.casefold() == ".pbip" else source).resolve()
        # A source below the config folder (``C:\Reports\brain.json`` with ``C:\Reports\Sales\Sales.pbip``)
        # is hashed. A source that is the config folder or holds it (the app's ``<project>/.pbibrain``
        # layout) leaves the config folder out: those files are PBIBrain's own.
        below_base = root != base and root.is_relative_to(base)
        for path in _source_files(source):
            resolved = path.resolve()
            if resolved in own_files or any(resolved.name.startswith(prefix) and resolved.parent == base
                                            for prefix in own_prefixes):
                continue
            if not below_base and resolved.is_relative_to(base):
                continue
            if len(hashes) >= MAX_SOURCE_FILES:
                return hashes
            try:
                hashes[_display(path, base)] = _file_hash(path)
            except OSError:
                continue
    return hashes


def _compact_record(record: dict[str, Any]) -> dict[str, Any]:
    """One serialized node or edge without the copies and parser detail no read route uses.

    ``to_dict`` repeats every property at the top level; the loader reads them back from
    ``properties``. ``dax_ast`` is the cached parse tree (only the scanner reads it). The
    ``behavior`` lists inside edge evidence repeat the same nested record for each measure
    that reads a table, which grows with the square of the model size; three are kept.
    """

    properties = {key: value for key, value in (record.get("properties") or {}).items() if key not in _DROPPED_PROPERTIES}
    compact = {key: value for key, value in record.items()
               if key != "properties" and key not in _DROPPED_PROPERTIES
               and (key in _RECORD_FIELDS or key not in properties or properties[key] != value)}
    if properties:
        compact["properties"] = properties
    evidence = compact.get("evidence")
    if isinstance(evidence, list):
        compact["evidence"] = [_trim_behavior(item) for item in evidence]
    return compact


def _trim_behavior(item: Any) -> Any:
    if isinstance(item, dict) and isinstance(item.get("behavior"), list) and len(item["behavior"]) > _MAX_BEHAVIORS:
        return {**item, "behavior": item["behavior"][:_MAX_BEHAVIORS], "behavior_count": len(item["behavior"])}
    return item


_DROPPED_PROPERTIES = {"dax_ast"}
# Fields node_from_dict / edge_from_dict read from the top level; a property never replaces them.
_RECORD_FIELDS = {"id", "type", "name", "description", "model_id", "report_id", "source_id", "status", "source",
                  "from_id", "to_id", "confidence", "evidence", "evidence_class"}
_MAX_BEHAVIORS = 3


def write_agent_snapshot(project: Any, repository: Any, *, scanned_at: str | None = None) -> Path:
    """Write the graph and source hashes of a finished scan. Atomic: a reader sees the old or the new file."""

    from backend.graph.schema import GRAPH_SCHEMA_VERSION, serialize_edges, serialize_nodes

    config_path = Path(project.config_path)
    target = snapshot_path(config_path)
    payload = {
        "version": SNAPSHOT_VERSION,
        "scanned_at": scanned_at or datetime.now(timezone.utc).isoformat(),
        "project": project.get_config().get("name"),
        "sources": source_fingerprint(config_path, project.source_paths()),
        "graph": {"schema_version": GRAPH_SCHEMA_VERSION,
                  "nodes": [_compact_record(item) for item in serialize_nodes(repository.all_nodes())],
                  "edges": [_compact_record(item) for item in serialize_edges(repository.all_edges())]},
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    staged = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    staged.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str), encoding="utf-8")
    os.replace(staged, target)
    return target


def load_agent_snapshot(config_path: str | Path) -> dict[str, Any] | None:
    path = snapshot_path(config_path)
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping) or payload.get("version") != SNAPSHOT_VERSION:
        raise ValueError(f"Unsupported agent snapshot: {path}. Rescan the project in PBIBrain.")
    return dict(payload)


def freshness(config_path: str | Path, recorded: Mapping[str, str] | None, *, source_paths: Iterable[Path] | None = None) -> dict[str, Any]:
    """Compare the hashes recorded at the last scan with the source files now on disk."""

    if recorded is None:
        return {"stale": None, "reason": "No scan snapshot yet. Scan the project in PBIBrain."}
    if source_paths is None:
        from backend.projects import ProjectService

        try:
            source_paths = ProjectService(config_path).source_paths()
        except (OSError, ValueError) as exc:
            return {"stale": None, "reason": f"The project configuration could not be read: {exc}"}
    current = source_fingerprint(config_path, source_paths)
    changed = sorted(
        [path for path, digest in current.items() if recorded.get(path) != digest]
        + [path for path in recorded if path not in current]
    )
    if not changed:
        return {"stale": False}
    return {"stale": True, "changed_count": len(changed), "changed_files": changed[:MAX_CHANGED_LISTED],
            "note": "Source files changed since the last scan. Rescan in PBIBrain for current facts."}


_sources_cache: dict[str, tuple[tuple[int, int], dict[str, str] | None]] = {}


def recorded_sources(config_path: str | Path) -> dict[str, str] | None:
    """The source hashes of the last scan; the snapshot file is parsed again only when it changes."""

    path = snapshot_path(config_path)
    try:
        stat = path.stat()
    except OSError:
        return None
    key = (stat.st_mtime_ns, stat.st_size)
    cached = _sources_cache.get(str(path))
    if cached and cached[0] == key:
        return cached[1]
    try:
        payload = load_agent_snapshot(config_path)
    except (OSError, ValueError):
        payload = None
    sources = dict(payload.get("sources") or {}) if payload else None
    _sources_cache[str(path)] = (key, sources)
    return sources


def app_freshness(config_path: str | Path) -> dict[str, Any]:
    """Freshness of a reply the running app gave: its graph is the last scan of this project."""

    return {"source": "app", **freshness(config_path, recorded_sources(config_path))}


class SnapshotClient:
    """Answer the read-only Brain routes from the last scan snapshot; no app, no database."""

    source = "snapshot"

    def __init__(self, config_path: str | Path) -> None:
        from backend.api.app import BrainAPI, BrainApp
        from backend.graph.repository import GraphRepository
        from backend.projects import ProjectService

        self.config_path = Path(config_path).resolve()
        payload = load_agent_snapshot(self.config_path)
        if payload is None:
            raise RuntimeError("PBIBrain is not running and this project has no scan snapshot yet. "
                               "Open the project in PBIBrain and scan it once, then retry.")
        self.snapshot = payload
        self.scanned_at = payload.get("scanned_at")
        repository = GraphRepository(use_native=False)
        repository._load_payload(payload["graph"])
        repository.storage = "snapshot"
        repository.last_scan = self.scanned_at
        self.recorded = dict(payload.get("sources") or {})
        project = ProjectService(self.config_path)
        overrides = project.paths()["overrides"]
        self.app = BrainApp(BrainAPI(repository, overrides_path=overrides))

    def _handle(self, method: str, path: str, body: Mapping[str, Any] | None = None) -> dict[str, Any]:
        status, reply = self.app.handle(method, "/api/" + path, body)
        if status >= 400:
            detail = reply.get("error") if isinstance(reply, Mapping) else None
            raise ValueError(str(detail or f"snapshot route failed with status {status}"))
        return reply if isinstance(reply, dict) else {"items": reply}

    def get(self, path: str, **params: Any) -> dict[str, Any]:
        if path == "pending-changes":
            # Issue #17: the files are compared with this snapshot directly; no app is needed.
            from backend.pending_changes import compute_pending_changes

            return compute_pending_changes(self.config_path)
        if not any(path == route or (route.endswith("/") and path.startswith(route)) for route in SNAPSHOT_GET_ROUTES):
            raise RuntimeError("This read needs the running PBIBrain app. Open the project in PBIBrain, then retry.")
        query = urlencode({key: value for key, value in params.items() if value is not None})
        return self._handle("GET", path + (f"?{query}" if query else ""))

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if path not in SNAPSHOT_POST_ROUTES:
            raise RuntimeError("This analysis needs the running PBIBrain app. Open the project in PBIBrain, then retry.")
        return self._handle("POST", path, payload)

    def devcenter(self, method: str, path: str, query: dict[str, Any] | None, body: dict[str, Any] | None) -> dict[str, Any]:
        return {"error": {"code": "app_not_running",
                          "message": "Development Center tools act on the session open in the app. Open the project in PBIBrain, then retry.",
                          "details": {}}}

    def freshness(self) -> dict[str, Any]:
        return {"source": "snapshot", "snapshot_at": self.scanned_at, **freshness(self.config_path, self.recorded)}
