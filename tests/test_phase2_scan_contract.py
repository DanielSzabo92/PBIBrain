"""Phase 2 end-to-end scan contracts."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from backend.graph.repository import GraphRepository
from backend.scanner.pipeline import Scanner

from tests.fixtures.phase2_sources import dax_model_source
from tests.support.canonical import by_type


def _node(typed: dict[str, list[dict]], node_type: str, source_id: str) -> dict:
    return next(item for item in typed[node_type] if item["source_id"] == source_id)


def _edge(graph, edge_type: str, from_id: str, to_id: str):
    return next(
        item
        for item in graph.edges
        if item.type == edge_type and item.from_id == from_id and item.to_id == to_id
    )


class Phase2ScanContractTests(unittest.TestCase):
    def test_scanner_scan_automatically_analyzes_all_expression_object_types(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = GraphRepository(root / "brain.json", use_native=False)
            graph = Scanner(
                repository,
                identity_path=root / "identity.json",
            ).scan(dax_model_source())
            typed = by_type(graph.nodes)

            expression_nodes = [
                item
                for node_type in ("MEASURE", "COLUMN", "CALCULATION_ITEM", "SHARED_EXPRESSION", "USER_DEFINED_FUNCTION")
                for item in typed.get(node_type, [])
                if item["properties"].get("expression")
            ]
            self.assertGreaterEqual(len(expression_nodes), 8)
            for item in expression_nodes:
                self.assertIn("dax_ast", item["properties"], item)
                self.assertTrue(item["properties"].get("dax_evidence"), item)

            calc_item = _node(typed, "CALCULATION_ITEM", "calc-item-ytd")
            self.assertEqual(calc_item["properties"].get("format_expression"), "SELECTEDMEASUREFORMATSTRING()")
            self.assertIn("format_expression", calc_item["properties"].get("dax_asts", {}))
            self.assertTrue(calc_item["properties"].get("dax_behaviors"))

            measure_sales = _node(typed, "MEASURE", "measure-sales")
            measure_net = _node(typed, "MEASURE", "measure-net-sales")
            measure_gross = _node(typed, "MEASURE", "measure-gross-margin")
            measure_formatted = _node(typed, "MEASURE", "measure-formatted-sales")
            calculated_profit = _node(typed, "COLUMN", "column-profit")
            shared_expression = _node(typed, "SHARED_EXPRESSION", "shared-expression-calendar")
            udf = _node(typed, "USER_DEFINED_FUNCTION", "udf-format-amount")

            self.assertEqual(
                _edge(graph, "DEPENDS_ON", measure_net["id"], measure_sales["id"]).evidence_class,
                "FACT",
            )
            _edge(graph, "DEPENDS_ON", measure_gross["id"], measure_net["id"])
            _edge(graph, "DEPENDS_ON", measure_formatted["id"], measure_net["id"])
            _edge(graph, "DEPENDS_ON", measure_formatted["id"], udf["id"])
            _edge(graph, "DEPENDS_ON", calc_item["id"], measure_net["id"])
            _edge(graph, "REFERENCES", calculated_profit["id"], _node(typed, "COLUMN", "column-amount")["id"])
            _edge(graph, "REFERENCES", calculated_profit["id"], _node(typed, "COLUMN", "column-cost")["id"])
            _edge(graph, "REFERENCES", shared_expression["id"], _node(typed, "COLUMN", "column-date-key")["id"])

            dax_edges = [item for item in graph.edges if item.source == "dax_analysis"]
            self.assertTrue(dax_edges)
            for edge in dax_edges:
                self.assertEqual(edge.status, "factual")
                self.assertEqual(edge.evidence_class, "FACT")
                self.assertTrue(edge.evidence)
                for evidence in edge.evidence:
                    self.assertIn(evidence["source"], {"dax_ast", "dax_analysis"})
                    self.assertTrue(evidence["extractor"])
                    self.assertTrue(evidence["ast_location"])
            self.assertFalse(graph.diagnostics)

            # The explicit JSON repository is a supported test double and
            # must persist the same DAX facts as the returned graph.
            self.assertEqual(
                {item.id for item in repository.all_edges()},
                {item.id for item in graph.edges},
            )
            repository.close()
            reopened = GraphRepository(root / "brain.json", use_native=False)
            self.assertTrue(reopened.get_edges(from_id=measure_net["id"], edge_types="DEPENDS_ON"))
            self.assertEqual(
                reopened.get_edges(from_id=measure_net["id"], edge_types="DEPENDS_ON")[0].to_id,
                measure_sales["id"],
            )
            reopened.close()


class Phase2CliScanContractTests(unittest.TestCase):
    def test_cli_scan_automatically_persists_dax_edges(self):
        try:
            with tempfile.TemporaryDirectory() as probe_directory:
                GraphRepository(Path(probe_directory) / "probe.lbug").close()
        except Exception as exc:
            self.skipTest(f"Ladybug C API shared library is unavailable: {exc}")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model_path = root / "model.json"
            database_path = root / "brain.lbug"
            identity_path = root / "identity.json"
            model = dax_model_source()
            model_path.write_text(json.dumps(model), encoding="utf-8")
            scan = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "backend.cli.main",
                    "--db",
                    str(database_path),
                    "--identity",
                    str(identity_path),
                    "scan",
                    str(model_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(scan.returncode, 0, scan.stderr)
            payload = json.loads(scan.stdout)
            self.assertGreater(payload["edges"], 0)

            repository = GraphRepository(database_path)
            typed = by_type(repository.all_nodes())
            net = _node(typed, "MEASURE", "measure-net-sales")
            sales = _node(typed, "MEASURE", "measure-sales")
            self.assertTrue(repository.get_edges(from_id=net["id"], to_id=sales["id"], edge_types="DEPENDS_ON"))
            repository.close()


if __name__ == "__main__":
    unittest.main()
