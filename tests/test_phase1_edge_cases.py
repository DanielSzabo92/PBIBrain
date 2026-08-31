"""Phase 1 regressions for realistic source envelopes and graph integrity."""

from __future__ import annotations

import copy
import unittest

from backend.graph.loader import build_fact_graph
from backend.graph.repository import GraphRepository
from backend.graph.schema import Node
from backend.scanner.model_reader import ModelReader
from backend.scanner.report_reader import ReportReader

from tests.fixtures.phase1_sources import model_source, report_source
from tests.support.canonical import by_type


class Phase1EdgeCaseTests(unittest.TestCase):
    def test_realistic_semantic_models_and_value_reports_stay_separate(self):
        first_model = model_source()
        first_model["id"] = "model-envelope-a"
        first_model["database"]["id"] = "model-envelope-a"
        first_model["name"] = "Envelope Model A"
        first_model["database"]["name"] = "Envelope Model A"

        second_model = model_source()
        second_model["id"] = "model-envelope-b"
        second_model["database"]["id"] = "model-envelope-b"
        second_model["name"] = "Envelope Model B"
        second_model["database"]["name"] = "Envelope Model B"

        first_report = report_source("report-envelope-a")
        first_report["modelId"] = "model-envelope-a"
        second_report = report_source("report-envelope-b")
        second_report["modelId"] = "model-envelope-b"

        model_envelope = {"semanticModels": [first_model, second_model]}
        report_envelope = {"value": [first_report, second_report]}
        with self.subTest("semanticModels model envelope"):
            self.assertEqual(len(ModelReader().read_many(model_envelope)), 2)
        with self.subTest("value report envelope"):
            self.assertEqual(len(ReportReader().read_many(report_envelope)), 2)

        graph = build_fact_graph(model_envelope, report_envelope)
        typed = by_type(graph.nodes)
        self.assertEqual({item["id"] for item in typed["MODEL"]}, {"model:model-envelope-a", "model:model-envelope-b"})
        self.assertEqual(
            {item["id"] for item in typed["REPORT"]},
            {"report:report-envelope-a", "report:report-envelope-b"},
        )
        self.assertEqual(
            {item["model_id"] for item in typed["REPORT"]},
            {"model:model-envelope-a", "model:model-envelope-b"},
        )

    def test_multiple_idless_models_receive_distinct_persisted_ids(self):
        first = model_source()
        second = copy.deepcopy(first)
        for source in (first, second):
            source.pop("id", None)
            source["database"].pop("id", None)
            source["name"] = "Unnamed model"
            source["database"]["name"] = "Unnamed model"

        graph = build_fact_graph([first, second])
        model_ids = [node.id for node in graph.nodes if node.type == "MODEL"]
        self.assertEqual(len(model_ids), 2)
        self.assertEqual(len(set(model_ids)), 2)
        self.assertNotIn("model:0", model_ids)
        self.assertNotIn("model:1", model_ids)

    def test_model_level_measure_is_contained_by_model(self):
        source = model_source()
        source["tables"][0]["measures"] = []
        source["measures"] = [
            {
                "id": "measure-model-level",
                "name": "Model Metric",
                "description": "A measure stored at model scope.",
                "expression": "1",
            }
        ]
        graph = build_fact_graph(source)
        measure = next(node for node in graph.nodes if node.source_id == "measure-model-level")
        self.assertEqual(measure.type, "MEASURE")
        self.assertEqual(measure.model_id, "model:model-001")
        self.assertIsNone(measure.properties.get("table_id"))
        self.assertTrue(
            any(
                edge.type == "CONTAINS"
                and edge.from_id == "model:model-001"
                and edge.to_id == measure.id
                and edge.status == "factual"
                and edge.evidence_class == "FACT"
                for edge in graph.edges
            )
        )

    def test_calculation_item_normalizes_format_string_expression(self):
        graph = build_fact_graph(model_source())
        item = next(node for node in graph.nodes if node.type == "CALCULATION_ITEM")
        self.assertEqual(item.properties.get("format_expression"), "SELECTEDMEASUREFORMATSTRING()")

    def test_native_sync_errors_are_not_swallowed(self):
        class FailingConnection:
            def execute(self, *_args, **_kwargs):
                raise RuntimeError("native sync failed")

        repository = GraphRepository(use_native=False)
        repository._native = (object(), FailingConnection())
        with self.assertRaises(RuntimeError) as raised:
            repository.upsert_node(Node(id="model:sync", type="MODEL", name="Sync"))
        self.assertIn("native sync failed", str(raised.exception.__cause__ or raised.exception))


if __name__ == "__main__":
    unittest.main()
