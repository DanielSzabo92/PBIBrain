"""Regression contracts for TMSL calculated-column semantics."""

from __future__ import annotations

import unittest

from backend.graph.loader import build_fact_graph

from tests.fixtures.tmsl_sources import (
    calculated_column_source,
    m_shared_expression_source,
    measure_expression_lines_source,
)


class TmslSemanticsContractTests(unittest.TestCase):
    def test_unqualified_calculated_column_references_resolve_to_sibling_columns(self):
        graph = build_fact_graph(calculated_column_source(), analyze_dax=True)

        calculated = next(node for node in graph.nodes if node.type == "COLUMN" and node.name == "MonthLabel")
        date_column = next(node for node in graph.nodes if node.type == "COLUMN" and node.name == "Date")
        month_no_column = next(node for node in graph.nodes if node.type == "COLUMN" and node.name == "MonthNo")

        expression_edges = [
            edge
            for edge in graph.edges
            if edge.source == "dax_analysis" and edge.from_id == calculated.id
        ]
        self.assertEqual(
            {(edge.type, edge.to_id) for edge in expression_edges},
            {
                ("REFERENCES", date_column.id),
                ("REFERENCES", month_no_column.id),
            },
        )
        self.assertFalse(
            [item for item in graph.diagnostics if item.get("source_object") == calculated.id],
        )

    def test_measure_expression_lines_join_and_analyze_as_dax(self):
        graph = build_fact_graph(measure_expression_lines_source(), analyze_dax=True)

        measure = next(node for node in graph.nodes if node.type == "MEASURE" and node.name == "Total Sales")
        amount_column = next(node for node in graph.nodes if node.type == "COLUMN" and node.name == "Amount")

        self.assertIsInstance(measure.properties.get("expression"), str)
        self.assertFalse(
            [item for item in graph.diagnostics if item.get("source_object") == measure.id],
        )
        self.assertEqual(
            {
                (edge.type, edge.to_id)
                for edge in graph.edges
                if edge.source == "dax_analysis" and edge.from_id == measure.id
            },
            {("REFERENCES", amount_column.id)},
        )

    def test_m_shared_expression_kind_is_preserved_and_skips_dax_analysis(self):
        graph = build_fact_graph(m_shared_expression_source(), analyze_dax=True)

        shared = next(node for node in graph.nodes if node.type == "SHARED_EXPRESSION" and node.name == "Date Query")
        raw_source = shared.properties.get("raw_source")
        self.assertIsInstance(raw_source, dict)
        self.assertEqual(raw_source.get("kind"), "m")
        self.assertFalse(
            [item for item in graph.diagnostics if item.get("source_object") == shared.id],
        )
        self.assertNotIn("dax_ast", shared.properties)


if __name__ == "__main__":
    unittest.main()
