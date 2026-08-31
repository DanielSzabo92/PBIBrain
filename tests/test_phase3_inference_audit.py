"""Focused Phase 3 regression tests found during implementation audit."""

from __future__ import annotations

from copy import deepcopy
import unittest
from unittest.mock import patch

from backend.dax.analyzer import analyze_nodes
from backend.graph.loader import build_fact_graph
from backend.graph.schema import Node
from backend.inference.engine import InferenceEngine
from backend.inference.engine import _fallback_selector_candidates
from backend.inference.selectors import discover_selector_options, discover_selectors
from backend.inference.semantics import detect_conflicts, infer_candidates

from tests.fixtures.phase3_sources import (
    TABLE_CONTROL,
    fallback_values_model_source,
    semantic_model_source,
)


def _table_node(graph, source_id: str):
    return next(item for item in graph.nodes if item.source_id == source_id)


class Phase3InferenceAuditTests(unittest.TestCase):
    def test_selector_identity_survives_display_name_change(self):
        original = semantic_model_source()
        renamed = deepcopy(original)
        next(table for table in renamed["tables"] if table["id"] == TABLE_CONTROL)["name"] = "Renamed Option Set"
        next(
            measure
            for table in renamed["tables"]
            for measure in table.get("measures", [])
            if measure.get("id") == "measure-net-revenue"
        )["expression"] = next(
            measure
            for table in original["tables"]
            for measure in table.get("measures", [])
            if measure.get("id") == "measure-net-revenue"
        )["expression"].replace("Display Controls", "Renamed Option Set")

        first = build_fact_graph(original, analyze_dax=False)
        second = build_fact_graph(renamed, analyze_dax=False)
        first_table = _table_node(first, TABLE_CONTROL)
        second_table = _table_node(second, TABLE_CONTROL)
        self.assertEqual(first_table.id, second_table.id)
        first_analyses = analyze_nodes(first.nodes)
        second_analyses = analyze_nodes(second.nodes)
        first_selectors = discover_selectors(first.nodes, first_analyses, first.edges)
        second_selectors = discover_selectors(second.nodes, second_analyses, second.edges)
        first_candidate = next(item for item in first_selectors if item.get("target_id") == first_table.id)
        second_candidate = next(item for item in second_selectors if item.get("target_id") == second_table.id)
        self.assertEqual(
            first_candidate.get("selector_id"),
            second_candidate.get("selector_id"),
        )

    def test_selector_options_only_use_behaviorally_referenced_columns(self):
        graph = build_fact_graph(semantic_model_source(), analyze_dax=False)
        analyses = analyze_nodes(graph.nodes)
        selectors = discover_selectors(graph.nodes, analyses, graph.edges)
        control_table = _table_node(graph, TABLE_CONTROL)
        control = next(item for item in selectors if item.get("target_id") == control_table.id)
        options = discover_selector_options([control], graph.nodes)
        values = {str(item.get("value")) for item in options}

        self.assertEqual(values, {"LOCAL", "USD"}, options)
        self.assertTrue(all(item.get("column_id", "").endswith("column-choice") for item in options), options)

    def test_referenced_base_measure_does_not_inherit_selector_behavior_or_conflict(self):
        graph = build_fact_graph(semantic_model_source(), analyze_dax=False)
        batch = analyze_nodes(graph.nodes)
        candidates = infer_candidates(graph.nodes, batch)
        base = next(item for item in graph.nodes if item.source_id == "measure-base-amount")

        self.assertFalse(
            any(
                item.target == base.id
                and item.type == "BEHAVIOR"
                and "SELECTOR" in str(item.value).upper()
                for item in candidates
            ),
            candidates,
        )
        self.assertFalse(
            any(
                item.target == base.id and "SELECTOR" in item.reason.upper()
                for item in detect_conflicts(graph.nodes, candidates, batch)
            ),
        )

    def test_fallback_values_selector_id_survives_rename_and_keeps_options(self):
        first = build_fact_graph(fallback_values_model_source(), analyze_dax=False)
        second = build_fact_graph(
            fallback_values_model_source("Renamed Option Set"), analyze_dax=False
        )
        first_batch = analyze_nodes(first.nodes)
        second_batch = analyze_nodes(second.nodes)
        first_candidates = _fallback_selector_candidates(first.nodes, first_batch.analyses, first.edges)
        second_candidates = _fallback_selector_candidates(second.nodes, second_batch.analyses, second.edges)
        first_candidate = next(item for item in first_candidates if item.target.endswith("table:fallback-options"))
        second_candidate = next(item for item in second_candidates if item.target.endswith("table:fallback-options"))

        from backend.inference.semantics import semantic_node_for

        self.assertEqual(semantic_node_for(first_candidate).id, semantic_node_for(second_candidate).id)
        first_options = discover_selector_options([first_candidate], first.nodes)
        second_options = discover_selector_options([second_candidate], second.nodes)
        self.assertEqual({item.get("value") for item in first_options}, {"A", "B"}, first_options)
        self.assertEqual({item.get("value") for item in second_options}, {"A", "B"}, second_options)

    def test_semantic_helpers_accept_a_real_dax_analysis_batch(self):
        graph = build_fact_graph(semantic_model_source(), analyze_dax=False)
        batch = analyze_nodes(graph.nodes)

        candidates = infer_candidates(graph.nodes, batch)
        self.assertTrue(candidates)
        conflicts = detect_conflicts(graph.nodes, candidates, batch)
        self.assertIsInstance(conflicts, list)

    def test_conflicts_consume_analysis_not_raw_expression_text(self):
        base = Node(
            id="measure:base",
            type="MEASURE",
            name="Amount",
            description="Invoice amount before currency conversion.",
            source_id="measure-base-amount",
            properties={"expression": "SUM('Sales'[Amount])"},
        )
        batch = analyze_nodes([base])
        candidates = infer_candidates([base])
        candidate = next(
            item
            for item in candidates
            if item.target == base.id and item.type == "BUSINESS_CONCEPT"
        )

        class ExplosiveDax:
            def __str__(self):  # pragma: no cover - failure sentinel
                raise AssertionError("conflict logic reread raw DAX")

        base.properties["expression"] = ExplosiveDax()
        conflicts = detect_conflicts([base], [candidate], batch)
        self.assertEqual(conflicts, [])

    def test_inference_helper_errors_are_visible(self):
        graph = build_fact_graph(semantic_model_source(), analyze_dax=False)
        batch = analyze_nodes(graph.nodes)
        with patch(
            "backend.inference.selectors.discover_selectors",
            side_effect=RuntimeError("selector helper failed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "selector helper failed"):
                InferenceEngine(graph.nodes, dax_analysis=batch, edges=graph.edges).infer()

    def test_analysis_diagnostics_survive_inference(self):
        graph = build_fact_graph(semantic_model_source(), analyze_dax=False)
        batch = analyze_nodes(graph.nodes)
        sentinel = {"code": "audit_probe", "message": "diagnostic must survive"}
        batch.diagnostics.append(sentinel)

        result = InferenceEngine(graph.nodes, dax_analysis=batch, edges=graph.edges).infer()
        self.assertIn(sentinel, result.diagnostics)


if __name__ == "__main__":
    unittest.main()
