"""Read-only API answers are reused until the graph or the decisions change (adversarial review 03, 04)."""

import json
import tempfile
import unittest
from pathlib import Path

from backend.api.app import create_app
from backend.api.review import _IndexedEdges, _candidate_target
from backend.graph.repository import GraphRepository
from backend.graph.schema import Edge, Node


def call(app, path, query=""):
    seen = {}

    def start_response(status, headers):
        seen["status"] = status

    body = b"".join(app({"REQUEST_METHOD": "GET", "PATH_INFO": path, "QUERY_STRING": query, "HTTP_HOST": "127.0.0.1"}, start_response))
    return seen["status"], json.loads(body)


def measure(identifier, name="Sales"):
    return Node(id=identifier, type="MEASURE", name=name, model_id="model:m")


class AnswerCacheTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.repository = GraphRepository(Path(self.folder.name) / "brain.lbug")
        self.repository.upsert_node(Node(id="model:m", type="MODEL", name="Model"))
        self.repository.upsert_node(measure("measure:a"))
        self.app = create_app(self.repository, overrides_path=Path(self.folder.name) / "overrides.json")
        self.addCleanup(self.app.close)
        self.handled = []
        original = self.app.handle

        def counted(method, path, body=None):
            self.handled.append(path)
            return original(method, path, body)

        self.app.handle = counted

    def test_a_repeated_read_is_answered_without_a_second_computation(self):
        first = call(self.app, "/api/overview")
        second = call(self.app, "/api/overview")
        self.assertEqual(first, second)
        self.assertEqual(["/api/overview"], self.handled)

    def test_a_graph_write_drops_the_cached_answer(self):
        before = call(self.app, "/api/overview")[1]
        self.repository.upsert_node(measure("measure:b", "Margin"))
        after = call(self.app, "/api/overview")[1]
        self.assertEqual(before["counts"]["nodes"] + 1, after["counts"]["nodes"])
        self.assertEqual(2, len(self.handled))

    def test_a_stored_decision_drops_the_cached_answer(self):
        call(self.app, "/api/search", "q=Sales")
        self.app.api.overrides.put("measure:a", "name", "Net sales")
        call(self.app, "/api/search", "q=Sales")
        self.assertEqual(2, len(self.handled))

    def test_requests_that_are_not_pure_reads_are_never_cached(self):
        call(self.app, "/api/config")
        call(self.app, "/api/config")
        self.assertEqual(2, len(self.handled))

    def test_review_snapshot_keeps_the_shape_and_drops_the_heavy_parts(self):
        self.repository.upsert_node(Node(id="measure:heavy", type="MEASURE", name="Heavy", model_id="model:m",
                                         properties={"expression": "SUM(T[A])", "dax_ast": {"kind": "call"}, "raw_source": "x" * 5000}))
        full = call(self.app, "/api/brain")[1]
        slim = call(self.app, "/api/brain", "view=review")[1]
        self.assertEqual(set(full) | {"view"}, set(slim))
        self.assertEqual([node["id"] for node in full["nodes"]], [node["id"] for node in slim["nodes"]])
        heavy = next(node for node in slim["nodes"] if node["id"] == "measure:heavy")
        self.assertEqual("SUM(T[A])", heavy.get("expression") or heavy["properties"].get("expression"))
        self.assertNotIn("dax_ast", json.dumps(heavy))
        self.assertNotIn("raw_source", json.dumps(heavy))

    def test_overview_reports_the_most_used_measures_itself(self):
        overview = call(self.app, "/api/overview")[1]
        self.assertEqual(1, overview["measure_count"])
        self.assertEqual(["measure:a"], [item["id"] for item in overview["top_measures"]])
        self.assertEqual([], overview["hot_unreviewed"])

    def test_shared_read_returns_the_same_objects_as_a_fresh_read(self):
        fresh = [node.to_dict() for node in self.repository.all_nodes()]
        with self.repository.reading():
            shared = [node.to_dict() for node in self.repository.all_nodes()]
            self.repository.upsert_node(measure("measure:c", "Cost"))
            self.assertEqual(len(fresh) + 1, len(self.repository.all_nodes()))
        self.assertEqual(fresh, shared)


class IndexedEdgesTests(unittest.TestCase):
    def test_index_gives_the_same_target_as_the_scan_of_all_edges(self):
        edges = [
            Edge(id="e2", type="HAS_ALIAS", from_id="measure:b", to_id="alias:x", evidence_class="INFERRED"),
            Edge(id="e1", type="HAS_ALIAS", from_id="measure:a", to_id="alias:x", evidence_class="INFERRED"),
            Edge(id="e0", type="CONTAINS", from_id="table:t", to_id="alias:x", evidence_class="FACT"),
            Edge(id="e3", type="HAS_ALIAS", from_id="measure:c", to_id="alias:y", evidence_class="INFERRED"),
        ]
        for identifier in ("alias:x", "alias:y", "alias:none"):
            item = {"id": identifier, "properties": {}}
            self.assertEqual(_candidate_target(item, edges), _candidate_target(item, _IndexedEdges(edges)))


if __name__ == "__main__":
    unittest.main()
