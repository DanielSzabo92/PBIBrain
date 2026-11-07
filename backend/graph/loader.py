"""Build the factual graph from normalized model/report nodes."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .data_sources import link_data_sources
from .repository import GraphRepository
from .schema import Edge, Node
from .usage_links import report_link_edges, visual_usage_properties
from backend.scanner.metadata_reader import pick
from backend.scanner.model_reader import ModelReader
from backend.scanner.normalization import Normalizer, StableIdentity
from backend.scanner.report_reader import ReportReader
from backend.scanner.pbip import is_pbip_source, read_pbip_project

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class FactGraph:
    nodes: list[Node]
    edges: list[Edge]
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    semantic_candidates: list[Any] = field(default_factory=list)
    conflicts: list[Any] = field(default_factory=list)
    observations: list[Edge] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        result = {
            "nodes": [node.to_dict() for node in sorted(self.nodes, key=lambda item: item.id)],
            "edges": [edge.to_dict() for edge in sorted(self.edges, key=lambda item: item.id)],
            **({"diagnostics": self.diagnostics} if self.diagnostics else {}),
        }
        if self.semantic_candidates:
            result["semantic_candidates"] = [
                item.to_dict() if hasattr(item, "to_dict") else item for item in self.semantic_candidates
            ]
        if self.conflicts:
            result["conflicts"] = [item.to_dict() if hasattr(item, "to_dict") else item for item in self.conflicts]
        if self.observations:
            result["observations"] = [item.to_dict() for item in self.observations]
        return result

    def load(self, repository: GraphRepository) -> "FactGraph":
        repository.replace(self.nodes, self.edges)
        return self


def _many_sources(source: Any, reader: Any) -> list[Any]:
    if source is None:
        return []
    if isinstance(source, (list, tuple, set)):
        return list(source)
    if isinstance(source, Mapping):
        keys = ("models", "semanticModels", "semantic_models", "value") if isinstance(reader, ModelReader) else (
            "reports", "value"
        )
        for key in keys:
            values = pick(source, key)
            if isinstance(values, (list, tuple)):
                return list(values)
    if isinstance(source, (str, Path)):
        # The adapter decides whether a JSON document contains one or many.
        value = reader.read_many(source)
        return value
    return [source]


class FactGraphBuilder:
    def __init__(
        self,
        *,
        identity: StableIdentity | None = None,
        identity_path: str | Path | None = None,
    ) -> None:
        self.normalizer = Normalizer(identity=identity, identity_path=identity_path)
        self._edges: dict[str, Edge] = {}

    def build(self, model_sources: Any, report_sources: Any = None, *, analyze_dax: bool = False) -> FactGraph:
        model_reader = ModelReader()
        report_reader = ReportReader()
        if is_pbip_source(model_sources):
            bundle = read_pbip_project(model_sources)
            model_sources = bundle["models"]
            if report_sources is None:
                report_sources = bundle["reports"]
        for source_index, source in enumerate(_many_sources(model_sources, model_reader)):
            self.normalizer.normalize_model(source, source_key=source_index)
        for source_index, source in enumerate(_many_sources(report_sources, report_reader)):
            self.normalizer.normalize_report(source, source_key=source_index)
        self._build_edges()
        diagnostics: list[dict[str, Any]] = []
        semantic_candidates: list[Any] = []
        conflicts: list[Any] = []
        observations: list[Edge] = []
        if analyze_dax:
            # Import lazily so Phase 1 callers can build mechanical graphs
            # without loading the parser runtime.
            from backend.dax.analyzer import analyze_nodes

            dax_result = analyze_nodes(self.normalizer.nodes)
            for edge in dax_result.edges:
                self._edges[edge.id] = edge
            diagnostics = list(dax_result.diagnostics)
            # Phase 3 consumes the already parsed/analyzed result.  It never
            # reparses expression text.
            from backend.inference.engine import InferenceEngine

            inference = InferenceEngine(
                self.normalizer.nodes,
                dax_analysis=dax_result,
                edges=list(self._edges.values()),
            ).infer()
            for node in inference.nodes:
                self.normalizer.nodes.setdefault(node.id, node)
            for edge in inference.edges:
                self._edges[edge.id] = edge
            semantic_candidates = inference.candidates
            conflicts = inference.conflicts
            observations = inference.observations
            for diagnostic in inference.diagnostics:
                if diagnostic not in diagnostics:
                    diagnostics.append(diagnostic)
        self.normalizer.identity.save()
        nodes = sorted(self.normalizer.nodes.values(), key=lambda item: item.id)
        edges = sorted(self._edges.values(), key=lambda item: item.id)
        LOGGER.info("built factual graph: %d nodes, %d edges", len(nodes), len(edges))
        if diagnostics:
            LOGGER.warning("DAX analysis reported %d diagnostics", len(diagnostics))
        return FactGraph(nodes, edges, diagnostics, semantic_candidates, conflicts, observations)

    def _add_edge(
        self,
        edge_type: str,
        from_id: str | None,
        to_id: str | None,
        *,
        source: str,
        evidence: Iterable[Any],
        properties: Mapping[str, Any] | None = None,
    ) -> None:
        if not from_id or not to_id or from_id not in self.normalizer.nodes or to_id not in self.normalizer.nodes:
            return
        evidence_values = list(evidence)
        marker = "|".join((edge_type.upper(), str(from_id), str(to_id), source))
        edge_id = "edge:" + hashlib.sha256(marker.encode("utf-8")).hexdigest()[:32]
        current = self._edges.get(edge_id)
        if current is None:
            self._edges[edge_id] = Edge(
                id=edge_id,
                type=edge_type,
                from_id=from_id,
                to_id=to_id,
                source=source,
                confidence=1.0,
                status="factual",
                evidence=evidence_values,
                evidence_class="FACT",
                properties=dict(properties or {}),
            )
            return
        if properties:
            current.properties.update(properties)
        values = {json.dumps(item, sort_keys=True, default=str): item for item in current.evidence}
        values.update({json.dumps(item, sort_keys=True, default=str): item for item in evidence_values})
        current.evidence = [values[key] for key in sorted(values)]

    def _build_edges(self) -> None:
        self._edges.clear()
        # Adds the DATA_SOURCE nodes first, so the links below can reach them.
        source_links = link_data_sources(self.normalizer.nodes)
        nodes = list(self.normalizer.nodes.values())
        node_ids = {node.id for node in nodes}
        models = [node for node in nodes if node.type == "MODEL"]
        shared_expressions: dict[tuple[str | None, str], str] = {}
        for node in nodes:
            if node.type == "SHARED_EXPRESSION":
                shared_expressions[(node.model_id, node.name)] = node.id
        model_child_types = {
            "TABLE",
            "RELATIONSHIP",
            "FIELD_PARAMETER",
            "SHARED_EXPRESSION",
            "USER_DEFINED_FUNCTION",
            "CALCULATION_GROUP",
            "SECURITY_ROLE",
        }
        for model in models:
            for node in nodes:
                if node.model_id == model.id and (
                    (node.type in model_child_types and not (node.type == "CALCULATION_GROUP" and node.properties.get("table_id")))
                    or (node.type == "MEASURE" and not node.properties.get("table_id"))
                ):
                    self._add_edge("CONTAINS", model.id, node.id, source="model_metadata", evidence=["model membership"])

        for node in nodes:
            properties = node.properties
            table_id = properties.get("table_id")
            if table_id in node_ids and node.type in {"COLUMN", "MEASURE", "HIERARCHY", "PARTITION", "CALCULATION_GROUP"}:
                self._add_edge("CONTAINS", str(table_id), node.id, source="model_metadata", evidence=["table membership"])
            if node.type == "LEVEL":
                self._add_edge("CONTAINS", properties.get("hierarchy_id"), node.id, source="model_metadata", evidence=["hierarchy membership"])
                self._add_edge("REFERENCES", node.id, properties.get("column_id"), source="model_metadata", evidence=["hierarchy level column"])
            if node.type in {"ROLE_FILTER", "OLS_PERMISSION"}:
                self._add_edge("CONTAINS", properties.get("role_id"), node.id, source="model_metadata", evidence=["role membership"])
            if node.type == "ROLE_FILTER":
                self._add_edge("FILTERS", node.id, properties.get("table_id"), source="model_metadata", evidence=["row-level security filter table"])
            if node.type == "OLS_PERMISSION":
                self._add_edge("REFERENCES", node.id, properties.get("target_id"), source="model_metadata", evidence=["object-level security permission"])
            if node.type in {"PARTITION", "SHARED_EXPRESSION"} and properties.get("expression") and not _is_dax(node):
                for expression_id in shared_expression_refs(node, shared_expressions):
                    self._add_edge("REFERENCES", node.id, expression_id, source="model_metadata", evidence=["M reference to shared expression"])
            group_id = properties.get("calculation_group_id")
            if group_id in node_ids and node.type == "CALCULATION_ITEM":
                self._add_edge("CONTAINS", str(group_id), node.id, source="model_metadata", evidence=["calculation group membership"])
            parent_id = properties.get("parent_id")
            if parent_id in node_ids and node.type in {"PAGE", "VISUAL", "VISUAL_CALCULATION", "VISUAL_FILTER", "PAGE_FILTER", "REPORT_FILTER", "REPORT_MEASURE", "BOOKMARK"}:
                self._add_edge("CONTAINS", str(parent_id), node.id, source="report_metadata", evidence=["report containment"])

            if node.type in {"MODEL", "REPORT"} and properties.get("workspace_node_id") in node_ids:
                self._add_edge("CONTAINS", str(properties["workspace_node_id"]), node.id, source="model_metadata",
                               evidence=["cloud workspace membership"])
            if node.type == "REPORT" and node.model_id in node_ids:
                self._add_edge("USES_MODEL", node.id, node.model_id, source="report_metadata", evidence=["report model reference"])
            if node.type == "VISUAL":
                usage = visual_usage_properties(node)
                for object_id in properties.get("field_ids", []):
                    self._add_edge("USES", node.id, str(object_id), source="report_metadata", evidence=["visual field binding"],
                                   properties=usage.get(str(object_id), {"visual_type": properties.get("visual_type")}))
                for object_id in sorted({item["object_id"] for item in properties.get("field_roles", [])
                                         if item.get("usage") == "conditional_formatting"}):
                    self._add_edge("FORMATS_BY", node.id, object_id, source="report_metadata",
                                   evidence=["visual formatting field reference"], properties={"visual_type": properties.get("visual_type")})
            if node.type == "PAGE":
                role = {"Drillthrough": "drillthrough_field", "Tooltip": "tooltip_page_field"}.get(properties.get("page_type"), "page_field")
                for object_id in properties.get("binding_field_ids", []):
                    self._add_edge("USES", node.id, str(object_id), source="report_metadata", evidence=["page binding field"],
                                   properties={"role": role, "roles": [{"role": role, "usage": "page_binding"}]})
                for item in properties.get("visual_interactions", []):
                    self._add_edge("INTERACTS_WITH", item.get("source_id"), item.get("target_id"), source="report_metadata",
                                   evidence=["page visual interaction"],
                                   properties={"interaction": item.get("interaction"), "type": item.get("type"), "page_id": node.id})
            if node.type == "BOOKMARK":
                for object_id in [properties.get("page_id"), *properties.get("visual_ids", []), *properties.get("field_ids", [])]:
                    self._add_edge("REFERENCES", node.id, str(object_id) if object_id else None, source="report_metadata", evidence=["bookmark state"])
            if node.type == "FIELD_PARAMETER":
                for object_id in properties.get("referenced_object_ids", []):
                    self._add_edge("REFERENCES", node.id, str(object_id), source="model_metadata", evidence=["field parameter entry"])
            if node.type == "RELATIONSHIP":
                for endpoint in (properties.get("from_column_id"), properties.get("to_column_id")):
                    self._add_edge("RELATES_TO", node.id, str(endpoint) if endpoint else None, source="model_metadata", evidence=["relationship endpoint"])
            if node.type in {"VISUAL_FILTER", "PAGE_FILTER", "REPORT_FILTER"}:
                target_id = properties.get("target_id")
                self._add_edge("FILTERS", node.id, str(target_id) if target_id else None, source="report_metadata", evidence=["filter target"])
        for edge_type, from_id, to_id, evidence, edge_properties in report_link_edges(nodes):
            self._add_edge(edge_type, from_id, to_id, source="report_metadata", evidence=[evidence], properties=edge_properties)
        for edge_type, from_id, to_id, evidence, edge_properties in source_links:
            self._add_edge(edge_type, from_id, to_id, source="model_metadata", evidence=[evidence], properties=edge_properties)


_M_STRING = re.compile(r'(?<!#)"(?:[^"]|"")*"')
_M_COMMENT = re.compile(r"//[^\n]*|/\*.*?\*/", re.DOTALL)


def _is_dax(node: Node) -> bool:
    if node.type == "SHARED_EXPRESSION":
        kind = node.properties.get("raw_source", {}).get("kind") if isinstance(node.properties.get("raw_source"), Mapping) else None
        return str(kind or "m").casefold() != "m"
    return str(node.properties.get("expression_language") or "").upper() == "DAX"


def shared_expression_refs(node: Node, shared_expressions: Mapping[tuple[str | None, str], str]) -> list[str]:
    """Find the shared expressions that an M text names. The M text is not parsed.

    The check removes comments and string literals, then looks for each shared
    expression name as an identifier or as a quoted identifier (#"Name").
    """

    text = _M_COMMENT.sub(" ", str(node.properties.get("expression") or ""))
    quoted = set(re.findall(r'#"((?:[^"]|"")*)"', text))
    bare = _M_STRING.sub(" ", re.sub(r'#"(?:[^"]|"")*"', " ", text))
    found: list[str] = []
    for (model_id, name), expression_id in sorted(shared_expressions.items(), key=lambda item: item[1]):
        if model_id != node.model_id or expression_id == node.id:
            continue
        if name.replace('"', '""') in quoted or re.search(r"(?<![\w.#])" + re.escape(name) + r"(?![\w.])", bare):
            found.append(expression_id)
    return found


def build_fact_graph(
    model_sources: Any,
    report_sources: Any = None,
    *,
    identity: StableIdentity | None = None,
    identity_path: str | Path | None = None,
    analyze_dax: bool = False,
) -> FactGraph:
    return FactGraphBuilder(identity=identity, identity_path=identity_path).build(
        model_sources,
        report_sources,
        analyze_dax=analyze_dax,
    )


def scan_sources(
    model_sources: Any,
    report_sources: Any = None,
    *,
    repository: GraphRepository | None = None,
    database_path: str | Path | None = None,
    identity_path: str | Path | None = None,
    use_native: bool | None = None,
    analyze_dax: bool = False,
) -> FactGraph:
    graph = build_fact_graph(model_sources, report_sources, identity_path=identity_path, analyze_dax=analyze_dax)
    target = repository or GraphRepository(database_path, use_native=use_native)
    graph.load(target)
    return graph


GraphLoader = FactGraphBuilder
