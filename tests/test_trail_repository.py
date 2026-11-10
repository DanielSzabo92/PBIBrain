"""Tests for the Trail graph repository, TrailStore cache schema, and PBIP line-span extraction."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.graph import Edge, GraphRepository, Node, TrailRepository, TrailStore
from backend.scanner.pbip import read_pbip_project
from backend.scanner.pipeline import Scanner
from tests.fixtures.pbip_sources import write_pbip_project


class TrailRepositoryTests(unittest.TestCase):
    def test_trail_repository_writes_wiring_json_ask_index_and_markdown_cards(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store_path = Path(directory) / "brain.trail"
            with TrailRepository(store_path) as repo:
                self.assertEqual(repo.storage, "trail")
                self.assertTrue(repo.is_native)
                model = Node(
                    id="model:sales",
                    type="MODEL",
                    name="Sales Model",
                    model_id="model:sales",
                    source_id="sales-model",
                    properties={"source_path": "Sales.SemanticModel"},
                )
                table = Node(
                    id="model:sales/table:orders",
                    type="TABLE",
                    name="Orders",
                    model_id="model:sales",
                    source_id="orders-table",
                    properties={
                        "ast_location": {
                            "source_file": "definition/tables/Orders.tmdl",
                            "span": "L1-L32",
                        }
                    },
                )
                measure = Node(
                    id="model:sales/measure:total-revenue",
                    type="MEASURE",
                    name="Total Revenue",
                    description="Sum of net order revenue",
                    model_id="model:sales",
                    source_id="rev-lineage-1",
                    properties={
                        "table_id": table.id,
                        "expression": "SUM('Orders'[NetAmount])",
                        "format_string": "$#,0.00",
                        "ast_location": {
                            "source_file": "definition/tables/Orders.tmdl",
                            "span": "L12-L18",
                        },
                    },
                )
                column = Node(
                    id="model:sales/column:net-amount",
                    type="COLUMN",
                    name="NetAmount",
                    model_id="model:sales",
                    source_id="col-lineage-1",
                    properties={
                        "table_id": table.id,
                        "datatype": "decimal",
                        "ast_location": {
                            "source_file": "definition/tables/Orders.tmdl",
                            "span": "L4-L10",
                        },
                    },
                )
                edge = Edge(
                    id="edge:rev-depends-net-amount",
                    type="DEPENDS_ON",
                    from_id=measure.id,
                    to_id=column.id,
                    source="dax_ast",
                    status="factual",
                    evidence_class="FACT",
                    evidence=["SUM('Orders'[NetAmount])"],
                )
                repo.replace([model, table, measure, column], [edge])

            wiring_file = store_path / ".graph" / "wiring.json"
            facts_file = store_path / ".graph" / "brain-facts.json"
            ask_index_file = store_path / ".cache" / "ask-index.json"
            index_md_file = store_path / "INDEX.md"
            table_card_file = store_path / "Sales.SemanticModel" / "definition" / "tables" / "Orders.tmdl.md"

            self.assertTrue(wiring_file.is_file())
            self.assertTrue(facts_file.is_file())
            self.assertTrue(ask_index_file.is_file())
            self.assertTrue(index_md_file.is_file())
            self.assertTrue(table_card_file.is_file())

            wiring = json.loads(wiring_file.read_text(encoding="utf-8"))
            self.assertEqual(wiring["meta"]["version"], 1)
            nodes_by_id = {item["id"]: item for item in wiring["nodes"]}
            self.assertEqual(nodes_by_id[measure.id]["kind"], "measure")
            self.assertEqual(nodes_by_id[measure.id]["path"], "Sales.SemanticModel/definition/tables/Orders.tmdl")
            self.assertEqual(nodes_by_id[measure.id]["span"], "L12-L18")
            self.assertEqual(nodes_by_id[measure.id]["owner"], "Orders")
            self.assertIn("SUM('Orders'[NetAmount])", nodes_by_id[measure.id]["signature"])

            self.assertEqual(len(wiring["edges"]), 1)
            self.assertEqual(wiring["edges"][0]["source"], measure.id)
            self.assertEqual(wiring["edges"][0]["target"], column.id)
            self.assertEqual(wiring["edges"][0]["relation"], "depends_on")
            self.assertEqual(wiring["edges"][0]["confidence"], "exact")

            ask_index = json.loads(ask_index_file.read_text(encoding="utf-8"))
            self.assertEqual(ask_index["version"], 1)
            self.assertEqual(ask_index["docCount"], 4)
            self.assertIn("revenue", ask_index["df"])

            card_text = table_card_file.read_text(encoding="utf-8")
            self.assertIn("`Total Revenue` (measure) — `L12-L18`", card_text)
            self.assertIn("depends_on `NetAmount`", card_text)
            self.assertIn("depends_on by `Total Revenue`", card_text)

    def test_rehydrates_from_standalone_wiring_json_when_brain_facts_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store_path = Path(directory) / "standalone.trail"
            with GraphRepository(store_path) as repo:
                measure = Node(
                    id="model:m/measure:margin",
                    type="MEASURE",
                    name="Margin %",
                    description="Gross margin ratio",
                    model_id="model:m",
                    source_id="margin-tag",
                    properties={"expression": "DIVIDE([Profit], [Sales])", "format_string": "0.0%"},
                )
                sales = Node(
                    id="model:m/measure:sales",
                    type="MEASURE",
                    name="Sales",
                    model_id="model:m",
                    source_id="sales-tag",
                    properties={"expression": "SUM(Fact[Amount])"},
                )
                edge = Edge(
                    id="edge:margin-sales",
                    type="DEPENDS_ON",
                    from_id=measure.id,
                    to_id=sales.id,
                    source="dax_ast",
                    status="factual",
                    evidence_class="FACT",
                )
                repo.replace([measure, sales], [edge])

            # Remove brain-facts.json to simulate a store produced by standalone trail-pbi CLI
            (store_path / ".graph" / "brain-facts.json").unlink()
            with GraphRepository(store_path) as reopened:
                self.assertEqual(reopened.storage, "trail")
                self.assertEqual(len(reopened.all_nodes()), 2)
                self.assertEqual(len(reopened.all_edges()), 1)
                loaded_margin = reopened.get_object("model:m/measure:margin")
                self.assertIsNotNone(loaded_margin)
                self.assertEqual(loaded_margin.type, "MEASURE")
                self.assertEqual(loaded_margin.name, "Margin %")
                self.assertEqual([n.id for n in reopened.get_dependencies("model:m/measure:margin")], ["model:m/measure:sales"])

    def test_pbip_scanner_populates_ast_location_line_spans_and_persists_to_trail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project_dir = root / "FinanceProject"
            pbip_file = write_pbip_project(project_dir)
            bundle = read_pbip_project(pbip_file)
            self.assertTrue(bundle["models"])
            model = bundle["models"][0]
            self.assertIn("ast_location", model)
            self.assertRegex(model["ast_location"]["span"], r"^L\d+-L\d+$")

            tables = model["tables"]
            sales_table = next(t for t in tables if t["name"] == "Sales")
            self.assertEqual(sales_table["ast_location"]["source_file"], "definition/tables/Sales.tmdl")
            self.assertRegex(sales_table["ast_location"]["span"], r"^L1-L\d+$")

            measures = sales_table["measures"]
            self.assertTrue(measures)
            for m in measures:
                self.assertEqual(m["ast_location"]["source_file"], "definition/tables/Sales.tmdl")
                self.assertRegex(m["ast_location"]["span"], r"^L\d+-L\d+$")

            store_path = root / "finance.trail"
            with GraphRepository(store_path) as repo:
                Scanner(repo, identity_path=root / "identity.json").scan(bundle["models"], bundle["reports"])
                measure_nodes = [n for n in repo.all_nodes() if n.type == "MEASURE"]
                self.assertTrue(measure_nodes)
                for m_node in measure_nodes:
                    self.assertIn("ast_location", m_node.properties)
                    self.assertRegex(m_node.properties["ast_location"]["span"], r"^L\d+-L\d+$")
                    self.assertNotIn("ast_location", m_node.properties.get("raw_source", {}))

            store = TrailStore(store_path)
            self.assertTrue(store.wiring_file.is_file())
            wiring = json.loads(store.wiring_file.read_text(encoding="utf-8"))
            measure_trail_nodes = [n for n in wiring["nodes"] if n["kind"] == "measure"]
            self.assertTrue(measure_trail_nodes)
            self.assertTrue(any(n["span"] != "L1-L1" for n in measure_trail_nodes))


if __name__ == "__main__":
    unittest.main()
