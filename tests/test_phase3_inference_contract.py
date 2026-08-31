"""Phase 3 semantic-inference contracts.

These tests inspect the canonical graph only.  They do not depend on a
particular inference class or persistence implementation.
"""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from backend.graph.loader import build_fact_graph
from backend.graph.repository import GraphRepository
from backend.scanner.pipeline import Scanner

from tests.fixtures.phase3_sources import (
    COL_CHOICE,
    COL_CONTROL_UNRELATED,
    COL_DATE,
    COL_NAMING_ONLY,
    MEASURE_CONFLICT,
    MEASURE_NET,
    MODEL_ID,
    TABLE_CONFLICT,
    TABLE_CONTROL,
    TABLE_NAMING_ONLY,
    semantic_model_source,
    semantic_report_source,
)


def _dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return dict(to_dict())
    return dict(vars(value))


def _records(graph: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes = [_dict(item) for item in graph.nodes]
    edges = [_dict(item) for item in graph.edges]
    return nodes, edges


def _node(nodes: list[dict[str, Any]], source_id: str) -> dict[str, Any]:
    return next(item for item in nodes if item.get("source_id") == source_id)


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, (list, tuple, set, frozenset)):
        for child in value:
            yield from _walk(child)


def _semantic_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        item
        for item in nodes
        if str(item.get("type", "")).upper()
        in {"BUSINESS_CONCEPT", "SELECTOR", "SELECTOR_OPTION"}
    ]


