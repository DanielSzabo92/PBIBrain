"""SQLite and Trail graph storage engine for PBIBrain.

Replaces LadybugDB with a pure-Python, zero-DLL SQLite engine providing:
- ACID transactions, write-ahead logging (WAL), and concurrent reader safety.
- Sub-millisecond lookups, indexed edge traversals, and FTS5 full-text search.
- Deterministic export of Trail cache cards and wiring (``.graph/wiring.json``,
  ``.cache/ask-index.json``, ``INDEX.md``, and per-file ``<path>.md`` cards).
"""

from __future__ import annotations

import collections
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from typing import Any
from collections.abc import Iterable, Mapping, Sequence

from .schema import (
    GRAPH_SCHEMA_VERSION,
    Edge,
    Node,
    edge_from_dict,
    node_from_dict,
    serialize_edges,
    serialize_nodes,
)

LOGGER = logging.getLogger(__name__)

TRAIL_GRAPH_VERSION = 1
ASK_INDEX_VERSION = 1

# Complete, non-lossy mappings between PBIBrain ontology and Trail kinds/relations
PBI_TYPE_TO_KIND: dict[str, str] = {
    "MODEL": "semantic_model",
    "TABLE": "table",
    "COLUMN": "column",
    "MEASURE": "measure",
    "RELATIONSHIP": "relationship",
    "CALCULATION_GROUP": "calculation_group",
    "CALCULATION_ITEM": "calculation_item",
    "HIERARCHY": "hierarchy",
    "LEVEL": "level",
    "PARTITION": "partition",
    "SHARED_EXPRESSION": "shared_expression",
    "USER_DEFINED_FUNCTION": "user_defined_function",
    "FIELD_PARAMETER": "field_parameter",
    "SECURITY_ROLE": "security_role",
    "ROLE_FILTER": "role_filter",
    "OLS_PERMISSION": "ols_permission",
    "DATA_SOURCE": "data_source",
    "REPORT": "report",
    "PAGE": "page",
    "VISUAL": "visual",
    "REPORT_MEASURE": "report_measure",
    "VISUAL_CALCULATION": "visual_calculation",
    "BOOKMARK": "bookmark",
    "PAGE_FILTER": "page_filter",
    "REPORT_FILTER": "report_filter",
    "VISUAL_FILTER": "visual_filter",
    "WORKSPACE": "workspace",
    "BUSINESS_CONCEPT": "business_concept",
    "KPI": "kpi",
    "METRIC_CONFLICT": "metric_conflict",
}

KIND_TO_PBI_TYPE: dict[str, str] = {value: key for key, value in PBI_TYPE_TO_KIND.items()}

PBI_EDGE_TO_RELATION: dict[str, str] = {
    "CONTAINS": "contains",
    "USES": "uses",
    "USES_MODEL": "uses_model",
    "DEPENDS_ON": "depends_on",
    "FILTERS": "filters",
    "MODIFIES_FILTER": "modifies_filter",
    "ACTIVATES_RELATIONSHIP": "activates_relationship",
    "MODIFIES_RELATIONSHIP": "modifies_relationship",
    "RELATES_TO": "relates_to",
    "IMPLEMENTS": "implements",
    "ALIASES": "aliases",
    "CONFLICTS_WITH": "conflicts_with",
    "INTERACTS_WITH": "interacts_with",
    "DRILLS_THROUGH_TO": "drills_through_to",
    "TOOLTIP_PAGE": "tooltip_page",
    "SYNCED_WITH": "synced_with",
    "FORMATS_BY": "formats_by",
    "SOURCES_FROM": "sources_from",
    "HAS_WORKSPACE_ITEM": "has_workspace_item",
    "REFERENCES": "references",
    "SEMANTICALLY_MAPS_TO": "semantically_maps_to",
    "OBSERVED_WITH": "observed_with",
    "SIMILAR_TO": "similar_to",
    "HAS_LINEAGE": "has_lineage",
}

RELATION_TO_PBI_EDGE: dict[str, str] = {value: key for key, value in PBI_EDGE_TO_RELATION.items()}


def _json_default(value: Any) -> str:
    return str(value)


