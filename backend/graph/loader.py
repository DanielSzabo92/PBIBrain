"""Build the factual graph from normalized model/report nodes."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .repository import GraphRepository
from .schema import Edge, Node
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
            )
            return
        values = {json.dumps(item, sort_keys=True, default=str): item for item in current.evidence}
        values.update({json.dumps(item, sort_keys=True, default=str): item for item in evidence_values})
        current.evidence = [values[key] for key in sorted(values)]

    def _build_edges(self) -> None:
        self._edges.clear()
        nodes = list(self.normalizer.nodes.values())
        node_ids = {node.id for node in nodes}
        models = [node for node in nodes if node.type == "MODEL"]
        model_child_types = {
            "TABLE",
            "RELATIONSHIP",
            "FIELD_PARAMETER",
            "SHARED_EXPRESSION",
            "USER_DEFINED_FUNCTION",
            "CALCULATION_GROUP",
        }
        for model in models:
            for node in nodes:
                if node.model_id == model.id and (
                    node.type in model_child_types
                    or (node.type == "MEASURE" and not node.properties.get("table_id"))
                ):
                    self._add_edge("CONTAINS", model.id, node.id, source="model_metadata", evidence=["model membership"])

        for node in nodes:
            properties = node.properties
            table_id = properties.get("table_id")
            if table_id in node_ids and node.type in {"COLUMN", "MEASURE"}:
                self._add_edge("CONTAINS", str(table_id), node.id, source="model_metadata", evidence=["table membership"])
            group_id = properties.get("calculation_group_id")
            if group_id in node_ids and node.type == "CALCULATION_ITEM":
                self._add_edge("CONTAINS", str(group_id), node.id, source="model_metadata", evidence=["calculation group membership"])
            parent_id = properties.get("parent_id")
            if parent_id in node_ids and node.type in {"PAGE", "VISUAL", "VISUAL_CALCULATION", "VISUAL_FILTER", "PAGE_FILTER", "REPORT_FILTER"}:
                self._add_edge("CONTAINS", str(parent_id), node.id, source="report_metadata", evidence=["report containment"])

            if node.type == "REPORT" and node.model_id in node_ids:
                self._add_edge("USES_MODEL", node.id, node.model_id, source="report_metadata", evidence=["report model reference"])
            if node.type == "VISUAL":
                for object_id in properties.get("field_ids", []):
                    self._add_edge("USES", node.id, str(object_id), source="report_metadata", evidence=["visual field binding"])
            if node.type == "FIELD_PARAMETER":
                for object_id in properties.get("referenced_object_ids", []):
                    self._add_edge("REFERENCES", node.id, str(object_id), source="model_metadata", evidence=["field parameter entry"])
            if node.type == "RELATIONSHIP":
                for endpoint in (properties.get("from_column_id"), properties.get("to_column_id")):
                    self._add_edge("RELATES_TO", node.id, str(endpoint) if endpoint else None, source="model_metadata", evidence=["relationship endpoint"])
            if node.type in {"VISUAL_FILTER", "PAGE_FILTER", "REPORT_FILTER"}:
                target_id = properties.get("target_id")
                self._add_edge("FILTERS", node.id, str(target_id) if target_id else None, source="report_metadata", evidence=["filter target"])


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
