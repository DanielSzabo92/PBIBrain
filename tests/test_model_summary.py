"""Model context must preserve exact evidence without mixing model scopes."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlencode

from backend.api.app import BrainAPI, BrainApp
from backend.api.review import OverrideStore
from backend.graph.repository import GraphRepository
from backend.graph.schema import Edge, Node
from backend.model_summary import build_model_summary
from backend.scanner.pipeline import Scanner
from tests import test_documentation_export
from tests.fixtures.pbip_sources import write_pbip_project


class ModelSummaryTests(unittest.TestCase):
    def setUp(self):
        self.repository = test_documentation_export.DocumentationExportTests()._repository()
        self.store = OverrideStore()

    def tearDown(self):
        self.repository.close()

    def test_scope_exact_expressions_unknowns_and_immutability(self):
        before = copy.deepcopy(self.repository._payload())
        first = build_model_summary(self.repository, "model:sales-a", store=self.store)
        self.assertEqual(first, build_model_summary(self.repository, "model:sales-a", store=self.store))
        text = first["markdown"]
        self.assertIn("VAR x = SUM('Sales'[Amount])\nRETURN x", text)
        self.assertIn('IF([Revenue | Net] > 0, "$#,0", "€#,0")', text)
        self.assertIn('{("Árvíz", NAMEOF([Revenue | Net]), 0)}', text)
        self.assertIn("'Sales'[Amount]", text)
        self.assertIn("Unknown (not provided)", text)
        self.assertIn("Unresolved relationship endpoint", text)
        self.assertIn("Missing KPI", text)
        self.assertIn("parse_error", text)
        self.assertIn("no RLS or OLS", text)
        self.assertNotIn("model:sales-b", text)
        self.assertNotIn("measure:revenue-b", text)
        self.assertNotIn("* 1.2", text)
        self.assertEqual(before, self.repository._payload())

    def test_shared_meanings_keep_edge_decisions_and_fingerprint_local(self):
        self.repository.upsert_node(Node("concept:shared", "BUSINESS_CONCEPT", "Revenue", properties={
            "candidate_ids": ["candidate:a", "candidate:b"], "value": "Revenue",
        }))
        self.repository.upsert_edges([
            Edge("semantic:a", "SEMANTICALLY_MAPS_TO", "measure:revenue-a", "concept:shared", status="approved",
                 evidence_class="INFERRED", confidence=0.8, properties={"candidate_id": "candidate:a", "value": "Revenue"}),
            Edge("semantic:b", "SEMANTICALLY_MAPS_TO", "measure:revenue-b", "concept:shared", status="candidate",
                 evidence_class="INFERRED", confidence=0.8, properties={"candidate_id": "candidate:b", "value": "Revenue"}),
        ])
        before = build_model_summary(self.repository, "model:sales-a", store=self.store)
        other = build_model_summary(self.repository, "model:sales-b", store=self.store)
        self.store.put("candidate:a", "meaning", "Booked revenue á", status="overridden")
        changed = build_model_summary(self.repository, "model:sales-a", store=self.store)
        self.assertIn("Booked revenue á", changed["markdown"])
        self.assertIn("INFERRED | overridden", changed["markdown"])
        self.assertNotEqual(before["snapshot_id"], changed["snapshot_id"])
        self.assertEqual(other, build_model_summary(self.repository, "model:sales-b", store=self.store))
        self.assertNotIn("semantic:b", changed["markdown"])
        self.assertNotIn("candidate:b", changed["markdown"])
        self.repository.get_object("measure:revenue-b").properties["expression"] = "999"
        self.assertEqual(changed, build_model_summary(self.repository, "model:sales-a", store=self.store))

    def test_direction_security_partitions_and_fence_are_preserved(self):
        self.repository.get_object("column:b").model_id = "model:sales-a"
        self.repository.get_object("column:b").properties["table_id"] = "table:sales-a"
        relation = self.repository.get_object("relationship:a")
        relation.properties.update(to_column_id="column:b", cross_filter_direction="oneDirection", active=False)
        self.repository.get_object("model:sales-a").properties["roles"] = [{
            "name": "Region", "modelPermission": "read", "tablePermissions": [
                {"name": "Sales", "filterExpression": "'Sales'[Amount] > 0", "metadataPermission": "none"},
            ],
        }]
        self.repository.get_object("table:sales-a").properties["partitions"] = [{
            "name": "Import", "mode": "import", "source": {"type": "m", "expression": ["let", "  Source = 1", "in Source"]},
        }]
        self.repository.get_object("measure:revenue-a").properties["expression"] = '// ```\nSUM(\'Sales\'[Amount])'
        text = build_model_summary(self.repository, "model:sales-a")["markdown"]
        self.assertIn("column:b) → 'Sales'[Amount] (column:a)", text)
        self.assertIn("| false |", text)
        self.assertIn("let\n  Source = 1\nin Source", text)
        self.assertIn("'Sales'[Amount] > 0", text)
        self.assertIn("metadata permission: `none`", text)
        self.assertIn("````dax\n// ```", text)

    def test_api_requires_unambiguous_model_and_rejects_writes(self):
        app = BrainApp(BrainAPI(self.repository))
        for query in ("", "?model_id=missing", "?model_id=column%3Aa", "?model_id=model%3Asales-a&model_id=model%3Asales-b"):
            status, payload = app.handle("GET", "/api/model-summary" + query)
            self.assertEqual(status, 400, payload)
        status, payload = app.handle("GET", "/api/model-summary?" + urlencode({"model_id": "model:sales-a"}))
        self.assertEqual(status, 200)
        self.assertEqual(payload["model_id"], "model:sales-a")
        self.assertEqual(app.handle("POST", "/api/model-summary", {"model_id": "model:sales-a"})[0], 404)

    def test_overview_uses_reviewed_roles_without_promoting_inference_to_fact(self):
        self.repository.upsert_node(Node("role:fact", "ROLE", "fact", model_id="model:sales-a", properties={"meaning": "fact"}))
        self.repository.upsert_edge(Edge("role-edge", "HAS_ROLE", "table:sales-a", "role:fact", evidence_class="INFERRED", status="candidate"))
        candidate = build_model_summary(self.repository, "model:sales-a")["markdown"]
        self.assertNotIn("fact (INFERRED, candidate)", candidate)
        self.repository.edges["role-edge"].status = "approved"
        approved = build_model_summary(self.repository, "model:sales-a")["markdown"]
        self.assertIn("fact (INFERRED, approved)", approved)
        self.assertNotIn("fact (FACT", approved)

    def test_native_scan_reopen_export_preserves_source_and_special_objects(self):
        source = {"id": "native-summary", "name": "Summary á", "tables": [
            {"id": "sales", "name": "Sales", "columns": [{"id": "key", "name": "Key", "dataType": "Int64", "isHidden": True}],
             "measures": [{"id": "total", "name": "Total", "expression": "SUM('Sales'[Key])"}]},
            {"id": "dimension", "name": "Customer", "columns": [{"id": "customer-key", "name": "Key", "dataType": "Int64"}]},
        ], "relationships": [{"id": "link", "fromTable": "Sales", "fromColumn": "Key", "toTable": "Customer", "toColumn": "Key",
                               "fromCardinality": "many", "toCardinality": "one", "crossFilteringBehavior": "bothDirections", "isActive": True}],
            "calculationGroups": [{"id": "time", "name": "Time", "precedence": 10, "calculationItems": [
                {"id": "ytd", "name": "YTD", "expression": "SELECTEDMEASURE()", "ordinal": 0},
            ]}], "userDefinedFunctions": [{"id": "fn", "name": "Double", "expression": "(x) => x * 2", "parameters": ["x"]}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            file = path / "model.json"
            file.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
            original = file.read_bytes()
            with GraphRepository(path / "brain.lbug", use_native=True) as repository:
                self.assertTrue(repository.is_native)
                Scanner(repository=repository).scan(file)
                first = build_model_summary(repository, "model:native-summary")
            with GraphRepository(path / "brain.lbug", use_native=True) as repository:
                second = build_model_summary(repository, "model:native-summary")
                self.assertEqual(first["snapshot_id"], second["snapshot_id"])
                self.assertIn("from=many; to=one", second["markdown"])
                self.assertIn("↔", second["markdown"])
                self.assertIn("SELECTEDMEASURE()", second["markdown"])
                self.assertIn("(x) => x * 2", second["markdown"])
                self.assertIn("precedence", second["markdown"])
                self.assertIn("| true |", second["markdown"])
            self.assertEqual(original, file.read_bytes())

    def test_tmdl_pbip_summary_preserves_relationship_and_report_bindings(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            project = write_pbip_project(folder / "Finance")
            source_files = {path: path.read_bytes() for path in project.parent.rglob("*") if path.is_file()}
            with GraphRepository(folder / "brain.lbug", use_native=True) as repository:
                Scanner(repository=repository).scan(project)
                model = next(node for node in repository.all_nodes() if node.type == "MODEL")
                summary = build_model_summary(repository, model.id)
                text = summary["markdown"]
                self.assertIn("'Sales'[DateKey]", text)
                self.assertIn("'Date'[DateKey]", text)
                self.assertIn("Sales by date", text)
                self.assertIn("Graph validation (project scope) | valid", text)
                self.assertIn("| RELATIONSHIP | 1 |", text)
                for node in repository.all_nodes():
                    if node.type == "MEASURE" and node.properties.get("expression"):
                        self.assertIn(node.properties["expression"], text)
            self.assertEqual(source_files, {path: path.read_bytes() for path in source_files})
