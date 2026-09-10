"""Native-independent desktop lifecycle and local transport checks."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from urllib.request import urlopen
from wsgiref.util import setup_testing_defaults

from backend.desktop import DesktopApplication, DesktopController, DesktopServer, discover_pbip_sources
from backend.graph.repository import GraphRepository


class DesktopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.static = self.root / "dist"
        self.static.mkdir()
        (self.static / "index.html").write_text("<main>PBIBrain</main>", encoding="utf-8")
        self.controller = DesktopController(
            static_dir=self.static,
            repository_factory=lambda path: GraphRepository(path, use_native=False),
            runtime_configurer=lambda: None,
        )

    def tearDown(self) -> None:
        self.controller.shutdown()
        self.temporary.cleanup()

    def _request(
        self,
        app: DesktopApplication,
        path: str,
        *,
        method: str = "GET",
        host: str = "127.0.0.1:8123",
        origin: str = "",
        session_id: str = "",
    ) -> tuple[str, dict[str, str], bytes]:
        environ: dict[str, object] = {}
        setup_testing_defaults(environ)
        environ.update(
            {
                "REQUEST_METHOD": method,
                "PATH_INFO": path,
                "HTTP_HOST": host,
                "HTTP_ORIGIN": origin,
                "HTTP_X_PBIBRAIN_SESSION": session_id,
                "wsgi.input": io.BytesIO(b""),
                "CONTENT_LENGTH": "0",
            }
        )
        response: dict[str, object] = {}

        def start_response(status: str, headers: list[tuple[str, str]]) -> None:
            response["status"] = status
            response["headers"] = dict(headers)

        raw = b"".join(app(environ, start_response))
        return str(response["status"]), dict(response["headers"]), raw

    def test_discovery_prefers_all_top_level_projects_and_skips_runtime_state(self):
        first = self.root / "Finance.pbip"
        second = self.root / "Operations.PBIP"
        first.write_text("{}", encoding="utf-8")
        second.write_text("{}", encoding="utf-8")
        nested = self.root / "backup" / "Finance_old.pbip"
        nested.parent.mkdir()
        nested.write_text("{}", encoding="utf-8")

        self.assertEqual(discover_pbip_sources(self.root), [first.resolve(), second.resolve()])

        first.unlink()
        second.unlink()
        ignored = self.root / ".pbibrain" / "ignored.pbip"
        ignored.parent.mkdir()
        ignored.write_text("{}", encoding="utf-8")
        self.assertEqual(discover_pbip_sources(self.root), [nested.resolve()])

    def test_open_creates_relative_config_and_owned_connection_marker(self):
        source = self.root / "Portfolio.pbip"
        source.write_text("{}", encoding="utf-8")
        self.controller.attach_server("http://127.0.0.1:8123")

        result = self.controller.open_project("Portfolio", str(self.root))

        self.assertTrue(result["ok"])
        self.assertEqual(result["source_count"], 1)
        config_path = self.root / ".pbibrain" / "brain.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual(config["database"], "brain.lbug")
        self.assertEqual(config["identity_map"], "identity-map.json")
        self.assertFalse(Path(config["sources"][0]).is_absolute())
        marker_path = self.root / ".pbibrain" / "connection.json"
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        self.assertEqual(set(marker), {"url", "config_path", "session_id"})
        self.assertEqual(marker["url"], "http://127.0.0.1:8123")

        self.controller.close_project()
        self.assertFalse(marker_path.exists())

    def test_existing_config_is_reopened_without_rewriting_it(self):
        source = self.root / "Original.pbip"
        source.write_text("{}", encoding="utf-8")
        self.controller.attach_server("http://127.0.0.1:8123")
        self.assertTrue(self.controller.open_project("Original", str(self.root))["ok"])
        config_path = self.root / ".pbibrain" / "brain.json"
        before = config_path.read_bytes()
        self.controller.close_project()

        reopened = self.controller.open_project("Replacement name", str(self.root))

        self.assertTrue(reopened["ok"])
        self.assertEqual(reopened["project"]["name"], "Original")
        self.assertEqual(config_path.read_bytes(), before)

    def test_reopen_rotates_connection_session_and_rejects_stale_agent_request(self):
        source = self.root / "Project.pbip"
        source.write_text("{}", encoding="utf-8")
        server = DesktopServer(self.controller)
        server.start()
        try:
            first = self.controller.open_project("Project", str(self.root))
            marker_path = self.root / ".pbibrain" / "connection.json"
            first_session = json.loads(marker_path.read_text(encoding="utf-8"))["session_id"]
            self.assertTrue(self.controller.close_project()["ok"])
            reopened = self.controller.open_project("Ignored rename", str(self.root))
            second_session = json.loads(marker_path.read_text(encoding="utf-8"))["session_id"]

            self.assertTrue(reopened["ok"])
            self.assertNotEqual(first_session, second_session)
            status, _, body = self._request(server.application, "/api/overview", session_id=first_session)
            self.assertEqual(status, "409 Conflict")
            self.assertIn(b"session changed", body)
            status, _, _ = self._request(server.application, "/api/overview", session_id=second_session)
            self.assertEqual(status, "200 OK")
        finally:
            server.stop()

    def test_empty_folder_opens_project_for_json_or_bim_onboarding(self):
        source = self.root / "model.json"
        source.write_text('{"models": []}', encoding="utf-8")
        self.controller.attach_server("http://127.0.0.1:8123")

        result = self.controller.open_project("JSON project", str(self.root))

        self.assertTrue(result["ok"])
        self.assertEqual(result["source_count"], 0)
        added = self.controller.add_sources([str(source)])
        self.assertTrue(added["ok"])
        self.assertEqual(len(added["sources"]), 1)

    def test_shutdown_preserves_connection_marker_owned_by_another_session(self):
        source = self.root / "Project.pbip"
        source.write_text("{}", encoding="utf-8")
        self.controller.attach_server("http://127.0.0.1:8123")
        self.assertTrue(self.controller.open_project("Project", str(self.root))["ok"])
        marker_path = self.root / ".pbibrain" / "connection.json"
        marker_path.write_text(
            json.dumps({"url": "http://127.0.0.1:9999", "config_path": "other", "session_id": "other"}),
            encoding="utf-8",
        )

        self.controller.shutdown()

        self.assertTrue(marker_path.is_file())
        self.assertEqual(json.loads(marker_path.read_text(encoding="utf-8"))["session_id"], "other")

    def test_wsgi_serves_onboarding_and_rejects_foreign_origins(self):
        app = DesktopApplication(self.controller)

        status, headers, body = self._request(app, "/")
        self.assertEqual(status, "200 OK")
        self.assertIn(b"PBIBrain", body)
        self.assertIn(b'<script src="/desktop/bootstrap.js"></script>', body)
        self.assertIn("default-src 'self'", headers["Content-Security-Policy"])

        status, headers, body = self._request(app, "/desktop/bootstrap.js")
        self.assertEqual(status, "200 OK")
        self.assertEqual(headers["Content-Type"], "application/javascript")
        self.assertEqual(body, b"window.__PBIBRAIN_DESKTOP__=true;")

        status, _, body = self._request(app, "/api/brain")
        self.assertEqual(status, "503 Service Unavailable")
        self.assertIn(b"Open a project first", body)

        status, _, _ = self._request(app, "/desktop/session", origin="https://example.com")
        self.assertEqual(status, "403 Forbidden")

    def test_session_endpoint_and_project_api_share_one_server(self):
        source = self.root / "Project.pbip"
        source.write_text("{}", encoding="utf-8")
        server = DesktopServer(self.controller)
        server.start()
        try:
            opened = self.controller.open_project("Project", str(self.root))
            self.assertTrue(opened["ok"])
            with urlopen(f"{server.url}/desktop/session", timeout=5) as response:
                endpoint = json.load(response)
            with urlopen(f"{server.url}/api/config", timeout=5) as response:
                config = json.load(response)
            self.assertTrue(endpoint["ok"])
            self.assertEqual(endpoint["project"]["config_path"], opened["project"]["config_path"])
            self.assertEqual(config["name"], "Project")
        finally:
            server.stop()

    def test_folder_picker_cancel_and_selection_have_stable_envelopes(self):
        cancelled = DesktopController(static_dir=self.static, folder_picker=lambda: None)
        selected = DesktopController(static_dir=self.static, folder_picker=lambda: self.root)
        try:
            self.assertEqual(cancelled.choose_folder(), {"ok": True, "folder": None})
            self.assertEqual(selected.choose_folder(), {"ok": True, "folder": str(self.root.resolve())})
        finally:
            cancelled.shutdown()
            selected.shutdown()

    def test_explicit_source_picker_appends_supported_files_atomically(self):
        source = self.root / "Project.pbip"
        export = self.root / "model.bim"
        source.write_text("{}", encoding="utf-8")
        export.write_text("{}", encoding="utf-8")
        self.controller.attach_server("http://127.0.0.1:8123")
        self.assertTrue(self.controller.open_project("Project", str(self.root))["ok"])

        selected = DesktopController(static_dir=self.static, source_picker=lambda: [export])
        try:
            self.assertEqual(selected.choose_sources(), {"ok": True, "sources": [str(export.resolve())]})
        finally:
            selected.shutdown()
        result = self.controller.add_sources([str(export), str(export)])

        self.assertTrue(result["ok"])
        self.assertEqual(len(result["added"]), 1)
        self.assertEqual(len(result["sources"]), 2)
        before = (self.root / ".pbibrain" / "brain.json").read_bytes()
        rejected = self.controller.add_sources([str(self.root / "missing.json")])
        self.assertFalse(rejected["ok"])
        self.assertEqual((self.root / ".pbibrain" / "brain.json").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
