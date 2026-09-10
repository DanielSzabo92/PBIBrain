"""Graph presentation filters and durable color configuration contracts."""

import tempfile
import unittest
from pathlib import Path

from backend.api.app import create_app
from backend.api.graph import get_graph
from backend.graph.artifacts import artifact_group
from backend.graph.repository import GraphRepository
from backend.graph.schema import Edge, Node
from backend.projects import ProjectConfigError, ProjectConfigStore, ProjectService


class GraphPresentationTests(unittest.TestCase):
    def setUp(self):
        self.repository = GraphRepository(use_native=False)
        self.repository.replace([
            Node("m", "MODEL", "Finance"),
            Node("r", "REPORT", "Finance report", model_id="m", report_id="r"),
            Node("v", "VISUAL", "Sales visual", model_id="m", report_id="r"),
            Node("measure", "MEASURE", "Net Sales", model_id="m", status="approved"),
            Node("future", "FUTURE_VISUAL", "New visual", model_id="m", report_id="r"),
            *[Node(f"c{i}", "COLUMN", f"Column {i}", model_id="m") for i in range(150)],
        ], [Edge("uses", "USES", "v", "measure"), Edge("contains", "CONTAINS", "r", "v")])
        self.addCleanup(self.repository.close)

    def test_filtering_precedes_limit_and_preserves_canonical_objects(self):
        before = [node.to_dict() for node in self.repository.all_nodes()]
        result = get_graph(self.repository, artifact="model", status="approved", object_types="MEASURE", limit=1)
        self.assertEqual([node["id"] for node in result["nodes"]], ["measure"])
        self.assertEqual(result["total_nodes"], 1)
        self.assertFalse(result["truncated"])
        self.assertEqual(result["nodes"][0]["artifact_group"], "model")
        self.assertEqual(before, [node.to_dict() for node in self.repository.all_nodes()])

    def test_report_filter_uses_report_ownership_even_with_model_ids(self):
        result = get_graph(self.repository, artifact="report")
        self.assertEqual({node["id"] for node in result["nodes"]}, {"r", "v", "future"})
        self.assertEqual([edge["id"] for edge in result["edges"]], ["contains"])
        self.assertEqual(artifact_group({"type": "MEASURE", "report_id": "r"}), "model")
        self.assertEqual(artifact_group({"type": "NEW"}), "other")
        self.assertEqual(artifact_group({"type": "ALIAS", "model_id": "m"}), "other")

    def test_centered_text_filter_and_edges_do_not_leak_nonmatches(self):
        result = get_graph(self.repository, center_id="v", depth=2, query="Net Sales", status="approved")
        self.assertEqual([node["id"] for node in result["nodes"]], ["measure"])
        self.assertEqual(result["edges"], [])

    def test_http_filters_and_invalid_parameters(self):
        app = create_app(self.repository)
        self.addCleanup(app.close)
        code, result = app.handle("GET", "/api/graph?artifact=report&object_type=VISUAL&query=Sales&status=factual&limit=1")
        self.assertEqual(code, 200)
        self.assertEqual([node["id"] for node in result["nodes"]], ["v"])
        self.assertEqual(result["scope"]["artifact"], "report")
        for query in ("artifact=invalid", "status=invalid"):
            self.assertEqual(app.handle("GET", f"/api/graph?{query}")[0], 400)


class GraphColorConfigTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "brain.json"
        self.store = ProjectConfigStore(self.path)
        self.config = {"version": 1, "name": "Finance", "sources": [], "database": "graph.lbug", "identity_map": "identity.json"}
        self.store.save(self.config)

    def test_colors_round_trip_without_changing_source_or_storage_contract(self):
        colors = {"groups": {"report": "#AA00CC"}, "types": {"MEASURE": "#123456"}}
        saved = self.store.save({**self.config, "graph_colors": colors})
        self.assertEqual(ProjectConfigStore(self.path).get(), saved)
        self.assertEqual(saved["graph_colors"]["groups"]["report"], "#aa00cc")
        self.assertEqual({key: saved[key] for key in self.config}, self.config)
        self.assertEqual(self.store.save({**saved, "graph_colors": {}})["graph_colors"], {"groups": {}, "types": {}})

    def test_invalid_colors_leave_saved_file_unchanged(self):
        original = self.path.read_bytes()
        for value in [None, [], {"unknown": {}}, {"groups": {"report": "red"}}, {"groups": {"unknown": "#112233"}}, {"types": {"MEASURE": "url(x)"}}, {"types": []}, {"types": {"bad-type": "#112233"}}]:
            with self.subTest(value=value), self.assertRaises(ProjectConfigError):
                self.store.save({**self.config, "graph_colors": value})
            self.assertEqual(self.path.read_bytes(), original)

    def test_settings_api_accepts_colors_and_still_blocks_storage_changes(self):
        app = create_app(use_native=False)
        self.addCleanup(app.close)
        app.project = ProjectService(self.path)
        code, saved = app.handle("POST", "/api/config", {**self.config, "graph_colors": {"groups": {"model": "#123456"}}})
        self.assertEqual(code, 200)
        self.assertEqual(app.handle("GET", "/api/config")[1], saved)
        self.assertEqual(app.handle("POST", "/api/config", {**saved, "database": "other.lbug"})[0], 400)
        self.assertEqual(self.store.get(), saved)