def tokenize_text(text: str) -> list[str]:
    """Tokenize text into lowercase alpha-numeric keywords, preserving words with dots/brackets."""
    clean = re.sub(r"[^\w\.\-\[\]]", " ", text.lower())
    tokens = [tok.strip("[]") for tok in clean.split() if len(tok.strip("[]")) > 1]
    return tokens


def _sanitize_path_segment(value: str, default: str = "item") -> str:
    r"""Sanitize a string for use as a single path segment across OSes.

    Removes/replaces invalid filesystem characters (/ \ : * ? " < > | control chars)
    and strips leading/trailing whitespace and trailing dots (forbidden on Windows).
    """
    if not value:
        return default
    cleaned = re.sub(r'[/\\:*?"<>|\x00-\x1f]', '_', str(value))
    cleaned = re.sub(r'\s+', ' ', cleaned).strip(' .')
    reserved = {
        "con", "prn", "aux", "nul",
        "com1", "com2", "com3", "com4", "com5", "com6", "com7", "com8", "com9",
        "lpt1", "lpt2", "lpt3", "lpt4", "lpt5", "lpt6", "lpt7", "lpt8", "lpt9",
    }
    if cleaned.casefold() in reserved or not cleaned:
        return f"{cleaned or default}_obj"
    return cleaned


