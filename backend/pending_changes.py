"""Pending changes: project files that changed outside the app since the last scan (issue #17).

The last scan wrote the agent snapshot (``.pbibrain/agent-snapshot.json``): the graph and a
SHA-256 hash of every source file. :func:`compute_pending_changes` hashes the files again
(unchanged files are not read again), and when some differ it scans the sources into a graph
without publishing anything and runs the shared safety check (:mod:`backend.safety`) on the
two graphs. The reply lists the changed files and the objects created, deleted, renamed or
changed, with the objects each change breaks or needs.

:class:`SourceWatcher` runs that check on a timer in the app, so a change made by an agent or
a person in another program shows a warning. It polls instead of using OS file events: a
project has a few hundred files, the hash cache makes a poll cheap, and polling behaves the
same on Windows, macOS, Linux and network drives.

Nothing here writes to the project, the graph, the identity map or the snapshot.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from backend.mcp_snapshot import MAX_CHANGED_LISTED, _compact_record, load_agent_snapshot, source_fingerprint
from backend.safety import assess_change

LOGGER = logging.getLogger(__name__)

PENDING_VERSION = 1
DEFAULT_INTERVAL_SECONDS = 5.0
# A watcher nobody reads for this long stops; the next read starts it again.
DEFAULT_IDLE_SECONDS = 120.0
MAX_FILES_LISTED = 50

_cache: dict[str, tuple[tuple, dict[str, Any]]] = {}
_cache_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _graph_payload(graph: Any) -> dict[str, Any]:
    from backend.graph.schema import serialize_edges, serialize_nodes

    return {"nodes": [_compact_record(item) for item in serialize_nodes(graph.nodes)],
            "edges": [_compact_record(item) for item in serialize_edges(graph.edges)]}


def _local_part(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    """The last-scan graph without the models and reports the preview did not read.

    The preview scan reads local files only, so a cloud model or report is missing from it.
    In a project with cloud items, a root that is missing from the preview is left out of the
    compare rather than shown as deleted (``cloud_not_checked`` says so in the reply).
    """

    roots = {node["id"] for node in after.get("nodes", []) if node.get("type") in {"MODEL", "REPORT"}}
    known = {node["id"] for node in before.get("nodes", []) if node.get("type") in {"MODEL", "REPORT"}}
    cloud = known - roots

    def local(node: Mapping[str, Any]) -> bool:
        root = node["id"] if node.get("type") in {"MODEL", "REPORT"} else node.get("report_id") or node.get("model_id")
        return root not in cloud

    nodes = [node for node in before.get("nodes", []) if local(node)]
    kept = {node["id"] for node in nodes}
    edges = [edge for edge in before.get("edges", []) if edge.get("from_id") in kept and edge.get("to_id") in kept]
    return {"nodes": nodes, "edges": edges}


def compute_pending_changes(config_path: str | Path, *, project: Any = None) -> dict[str, Any]:
    """Changes in the project files since the last scan, with their Breaks and Needs."""

    from backend.projects import ProjectService

    config_path = Path(config_path).resolve()
    project = project or ProjectService(config_path)
    snapshot = load_agent_snapshot(config_path)
    if snapshot is None:
        return {"pending_version": PENDING_VERSION, "status": "NO_SCAN", "checked_at": _now(),
                "note": "No scan yet. Scan the project in PBIBrain first; changes are measured against the last scan."}
    recorded = dict(snapshot.get("sources") or {})
    current = source_fingerprint(config_path, project.source_paths())
    files = sorted(
        [{"file": path, "change": "changed" if path in recorded else "created"} for path, digest in current.items() if recorded.get(path) != digest]
        + [{"file": path, "change": "deleted"} for path in recorded if path not in current],
        key=lambda item: item["file"])
    base = {"pending_version": PENDING_VERSION, "checked_at": _now(), "scanned_at": snapshot.get("scanned_at")}
    if not files:
        return {**base, "status": "UNCHANGED", "file_count": 0, "files": []}
    key = (snapshot.get("scanned_at"), tuple(sorted(current.items())))
    with _cache_lock:
        cached = _cache.get(str(config_path))
    if cached and cached[0] == key:
        return {**cached[1], "checked_at": base["checked_at"]}
    reply: dict[str, Any] = {**base, "file_count": len(files), "files": files[:MAX_FILES_LISTED]}
    try:
        after = _graph_payload(project.preview_graph())
    except Exception as exc:  # noqa: BLE001 - a half-saved file must not stop the watcher
        reply.update(status="UNREADABLE", error=str(exc)[:500],
                     note="The changed files could not be read as a model or report. They may still be saving; the check runs again.")
        return reply
    before = snapshot.get("graph") or {}
    if project.get_config().get("cloud_sources"):
        before = _local_part(before, after)
        reply["cloud_not_checked"] = True
    safety = assess_change(before, after)
    reply.update(status=safety["status"], safety=safety,
                 note="Files changed outside PBIBrain since the last scan. Breaks are objects that still use a deleted "
                      "or renamed object. Rescan in PBIBrain to accept the files as the new state.")
    with _cache_lock:
        _cache[str(config_path)] = (key, reply)
    return reply


class SourceWatcher:
    """Run :func:`compute_pending_changes` on a timer and keep the latest result.

    ``on_change`` is called with the new result when its status or file list changes. The app
    reads :meth:`read` from its pending-changes route, so a slow preview scan of a big model
    never blocks a request. With ``idle_timeout`` the thread stops when nobody has read the
    result for that long (an app that switched project leaves no thread behind).
    """

    def __init__(self, config_path: str | Path, *, interval: float = DEFAULT_INTERVAL_SECONDS,
                 on_change: Callable[[dict[str, Any]], None] | None = None, project: Any = None,
                 idle_timeout: float | None = None) -> None:
        self.config_path = Path(config_path).resolve()
        self.interval = interval
        self.idle_timeout = idle_timeout
        self._last_read = time.monotonic()
        self.on_change = on_change
        self.project = project
        self.latest: dict[str, Any] | None = None
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._generation = 0

    def check(self) -> dict[str, Any]:
        with self._lock:
            generation = self._generation
        result = compute_pending_changes(self.config_path, project=self.project)
        with self._lock:
            if generation != self._generation:
                return result  # a scan finished during this check; its result is already old
            previous, self.latest = self.latest, result
        if self.on_change and (previous is None or (previous.get("status"), previous.get("files")) != (result.get("status"), result.get("files"))):
            try:
                self.on_change(result)
            except Exception:  # noqa: BLE001 - a listener error never stops the watcher
                LOGGER.warning("A pending-changes listener failed", exc_info=True)
        return result

    def read(self) -> dict[str, Any]:
        """The latest result, starting the watcher when it is not running."""

        self._last_read = time.monotonic()
        self.start()
        with self._lock:
            latest = self.latest
        return latest or {"pending_version": PENDING_VERSION, "status": "CHECKING", "checked_at": _now()}

    def reset(self) -> None:
        """Forget the latest result (after a scan) and check again at once."""

        with self._lock:
            self.latest = None
            self._generation += 1
        if self._thread is not None and self._thread.is_alive():
            self._wake.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            if self.idle_timeout is not None and time.monotonic() - self._last_read > self.idle_timeout:
                return
            try:
                self.check()
            except Exception:  # noqa: BLE001 - keep watching after a failed check
                LOGGER.warning("The source watcher check failed", exc_info=True)
            self._wake.wait(self.interval)
            self._wake.clear()

    def start(self) -> "SourceWatcher":
        if self._thread is None or not self._thread.is_alive():
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="pbibrain-source-watcher", daemon=True)
            self._thread.start()
        return self

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout)
            self._thread = None

    def wait_for(self, predicate: Callable[[dict[str, Any]], bool], timeout: float = 10.0) -> dict[str, Any] | None:
        """Test helper: the latest result once it matches ``predicate``, else None after ``timeout``."""

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                latest = self.latest
            if latest is not None and predicate(latest):
                return latest
            time.sleep(0.05)
        return None
