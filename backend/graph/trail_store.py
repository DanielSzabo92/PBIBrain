"""Native Trail graph storage engine for PBIBrain.

Persists and hydrates canonical Power BI semantic model and report graphs using
the deterministic Trail cache layout (``.graph/wiring.json``, ``.cache/ask-index.json``,
``INDEX.md``, per-file ``<path>.md`` wiring cards, and lossless ``.graph/brain-facts.json``).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .schema import GRAPH_SCHEMA_VERSION

TRAIL_GRAPH_VERSION = 1
ASK_INDEX_VERSION = 1

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
}

RELATION_TO_PBI_EDGE: dict[str, str] = {value: key for key, value in PBI_EDGE_TO_RELATION.items()}
RELATION_TO_PBI_EDGE.update(
    {
        "calls": "DEPENDS_ON",
        "references": "DEPENDS_ON",
        "imports": "SOURCES_FROM",
        "defines": "CONTAINS",
    }
)

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")
_CAMEL_RE = re.compile(r"([a-z0-9])([A-Z])")
_SAFE_SEGMENT_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _atomic_write_text(target: Path, content: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=target.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _sha256_prefixed(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _tokenize(text: str) -> list[str]:
    if not text:
        return []
    expanded = _CAMEL_RE.sub(r"\1 \2", text)
    return [token.casefold() for token in _TOKEN_RE.findall(expanded) if len(token) >= 2]


def _safe_rel_path(raw_path: str) -> str:
    cleaned = raw_path.replace("\\", "/").strip("/")
    if not cleaned:
        return "model/objects.tmdl"
    parts = [
        _SAFE_SEGMENT_RE.sub("_", part).strip(".") or "item"
        for part in cleaned.split("/")
        if part and part not in {".", ".."}
    ]
    return "/".join(parts) if parts else "model/objects.tmdl"


def _node_path_and_span(node: Mapping[str, Any], nodes_by_id: Mapping[str, Mapping[str, Any]]) -> tuple[str, str]:
    props = node.get("properties") if isinstance(node.get("properties"), Mapping) else {}
    raw = props.get("raw_source") if isinstance(props.get("raw_source"), Mapping) else {}
    ast_loc = props.get("ast_location") if isinstance(props.get("ast_location"), Mapping) else {}
    if not ast_loc and isinstance(raw.get("ast_location"), Mapping):
        ast_loc = raw["ast_location"]

    span = str(ast_loc.get("span") or "L1-L1")
    if not re.fullmatch(r"L\d+-L\d+", span):
        span = "L1-L1"

    source_file = ast_loc.get("source_file") or raw.get("source_file") or props.get("source_file")
    owner_prefix = ""
    model_id = node.get("model_id")
    report_id = node.get("report_id")
    if model_id and model_id in nodes_by_id and model_id != node.get("id"):
        model_node = nodes_by_id[model_id]
        model_props = model_node.get("properties") if isinstance(model_node.get("properties"), Mapping) else {}
        src_path = model_props.get("source_path")
        if isinstance(src_path, str) and src_path.strip():
            owner_prefix = Path(src_path.replace("\\", "/")).name
    elif report_id and report_id in nodes_by_id and report_id != node.get("id"):
        report_node = nodes_by_id[report_id]
        report_props = report_node.get("properties") if isinstance(report_node.get("properties"), Mapping) else {}
        src_path = report_props.get("source_path")
        if isinstance(src_path, str) and src_path.strip():
            owner_prefix = Path(src_path.replace("\\", "/")).name

    if isinstance(source_file, str) and source_file.strip():
        rel = source_file.replace("\\", "/").lstrip("/")
        if owner_prefix and not rel.startswith(owner_prefix + "/"):
            rel = f"{owner_prefix}/{rel}"
        return _safe_rel_path(rel), span

    source_path = props.get("source_path") or raw.get("source_path")
    if isinstance(source_path, str) and source_path.strip():
        base_name = Path(source_path.replace("\\", "/")).name
        node_type = str(node.get("type") or "OBJECT").upper()
        if node_type == "MODEL":
            return _safe_rel_path(f"{base_name}/definition/model.tmdl"), span
        if node_type == "REPORT":
            return _safe_rel_path(f"{base_name}/definition/report.json"), span
        return _safe_rel_path(base_name), span

    table_id = props.get("table_id")
    if isinstance(table_id, str) and table_id in nodes_by_id:
        table_node = nodes_by_id[table_id]
        table_name = str(table_node.get("name") or "table")
        prefix = f"{owner_prefix}/" if owner_prefix else ""
        return _safe_rel_path(f"{prefix}definition/tables/{table_name}.tmdl"), span

    node_type = str(node.get("type") or "OBJECT").upper()
    node_name = str(node.get("name") or node.get("id") or "item")
    prefix = f"{owner_prefix}/" if owner_prefix else ""
    if node_type == "TABLE":
        return _safe_rel_path(f"{prefix}definition/tables/{node_name}.tmdl"), span
    if node_type == "RELATIONSHIP":
        return _safe_rel_path(f"{prefix}definition/relationships.tmdl"), span
    if node_type == "SHARED_EXPRESSION":
        return _safe_rel_path(f"{prefix}definition/expressions.tmdl"), span
    if node_type in {"PAGE", "VISUAL", "VISUAL_CALCULATION", "VISUAL_FILTER", "PAGE_FILTER", "REPORT_FILTER"}:
        return _safe_rel_path(f"{prefix}definition/report.json"), span
    if node_type == "BOOKMARK":
        return _safe_rel_path(f"{prefix}definition/bookmarks/{node_name}.bookmark.json"), span
    return _safe_rel_path(f"{prefix}{node_type.lower()}/{node_name}.tmdl"), span


def _node_signature(node: Mapping[str, Any]) -> str:
    props = node.get("properties") if isinstance(node.get("properties"), Mapping) else {}
    node_type = str(node.get("type") or "OBJECT").upper()
    name = str(node.get("name") or node.get("id") or "")
    expression = props.get("expression")
    if isinstance(expression, str) and expression.strip():
        compact = " ".join(expression.strip().splitlines())
        if len(compact) > 160:
            compact = compact[:157] + "..."
        return f"{node_type.lower()} {name} = {compact}"
    datatype = props.get("datatype")
    if datatype:
        return f"{node_type.lower()} {name} : {datatype}"
    visual_type = props.get("visual_type")
    if visual_type:
        return f"visual {name} ({visual_type})"
    return f"{node_type.lower()} {name}".strip()


def _node_owner(node: Mapping[str, Any], nodes_by_id: Mapping[str, Mapping[str, Any]]) -> str | None:
    props = node.get("properties") if isinstance(node.get("properties"), Mapping) else {}
    for parent_key in ("table_id", "calculation_group_id", "hierarchy_id", "visual_id", "page_id", "role_id"):
        parent_id = props.get(parent_key)
        if isinstance(parent_id, str) and parent_id in nodes_by_id:
            return str(nodes_by_id[parent_id].get("name") or parent_id)
    for root_key in ("model_id", "report_id"):
        root_id = node.get(root_key)
        if isinstance(root_id, str) and root_id != node.get("id") and root_id in nodes_by_id:
            return str(nodes_by_id[root_id].get("name") or root_id)
    return None


class TrailStore:
    """File-backed Trail store reading and writing `.graph/wiring.json` and `.cache/ask-index.json`."""

    def __init__(self, path: str | Path) -> None:
        self.root = Path(path)
        self.graph_dir = self.root / ".graph"
        self.cache_dir = self.root / ".cache"
        self.wiring_file = self.graph_dir / "wiring.json"
        self.facts_file = self.graph_dir / "brain-facts.json"
        self.ask_index_file = self.cache_dir / "ask-index.json"
        self.index_md_file = self.root / "INDEX.md"

    def initialize(self) -> None:
        if self.root.exists() and not self.root.is_dir():
            # If a plain file exists at root (e.g. a pre-created tempfile), convert it if empty or JSON.
            legacy_payload = None
            try:
                raw_text = self.root.read_text(encoding="utf-8").strip()
                if raw_text:
                    legacy_payload = json.loads(raw_text)
            except Exception:
                legacy_payload = None
            self.root.unlink()
            self.root.mkdir(parents=True, exist_ok=True)
            if isinstance(legacy_payload, Mapping):
                self.write(legacy_payload)
                return
        self.root.mkdir(parents=True, exist_ok=True)
        self.graph_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        if not self.wiring_file.is_file() and not self.facts_file.is_file():
            self.write(
                {
                    "schema_version": GRAPH_SCHEMA_VERSION,
                    "last_scan": None,
                    "nodes": [],
                    "edges": [],
                }
            )

    def exists(self) -> bool:
        return self.facts_file.is_file() or self.wiring_file.is_file()

    def load(self) -> dict[str, Any]:
        """Load the canonical PBIBrain payload from `.graph/brain-facts.json` or `.graph/wiring.json`."""
        if self.facts_file.is_file():
            payload = json.loads(self.facts_file.read_text(encoding="utf-8"))
            if isinstance(payload, Mapping):
                return dict(payload)
        if self.wiring_file.is_file():
            wiring = json.loads(self.wiring_file.read_text(encoding="utf-8"))
            if isinstance(wiring, Mapping):
                return self._payload_from_wiring(wiring)
        return {
            "schema_version": GRAPH_SCHEMA_VERSION,
            "last_scan": None,
            "nodes": [],
            "edges": [],
        }

    def _payload_from_wiring(self, wiring: Mapping[str, Any]) -> dict[str, Any]:
        meta = wiring.get("meta") if isinstance(wiring.get("meta"), Mapping) else {}
        raw_nodes = wiring.get("nodes") if isinstance(wiring.get("nodes"), list) else []
        raw_edges = wiring.get("edges") if isinstance(wiring.get("edges"), list) else []

        nodes: list[dict[str, Any]] = []
        for item in raw_nodes:
            if not isinstance(item, Mapping):
                continue
            pbi_meta = item.get("pbi_meta") if isinstance(item.get("pbi_meta"), Mapping) else {}
            if pbi_meta.get("pbibrain_node"):
                nodes.append(dict(pbi_meta["pbibrain_node"]))
                continue
            kind = str(item.get("kind") or "measure")
            node_type = str(pbi_meta.get("object_type") or KIND_TO_PBI_TYPE.get(kind, "MEASURE"))
            props: dict[str, Any] = dict(pbi_meta.get("properties") or {})
            if item.get("path") and item.get("span"):
                props.setdefault(
                    "ast_location",
                    {"source_file": str(item["path"]), "span": str(item["span"])},
                )
            if pbi_meta.get("expression"):
                props.setdefault("expression", pbi_meta["expression"])
            if pbi_meta.get("datatype"):
                props.setdefault("datatype", pbi_meta["datatype"])
            if pbi_meta.get("format_string"):
                props.setdefault("format_string", pbi_meta["format_string"])
            nodes.append(
                {
                    "id": str(item.get("id") or item.get("name")),
                    "type": node_type,
                    "name": str(item.get("name") or item.get("id")),
                    "description": item.get("summary") or None,
                    "model_id": pbi_meta.get("model_id"),
                    "report_id": pbi_meta.get("report_id"),
                    "source_id": pbi_meta.get("lineage_tag") or str(item.get("name") or item.get("id")),
                    "properties": props,
                    "source": str(pbi_meta.get("source") or "trail_pbi"),
                    "status": str(pbi_meta.get("status") or "factual"),
                    "confidence": 1.0,
                    "evidence": [f"{item.get('path', '')}:{item.get('span', 'L1-L1')}"],
                }
            )

        edges: list[dict[str, Any]] = []
        for index, item in enumerate(raw_edges):
            if not isinstance(item, Mapping):
                continue
            pbi_meta = item.get("pbi_meta") if isinstance(item.get("pbi_meta"), Mapping) else {}
            if pbi_meta.get("pbibrain_edge"):
                edges.append(dict(pbi_meta["pbibrain_edge"]))
                continue
            relation = str(item.get("relation") or "depends_on")
            edge_type = str(pbi_meta.get("edge_type") or RELATION_TO_PBI_EDGE.get(relation, "DEPENDS_ON"))
            source = str(item.get("source") or "")
            target = str(item.get("target") or "")
            if not source or not target:
                continue
            confidence_str = str(item.get("confidence") or "exact")
            confidence = 1.0 if confidence_str == "exact" else 0.8 if confidence_str == "inferred" else 0.5
            edges.append(
                {
                    "id": str(pbi_meta.get("id") or f"edge:{edge_type.lower()}:{index}:{source}->{target}"),
                    "type": edge_type,
                    "from_id": source,
                    "to_id": target,
                    "properties": dict(pbi_meta.get("properties") or {}),
                    "source": str(pbi_meta.get("source") or "trail_pbi"),
                    "status": str(pbi_meta.get("status") or "factual"),
                    "confidence": confidence,
                    "evidence_class": str(pbi_meta.get("evidence_class") or "FACT"),
                    "evidence": list(pbi_meta.get("evidence") or []),
                }
            )

        return {
            "schema_version": int(meta.get("pbibrain_schema_version") or GRAPH_SCHEMA_VERSION),
            "last_scan": meta.get("last_scan") or meta.get("created"),
            "nodes": nodes,
            "edges": edges,
        }

    def write(self, payload: Mapping[str, Any]) -> None:
        """Atomically persist `.graph/brain-facts.json`, `.graph/wiring.json`, `.cache/ask-index.json`, and cards."""
        self.root.mkdir(parents=True, exist_ok=True)
        self.graph_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        raw_nodes = list(payload.get("nodes") or [])
        raw_edges = list(payload.get("edges") or [])
        last_scan = payload.get("last_scan")
        created_iso = str(last_scan) if last_scan else datetime.now(timezone.utc).isoformat()

        nodes_by_id: dict[str, Mapping[str, Any]] = {
            str(node["id"]): node for node in raw_nodes if isinstance(node, Mapping) and node.get("id")
        }

        trail_nodes: list[dict[str, Any]] = []
        file_hashes: dict[str, str] = {}
        nodes_by_file: dict[str, list[dict[str, Any]]] = {}

        for node_id in sorted(nodes_by_id):
            node = nodes_by_id[node_id]
            node_type = str(node.get("type") or "MEASURE").upper()
            kind = PBI_TYPE_TO_KIND.get(node_type, "measure")
            path, span = _node_path_and_span(node, nodes_by_id)
            signature = _node_signature(node)
            owner = _node_owner(node, nodes_by_id)
            props = node.get("properties") if isinstance(node.get("properties"), Mapping) else {}
            summary = str(node.get("description") or "")
            body_text = json.dumps(
                {
                    "id": node_id,
                    "type": node_type,
                    "name": node.get("name"),
                    "signature": signature,
                    "expression": props.get("expression"),
                },
                sort_keys=True,
                default=str,
            )
            body_hash = _sha256_prefixed(body_text)
            file_hashes.setdefault(path, body_hash)

            trail_node: dict[str, Any] = {
                "id": node_id,
                "name": str(node.get("name") or node_id),
                "kind": kind,
                "owner": owner,
                "path": path,
                "span": span,
                "signature": signature,
                "exported": not bool(props.get("hidden", False)),
                "origin": "ast",
                "body_hash": body_hash,
                "summary_state": "fresh" if summary else "pending",
                "summary": summary,
                "crux": None,
                "pbi_meta": {
                    "object_type": node_type,
                    "model_id": node.get("model_id"),
                    "report_id": node.get("report_id"),
                    "table_id": props.get("table_id"),
                    "lineage_tag": node.get("source_id"),
                    "datatype": props.get("datatype"),
                    "format_string": props.get("format_string"),
                    "expression_language": props.get("expression_language"),
                    "hidden": props.get("hidden"),
                    "status": node.get("status"),
                },
            }
            trail_nodes.append(trail_node)
            nodes_by_file.setdefault(path, []).append(trail_node)

        trail_edges: list[dict[str, Any]] = []
        outbound_by_node: dict[str, list[tuple[str, str]]] = {}
        inbound_by_node: dict[str, list[tuple[str, str]]] = {}

        sorted_edges = sorted(
            (edge for edge in raw_edges if isinstance(edge, Mapping)),
            key=lambda item: (
                str(item.get("from_id") or ""),
                str(item.get("to_id") or ""),
                str(item.get("type") or ""),
                str(item.get("id") or ""),
            ),
        )
        for edge in sorted_edges:
            edge_type = str(edge.get("type") or "DEPENDS_ON").upper()
            relation = PBI_EDGE_TO_RELATION.get(edge_type, "depends_on")
            source_id = str(edge.get("from_id") or "")
            target_id = str(edge.get("to_id") or "")
            if not source_id or not target_id:
                continue
            evidence_class = str(edge.get("evidence_class") or "FACT").upper()
            confidence = "exact" if evidence_class == "FACT" else "inferred"
            trail_edges.append(
                {
                    "source": source_id,
                    "target": target_id,
                    "relation": relation,
                    "confidence": confidence,
                    "pbi_meta": {
                        "id": edge.get("id"),
                        "edge_type": edge_type,
                        "evidence_class": evidence_class,
                        "status": edge.get("status"),
                    },
                }
            )
            outbound_by_node.setdefault(source_id, []).append((relation, target_id))
            inbound_by_node.setdefault(target_id, []).append((relation, source_id))

        wiring_payload = {
            "meta": {
                "version": TRAIL_GRAPH_VERSION,
                "created": created_iso,
                "commit": "pbibrain",
                "pbibrain_schema_version": int(payload.get("schema_version") or GRAPH_SCHEMA_VERSION),
                "last_scan": last_scan,
                "file_hashes": {key: file_hashes[key] for key in sorted(file_hashes)},
            },
            "nodes": trail_nodes,
            "edges": trail_edges,
        }

        ask_index_payload = self._build_ask_index(trail_nodes, nodes_by_id, outbound_by_node)

        # Write wiring.json, ask-index.json, INDEX.md, per-file .md cards, and brain-facts.json atomically.
        _atomic_write_text(
            self.wiring_file,
            json.dumps(wiring_payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        )
        _atomic_write_text(
            self.ask_index_file,
            json.dumps(ask_index_payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n",
        )
        self._write_markdown_cards(trail_nodes, trail_edges, nodes_by_file, outbound_by_node, inbound_by_node)
        _atomic_write_text(
            self.facts_file,
            json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )

    def _build_ask_index(
        self,
        trail_nodes: list[dict[str, Any]],
        nodes_by_id: Mapping[str, Mapping[str, Any]],
        outbound_by_node: Mapping[str, list[tuple[str, str]]],
    ) -> dict[str, Any]:
        docs: list[dict[str, Any]] = []
        df: dict[str, int] = {}
        total_body_len = 0

        for trail_node in trail_nodes:
            node_id = trail_node["id"]
            raw_node = nodes_by_id.get(node_id, {})
            props = raw_node.get("properties") if isinstance(raw_node.get("properties"), Mapping) else {}
            name_tokens = _tokenize(trail_node["name"])
            path_tokens = _tokenize(trail_node["path"])
            callee_names = [
                str(nodes_by_id.get(target_id, {}).get("name") or target_id)
                for _, target_id in outbound_by_node.get(node_id, [])
            ]
            body_parts = [
                trail_node["name"],
                trail_node["kind"],
                str(trail_node.get("owner") or ""),
                trail_node["signature"],
                trail_node["summary"],
                str(props.get("expression") or ""),
                " ".join(callee_names),
            ]
            body_tokens = _tokenize(" ".join(part for part in body_parts if part))
            tf: dict[str, int] = {}
            for token in body_tokens:
                tf[token] = tf.get(token, 0) + 1
            for token in set(tf.keys()) | set(name_tokens) | set(path_tokens):
                df[token] = df.get(token, 0) + 1
            body_len = len(body_tokens)
            total_body_len += body_len
            docs.append(
                {
                    "id": node_id,
                    "nameTokens": name_tokens,
                    "pathTokens": path_tokens,
                    "tf": tf,
                    "bodyLen": body_len,
                }
            )

        doc_count = len(docs)
        avg_body_len = (total_body_len / doc_count) if doc_count > 0 else 0.0
        return {
            "version": ASK_INDEX_VERSION,
            "avgBodyLen": avg_body_len,
            "df": df,
            "docCount": doc_count,
            "docs": docs,
        }

    def _write_markdown_cards(
        self,
        trail_nodes: list[dict[str, Any]],
        trail_edges: list[dict[str, Any]],
        nodes_by_file: Mapping[str, list[dict[str, Any]]],
        outbound_by_node: Mapping[str, list[tuple[str, str]]],
        inbound_by_node: Mapping[str, list[tuple[str, str]]],
    ) -> None:
        node_names = {item["id"]: item["name"] for item in trail_nodes}
        hubs = sorted(
            trail_nodes,
            key=lambda item: (-len(inbound_by_node.get(item["id"], [])), item["name"].casefold()),
        )[:15]

        index_lines = [
            "# Trail Power BI Wiring Index",
            "",
            f"- **Nodes:** {len(trail_nodes)}",
            f"- **Edges:** {len(trail_edges)}",
            f"- **Files:** {len(nodes_by_file)}",
            "",
            "## Top Hubs",
            "",
        ]
        if hubs:
            for hub in hubs:
                in_count = len(inbound_by_node.get(hub["id"], []))
                out_count = len(outbound_by_node.get(hub["id"], []))
                index_lines.append(
                    f"- `{hub['name']}` ({hub['kind']}) — `{hub['path']}:{hub['span']}` "
                    f"[inbound: {in_count}, outbound: {out_count}]"
                )
        else:
            index_lines.append("- _(empty graph)_")

        index_lines.extend(["", "## Indexed Files", ""])
        for file_path in sorted(nodes_by_file):
            file_nodes = nodes_by_file[file_path]
            index_lines.append(f"- `{file_path}` ({len(file_nodes)} symbols) -> `{file_path}.md`")

        _atomic_write_text(self.index_md_file, "\n".join(index_lines) + "\n")

        for file_path, file_nodes in sorted(nodes_by_file.items()):
            card_path = self.root / f"{file_path}.md"
            card_lines = [
                f"# `{file_path}`",
                "",
                "## Symbols",
                "",
            ]
            for item in file_nodes:
                card_lines.append(f"### `{item['name']}` ({item['kind']}) — `{item['span']}`")
                card_lines.append(f"- **ID:** `{item['id']}`")
                card_lines.append(f"- **Signature:** `{item['signature']}`")
                if item.get("owner"):
                    card_lines.append(f"- **Owner:** `{item['owner']}`")
                if item.get("summary"):
                    card_lines.append(f"- **Summary:** {item['summary']}")
                outbound = outbound_by_node.get(item["id"], [])
                if outbound:
                    formatted_out = ", ".join(
                        f"{rel} `{node_names.get(target, target)}`" for rel, target in outbound[:20]
                    )
                    card_lines.append(f"- **Depends on / Uses:** {formatted_out}")
                inbound = inbound_by_node.get(item["id"], [])
                if inbound:
                    formatted_in = ", ".join(
                        f"{rel} by `{node_names.get(source, source)}`" for rel, source in inbound[:20]
                    )
                    card_lines.append(f"- **Used by:** {formatted_in}")
                card_lines.append("")
            _atomic_write_text(card_path, "\n".join(card_lines))


__all__ = [
    "ASK_INDEX_VERSION",
    "KIND_TO_PBI_TYPE",
    "PBI_EDGE_TO_RELATION",
    "PBI_TYPE_TO_KIND",
    "RELATION_TO_PBI_EDGE",
    "TRAIL_GRAPH_VERSION",
    "TrailStore",
]
