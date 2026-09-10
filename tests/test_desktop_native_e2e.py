"""Production desktop path: PBIP scan, live agent reads, close and native reopen."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from urllib.request import Request, urlopen

from backend.agent import live_client
from backend.desktop import DesktopController, DesktopServer
from backend.graph.repository import GraphRepository
from tests.fixtures.pbip_sources import write_pbip_project


class DesktopNativeTests(unittest.TestCase):
    def test_scan_live_reads_switch_guard_and_reopen(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            try:
                probe = GraphRepository(root / "probe.lbug")
                probe.close()
            except RuntimeError as exc:
                self.skipTest(f"Native runtime unavailable: {exc}")
            project = root / "Finance project"
            write_pbip_project(project)
            before = {path.relative_to(project): hashlib.sha256(path.read_bytes()).hexdigest()
                      for path in project.rglob("*") if path.is_file()}
            static = root / "ui"
            static.mkdir()
            (static / "index.html").write_text("<html><head></head><body>PBIBrain</body></html>", encoding="utf-8")
            controller = DesktopController(static_dir=static)
            server = DesktopServer(controller)
            server.start()
            try:
                opened = controller.open_project("Finance", str(project))
                self.assertTrue(opened["ok"], opened)
                config = project / ".pbibrain/brain.json"
                client = live_client(config)
                self.assertIsNotNone(client)
                with urlopen(Request(server.url + "/api/scan", data=b"{}", headers={"Content-Type": "application/json"}), timeout=60) as response:
                    scanned = json.load(response)
                self.assertGreater(scanned["overview"]["counts"]["nodes"], 0)
                expected = client.get("overview")["counts"]
                self.assertTrue(client.get("search", q="Net Sales")["items"])
                self.assertTrue(controller.close_project()["ok"])
                self.assertFalse((config.parent / "connection.json").exists())
                opened = controller.open_project("Ignored rename", str(project))
                self.assertTrue(opened["ok"], opened)
                self.assertEqual(opened["project"]["name"], "Finance")
                with self.assertRaisesRegex(ValueError, "session|Session|changed"):
                    client.get("overview")
                reopened = live_client(config)
                self.assertEqual(reopened.get("overview")["counts"], expected)
                self.assertTrue(controller.close_project()["ok"])
                with GraphRepository(config.parent / "brain.lbug") as repository:
                    self.assertTrue(repository.is_native)
                    self.assertEqual(len(repository.all_nodes()), expected["nodes"])
                    self.assertEqual(len(repository.all_edges()), expected["edges"])
                after = {path.relative_to(project): hashlib.sha256(path.read_bytes()).hexdigest()
                         for path in project.rglob("*") if path.is_file() and ".pbibrain" not in path.parts}
                self.assertEqual(before, after)
            finally:
                controller.shutdown()
                server.stop()


if __name__ == "__main__":
    unittest.main()