def _semantic_edges(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    semantic_types = {
        "CONTROLLED_BY",
        "HAS_OPTION",
        "DEFAULTS_TO",
        "SEMANTICALLY_MAPS_TO",
        "SIMILAR_TO",
        "CONFLICT",
    }
    return [
        item
        for item in edges
        if str(item.get("evidence_class", "")).upper() == "INFERRED"
        or str(item.get("type", "")).upper() in semantic_types
        or str(item.get("status", "")).lower() == "candidate"
    ]


def _semantic_blob(
    nodes: list[dict[str, Any]], edges: list[dict[str, Any]], object_id: str | None = None
) -> list[dict[str, Any]]:
    selected_nodes = _semantic_nodes(nodes)
    selected_edges = _semantic_edges(edges)
    if object_id is not None:
        selected_nodes += [item for item in nodes if item.get("id") == object_id]
        selected_edges += [
            item
            for item in edges
            if item.get("from_id") == object_id or item.get("to_id") == object_id
        ]
    unique: dict[str, dict[str, Any]] = {}
    for item in selected_nodes + selected_edges:
        marker = json.dumps(item, sort_keys=True, default=str)
        unique[marker] = item
    return list(unique.values())


def _has_provenance_source(records: list[dict[str, Any]], source: str) -> bool:
    return any(
        str(mapping.get("source", "")).casefold() == source.casefold()
        for record in records
        for mapping in _walk(record)
    )


def _has_conflict(records: list[dict[str, Any]]) -> bool:
    keys = {
        "conflict",
        "conflicts",
        "contradiction",
        "contradictions",
        "conflict_type",
        "warning",
        "warnings",
        "issue_type",
    }
    for record in records:
        for mapping in _walk(record):
            for key, value in mapping.items():
                value_text = str(value).casefold()
                if str(key).casefold() in keys and (
                    "conflict" in value_text or "contradict" in value_text
                ):
                    return True
    return False


def _contains_text(records: list[dict[str, Any]], *needles: str) -> bool:
    text = json.dumps(records, sort_keys=True, default=str).casefold()
    return all(needle.casefold() in text for needle in needles)


class Phase3InferenceContractTests(unittest.TestCase):
    def _build(self, report: bool = False):
        return build_fact_graph(
            semantic_model_source(),
            semantic_report_source() if report else None,
            analyze_dax=True,
        )

    def test_description_first_arbitrary_concept_and_alias_are_reviewable(self):
        graph = self._build()
        nodes, edges = _records(graph)
        source = _node(nodes, MEASURE_NET)
        semantic = _semantic_blob(nodes, edges, source["id"])

        self.assertTrue(_semantic_nodes(nodes), "semantic nodes missing")
        self.assertTrue(_has_provenance_source(semantic, "description"), semantic)
        self.assertTrue(_contains_text(semantic, "net invoiced revenue", "booked revenue"), semantic)
        self.assertTrue(
            any(
                str(item.get("type", "")).upper() == "BUSINESS_CONCEPT"
                and item.get("status") in {"candidate", "approved", "rejected", "overridden"}
                for item in nodes
            ),
            nodes,
        )

    def test_candidate_confidence_is_bounded_and_has_evidence(self):
        graph = self._build()
        nodes, edges = _records(graph)
        candidates = [
            item
            for item in _semantic_nodes(nodes) + _semantic_edges(edges)
            if item.get("status") == "candidate" or item.get("evidence_class") == "INFERRED"
        ]
        self.assertTrue(candidates, "no semantic candidates")
        for item in candidates:
            confidence = item.get("confidence")
            if confidence is None:
                confidence = (item.get("properties") or {}).get("confidence")
            self.assertIsNotNone(confidence, item)
            self.assertGreaterEqual(float(confidence), 0.0, item)
            self.assertLessEqual(float(confidence), 1.0, item)
            evidence = item.get("evidence") or (item.get("properties") or {}).get("evidence")
            self.assertTrue(evidence, item)

    def test_selector_is_behavioral_and_not_name_only(self):
        graph = self._build()
        nodes, edges = _records(graph)
        selectors = [item for item in nodes if item.get("type") == "SELECTOR"]
        self.assertTrue(selectors, "behavioral selector candidate missing")
        control_selectors = [
            item
            for item in selectors
            if TABLE_CONTROL.casefold() in json.dumps(item, default=str).casefold()
            or COL_CHOICE.casefold() in json.dumps(item, default=str).casefold()
        ]
        self.assertTrue(control_selectors, selectors)
        self.assertFalse(
            any(
                TABLE_NAMING_ONLY.casefold() in json.dumps(item, default=str).casefold()
                or COL_NAMING_ONLY.casefold() in json.dumps(item, default=str).casefold()
                for item in selectors
            ),
            selectors,
        )
        selector_ids = {item["id"] for item in control_selectors}
        measure_id = _node(nodes, MEASURE_NET)["id"]
        self.assertTrue(
            any(
                item.get("type") == "CONTROLLED_BY"
                and measure_id in {item.get("from_id"), item.get("to_id")}
                and ({item.get("from_id"), item.get("to_id")} & selector_ids)
                for item in edges
            ),
            edges,
        )
        option_edges = [
            item
            for item in edges
            if item.get("type") == "HAS_OPTION" and item.get("from_id") in selector_ids
        ]
        self.assertGreaterEqual(len(option_edges), 2, option_edges)
        option_records = option_edges + [
            item for item in nodes if item.get("id") in {edge.get("to_id") for edge in option_edges}
        ]
        self.assertTrue(_contains_text(option_records, "LOCAL", "USD"), option_records)
        self.assertFalse(_contains_text(option_records, "INTERNAL", "PUBLIC"), option_records)

    def test_selectedvalue_default_keeps_ast_evidence(self):
        graph = self._build()
        nodes, edges = _records(graph)
        defaults = [item for item in edges if item.get("type") == "DEFAULTS_TO"]
        self.assertTrue(defaults, "default candidate missing")
        default_records = defaults + [
            item for item in nodes if item.get("id") in {edge.get("to_id") for edge in defaults}
        ]
        self.assertTrue(_contains_text(default_records, "LOCAL", "SELECTEDVALUE"), default_records)
        self.assertTrue(
            any(
                mapping.get("ast_location") or mapping.get("location")
                for record in default_records
                for mapping in _walk(record)
            ),
            default_records,
        )

    def test_conflicting_description_and_behavior_is_not_silently_resolved(self):
        graph = self._build()
        nodes, edges = _records(graph)
        source = _node(nodes, MEASURE_CONFLICT)
        relevant = _semantic_blob(nodes, edges, source["id"])
        relevant.append(_node(nodes, TABLE_CONFLICT))
        relevant += [
            item
            for item in _semantic_blob(nodes, edges)
            if TABLE_CONFLICT.casefold() in json.dumps(item, default=str).casefold()
        ]
        self.assertTrue(_has_conflict(relevant), relevant)

    def test_report_cooccurrence_is_observed_only(self):
        graph = self._build(report=True)
        nodes, edges = _records(graph)
        measure = _node(nodes, MEASURE_NET)["id"]
        date = _node(nodes, COL_DATE)["id"]
        observed = [
            item
            for item in edges
            if item.get("type") == "OBSERVED_WITH"
            and {item.get("from_id"), item.get("to_id")} == {measure, date}
        ]
        self.assertTrue(observed, edges)
        for item in observed:
            self.assertEqual(item.get("evidence_class"), "OBSERVED", item)
            self.assertTrue(item.get("evidence"), item)
        self.assertFalse(
            any("COMPATIB" in str(item.get("type", "")).upper() for item in edges),
            edges,
        )

    def test_facts_inferences_and_observations_never_collapse(self):
        graph = self._build(report=True)
        nodes, edges = _records(graph)
        self.assertTrue(any(item.get("evidence_class") == "FACT" for item in edges))
        self.assertTrue(any(item.get("evidence_class") == "INFERRED" for item in edges))
        self.assertTrue(any(item.get("evidence_class") == "OBSERVED" for item in edges))
        for item in edges:
            if item.get("evidence_class") == "INFERRED":
                self.assertIn(
                    item.get("status"),
                    {"candidate", "approved", "rejected", "overridden"},
                    item,
                )
        self.assertTrue(any(item.get("status") == "candidate" for item in _semantic_nodes(nodes) + edges))

    def test_semantic_graph_is_deterministic_and_uses_parsed_dax(self):
        first = self._build(report=True).to_dict()
        second = self._build(report=True).to_dict()
        self.assertEqual(first, second)
        expression_nodes = [
            item
            for item in first["nodes"]
            if item["type"] in {"MEASURE", "COLUMN"}
            and (item.get("properties") or {}).get("expression")
        ]
        self.assertTrue(expression_nodes)
        for item in expression_nodes:
            self.assertIn("dax_ast", item.get("properties", {}), item)
        for item in first["edges"]:
            if item.get("evidence_class") == "INFERRED":
                for evidence in item.get("evidence", []):
                    if isinstance(evidence, dict) and evidence.get("source") in {"dax_ast", "dax_analysis"}:
                        self.assertTrue(evidence.get("ast_location") or evidence.get("location"), evidence)

    def test_scanner_persists_semantic_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = GraphRepository(root / "brain.json", use_native=False)
            graph = Scanner(repository, identity_path=root / "identity.json").scan(
                semantic_model_source(), semantic_report_source()
            )
            self.assertTrue(any(item.evidence_class == "INFERRED" for item in graph.edges))
            self.assertTrue(any(item.type == "SELECTOR" for item in repository.all_nodes()))
            self.assertTrue(any(item.type == "OBSERVED_WITH" for item in repository.all_edges()))
            repository.close()


if __name__ == "__main__":
    unittest.main()
