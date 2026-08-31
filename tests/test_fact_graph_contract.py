"""Phase 1 factual graph reconstruction acceptance tests."""

import copy
import tempfile
import unittest
from pathlib import Path

from backend.graph.loader import build_fact_graph, scan_sources
from backend.graph.repository import GraphRepository

from tests.fixtures.phase1_sources import MODEL_ID, REPORT_A_ID, REPORT_B_ID, model_source, report_source
from tests.support.canonical import as_mapping, by_type


def edge_tuples(graph):
    return {
        (edge.type, edge.from_id, edge.to_id, edge.evidence_class, edge.status)
        for edge in graph.edges
    }


class FactGraphContractTests(unittest.TestCase):
    def test_reconstructs_model_report_topology_and_factual_edges(self):
        graph = build_fact_graph(
            model_source(),
            [report_source(REPORT_A_ID), report_source(REPORT_B_ID)],
        )
        typed = by_type(graph.nodes)
        self.assertEqual(len(typed["MODEL"]), 1)
        self.assertEqual(len(typed["REPORT"]), 2)
        self.assertEqual(len(typed["TABLE"]), 3)
        self.assertEqual(len(typed["MEASURE"]), 1)
        self.assertEqual(
            {item["model_id"] for item in typed["REPORT"]},
            {f"model:{MODEL_ID}"},
        )

        model_ids = {item["id"] for item in typed["MODEL"]}
        measure_ids = {item["id"] for item in typed["MEASURE"]}
        column_ids = {item["id"] for item in typed["COLUMN"] if item["source_id"] == "column-date-key"}
        amount_column_ids = {item["id"] for item in typed["COLUMN"] if item["source_id"] == "column-amount"}
        relationship_ids = {item["id"] for item in typed["RELATIONSHIP"]}
        parameter_ids = {item["id"] for item in typed["FIELD_PARAMETER"]}
        table_ids = {item["id"] for item in typed["TABLE"]}
        report_ids = {item["id"] for item in typed["REPORT"]}
        visual_ids = {item["id"] for item in typed["VISUAL"]}
        edges = edge_tuples(graph)
        self.assertTrue(any(kind == "CONTAINS" and source in model_ids and target in table_ids for kind, source, target, _, _ in edges))
        self.assertTrue(any(kind == "USES_MODEL" and source in report_ids and target in model_ids for kind, source, target, _, _ in edges))
        self.assertTrue(any(kind == "USES" and source in visual_ids and target in measure_ids for kind, source, target, _, _ in edges))
        self.assertTrue(any(kind == "USES" and source in visual_ids and target in column_ids for kind, source, target, _, _ in edges))
        self.assertTrue(any(kind == "RELATES_TO" and source in relationship_ids for kind, source, *_ in edges))
        self.assertTrue(any(kind == "REFERENCES" and source in parameter_ids and target in amount_column_ids for kind, source, target, _, _ in edges))
        self.assertTrue(any(kind == "FILTERS" for kind, *_ in edges))
        self.assertTrue(all(edge.evidence_class == "FACT" for edge in graph.edges))
        self.assertTrue(all(edge.status == "factual" for edge in graph.edges))
        self.assertTrue(all(edge.source in {"model_metadata", "report_metadata"} for edge in graph.edges))

    def test_two_reports_share_model_nodes_without_duplication(self):
        graph = build_fact_graph(model_source(), [report_source(REPORT_A_ID), report_source(REPORT_B_ID)])
        typed = by_type(graph.nodes)
        model_object_types = {"MODEL", "TABLE", "COLUMN", "MEASURE", "RELATIONSHIP"}
        for object_type in model_object_types:
            ids = [item["id"] for item in typed.get(object_type, [])]
            self.assertEqual(len(ids), len(set(ids)), object_type)
        report_ids = {item["report_id"] for item in typed["VISUAL"]}
        self.assertEqual(report_ids, {f"report:{REPORT_A_ID}", f"report:{REPORT_B_ID}"})
        model_ids = {item["model_id"] for item in typed["TABLE"]}
        self.assertEqual(model_ids, {f"model:{MODEL_ID}"})

    def test_same_inputs_produce_equivalent_graph(self):
        first = build_fact_graph(model_source(), [report_source(REPORT_A_ID), report_source(REPORT_B_ID)])
        second = build_fact_graph(
            copy.deepcopy(model_source()),
            [copy.deepcopy(report_source(REPORT_B_ID)), copy.deepcopy(report_source(REPORT_A_ID))],
        )
        self.assertEqual(first.to_dict(), second.to_dict())

    def test_scan_loads_reconstructed_graph_into_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "brain.lbug"
            repository = GraphRepository(path, use_native=False)
            graph = scan_sources(
                model_source(),
                report_source(REPORT_A_ID),
                repository=repository,
            )
            self.assertEqual(
                [node.to_dict() for node in repository.all_nodes()],
                [node.to_dict() for node in graph.nodes],
            )
            self.assertEqual(
                [edge.to_dict() for edge in repository.all_edges()],
                [edge.to_dict() for edge in graph.edges],
            )
            repository.close()


if __name__ == "__main__":
    unittest.main()
