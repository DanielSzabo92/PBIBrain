"""Graph repository abstraction backed by pure-Python SQLite and Trail.

The JSON implementation is an explicit test double selected with
``use_native=False``.  Production callers use the Trail SQLite store.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any
from collections.abc import Iterable, Mapping, Sequence

from .schema import Edge, Node, edge_from_dict, node_from_dict, serialize_edges, serialize_nodes, GRAPH_SCHEMA_VERSION
from .sqlite_store import SQLiteStore

LOGGER = logging.getLogger(__name__)


def _json_default(value: Any) -> str:
    return str(value)


class _NativeConnectionWrapper:
    """Compatibility bridge for native transaction and checkpoint operations."""

    def __init__(self, store: SQLiteStore) -> None:
        self._store = store

    def execute(self, statement: str, params: Any = None) -> Any:
        conn = self._store._get_connection()
        stmt = statement.strip()
        if stmt.startswith("MATCH (n:BrainNode) DETACH DELETE"):
            conn.execute("DELETE FROM edges;")
            return conn.execute("DELETE FROM nodes;")
        if stmt == "BEGIN TRANSACTION":
            return conn.execute("BEGIN IMMEDIATE;")
        if stmt == "COMMIT":
            return conn.commit()
        if stmt == "ROLLBACK":
            return conn.rollback()
        if stmt == "CHECKPOINT":
            return conn.execute("PRAGMA wal_checkpoint(PASSIVE);")
        return conn.execute(statement, params or ())

    def close(self) -> None:
        pass

    def __getattr__(self, name: str) -> Any:
        return getattr(self._store._get_connection(), name)


class GraphRepository:
    """Store and query canonical nodes and edges in SQLite + Trail."""

    def __init__(self, path: str | Path | None = None, *, use_native: bool | None = None) -> None:
        self.path = Path(path) if path is not None else None
        self.nodes: dict[str, Node] = {}
        self.edges: dict[str, Edge] = {}
        self._store: SQLiteStore | None = None
        self._native: tuple[Any, Any] | None = None
        self._native_error: str | None = None
        self.storage = "memory"
        # Validation is a read-only runtime result.  Source synchronization
        # owns when it is refreshed; graph persistence stays canonical facts.
        self.validation_result: Any = None

        if use_native is False:
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
            self._native = (self._store, _NativeConnectionWrapper(self._store))
            self.storage = "trail"
            self._load_store()
        except Exception as exc:
            self._native_error = str(exc)
            LOGGER.debug("SQLiteStore initialization failed", exc_info=True)
            self._store = None
            self._native = None
            raise RuntimeError(f"Failed to initialize graph storage: {exc}") from exc

    @property
    def is_native(self) -> bool:
        return self._store is not None

    def _load_store(self) -> None:
        if self._store is None:
            return
        for node in self._store.all_nodes():
            self.nodes[node.id] = node
        for edge in self._store.all_edges():
            self.edges[edge.id] = edge

    def _load_payload(self, payload: Mapping[str, Any]) -> None:
        from .migrations import migrate_payload

        payload = migrate_payload(payload)
        for value in payload.get("nodes", []):
            node = node_from_dict(value)
            self.nodes[node.id] = node
        for value in payload.get("edges", []):
            edge = edge_from_dict(value)
            self.edges[edge.id] = edge

    def _payload(self) -> dict[str, Any]:
        return {"schema_version": GRAPH_SCHEMA_VERSION, "nodes": serialize_nodes(self.nodes.values()), "edges": serialize_edges(self.edges.values())}

    def _persist(self) -> None:
        if self._native is not None:
            self._sync_native()
            return
        if self._store is not None:
            self._store.replace_all(self.nodes.values(), self.edges.values())
            return
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._payload(), ensure_ascii=False, indent=2, sort_keys=True, default=_json_default) + "\n",
            encoding="utf-8",
        )

    def _sync_native(self) -> None:
        if self._native is None:
            return
        _, connection = self._native
        try:
            connection.execute("BEGIN TRANSACTION")
            self._write_native_graph(connection)
            connection.execute("COMMIT")
        except Exception as exc:
            try:
                connection.execute("ROLLBACK")
            except Exception:
                LOGGER.debug("Native rollback unavailable", exc_info=True)
            LOGGER.error("Native graph replacement failed", exc_info=True)
            raise RuntimeError(f"Native graph replacement failed: {exc}") from exc
        try:
            connection.execute("CHECKPOINT")
        except Exception:
            LOGGER.warning("Graph committed, but native checkpoint failed; close the database cleanly", exc_info=True)

    def _write_native_graph(self, connection: Any) -> None:
        if self._store is not None and isinstance(connection, _NativeConnectionWrapper):
            self._store.replace_all(self.nodes.values(), self.edges.values(), in_transaction=True)
            return
        connection.execute("MATCH (n:BrainNode) DETACH DELETE n")
        for node in self.nodes.values():
            props = json.dumps(node.properties, ensure_ascii=False, sort_keys=True, default=_json_default)
            connection.execute(
                "CREATE (n:BrainNode {"
                "id: $id, type: $type, name: $name, description: $description, "
                "model_id: $model_id, report_id: $report_id, source_id: $source_id, "
                "status: $status, source: $source, properties: $properties"
                "})",
                {
                    "id": node.id,
                    "type": node.type,
                    "name": node.name,
                    "description": node.description,
                    "model_id": node.model_id,
                    "report_id": node.report_id,
                    "source_id": node.source_id,
                    "status": node.status,
                    "source": node.source,
                    "properties": props,
                },
            )
        for edge in self.edges.values():
            evidence = json.dumps(edge.evidence, ensure_ascii=False, sort_keys=True, default=_json_default)
            properties = json.dumps(edge.properties, ensure_ascii=False, sort_keys=True, default=_json_default)
            connection.execute(
                "MATCH (a:BrainNode {id: $from_id}), (b:BrainNode {id: $to_id}) "
                "CREATE (a)-[:BrainEdge {"
                "id: $id, type: $type, source: $source, confidence: $confidence, "
                "status: $status, evidence_class: $evidence_class, "
                "evidence: $evidence, properties: $properties"
                "}]->(b)",
                {
                    "from_id": edge.from_id,
                    "to_id": edge.to_id,
                    "id": edge.id,
                    "type": edge.type,
                    "source": edge.source,
                    "confidence": edge.confidence,
                    "status": edge.status,
                    "evidence_class": edge.evidence_class,
                    "evidence": evidence,
                    "properties": properties,
                },
            )

    def upsert_node(self, node: Node | Mapping[str, Any]) -> Node:
        value = node if isinstance(node, Node) else node_from_dict(node)
        self.nodes[value.id] = value
        if self._native is not None and not isinstance(self._native[1], _NativeConnectionWrapper):
            self._persist()
        elif self._store is not None:
            self._store.upsert_node(value)
        elif self.path is not None:
            self._persist()
        return value

    def upsert_nodes(self, nodes: Iterable[Node | Mapping[str, Any]]) -> list[Node]:
        values = [node if isinstance(node, Node) else node_from_dict(node) for node in nodes]
        for v in values:
            self.nodes[v.id] = v
        if self._store is not None:
            for v in values:
                self._store.upsert_node(v)
        elif self.path is not None:
            self._persist()
        return values

    add_node = upsert_node
    add_nodes = upsert_nodes

    def upsert_edge(self, edge: Edge | Mapping[str, Any]) -> Edge:
        value = edge if isinstance(edge, Edge) else edge_from_dict(edge)
        self.edges[value.id] = value
        if self._store is not None:
            self._store.upsert_edge(value)
        elif self.path is not None:
            self._persist()
        return value

    def upsert_edges(self, edges: Iterable[Edge | Mapping[str, Any]]) -> list[Edge]:
        values = [edge if isinstance(edge, Edge) else edge_from_dict(edge) for edge in edges]
        for v in values:
            self.edges[v.id] = v
        if self._store is not None:
            for v in values:
                self._store.upsert_edge(v)
        elif self.path is not None:
            self._persist()
        return values

    add_edge = upsert_edge
    add_edges = upsert_edges

    def replace(self, nodes: Iterable[Node | Mapping[str, Any]], edges: Iterable[Edge | Mapping[str, Any]]) -> None:
        node_values = [node if isinstance(node, Node) else node_from_dict(node) for node in nodes]
        edge_values = [edge if isinstance(edge, Edge) else edge_from_dict(edge) for edge in edges]
        previous_nodes, previous_edges = self.nodes, self.edges
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

    get_node = get_object

    def all_nodes(self) -> list[Node]:
        if self._store is not None:
            return self._store.all_nodes()
        return [self.nodes[key] for key in sorted(self.nodes)]

    def all_edges(self) -> list[Edge]:
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

    search = search_objects

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

    neighbors = get_neighbors

    def get_dependencies(self, object_id: str) -> list[Node]:
        return self.get_neighbors(object_id, ["DEPENDS_ON"], direction="out")

    dependencies = get_dependencies

    def get_dependents(self, object_id: str) -> list[Node]:
        return self.get_neighbors(object_id, ["DEPENDS_ON"], direction="in")

    dependents = get_dependents

    def get_usage(self, object_id: str) -> list[Node]:
        if self._store is not None:
            return self._store.get_usage(object_id)
        # Report visuals point at model objects with USES.  Include any other
        # incoming usage edge too; callers can filter by node type.
        target = str(object_id)
        ids = {edge.from_id for edge in self.edges.values() if edge.to_id == target and edge.type == "USES"}
        return [self.nodes[item] for item in sorted(ids) if item in self.nodes]

    usage = get_usage

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

    def query_graph(self, cypher: str, params: Mapping[str, Any] | None = None) -> Any:
        """Run trusted query on SQLite or the explicit test double."""

        text = " ".join(str(cypher).split())
        if re.fullmatch(r"MATCH \(\w+:BrainNode\) RETURN \w+\.\*", text, re.I):
            return [node.to_dict() for node in self.all_nodes()]
        match = re.fullmatch(
            r"MATCH \(\w+:BrainNode \{type:\s*'([^']+)'\}\) RETURN \w+\.\*", text, re.I
        )
        if match:
            wanted = match.group(1).upper()
            return [node.to_dict() for node in self.all_nodes() if node.type == wanted]
        if self._store is not None:
            conn = self._store._get_connection()
            cursor = conn.execute(cypher, params or ())
            return cursor.fetchall()
        raise RuntimeError("Cypher fallback supports only simple BrainNode reads")

    execute = query_graph

    def close(self) -> None:
        if self._store is not None:
            self._store.close()
            self._store = None

    def __enter__(self) -> GraphRepository:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()


class LadybugRepository(GraphRepository):
    """Explicit name for callers that want to document the canonical store."""
