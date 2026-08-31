"""Graph repository abstraction backed by LadybugDB.

The JSON implementation is an explicit test double selected with
``use_native=False``.  Production callers use the native Ladybug store.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .schema import Edge, Node, edge_from_dict, node_from_dict, serialize_edges, serialize_nodes, ladybug_schema

LOGGER = logging.getLogger(__name__)


def _json_default(value: Any) -> str:
    return str(value)


class GraphRepository:
    """Store and query canonical nodes and edges in LadybugDB."""

    def __init__(self, path: str | Path | None = None, *, use_native: bool | None = None) -> None:
        self.path = Path(path) if path is not None else None
        self.nodes: dict[str, Node] = {}
        self.edges: dict[str, Edge] = {}
        self._native = None
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

        self._try_open_native()
        if self._native is None:
            detail = getattr(self, "_native_error", None)
            message = "LadybugDB is required for the production graph repository"
            if detail:
                message += f": {detail}"
            message += "; pass use_native=False only for an explicit test double"
            raise RuntimeError(message)

    @property
    def is_native(self) -> bool:
        return self._native is not None

    def _try_open_native(self) -> None:
        try:
            import ladybug as lb  # type: ignore[import-not-found]
        except ImportError:
            self._native_error = "the ladybug package is not installed"
            return
        try:
            if self.path:
                self.path.parent.mkdir(parents=True, exist_ok=True)
            database = lb.Database(str(self.path) if self.path else ":memory:")
            connection = lb.Connection(database)
            for statement in ladybug_schema():
                try:
                    connection.execute(statement)
                except Exception as exc:  # existing schema is safe to reuse
                    if "already" not in str(exc).lower() and "exists" not in str(exc).lower():
                        raise
            self._native = (database, connection)
            self.storage = "ladybug"
            self._load_native()
        except Exception as exc:
            self._native_error = str(exc)
            LOGGER.debug("LadybugDB initialization failed", exc_info=True)
            self._native = None

    def _native_rows(self, query: str) -> list[Mapping[str, Any]]:
        if self._native is None:
            return []
        result = self._native[1].execute(query)
        rows_as_dict = getattr(result, "rows_as_dict", None)
        if callable(rows_as_dict):
            rows = rows_as_dict().get_all()
        else:
            rows = result.get_all()
        return [row if isinstance(row, Mapping) else {} for row in rows]

    def _load_native(self) -> None:
        """Hydrate the in-memory query index from an existing Ladybug graph."""

        node_query = (
            "MATCH (n:BrainNode) RETURN n.id AS id, n.type AS type, n.name AS name, "
            "n.description AS description, n.model_id AS model_id, n.report_id AS report_id, "
            "n.source_id AS source_id, n.status AS status, n.source AS source, n.properties AS properties"
        )
        edge_query = (
            "MATCH (a:BrainNode)-[e:BrainEdge]->(b:BrainNode) RETURN e.id AS id, e.type AS type, "
            "a.id AS from_id, b.id AS to_id, e.source AS source, e.confidence AS confidence, "
            "e.status AS status, e.evidence_class AS evidence_class, e.evidence AS evidence, e.properties AS properties"
        )
        for row in self._native_rows(node_query):
            properties = row.get("properties", {})
            if isinstance(properties, str):
                properties = json.loads(properties) if properties else {}
            node = Node(
                id=row.get("id", ""),
                type=row.get("type", "UNKNOWN"),
                name=row.get("name", ""),
                description=row.get("description"),
                model_id=row.get("model_id"),
                report_id=row.get("report_id"),
                source_id=row.get("source_id"),
                status=row.get("status", "factual"),
                source=row.get("source", "model_metadata"),
                properties=properties if isinstance(properties, Mapping) else {},
            )
            self.nodes[node.id] = node
        for row in self._native_rows(edge_query):
            evidence = row.get("evidence", [])
            properties = row.get("properties", {})
            if isinstance(evidence, str):
                evidence = json.loads(evidence) if evidence else []
            if isinstance(properties, str):
                properties = json.loads(properties) if properties else {}
            edge = Edge(
                id=row.get("id", ""),
                type=row.get("type", "UNKNOWN"),
                from_id=row.get("from_id", ""),
                to_id=row.get("to_id", ""),
                source=row.get("source", "model_metadata"),
                confidence=row.get("confidence", 1.0),
                status=row.get("status", "factual"),
                evidence=evidence if isinstance(evidence, list) else [evidence],
                evidence_class=row.get("evidence_class", "FACT"),
                properties=properties if isinstance(properties, Mapping) else {},
            )
            self.edges[edge.id] = edge

    def _load_payload(self, payload: Mapping[str, Any]) -> None:
        for value in payload.get("nodes", []):
            node = node_from_dict(value)
            self.nodes[node.id] = node
        for value in payload.get("edges", []):
            edge = edge_from_dict(value)
            self.edges[edge.id] = edge

    def _payload(self) -> dict[str, Any]:
        return {"nodes": serialize_nodes(self.nodes.values()), "edges": serialize_edges(self.edges.values())}

    def _persist(self) -> None:
        if self._native is not None:
            self._sync_native()
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
        # ponytail: rebuild the tiny canonical tables per write; incremental
        # mutation belongs to Phase 5 and this keeps the native path reliable.
        try:
            connection.execute("MATCH (n:BrainNode) DETACH DELETE n")
        except Exception as exc:
            LOGGER.error("LadybugDB graph replacement failed", exc_info=True)
            raise RuntimeError(f"LadybugDB graph replacement failed: {exc}") from exc
        for node in self.nodes.values():
            props = json.dumps(node.properties, ensure_ascii=False, sort_keys=True, default=_json_default)
            query = (
                "CREATE (n:BrainNode {"
                "id: $id, type: $type, name: $name, description: $description, "
                "model_id: $model_id, report_id: $report_id, source_id: $source_id, "
                "status: $status, source: $source, properties: $properties"
                "})"
            )
            connection.execute(
                query,
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
            query = (
                "MATCH (a:BrainNode {id: $from_id}), (b:BrainNode {id: $to_id}) "
                "CREATE (a)-[:BrainEdge {"
                "id: $id, type: $type, source: $source, confidence: $confidence, "
                "status: $status, evidence_class: $evidence_class, "
                "evidence: $evidence, properties: $properties"
                "}]->(b)"
            )
            connection.execute(
                query,
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
        value = node_from_dict(node)
        self.nodes[value.id] = value
        self._persist()
        return value

    def upsert_nodes(self, nodes: Iterable[Node | Mapping[str, Any]]) -> list[Node]:
        values = [node_from_dict(node) for node in nodes]
        for value in values:
            self.nodes[value.id] = value
        self._persist()
        return values

    add_node = upsert_node
    add_nodes = upsert_nodes

    def upsert_edge(self, edge: Edge | Mapping[str, Any]) -> Edge:
        value = edge_from_dict(edge)
        self.edges[value.id] = value
        self._persist()
        return value

    def upsert_edges(self, edges: Iterable[Edge | Mapping[str, Any]]) -> list[Edge]:
        values = [edge_from_dict(edge) for edge in edges]
        for value in values:
            self.edges[value.id] = value
        self._persist()
        return values

    add_edge = upsert_edge
    add_edges = upsert_edges

    def replace(self, nodes: Iterable[Node | Mapping[str, Any]], edges: Iterable[Edge | Mapping[str, Any]]) -> None:
        node_values = [node_from_dict(value) for value in nodes]
        edge_values = [edge_from_dict(value) for value in edges]
        self.nodes = {value.id: value for value in node_values}
        self.edges = {value.id: value for value in edge_values}
        self._persist()

    def clear(self) -> None:
        self.nodes.clear()
        self.edges.clear()
        self._persist()

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
        return self.nodes.get(str(object_id))

    get_node = get_object

    def all_nodes(self) -> list[Node]:
        return [self.nodes[key] for key in sorted(self.nodes)]

    def all_edges(self) -> list[Edge]:
        return [self.edges[key] for key in sorted(self.edges)]

    def search_objects(self, query: str) -> list[Node]:
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
        """Run trusted Cypher on native Ladybug or the explicit test double."""

        if self._native is not None:
            return self._native[1].execute(cypher, params or {})
        text = " ".join(str(cypher).split())
        if re.fullmatch(r"MATCH \(\w+:BrainNode\) RETURN \w+\.\*", text, re.I):
            return [node.to_dict() for node in self.all_nodes()]
        match = re.fullmatch(
            r"MATCH \(\w+:BrainNode \{type:\s*'([^']+)'\}\) RETURN \w+\.\*", text, re.I
        )
        if match:
            wanted = match.group(1).upper()
            return [node.to_dict() for node in self.all_nodes() if node.type == wanted]
        raise RuntimeError("Cypher fallback supports only simple BrainNode reads; install ladybug for query_graph")

    execute = query_graph

    def close(self) -> None:
        if self._native is not None:
            database = self._native[0]
            connection = self._native[1]
            close = getattr(connection, "close", None)
            if close:
                close()
            close_database = getattr(database, "close", None)
            if close_database:
                close_database()
            self._native = None

    def __enter__(self) -> "GraphRepository":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()


class LadybugRepository(GraphRepository):
    """Explicit name for callers that want to document the canonical store."""
