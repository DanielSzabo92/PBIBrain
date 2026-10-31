"""Route list test: no HTTP route of the real app changes session state (ADR 0003, S2, U0).

This test reads the real app only (backend/api/app.py through BrainApp). The
fake server tests/devcenter_ui_server.py has /__test__ routes and a JS API mock
over HTTP, so this test must never read the fake server.

Contract for later steps: an HTTP route that does not exist answers 404 (or 405)
before any session check. Only reads and the agent proposal endpoints
(technical design sections 14.1 and 14.3) can exist under /api/devcenter.
"""

import io
import json
import tempfile
import unittest
from pathlib import Path

from backend.api.app import BrainAPI, BrainApp
from backend.graph.repository import GraphRepository

ROOT = Path(__file__).resolve().parents[1]
TEST_ROUTES = ("health", "scenario", "fault", "delay", "agent-proposal", "pywebview-shim.js", "jsapi/merge_choice_set", "desktop/get_session")
MISSING = {404, 405}


def jsapi_methods() -> list[str]:
    """The JS API method names of technical design section 14.2. These are pywebview calls only."""
    design = (ROOT / "docs" / "DEV_CENTER_TECHNICAL_DESIGN.md").read_text(encoding="utf-8")
    section = design[design.index("### 14.2"):design.index("### 14.3")]
    listed = section.split("\n\n")[1]
    return [part.strip().strip("`").split("`")[0] for part in listed.split(",")] + ["cloud_items_list"]


class RealAppRouteListTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.folder = tempfile.TemporaryDirectory(prefix="pbibrain-route-list-")
        cls.repository = GraphRepository(use_native=False)
        cls.app = BrainApp(BrainAPI(cls.repository, overrides_path=Path(cls.folder.name) / "overrides.json"))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.app.close()
        cls.folder.cleanup()

    def status(self, method: str, path: str, body: dict | None = None) -> int:
        raw = json.dumps(body or {}).encode("utf-8") if method == "POST" else b""
        environ = {
            "REQUEST_METHOD": method, "PATH_INFO": path, "QUERY_STRING": "", "HTTP_HOST": "127.0.0.1:8000",
            "CONTENT_TYPE": "application/json", "CONTENT_LENGTH": str(len(raw)), "wsgi.input": io.BytesIO(raw),
        }
        statuses: list[str] = []
        self.app(environ, lambda status, _headers: statuses.append(status))
        return int(statuses[0].split()[0])

    def test_the_method_list_has_the_section_14_2_calls(self) -> None:
        methods = jsapi_methods()
        self.assertEqual(len(methods), 33)
        for name in ("merge_choice_set", "apply", "undo_apply", "proposal_accept", "session_open", "pull_to_local"):
            self.assertIn(name, methods)

    def test_the_probe_sees_a_route_that_exists(self) -> None:
        # POST /api/review exists (it refuses the empty body). The probe must not give 404 for it.
        self.assertNotIn(self.status("POST", "/api/review"), MISSING)
        self.assertEqual(self.status("GET", "/api/overview"), 200)

    def test_no_http_route_runs_a_js_api_call(self) -> None:
        for method_name in jsapi_methods():
            for name in {method_name, method_name.replace("_", "-")}:
                for path in (f"/api/devcenter/{name}", f"/api/{name}", f"/api/devcenter/session/{name}"):
                    for verb in ("POST", "PUT", "PATCH", "DELETE"):
                        with self.subTest(verb=verb, path=path):
                            self.assertIn(self.status(verb, path, {"base_revision": 0}), MISSING)

    def test_the_real_app_has_no_test_route(self) -> None:
        for route in TEST_ROUTES:
            for verb in ("GET", "POST"):
                with self.subTest(verb=verb, route=route):
                    self.assertIn(self.status(verb, f"/__test__/{route}", {"name": "default"}), MISSING)

    def test_backend_code_never_refers_to_the_fake_server_or_the_shim(self) -> None:
        markers = ("__test__", "devcenter_ui_server", "pywebviewShim", "pywebview-shim")
        for path in sorted((ROOT / "backend").rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            for marker in markers:
                with self.subTest(path=str(path.relative_to(ROOT)), marker=marker):
                    self.assertNotIn(marker, text)


if __name__ == "__main__":
    unittest.main()
