"""Agent routing must never open a second writer or read a reused port."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import agent
from backend.native_runtime import configure_native_runtime


class AgentRoutingTests(unittest.TestCase):
    def test_project_folder_resolves_config_even_with_spaces(self):
        args = agent.project_arguments(["--project", "a folder", "status", "--json"])
        self.assertEqual(args, ["--config", str(Path("a folder/.pbibrain/brain.json").resolve()), "status", "--json"])

    def test_missing_connection_allows_offline_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(agent.live_client(Path(directory) / "brain.json"))

    def test_invalid_marker_does_not_fall_back_to_native_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "brain.json"
            (config.parent / "connection.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "Reopen"):
                agent.live_client(config)

    def test_port_reuse_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "brain.json"
            connection = {"url": "http://127.0.0.1:9999", "config_path": str(config), "session_id": "old"}
            (config.parent / "connection.json").write_text(json.dumps(connection), encoding="utf-8")
            reply = io.BytesIO(json.dumps({"session_id": "new", "project": {"config_path": str(config)}}).encode())
            with patch("backend.mcp_server.BrainClient") as client:
                client.return_value.url = connection["url"]
                client.return_value.opener.open.return_value = reply
                with self.assertRaisesRegex(RuntimeError, "Reopen"):
                    agent.live_client(config)

    def test_live_status_uses_http_and_matches_cli_shape(self):
        with patch.object(agent, "live_client") as live, patch("backend.cli.main.main") as offline:
            live.return_value.get.return_value = {"counts": {"nodes": 4, "edges": 3}, "storage": "trail"}
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(agent.main(["status", "--json"]), 0)
            self.assertEqual(json.loads(output.getvalue()), {"nodes": 4, "edges": 3, "storage": "trail"})
            offline.assert_not_called()

    def test_live_mutation_rejected_without_opening_database(self):
        with patch.object(agent, "live_client"), patch("backend.cli.main.main") as offline:
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(agent.main(["project-scan"]), 2)
            offline.assert_not_called()


class BundledRuntimeTests(unittest.TestCase):
    def test_missing_frozen_runtime_returns_none_gracefully(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("sys._MEIPASS", directory, create=True), patch("sys.frozen", True, create=True), patch("sys.platform", "win32"):
                self.assertIsNone(configure_native_runtime())

    def test_bundle_locates_runtime_native_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            native_dir = Path(directory) / "runtime/native"
            native_dir.mkdir(parents=True)
            with patch("sys._MEIPASS", directory, create=True), patch("sys.platform", "linux"):
                self.assertEqual(configure_native_runtime(), native_dir)


if __name__ == "__main__":
    unittest.main()
