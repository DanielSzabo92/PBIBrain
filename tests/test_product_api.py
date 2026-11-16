"""Local transport, graph scope, and failed-write acceptance checks."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.api.app import BrainAPI, BrainApp
from backend.graph.repository import GraphRepository
from backend.graph.schema import Node, Edge


class ProductAPITests(unittest.TestCase):
    def setUp(self):
        self.repo = GraphRepository(use_sqlite=False)
        self.repo.replace([
            Node(id="m1", type="MODEL", name="First", model_id="m1"),
            Node(id="m2", type="MODEL", name="Second", model_id="m2"),
            Node(id="z", type="MEASURE", name="Sales", model_id="m1"),
            Node(id="a", type="MEASURE", name="Sales", model_id="m2"),
        ], [Edge(id="e1", type="CONTAINS", from_id="m1", to_id="z"),
            Edge(id="e2", type="DEPENDS_ON", from_id="z", to_id="a")])
        self.app = BrainApp(BrainAPI(self.repo))

    def request(self, path="/api/overview", **environ):
        captured = {}
        env = {"REQUEST_METHOD": "GET", "PATH_INFO": path, "HTTP_HOST": "127.0.0.1:8000", **environ}
        def start(status, headers):
            captured.update(status=int(status.split()[0]), headers=dict(headers))
        raw = b"".join(self.app(env, start))
        return captured, json.loads(raw) if raw else None

    def test_scope_prevents_cross_model_traversal_and_keeps_center(self):
        status, data = self.app.handle("GET", "/api/graph?center_id=z&model_id=m1&depth=3&limit=1")
        self.assertEqual(status, 200)
        self.assertEqual([n["id"] for n in data["nodes"]], ["z"])
        self.assertEqual(data["total_nodes"], 2)
        self.assertTrue(data["truncated"])
        self.assertEqual(data["edges"], [])
        self.assertEqual(self.app.handle("GET", "/api/graph?center_id=a&model_id=m1")[0], 404)

    def test_graph_rejects_excessive_bounds(self):
        for query in ("depth=999", "depth=-1", "limit=1001", "limit=0"):
            self.assertEqual(self.app.handle("GET", "/api/graph?" + query)[0], 400)

    def test_unknown_scan_time_not_invented(self):
        self.assertIsNone(self.app.api.get_overview()["last_scan"])

    def test_browser_boundaries(self):
        self.assertEqual(self.request(HTTP_ORIGIN="https://evil.example")[0]["status"], 403)
        self.assertEqual(self.request(HTTP_HOST="evil.example:8000")[0]["status"], 403)
        headers, _ = self.request(HTTP_ORIGIN="http://127.0.0.1:5173")
        self.assertEqual(headers["headers"]["Access-Control-Allow-Origin"], "http://127.0.0.1:5173")
        self.assertNotIn("Access-Control-Allow-Origin", self.request()[0]["headers"])

    def test_request_limits_and_json(self):
        self.assertEqual(self.request(CONTENT_LENGTH="no")[0]["status"], 400)
        self.assertEqual(self.request(CONTENT_LENGTH="1048577")[0]["status"], 413)
        self.assertEqual(self.request(REQUEST_METHOD="POST", CONTENT_TYPE="text/plain")[0]["status"], 415)

    def test_static_files_stay_under_root(self):
        with tempfile.TemporaryDirectory() as directory:
            self.app.static_dir = Path(directory)
            self.assertEqual(self.request("/../secret")[0]["status"], 403)

    def test_failed_replace_rolls_back_disk_and_memory(self):
        with GraphRepository() as repo:
            repo.replace(self.repo.all_nodes(), self.repo.all_edges())
            before = repo._payload()
            store = repo._store
            original = store._write_records
            def fail_after_delete(conn, *args, **kwargs):
                conn.execute("DELETE FROM edges;")
                conn.execute("DELETE FROM nodes;")
                raise RuntimeError("injected insert failure")
            store._write_records = fail_after_delete
            with self.assertRaisesRegex(RuntimeError, "injected insert failure"):
                repo.replace([Node(id="new", type="MODEL", name="New")], [])
            store._write_records = original
            self.assertEqual(repo._payload(), before)
            self.assertEqual({node.id for node in store.all_nodes()}, set(repo.nodes))

    def test_search_route_is_bounded_and_scoped(self):
        status, data = self.app.handle("GET", "/api/search?q=Sales&model_id=m1&limit=1")
        self.assertEqual(status, 200)
        self.assertEqual([n["id"] for n in data["items"]], ["z"])
        self.assertEqual(data["total"], 1)

    def test_transaction_restores_deleted_graph_after_failure_and_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rollback.sqlite"
            with GraphRepository(path) as repo:
                repo.replace(self.repo.all_nodes(), self.repo.all_edges())
                expected = repo._payload()
                def fail_after_delete(conn, *args, **kwargs):
                    conn.execute("DELETE FROM edges;")
                    conn.execute("DELETE FROM nodes;")
                    raise RuntimeError("failure after actual deletion")
                repo._store._write_records = fail_after_delete
                with self.assertRaisesRegex(RuntimeError, "actual deletion"):
                    repo.replace([Node(id="replacement", type="MODEL", name="Replacement")], [])
                self.assertEqual(repo._payload(), expected)
            with GraphRepository(path) as reopened:
                self.assertEqual(reopened._payload(), expected)

    def test_checkpoint_failure_does_not_undo_a_committed_replace(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint.sqlite"
            with GraphRepository(path) as repo:
                connection = repo._store._get_connection()

                class CheckpointFails:
                    def execute(self, statement, *args):
                        if "wal_checkpoint" in statement:
                            raise sqlite3.OperationalError("checkpoint unavailable")
                        return connection.execute(statement, *args)

                    def __getattr__(self, name):
                        return getattr(connection, name)

                repo._store._conn = CheckpointFails()
                with self.assertLogs("backend.graph.sqlite_store", level="WARNING"):
                    repo.replace([Node(id="new", type="MODEL", name="New")], [])
                repo._store._conn = connection
                self.assertEqual(set(repo.nodes), {"new"})
            with GraphRepository(path) as reopened:
                self.assertEqual(set(reopened.nodes), {"new"})

if __name__ == "__main__":
    unittest.main()
