"""Graph repository backed by SQLite.

``use_sqlite=False`` keeps the graph in memory, or in a JSON file when a path is
given; scans stage their graphs that way and tests use it as a double.
Production callers use the SQLite store.
"""

from __future__ import annotations

import json
import os
import logging
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from collections.abc import Iterable, Iterator, Mapping, Sequence

from .schema import Edge, Node, edge_from_dict, node_from_dict, serialize_edges, serialize_nodes, GRAPH_SCHEMA_VERSION
from .sqlite_store import SQLiteStore

LOGGER = logging.getLogger(__name__)


def _json_default(value: Any) -> str:
    return str(value)


class GraphRepository:
    """Store and query canonical nodes and edges in SQLite."""

    def __init__(self, path: str | Path | None = None, *, use_sqlite: bool = True) -> None:
        self.path = Path(path) if path is not None else None
        self.nodes: dict[str, Node] = {}
        self.edges: dict[str, Edge] = {}
        self._store: SQLiteStore | None = None
        self.storage = "memory"
        # Validation is a read-only runtime result.  Source synchronization
        # owns when it is refreshed; graph persistence stays canonical facts.
        self.validation_result: Any = None
        # Counts every write. Readers that cache derived answers compare it to know when to drop them.
        self.revision = 0
        self._reading = threading.local()
        self._shared_read: tuple[tuple[Any, ...], list[Node], list[Edge]] | None = None
        self._shared_lock = threading.Lock()

        if not use_sqlite:
            if self.path and self.path.is_file():
                payload = json.loads(self.path.read_text(encoding="utf-8"))
                self._load_payload(payload)
                self.storage = "json"
            elif self.path:
                self.storage = "json"
            else:
                self.storage = "memory"
            return

        try:
            self._store = SQLiteStore(self.path)
            self.storage = "trail"
            self._load_store()
        except Exception as exc:
            LOGGER.debug("SQLiteStore initialization failed", exc_info=True)
            self._store = None
            raise RuntimeError(f"Failed to initialize graph storage: {exc}") from exc

    # State that answers are built from but that is set as a plain attribute (the scanner sets the
    # scan time and the validation result this way). Each change counts as a write, so readers
    # that keep answers per revision never show the state from before it.
    _COUNTED = frozenset({"validation_result", "last_scan"})

    def __setattr__(self, name: str, value: Any) -> None:
        object.__setattr__(self, name, value)
        if name in self._COUNTED and "revision" in self.__dict__:
            object.__setattr__(self, "revision", self.revision + 1)

    def _load_store(self) -> None:
        if self._store is None:
            return
        for node in self._store.all_nodes():
            self.nodes[node.id] = node
        for edge in self._store.all_edges():
            self.edges[edge.id] = edge

    def _load_payload(self, payload: Mapping[str, Any]) -> None:
        version = payload.get("schema_version")
        if version != GRAPH_SCHEMA_VERSION:
            raise ValueError(f"The graph file has schema version {version!r}. This app reads version {GRAPH_SCHEMA_VERSION}")
        for value in payload.get("nodes", []):
            node = node_from_dict(value)
            self.nodes[node.id] = node
        for value in payload.get("edges", []):
            edge = edge_from_dict(value)
            self.edges[edge.id] = edge

    def _payload(self) -> dict[str, Any]:
        return {"schema_version": GRAPH_SCHEMA_VERSION, "nodes": serialize_nodes(self.nodes.values()), "edges": serialize_edges(self.edges.values())}

    def _persist(self) -> None:
        if self._store is not None:
            self._store.replace_all(self.nodes.values(), self.edges.values())
            return
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # One record at a time: a single dump of the whole graph is one call that holds the interpreter
        # lock, so every other thread (the requests a scan answers meanwhile) stopped for 0.7 s on the large
        # project (review 04). Written beside the file and moved into place, so a reader never sees half.
        payload = self._payload()
        partial = self.path.with_name(self.path.name + ".partial")
        with partial.open("w", encoding="utf-8") as handle:
            handle.write("{\n")
            for index, key in enumerate(sorted(payload)):
                value = payload[key]
                handle.write(f'  {json.dumps(key)}: ')
                if isinstance(value, list) and value:
                    handle.write("[\n")
                    for position, item in enumerate(value):
                        text = json.dumps(item, ensure_ascii=False, indent=2, sort_keys=True, default=_json_default)
                        handle.write("    " + text.replace("\n", "\n    ") + (",\n" if position < len(value) - 1 else "\n"))
                    handle.write("  ]")
                else:
                    handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True, default=_json_default))
                handle.write(",\n" if index < len(payload) - 1 else "\n")
            handle.write("}\n")
        os.replace(partial, self.path)

    def upsert_node(self, node: Node | Mapping[str, Any]) -> Node:
        self.revision += 1
        value = node if isinstance(node, Node) else node_from_dict(node)
        self.nodes[value.id] = value
        if self._store is not None:
            self._store.upsert_node(value)
        elif self.path is not None:
            self._persist()
        return value

    def upsert_nodes(self, nodes: Iterable[Node | Mapping[str, Any]]) -> list[Node]:
        self.revision += 1
        values = [node if isinstance(node, Node) else node_from_dict(node) for node in nodes]
        for v in values:
            self.nodes[v.id] = v
        if self._store is not None:
            for v in values:
                self._store.upsert_node(v)
        elif self.path is not None:
            self._persist()
        return values

    def upsert_edge(self, edge: Edge | Mapping[str, Any]) -> Edge:
        self.revision += 1
        value = edge if isinstance(edge, Edge) else edge_from_dict(edge)
        self.edges[value.id] = value
        if self._store is not None:
            self._store.upsert_edge(value)
        elif self.path is not None:
            self._persist()
        return value

    def upsert_edges(self, edges: Iterable[Edge | Mapping[str, Any]]) -> list[Edge]:
        self.revision += 1
        values = [edge if isinstance(edge, Edge) else edge_from_dict(edge) for edge in edges]
        for v in values:
            self.edges[v.id] = v
        if self._store is not None:
            for v in values:
                self._store.upsert_edge(v)
        elif self.path is not None:
            self._persist()
        return values

    def replace(self, nodes: Iterable[Node | Mapping[str, Any]], edges: Iterable[Edge | Mapping[str, Any]]) -> None:
        node_values = [node if isinstance(node, Node) else node_from_dict(node) for node in nodes]
        edge_values = [edge if isinstance(edge, Edge) else edge_from_dict(edge) for edge in edges]
        previous_nodes, previous_edges = self.nodes, self.edges
        self.revision += 1
        self.nodes = {value.id: value for value in node_values}
        self.edges = {value.id: value for value in edge_values}
        try:
            self._persist()
        except Exception:
            self.nodes, self.edges = previous_nodes, previous_edges
            raise

    def clear(self) -> None:
        self.replace([], [])

    def set_validation_result(self, result: Any) -> Any:
        """Publish the latest validation result without changing graph facts."""

        self.validation_result = result
        return result

    def get_validation_result(self) -> Any:
        return self.validation_result

    @property
    def validation_state(self) -> str:
        result = self.validation_result
        if result is None:
            return "not_run"
        state = getattr(result, "state", None)
        if state is not None:
            return str(state)
        if isinstance(result, Mapping):
            return str(result.get("state", result.get("status", "not_run")))
        return "not_run"

    def get_object(self, object_id: str) -> Node | None:
        node = self.nodes.get(str(object_id))
        if node is not None:
            return node
        if self._store is not None:
            found = self._store.get_node(str(object_id))
            if found is not None:
                self.nodes[found.id] = found
            return found
        return None

    @contextmanager
    def reading(self) -> Iterator[None]:
        """Serve all_nodes and all_edges from one shared read of the store while the block runs.

        A read-only request asks for the full lists many times, and each read of the store
        decodes every row again (about 1.2 s for 14,000 objects). Inside this block the lists
        are read once per revision and shared. Use it only around code that does not change
        the objects it gets; writers keep the fresh copies they have today.
        """

        depth = getattr(self._reading, "depth", 0)
        self._reading.depth = depth + 1
        try:
            yield
        finally:
            self._reading.depth = depth

    def _shared(self) -> tuple[list[Node], list[Edge]] | None:
        if self._store is None or not getattr(self._reading, "depth", 0):
            return None
        stamp: tuple[Any, ...] = (self.revision,)
        if self.path is not None:
            for candidate in (self.path, Path(str(self.path) + "-wal")):
                try:
                    stamp += (candidate.stat().st_mtime_ns,)
                except OSError:
                    stamp += (0,)
        with self._shared_lock:
            if self._shared_read is None or self._shared_read[0] != stamp:
                self._shared_read = (stamp, self._store.all_nodes(), self._store.all_edges())
            return self._shared_read[1], self._shared_read[2]

    def all_nodes(self) -> list[Node]:
        shared = self._shared()
        if shared is not None:
            return list(shared[0])
        if self._store is not None:
            return self._store.all_nodes()
        return [self.nodes[key] for key in sorted(self.nodes)]

    def all_edges(self) -> list[Edge]:
        shared = self._shared()
        if shared is not None:
            return list(shared[1])
        if self._store is not None:
            return self._store.all_edges()
        return [self.edges[key] for key in sorted(self.edges)]

    def search_objects(self, query: str) -> list[Node]:
        if self._store is not None:
            return self._store.search_objects(query)
        needle = str(query).casefold()
        if not needle:
            return self.all_nodes()
        return [
            node
            for node in self.all_nodes()
            if needle in node.id.casefold()
            or needle in node.name.casefold()
            or needle in (node.description or "").casefold()
            or needle in json.dumps(node.properties, ensure_ascii=False, default=_json_default).casefold()
        ]

    def get_neighbors(
        self,
        object_id: str,
        edge_types: Sequence[str] | None = None,
        *,
        direction: str = "both",
    ) -> list[Node]:
        if self._store is not None:
            return self._store.get_neighbors(object_id, edge_types, direction=direction)
        object_id = str(object_id)
        if isinstance(edge_types, str):
            edge_types = [edge_types]
        allowed = {str(item).upper() for item in edge_types} if edge_types else None
        direction = direction.lower()
        result_ids: set[str] = set()
        for edge in self.edges.values():
            if allowed and edge.type not in allowed:
                continue
            if edge.from_id == object_id and direction in {"both", "out", "outgoing"}:
                result_ids.add(edge.to_id)
            if edge.to_id == object_id and direction in {"both", "in", "incoming"}:
                result_ids.add(edge.from_id)
        return [self.nodes[item] for item in sorted(result_ids) if item in self.nodes]

    def get_dependencies(self, object_id: str) -> list[Node]:
        return self.get_neighbors(object_id, ["DEPENDS_ON"], direction="out")

    def get_dependents(self, object_id: str) -> list[Node]:
        return self.get_neighbors(object_id, ["DEPENDS_ON"], direction="in")

    def get_usage(self, object_id: str) -> list[Node]:
        if self._store is not None:
            return self._store.get_usage(object_id)
        # Report visuals point at model objects with USES.  Include any other
        # incoming usage edge too; callers can filter by node type.
        target = str(object_id)
        ids = {edge.from_id for edge in self.edges.values() if edge.to_id == target and edge.type == "USES"}
        return [self.nodes[item] for item in sorted(ids) if item in self.nodes]

    def get_edges(
        self,
        *,
        from_id: str | None = None,
        to_id: str | None = None,
        edge_types: Sequence[str] | None = None,
    ) -> list[Edge]:
        if self._store is not None:
            return self._store.get_edges(from_id=from_id, to_id=to_id, edge_types=edge_types)
        if isinstance(edge_types, str):
            edge_types = [edge_types]
        allowed = {str(item).upper() for item in edge_types} if edge_types else None
        return [
            edge
            for edge in self.all_edges()
            if (from_id is None or edge.from_id == str(from_id))
            and (to_id is None or edge.to_id == str(to_id))
            and (allowed is None or edge.type in allowed)
        ]

    def find_path(self, from_id: str, to_id: str) -> list[Node]:
        """Return a shortest factual path, or an empty list when absent."""
        if self._store is not None:
            return self._store.find_path(from_id, to_id)

        start, target = str(from_id), str(to_id)
        if start not in self.nodes or target not in self.nodes:
            return []
        queue: list[str] = [start]
        previous: dict[str, str | None] = {start: None}
        while queue:
            current = queue.pop(0)
            if current == target:
                break
            for neighbor in self.get_neighbors(current, direction="out"):
                if neighbor.id not in previous:
                    previous[neighbor.id] = current
                    queue.append(neighbor.id)
        if target not in previous:
            return []
        path: list[Node] = []
        current: str | None = target
        while current is not None:
            path.append(self.nodes[current])
            current = previous[current]
        return list(reversed(path))

    def close(self) -> None:
        if self._store is not None:
            self._store.close()
            self._store = None

    def __enter__(self) -> GraphRepository:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