class SQLiteStore:
    """ACID SQLite storage for PBIBrain graphs with Trail exporter."""

    def __init__(self, location: str | Path | None = None) -> None:
        self.location = Path(location) if location is not None else None
        if self.location is not None:
            if self.location.is_dir():
                self.directory = self.location
                self.db_path = self.directory / "brain.sqlite"
            elif self.location.suffix.lower() in {".lbug", ".sqlite", ".db"}:
                self.db_path = self.location
                self.directory = self.location.parent
            else:
                self.directory = self.location
                self.db_path = self.directory / "brain.sqlite"
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._db_file = str(self.db_path)
            self.is_memory = False
        else:
            self.directory = None
            self.db_path = None
            self._db_file = ":memory:"
            self.is_memory = True

        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self._conn is None:
            conn = sqlite3.connect(self._db_file, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            if not self.is_memory:
                conn.execute("PRAGMA journal_mode = WAL;")
                conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA busy_timeout = 10000;")
            self._conn = conn
        return self._conn

    def _init_db(self) -> None:
        conn = self._get_connection()
        with conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS nodes (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    model_id TEXT,
                    report_id TEXT,
                    source_id TEXT,
                    status TEXT NOT NULL,
                    source TEXT,
                    source_file TEXT,
                    span TEXT,
                    properties TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type);
                CREATE INDEX IF NOT EXISTS idx_nodes_name ON nodes(name);
                CREATE INDEX IF NOT EXISTS idx_nodes_model_id ON nodes(model_id);
                CREATE INDEX IF NOT EXISTS idx_nodes_report_id ON nodes(report_id);
                CREATE INDEX IF NOT EXISTS idx_nodes_source_file ON nodes(source_file);

                CREATE TABLE IF NOT EXISTS edges (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    from_id TEXT NOT NULL,
                    to_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    status TEXT NOT NULL,
                    evidence_class TEXT NOT NULL,
                    evidence TEXT NOT NULL,
                    properties TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_edges_from ON edges(from_id);
                CREATE INDEX IF NOT EXISTS idx_edges_to ON edges(to_id);
                CREATE INDEX IF NOT EXISTS idx_edges_type ON edges(type);
                CREATE INDEX IF NOT EXISTS idx_edges_from_to ON edges(from_id, to_id);
                """
            )
            # Check for FTS5 support
            try:
                conn.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
                        id UNINDEXED,
                        name,
                        description,
                        type,
                        tokenize='porter unicode61'
                    );
                    """
                )
                conn.execute("INSERT OR IGNORE INTO meta (key, value) VALUES ('fts5_enabled', '1');")
            except Exception:
                LOGGER.debug("FTS5 table creation skipped or not supported in this SQLite build")

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def __enter__(self) -> SQLiteStore:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    # Node and Edge operations ------------------------------------------------

    def node_from_row(self, row: sqlite3.Row) -> Node:
        props = row["properties"]
        if isinstance(props, str):
            try:
                properties = json.loads(props)
            except Exception:
                properties = {}
        else:
            properties = {}
        if row["source_file"] and "source_file" not in properties:
            properties["source_file"] = row["source_file"]
        if row["span"] and "span" not in properties:
            properties["span"] = row["span"]

        return Node(
            id=row["id"],
            type=row["type"],
            name=row["name"],
            description=row["description"],
            model_id=row["model_id"],
            report_id=row["report_id"],
            source_id=row["source_id"],
            status=row["status"],
            source=row["source"],
            properties=properties,
        )

    def edge_from_row(self, row: sqlite3.Row) -> Edge:
        ev = row["evidence"]
        if isinstance(ev, str):
            try:
                evidence = json.loads(ev)
            except Exception:
                evidence = []
        else:
            evidence = []
        props = row["properties"]
        if isinstance(props, str):
            try:
                properties = json.loads(props)
            except Exception:
                properties = {}
        else:
            properties = {}

        return Edge(
            id=row["id"],
            type=row["type"],
            from_id=row["from_id"],
            to_id=row["to_id"],
            source=row["source"],
            confidence=float(row["confidence"]),
            status=row["status"],
            evidence_class=row["evidence_class"],
            evidence=evidence if isinstance(evidence, list) else [evidence],
            properties=properties,
        )

    def get_node(self, node_id: str) -> Node | None:
        conn = self._get_connection()
        cursor = conn.execute("SELECT * FROM nodes WHERE id = ?", (node_id,))
        row = cursor.fetchone()
        return self.node_from_row(row) if row else None

    def all_nodes(self) -> list[Node]:
        conn = self._get_connection()
        cursor = conn.execute("SELECT * FROM nodes ORDER BY id")
        return [self.node_from_row(row) for row in cursor.fetchall()]

    def all_edges(self) -> list[Edge]:
        conn = self._get_connection()
        cursor = conn.execute("SELECT * FROM edges ORDER BY id")
        return [self.edge_from_row(row) for row in cursor.fetchall()]

    def count(self) -> tuple[int, int]:
        conn = self._get_connection()
        n_count = conn.execute("SELECT count(*) FROM nodes").fetchone()[0]
        e_count = conn.execute("SELECT count(*) FROM edges").fetchone()[0]
        return n_count, e_count

    def _write_records(
        self,
        conn: sqlite3.Connection,
        node_objs: list[Node],
        edge_objs: list[Edge],
        last_scan: Mapping[str, Any] | None = None,
    ) -> None:
        conn.execute("DELETE FROM edges;")
        conn.execute("DELETE FROM nodes;")
        try:
            conn.execute("DELETE FROM nodes_fts;")
        except Exception:
            pass

        node_records = []
        fts_records = []
        for n in node_objs:
            props = n.properties or {}
            source_file = props.get("source_file") or (props.get("ast_location", {}).get("source_file"))
            span = props.get("span") or (props.get("ast_location", {}).get("span"))
            props_json = json.dumps(props, ensure_ascii=False, sort_keys=True, default=_json_default)
            node_records.append(
                (
                    n.id,
                    n.type,
                    n.name,
                    n.description,
                    n.model_id,
                    n.report_id,
                    n.source_id,
                    n.status,
                    n.source,
                    source_file,
                    span,
                    props_json,
                )
            )
            fts_records.append((n.id, n.name, n.description or "", n.type))

        conn.executemany(
            """
            INSERT INTO nodes (id, type, name, description, model_id, report_id, source_id, status, source, source_file, span, properties)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            node_records,
        )

        try:
            conn.executemany(
                "INSERT INTO nodes_fts (id, name, description, type) VALUES (?, ?, ?, ?);",
                fts_records,
            )
        except Exception:
            pass

        edge_records = []
        for e in edge_objs:
            evidence_json = json.dumps(e.evidence, ensure_ascii=False, sort_keys=True, default=_json_default)
            props_json = json.dumps(e.properties or {}, ensure_ascii=False, sort_keys=True, default=_json_default)
            edge_records.append(
                (
                    e.id,
                    e.type,
                    e.from_id,
                    e.to_id,
                    e.source,
                    float(e.confidence),
                    e.status,
                    e.evidence_class,
                    evidence_json,
                    props_json,
                )
            )

        conn.executemany(
            """
            INSERT INTO edges (id, type, from_id, to_id, source, confidence, status, evidence_class, evidence, properties)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            edge_records,
        )

        if last_scan is not None:
            conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('last_scan', ?);",
                (json.dumps(last_scan, ensure_ascii=False, default=_json_default),),
            )

    def replace_all(
        self,
        nodes: Iterable[Node | Mapping[str, Any]],
        edges: Iterable[Edge | Mapping[str, Any]],
        last_scan: Mapping[str, Any] | None = None,
        *,
        in_transaction: bool = False,
    ) -> None:
        """Atomically replace the full graph."""
        node_objs = [n if isinstance(n, Node) else node_from_dict(n) for n in nodes]
        edge_objs = [e if isinstance(e, Edge) else edge_from_dict(e) for e in edges]

        conn = self._get_connection()
        if in_transaction:
            self._write_records(conn, node_objs, edge_objs, last_scan)
        else:
            with conn:
                self._write_records(conn, node_objs, edge_objs, last_scan)

        # Export Trail cache cards if directory is configured
        if self.directory is not None:
            try:
                self.export_trail()
            except Exception:
                LOGGER.warning("Exporting Trail cache failed", exc_info=True)

    def upsert_node(self, node: Node | Mapping[str, Any]) -> Node:
        n = node if isinstance(node, Node) else node_from_dict(node)
        props = n.properties or {}
        source_file = props.get("source_file") or (props.get("ast_location", {}).get("source_file"))
        span = props.get("span") or (props.get("ast_location", {}).get("span"))
        props_json = json.dumps(props, ensure_ascii=False, sort_keys=True, default=_json_default)

        conn = self._get_connection()
        with conn:
            conn.execute(
                """
                INSERT INTO nodes (id, type, name, description, model_id, report_id, source_id, status, source, source_file, span, properties)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    type=excluded.type,
                    name=excluded.name,
                    description=excluded.description,
                    model_id=excluded.model_id,
                    report_id=excluded.report_id,
                    source_id=excluded.source_id,
                    status=excluded.status,
                    source=excluded.source,
                    source_file=excluded.source_file,
                    span=excluded.span,
                    properties=excluded.properties;
                """,
                (
                    n.id,
                    n.type,
                    n.name,
                    n.description,
                    n.model_id,
                    n.report_id,
                    n.source_id,
                    n.status,
                    n.source,
                    source_file,
                    span,
                    props_json,
                ),
            )
            try:
                conn.execute("DELETE FROM nodes_fts WHERE id = ?;", (n.id,))
                conn.execute("INSERT INTO nodes_fts (id, name, description, type) VALUES (?, ?, ?, ?);",
                             (n.id, n.name, n.description or "", n.type))
            except Exception:
                pass

        return n

    def upsert_edge(self, edge: Edge | Mapping[str, Any]) -> Edge:
        e = edge if isinstance(edge, Edge) else edge_from_dict(edge)
        evidence_json = json.dumps(e.evidence, ensure_ascii=False, sort_keys=True, default=_json_default)
        props_json = json.dumps(e.properties or {}, ensure_ascii=False, sort_keys=True, default=_json_default)

        conn = self._get_connection()
        with conn:
            conn.execute(
                """
                INSERT INTO edges (id, type, from_id, to_id, source, confidence, status, evidence_class, evidence, properties)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    type=excluded.type,
                    from_id=excluded.from_id,
                    to_id=excluded.to_id,
                    source=excluded.source,
                    confidence=excluded.confidence,
                    status=excluded.status,
                    evidence_class=excluded.evidence_class,
                    evidence=excluded.evidence,
                    properties=excluded.properties;
                """,
                (
                    e.id,
                    e.type,
                    e.from_id,
                    e.to_id,
                    e.source,
                    float(e.confidence),
                    e.status,
                    e.evidence_class,
                    evidence_json,
                    props_json,
                ),
            )
        return e

    def get_neighbors(
        self,
        node_id: str,
        edge_types: Sequence[str] | str | None = None,
        *,
        direction: str = "both",
    ) -> list[Node]:
        conn = self._get_connection()
        if isinstance(edge_types, str):
            edge_types = [edge_types]
        type_clause = ""
        params: list[Any] = []
        if edge_types:
            placeholders = ",".join("?" for _ in edge_types)
            type_clause = f"AND e.type IN ({placeholders})"
            params.extend(edge_types)

        if direction == "out":
            query = f"SELECT DISTINCT n.* FROM edges e JOIN nodes n ON e.to_id = n.id WHERE e.from_id = ? {type_clause} ORDER BY n.id"
            full_params = [node_id, *params]
        elif direction == "in":
            query = f"SELECT DISTINCT n.* FROM edges e JOIN nodes n ON e.from_id = n.id WHERE e.to_id = ? {type_clause} ORDER BY n.id"
            full_params = [node_id, *params]
        else:
            query = f"""
                SELECT DISTINCT n.* FROM (
                    SELECT e.to_id AS nid FROM edges e WHERE e.from_id = ? {type_clause}
                    UNION
                    SELECT e.from_id AS nid FROM edges e WHERE e.to_id = ? {type_clause}
                ) x JOIN nodes n ON x.nid = n.id ORDER BY n.id
            """
            full_params = [node_id, *params, node_id, *params]

        cursor = conn.execute(query, full_params)
        return [self.node_from_row(row) for row in cursor.fetchall()]

    def get_dependencies(self, node_id: str) -> list[Node]:
        return self.get_neighbors(node_id, ["DEPENDS_ON"], direction="out")

    def get_dependents(self, node_id: str) -> list[Node]:
        return self.get_neighbors(node_id, ["DEPENDS_ON"], direction="in")

    def get_usage(self, node_id: str) -> list[Node]:
        conn = self._get_connection()
        query = """
            SELECT DISTINCT n.* FROM edges e
            JOIN nodes n ON e.from_id = n.id
            WHERE e.to_id = ? AND e.type = 'USES'
            ORDER BY n.id
        """
        cursor = conn.execute(query, (node_id,))
        return [self.node_from_row(row) for row in cursor.fetchall()]

    def get_edges(
        self,
        *,
        from_id: str | None = None,
        to_id: str | None = None,
        edge_types: Sequence[str] | str | None = None,
    ) -> list[Edge]:
        conn = self._get_connection()
        if isinstance(edge_types, str):
            edge_types = [edge_types]
        clauses = []
        params: list[Any] = []
        if from_id is not None:
            clauses.append("from_id = ?")
            params.append(from_id)
        if to_id is not None:
            clauses.append("to_id = ?")
            params.append(to_id)
        if edge_types:
            placeholders = ",".join("?" for _ in edge_types)
            clauses.append(f"type IN ({placeholders})")
            params.extend(edge_types)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"SELECT * FROM edges {where} ORDER BY id"
        cursor = conn.execute(query, params)
        return [self.edge_from_row(row) for row in cursor.fetchall()]

    def find_path(self, from_id: str, to_id: str) -> list[Node]:
        """BFS search finding the shortest directed path between two nodes."""
        start_node = self.get_node(from_id)
        target_node = self.get_node(to_id)
        if not start_node or not target_node:
            return []
        if from_id == to_id:
            return [start_node]

        conn = self._get_connection()
        queue = collections.deque([[from_id]])
        visited = {from_id}

        while queue:
            path = queue.popleft()
            current = path[-1]

            cursor = conn.execute("SELECT to_id FROM edges WHERE from_id = ? ORDER BY to_id", (current,))
            for (neighbor,) in cursor.fetchall():
                if neighbor == to_id:
                    full_ids = [*path, neighbor]
                    placeholders = ",".join("?" for _ in full_ids)
                    nodes_by_id = {
                        row["id"]: self.node_from_row(row)
                        for row in conn.execute(f"SELECT * FROM nodes WHERE id IN ({placeholders})", full_ids).fetchall()
                    }
                    return [nodes_by_id[nid] for nid in full_ids if nid in nodes_by_id]
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append([*path, neighbor])

        return []

    def search_objects(
        self,
        query: str,
        *,
        model_id: str | None = None,
        report_id: str | None = None,
        object_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Node]:
        """Rank objects matching query using FTS5 or LIKE matching."""
        conn = self._get_connection()
        q_clean = query.strip()
        tokens = tokenize_text(q_clean) if q_clean else []

        clauses = []
        params: list[Any] = []
        if model_id:
            clauses.append("n.model_id = ?")
            params.append(model_id)
        if report_id:
            clauses.append("n.report_id = ?")
            params.append(report_id)
        if object_type:
            clauses.append("n.type = ?")
            params.append(object_type.upper())

        # Use FTS5 when the query has tokens; fall back to LIKE matching if it fails.
        if tokens:
            try:
                fts_query = " AND ".join(f'"{tok}"*' for tok in tokens)
                where_extra = f"AND {' AND '.join(clauses)}" if clauses else ""
                sql = f"""
                    SELECT n.*, bm25(nodes_fts) AS rank
                    FROM nodes_fts f
                    JOIN nodes n ON f.id = n.id
                    WHERE nodes_fts MATCH ? {where_extra}
                    ORDER BY rank ASC, n.id ASC
                    LIMIT ? OFFSET ?;
                """
                cursor = conn.execute(sql, [fts_query, *params, limit, offset])
                rows = cursor.fetchall()
                return [self.node_from_row(row) for row in rows]
            except Exception:
                pass

        # Fallback to standard LIKE matching
        if q_clean:
            like_clause = "(n.name LIKE ? OR n.description LIKE ? OR n.id LIKE ?)"
            pat = f"%{q_clean}%"
            clauses.append(like_clause)
            params.extend([pat, pat, pat])

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT n.* FROM nodes n {where} ORDER BY n.name ASC, n.id ASC LIMIT ? OFFSET ?"
        cursor = conn.execute(sql, [*params, limit, offset])
        return [self.node_from_row(row) for row in cursor.fetchall()]

    # Trail cache exporter ----------------------------------------------------

    def _resolve_card_path(self, node: Node) -> str:
        """Resolve a deterministic file path for a node card, preventing collision across models."""
        props = node.properties or {}
        source_file = props.get("source_file") or props.get("ast_location", {}).get("source_file")

        # Determine model/report folder prefix
        is_report_obj = node.type in {
            "PAGE", "VISUAL", "BOOKMARK", "REPORT", "REPORT_MEASURE", "VISUAL_CALCULATION",
            "PAGE_FILTER", "REPORT_FILTER", "VISUAL_FILTER",
        } or (node.report_id and not node.model_id)

        scope_prefix = ""
        if is_report_obj and node.report_id:
            scope_prefix = node.report_id.replace("report:", "").strip("/")
            if scope_prefix and not scope_prefix.endswith(".Report"):
                scope_prefix += ".Report"
        elif node.model_id:
            scope_prefix = node.model_id.replace("model:", "").strip("/")
            if scope_prefix and not scope_prefix.endswith(".SemanticModel"):
                scope_prefix += ".SemanticModel"
        elif node.report_id:
            scope_prefix = node.report_id.replace("report:", "").strip("/")
            if scope_prefix and not scope_prefix.endswith(".Report"):
                scope_prefix += ".Report"

        if scope_prefix:
            scope_prefix = _sanitize_path_segment(scope_prefix)

        if source_file:
            path_str = str(source_file).replace("\\", "/").strip("/")
            segments = [_sanitize_path_segment(part) for part in path_str.split("/") if part]
            safe_path_str = "/".join(segments)
            if scope_prefix and not safe_path_str.startswith(scope_prefix):
                return f"{scope_prefix}/{safe_path_str}"
            return safe_path_str

        # Fallback based on type
        owner = props.get("table_id") or node.name
        if isinstance(owner, str) and ":" in owner:
            owner = owner.split(":")[-1]
        safe_owner = _sanitize_path_segment(str(owner or "table"))
        safe_name = _sanitize_path_segment(str(node.name or "item"))

        if node.type in {"TABLE", "MEASURE", "COLUMN", "HIERARCHY", "PARTITION"}:
            return f"{scope_prefix or 'Model'}/definition/tables/{safe_owner}.tmdl"
        if node.type in {"PAGE", "VISUAL"}:
            return f"{scope_prefix or 'Report'}/definition/pages/{safe_name}/page.json"
        if node.type == "BOOKMARK":
            return f"{scope_prefix or 'Report'}/definition/bookmarks/{safe_name}"
        return f"{scope_prefix or 'Project'}/{safe_name}"

    def export_trail(self, target_dir: Path | None = None) -> None:
        """Export the on-disk Trail cache: wiring.json, ask-index.json, INDEX.md, and cards."""
        out_dir = Path(target_dir) if target_dir is not None else self.directory
        if out_dir is None:
            return

        all_nodes = self.all_nodes()
        all_edges = self.all_edges()

        graph_dir = out_dir / ".graph"
        cache_dir = out_dir / ".cache"
        graph_dir.mkdir(parents=True, exist_ok=True)
        cache_dir.mkdir(parents=True, exist_ok=True)

        # 1. Write lossless brain-facts.json
        facts_payload = {
            "schema_version": GRAPH_SCHEMA_VERSION,
            "nodes": serialize_nodes(all_nodes),
            "edges": serialize_edges(all_edges),
        }
        self._atomic_write_json(graph_dir / "brain-facts.json", facts_payload)

        # 2. Build Trail GraphV1
        trail_nodes: list[dict[str, Any]] = []
        trail_edges: list[dict[str, Any]] = []
        scopes_set: set[str] = set()

        for n in all_nodes:
            kind = PBI_TYPE_TO_KIND.get(n.type, n.type.lower())
            card_path = self._resolve_card_path(n)
            scope = card_path.split("/")[0] if "/" in card_path else ""
            if scope:
                scopes_set.add(scope)

            props = n.properties or {}
            span = props.get("span") or props.get("ast_location", {}).get("span") or "L1-L1"
            owner = props.get("table_id") or props.get("entity")
            if isinstance(owner, str) and ":" in owner:
                owner = owner.split(":")[-1]

            signature = n.name
            if n.type == "MEASURE" and props.get("expression"):
                signature = f"measure [{n.name}] = {props['expression'].strip()[:80]}"
            elif n.type == "COLUMN":
                datatype = props.get("datatype", "string")
                signature = f"column '{owner or ''}'[{n.name}] : {datatype}"
            elif n.type == "TABLE":
                signature = f"table {n.name}"

            trail_nodes.append(
                {
                    "id": n.id,
                    "kind": kind,
                    "name": n.name,
                    "path": card_path,
                    "span": span,
                    "owner": owner or None,
                    "signature": signature,
                }
            )

        for e in all_edges:
            relation = PBI_EDGE_TO_RELATION.get(e.type, e.type.lower())
            trail_edges.append(
                {
                    "source": e.from_id,
                    "target": e.to_id,
                    "relation": relation,
                    "confidence": "exact" if e.status == "factual" else "inferred",
                }
            )

        trail_nodes.sort(key=lambda item: item["id"])
        trail_edges.sort(key=lambda item: (item["source"], item["relation"], item["target"]))

        wiring_payload = {
            "meta": {"version": TRAIL_GRAPH_VERSION},
            "scopes": [{"name": s} for s in sorted(scopes_set)],
            "nodes": trail_nodes,
            "edges": trail_edges,
        }
        self._atomic_write_json(graph_dir / "wiring.json", wiring_payload)

        # 3. Build AskIndex (BM25 token inverted index)
        doc_count = len(trail_nodes)
        df: dict[str, int] = collections.defaultdict(int)
        doc_lengths: list[int] = []

        for node in trail_nodes:
            text = f"{node['name']} {node.get('signature') or ''} {node['path']}"
            tokens = set(tokenize_text(text))
            doc_lengths.append(len(tokens))
            for tok in tokens:
                df[tok] += 1

        avg_body_len = sum(doc_lengths) / max(1, doc_count)
        ask_index = {
            "version": ASK_INDEX_VERSION,
            "docCount": doc_count,
            "avgBodyLen": round(avg_body_len, 2),
            "df": dict(df),
        }
        self._atomic_write_json(cache_dir / "ask-index.json", ask_index)

        # 4. Generate Markdown wiring cards and INDEX.md
        self._generate_cards(out_dir, all_nodes, all_edges)

    def _generate_cards(
        self,
        out_dir: Path,
        nodes: list[Node],
        edges: list[Edge],
    ) -> None:
        nodes_by_path: dict[str, list[Node]] = collections.defaultdict(list)
        for n in nodes:
            path_key = self._resolve_card_path(n)
            nodes_by_path[path_key].append(n)

        # Read previous card manifest to delete stale cards
        manifest_file = out_dir / ".graph" / "cards_manifest.json"
        prev_cards: set[str] = set()
        if manifest_file.is_file():
            try:
                prev_cards = set(json.loads(manifest_file.read_text(encoding="utf-8")).get("cards", []))
            except Exception:
                prev_cards = set()

        curr_cards: set[str] = set()

        # Build edge adjacency for cards
        out_edges: dict[str, list[Edge]] = collections.defaultdict(list)
        in_edges: dict[str, list[Edge]] = collections.defaultdict(list)
        node_names = {n.id: n.name for n in nodes}

        for e in edges:
            out_edges[e.from_id].append(e)
            in_edges[e.to_id].append(e)

        index_entries: list[str] = ["# Context Graph Index\n"]

        for path_key, path_nodes in sorted(nodes_by_path.items()):
            card_file = out_dir / f"{path_key}.md"
            curr_cards.add(f"{path_key}.md")
            card_file.parent.mkdir(parents=True, exist_ok=True)

            card_lines = [f"# {path_key}\n"]
            for n in sorted(path_nodes, key=lambda item: item.name):
                props = n.properties or {}
                span = props.get("span") or props.get("ast_location", {}).get("span") or "L1-L1"
                kind = PBI_TYPE_TO_KIND.get(n.type, n.type.lower())
                expr_snippet = ""
                if props.get("expression"):
                    clean_expr = " ".join(props["expression"].split())
                    expr_snippet = f" — `{clean_expr[:70]}`"

                card_lines.append(f"- `{n.name}` ({kind}) — `{span}`{expr_snippet}")

                # Dependencies (outgoing)
                outgoing = out_edges.get(n.id, [])
                for oe in outgoing[:10]:
                    target_name = node_names.get(oe.to_id, oe.to_id)
                    rel = PBI_EDGE_TO_RELATION.get(oe.type, oe.type.lower())
                    card_lines.append(f"  - {rel} `{target_name}`")

                # Dependents (incoming)
                incoming = in_edges.get(n.id, [])
                for ie in incoming[:10]:
                    src_name = node_names.get(ie.from_id, ie.from_id)
                    rel = PBI_EDGE_TO_RELATION.get(ie.type, ie.type.lower())
                    card_lines.append(f"  - {rel} by `{src_name}`")

            card_lines.append("")
            try:
                self._atomic_write_text(card_file, "\n".join(card_lines))
                index_entries.append(f"- [{path_key}](file://{path_key}.md) ({len(path_nodes)} symbols)")
            except Exception:
                LOGGER.warning("Failed to write Trail card for %s", path_key, exc_info=True)

        # Write INDEX.md
        try:
            self._atomic_write_text(out_dir / "INDEX.md", "\n".join(index_entries) + "\n")
        except Exception:
            LOGGER.warning("Failed to write INDEX.md", exc_info=True)

        # Delete stale cards
        stale_cards = prev_cards - curr_cards
        for stale in stale_cards:
            stale_path = out_dir / stale
            if stale_path.is_file():
                try:
                    stale_path.unlink()
                except Exception:
                    pass

        # Write current card manifest
        try:
            self._atomic_write_json(manifest_file, {"cards": sorted(curr_cards)})
        except Exception:
            LOGGER.warning("Failed to write cards manifest", exc_info=True)

    def _atomic_write_text(self, file_path: Path, content: str) -> None:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        temp_name = None
        try:
            with tempfile.NamedTemporaryFile("w", dir=file_path.parent, delete=False, encoding="utf-8") as tf:
                tf.write(content)
                temp_name = tf.name
            os.replace(temp_name, file_path)
        except Exception:
            if temp_name and os.path.exists(temp_name):
                try:
                    os.unlink(temp_name)
                except Exception:
                    pass
            raise

    def _atomic_write_json(self, file_path: Path, payload: Any) -> None:
        content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=_json_default) + "\n"
        self._atomic_write_text(file_path, content)
