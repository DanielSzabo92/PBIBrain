"""Phase 1 report visual-container compatibility checks."""

from __future__ import annotations

import unittest

from backend.graph.loader import build_fact_graph

from tests.fixtures.phase1_sources import json_visual_report_source, model_source


class ReportVisualContractTests(unittest.TestCase):
    def test_legacy_json_strings_and_pbir_visuals_bind_canonical_objects(self):
        report = json_visual_report_source()
        legacy = report["sections"][0]["visualContainers"][0]
        self.assertTrue(all(isinstance(legacy[key], str) for key in ("config", "query", "filters")))
        pbir = report["sections"][0]["visualContainers"][1]
        self.assertIn("visual", pbir)
        self.assertIn("queryState", pbir["visual"]["query"])
        graph = build_fact_graph(model_source(), report)
        visuals = {node.source_id: node for node in graph.nodes if node.type == "VISUAL"}
        expected_visuals = {
            "report-json-visual-visual-sales": ("columnChart", "Sales by date"),
            "report-json-visual-visual-pbir": ("lineChart", "Sales trend (PBIR)"),
        }
        self.assertEqual(set(visuals), set(expected_visuals))

        model_column = next(
            node for node in graph.nodes if node.type == "COLUMN" and node.source_id == "column-date-key"
        )
        model_measure = next(
            node for node in graph.nodes if node.type == "MEASURE" and node.source_id == "measure-sales"
        )
        uses = [edge for edge in graph.edges if edge.type == "USES"]
        for source_id, (visual_type, title) in expected_visuals.items():
            visual = visuals[source_id]
            self.assertEqual(visual.properties.get("visual_type"), visual_type)
            self.assertEqual(visual.properties.get("title"), title)
            self.assertEqual(visual.source, "report_metadata")
            targets = {edge.to_id for edge in uses if edge.from_id == visual.id}
            self.assertEqual(targets, {model_column.id, model_measure.id})
            for edge in uses:
                if edge.from_id == visual.id:
                    self.assertEqual(edge.status, "factual")
                    self.assertEqual(edge.evidence_class, "FACT")
                    self.assertEqual(edge.source, "report_metadata")
                    self.assertTrue(edge.evidence)

        filters = [node for node in graph.nodes if node.type == "VISUAL_FILTER"]
        self.assertEqual(len(filters), 1)
        visual_filter = filters[0]
        self.assertEqual(visual_filter.properties.get("target_id"), model_column.id)
        self.assertEqual(visual_filter.source, "report_metadata")
        self.assertEqual(visual_filter.status, "factual")
        self.assertIn("raw_source", visual_filter.properties)

        filter_edges = [edge for edge in graph.edges if edge.type == "FILTERS"]
        matching = [edge for edge in filter_edges if edge.from_id == visual_filter.id and edge.to_id == model_column.id]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0].status, "factual")
        self.assertEqual(matching[0].evidence_class, "FACT")
        self.assertEqual(matching[0].source, "report_metadata")
        self.assertTrue(matching[0].evidence)


if __name__ == "__main__":
    unittest.main()
