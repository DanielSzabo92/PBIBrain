"""Phase 1 scan entry point."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.graph.loader import FactGraph, build_fact_graph
from backend.graph.repository import GraphRepository
from backend.graph.schema import Edge, Node
from backend.sync import (
    CHANGED,
    DELETED,
    NEW,
    UNCHANGED,
    SyncResult,
    classify_changes,
    edge_fingerprint,
    node_fingerprint,
    preserve_review_statuses,
    reconcile_overrides,
)

LOGGER = logging.getLogger(__name__)


_ANALYSIS_PROPERTIES = (
    "dax_ast",
    "dax_asts",
    "dax_behaviors",
    "dax_evidence",
    "dax_diagnostics",
)


def _stamp_hashes(nodes: list[Node]) -> None:
    """Persist a source fingerprint without making it part of identity."""

    for node in nodes:
        value = node_fingerprint(node)
        node.properties["source_hash"] = value
        node.properties["source_fingerprint"] = value


def _copy_cached_analysis(
    current: dict[str, Node],
    previous: dict[str, Node],
    allowed_ids: set[str] | None = None,
) -> None:
    """Reuse analysis payloads for unchanged nodes before inference runs."""

    for identifier, node in current.items():
        if allowed_ids is not None and identifier not in allowed_ids:
            continue
        old = previous.get(identifier)
        if old is None:
            continue
        for key in _ANALYSIS_PROPERTIES:
            if key in old.properties and key not in node.properties:
                node.properties[key] = old.properties[key]


def _analysis_map_for_inference(
    nodes: list[Node],
    dax_result: Any,
    previous: dict[str, Node],
    previous_edges: list[Edge],
    affected_ids: set[str],
) -> dict[str, Any]:
    values = dict(getattr(dax_result, "analyses", {}) or {})
    for node in nodes:
        if node.id in affected_ids or node.id in values:
            continue
        old = previous.get(node.id)
        if old is None:
            continue
        behaviors = old.properties.get("dax_behaviors", [])
        evidence = old.properties.get("dax_evidence", [])
        if behaviors or evidence:
            references = []
            for edge in previous_edges:
                if edge.from_id != node.id or edge.source not in {"dax_analysis", "dax_ast"}:
                    continue
                references.append(
                    {
                        "target": edge.to_id,
                        "target_id": edge.to_id,
                        "type": "MEASURE" if edge.type == "DEPENDS_ON" else "COLUMN",
                        "source": "dax_ast",
                        "status": "factual",
                        "evidence_class": "FACT",
                        "evidence": edge.evidence,
                    }
                )
            values[node.id] = {
                "source_object_id": node.id,
                "ast": old.properties.get("dax_ast"),
                "dax_ast": old.properties.get("dax_ast"),
                "dax_asts": old.properties.get("dax_asts", {}),
                "behaviors": behaviors,
                "evidence": evidence,
                "references": references,
            }
    return values


def _unique_nodes(nodes: list[Node]) -> list[Node]:
    return list({node.id: node for node in nodes}.values())


def _unique_edges(edges: list[Edge]) -> list[Edge]:
    return list({edge.id: edge for edge in edges}.values())


def _preserve_candidate_statuses(
    graph: FactGraph,
    previous_nodes: list[Node],
    previous_edges: list[Edge],
) -> None:
    statuses: dict[str, str] = {}
    for node in previous_nodes:
        candidate_id = node.properties.get("candidate_id")
        if candidate_id and not node.properties.get("candidate_ids") and node.status != "factual":
            statuses[str(candidate_id)] = node.status
    for edge in previous_edges:
        candidate_id = edge.properties.get("candidate_id")
        if candidate_id and edge.status != "factual":
            statuses[str(candidate_id)] = edge.status
    for candidate in [*graph.semantic_candidates, *graph.conflicts]:
        identifier = str(getattr(candidate, "id", ""))
        if identifier in statuses:
            candidate.status = statuses[identifier]


def _clear_analysis(node: Node) -> None:
    """Drop cached parser output before an affected expression is analyzed."""

    for key in _ANALYSIS_PROPERTIES:
        node.properties.pop(key, None)


class Scanner:
    """Scan source metadata and load a rebuildable factual graph."""

    def __init__(
        self,
        repository: GraphRepository | None = None,
        *,
        database_path: str | Path | None = None,
        identity_path: str | Path | None = None,
        use_native: bool | None = None,
        overrides_path: str | Path | None = None,
        override_store: Any = None,
    ) -> None:
        self.repository = repository or GraphRepository(database_path, use_native=use_native)
        self.identity_path = identity_path
        self.overrides_path = Path(overrides_path) if overrides_path is not None else None
        self.override_store = override_store
        self.last_sync: SyncResult | None = None
        self.last_validation: Any = None

    def scan(self, model_source: Any, report_source: Any = None) -> FactGraph:
        # A second scan is a synchronization.  The first scan keeps the
        # existing full-build behavior and publishes an initial NEW delta.
        if self.repository.nodes:
            return self.rescan(model_source, report_source).graph
        graph = self._full_scan(model_source, report_source)
        self.last_sync = self._publish_sync(graph, [], [])
        return graph

    def _full_scan(self, model_source: Any, report_source: Any = None) -> FactGraph:
        graph = build_fact_graph(
            model_source,
            report_source,
            identity_path=self.identity_path,
            analyze_dax=True,
        )
        _stamp_hashes(graph.nodes)
        graph.load(self.repository)
        self.repository.last_scan = datetime.now(timezone.utc).isoformat()
        self._run_validation(graph)
        LOGGER.info("scan complete: %d nodes, %d factual edges", len(graph.nodes), len(graph.edges))
        return graph

    def scan_incremental(self, model_source: Any, report_source: Any = None) -> SyncResult:
        """Synchronize source metadata and return its deterministic delta."""

        if not self.repository.nodes:
            self._full_scan(model_source, report_source)
            assert self.last_sync is None
            self.last_sync = self._publish_sync(self._graph_from_repository(), [], [])
            return self.last_sync
        self.last_sync = self._incremental_scan(model_source, report_source)
        return self.last_sync

    # Public spelling used by the CLI/UI integrations.
    rescan = scan_incremental
    sync = scan_incremental

    def _incremental_scan(self, model_source: Any, report_source: Any = None) -> SyncResult:
        previous_nodes = self.repository.all_nodes()
        previous_edges = self.repository.all_edges()
        graph = build_fact_graph(
            model_source,
            report_source,
            identity_path=self.identity_path,
            analyze_dax=False,
        )
        current_by_id = {node.id: node for node in graph.nodes}
        previous_by_id = {node.id: node for node in previous_nodes}
        _stamp_hashes(graph.nodes)
        node_changes = classify_changes(previous_nodes, graph.nodes)
        _copy_cached_analysis(current_by_id, previous_by_id, set(node_changes[UNCHANGED]))
        changed_ids = set(node_changes[CHANGED]) | set(node_changes[NEW])
        deleted_ids = set(node_changes[DELETED])

        # A changed/deleted dependency invalidates its DAX consumers even when
        # the consumer expression text itself did not change.
        affected_ids = set(changed_ids)
        dependency_targets = changed_ids | deleted_ids
        for edge in previous_edges:
            if edge.source not in {"dax_analysis", "dax_ast"}:
                continue
            if edge.to_id in dependency_targets:
                affected_ids.add(edge.from_id)

        from backend.dax.analyzer import DaxAnalyzer

        expression_nodes = [
            current_by_id[item]
            for item in sorted(affected_ids)
            if item in current_by_id and current_by_id[item].type in {
                "MEASURE",
                "CALCULATION_ITEM",
                "SHARED_EXPRESSION",
                "USER_DEFINED_FUNCTION",
                "COLUMN",
            }
        ]
        for node in expression_nodes:
            _clear_analysis(node)
        analyzer = DaxAnalyzer(graph.nodes)
        dax_result = analyzer.analyze(expression_nodes)

        # Retain facts for untouched expressions.  Facts for affected sources
        # are replaced by this scan, including the unresolved-reference case.
        kept_dax_edges = [
            edge
            for edge in previous_edges
            if edge.source in {"dax_analysis", "dax_ast"}
            and edge.from_id not in affected_ids
            and edge.from_id in current_by_id
            and edge.to_id in current_by_id
        ]
        graph.edges.extend(kept_dax_edges)
        graph.edges.extend(dax_result.edges)
        analysis_map = _analysis_map_for_inference(
            graph.nodes,
            dax_result,
            previous_by_id,
            previous_edges,
            affected_ids,
        )

        from backend.inference.engine import InferenceEngine

        inference = InferenceEngine(graph.nodes, dax_analysis=analysis_map, edges=graph.edges).infer()
        graph.nodes.extend(inference.nodes)
        graph.edges.extend(inference.edges)
        graph.nodes = _unique_nodes(graph.nodes)
        graph.edges = _unique_edges(graph.edges)
        graph.semantic_candidates = inference.candidates
        graph.conflicts = inference.conflicts
        graph.observations = inference.observations
        graph.diagnostics = list(dax_result.diagnostics)
        for diagnostic in inference.diagnostics:
            if diagnostic not in graph.diagnostics:
                graph.diagnostics.append(diagnostic)
        preserve_review_statuses(graph.nodes, graph.edges, previous_nodes, previous_edges)
        _preserve_candidate_statuses(graph, previous_nodes, previous_edges)
        _stamp_hashes(graph.nodes)
        graph.load(self.repository)
        self.repository.last_scan = datetime.now(timezone.utc).isoformat()
        self._run_validation(
            graph,
            previous={"nodes": previous_nodes, "edges": previous_edges},
        )
        LOGGER.info(
            "incremental scan complete: %d nodes, %d edges (%d affected)",
            len(graph.nodes),
            len(graph.edges),
            len(affected_ids),
        )
        return self._publish_sync(graph, previous_nodes, previous_edges, affected_ids=affected_ids)

    def _run_validation(
        self,
        graph: FactGraph,
        *,
        previous: Any = None,
    ) -> Any:
        """Run read-only validation and publish its runtime result.

        Validation is deliberately kept beside scan orchestration.  It reads
        the canonical graph after load and never changes graph facts or the
        source adapter.
        """

        from backend.validation import validate

        store = self.override_store if self.override_store is not None else self._load_override_store()
        result = validate(
            graph,
            overrides=store,
            previous=previous,
            current=graph if previous is not None else None,
        )
        self.last_validation = result
        setter = getattr(self.repository, "set_validation_result", None)
        if callable(setter):
            setter(result)
        else:
            self.repository.validation_result = result
        return result

    def _publish_sync(
        self,
        graph: FactGraph,
        previous_nodes: list[Node],
        previous_edges: list[Edge],
        *,
        affected_ids: set[str] | None = None,
    ) -> SyncResult:
        changes = classify_changes(previous_nodes, graph.nodes)
        edge_changes = classify_changes(previous_edges, graph.edges)
        reconciliation = reconcile_overrides(
            self.override_store or self._load_override_store(),
            graph.nodes,
            graph.edges,
        )
        result = SyncResult(
            graph=graph,
            changes=changes,
            edge_changes=edge_changes,
            stale_overrides=reconciliation.stale,
            override_conflicts=reconciliation.conflicts,
            affected_ids=sorted(affected_ids or set()),
            diagnostics=list(graph.diagnostics),
        )
        # Keep edge deltas available without mixing edge IDs into the object
        # delta most callers use for source-change decisions.
        return result

    def _load_override_store(self) -> Any:
        if self.overrides_path is None or not self.overrides_path.is_file():
            return None
        from backend.api.review import OverrideStore

        return OverrideStore(self.overrides_path)

    def _graph_from_repository(self) -> FactGraph:
        return FactGraph(self.repository.all_nodes(), self.repository.all_edges())


def scan(
    model_source: Any,
    report_source: Any = None,
    *,
    repository: GraphRepository | None = None,
    database_path: str | Path | None = None,
    identity_path: str | Path | None = None,
    use_native: bool | None = None,
    overrides_path: str | Path | None = None,
    override_store: Any = None,
) -> FactGraph:
    return Scanner(
        repository,
        database_path=database_path,
        identity_path=identity_path,
        use_native=use_native,
        overrides_path=overrides_path,
        override_store=override_store,
    ).scan(model_source, report_source)
