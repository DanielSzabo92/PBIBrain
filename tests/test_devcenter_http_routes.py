"""Build step S2: no HTTP route changes session state (route list test, ADR 0003)."""

from __future__ import annotations

import io
import json
from pathlib import Path
import re
import shutil
import tempfile
import unittest
from wsgiref.util import setup_testing_defaults

from backend.api.app import create_app
from backend.desktop import DesktopApplication, DesktopController
from backend.devcenter import http_routes, jsapi
from backend.devcenter.session.manager import DevCenterSessions
from backend.graph.repository import GraphRepository

REPOSITORY = Path(__file__).resolve().parents[1]
DESIGN = REPOSITORY / "docs" / "DEV_CENTER_TECHNICAL_DESIGN.md"
LAB = REPOSITORY / "tests" / "fixtures" / "merge_lab"
WRITE_METHODS = ("POST", "PUT", "PATCH", "DELETE")


def state_change_names() -> list[str]:
    """Read the JS API method names of section 14.2 and of the change requests (section 14.4)."""

    text = DESIGN.read_text(encoding="utf-8")
    section = text.split("### 14.2 State changes", 1)[1].split("\n### ", 1)[0]
    first_paragraph = section.split("\n", 1)[1].strip().split("\n\n", 1)[0]
    names = re.findall(r"`([a-z_]+)`", first_paragraph)
    changes = text.split("### 14.4 UI change requests", 1)[1].split("\n## ", 1)[0]
    names += re.findall(r"\| JS API `([a-z_]+)`", changes)
    return sorted(set(names))


def wsgi(app, method: str, path: str, body: bytes = b"") -> tuple[int, dict]:
    environ: dict = {}
    setup_testing_defaults(environ)
    environ.update({
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "HTTP_HOST": "127.0.0.1:8123",
        "CONTENT_TYPE": "application/json",
        "CONTENT_LENGTH": str(len(body)),
        "wsgi.input": io.BytesIO(body),
    })
    response: dict = {}

    def start_response(status: str, headers: list) -> None:
        response["status"] = int(status.split(" ", 1)[0])

    raw = b"".join(app(environ, start_response))
    return response["status"], json.loads(raw) if raw else {}


# The apply reads of build step S9 (ticket 23).
APPLY_READS = {("apply", "preview"), ("apply", "progress"), ("apply", "last")}


class RouteListTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "project"
        shutil.copytree(LAB / "SalesA", self.root / "SalesA")
        self.devcenter = DevCenterSessions(app_data_dir=None)
        self.devcenter.attach_project(self.root)
        self.app = create_app(use_native=False)
        self.app.devcenter = self.devcenter

    def tearDown(self) -> None:
        self.devcenter.close()
        self.app.close()
        self.temporary.cleanup()

    def test_the_design_list_has_the_state_change_names(self):
        names = state_change_names()
        for name in ("session_create", "source_add", "target_set", "row_confirm", "apply", "proposal_accept_all", "cloud_items_list"):
            self.assertIn(name, names)
        self.assertLessEqual(set(jsapi.METHODS), set(names), "Each JS API method must be a section 14.2 or 14.4 name")

    def test_route_table_has_only_reads_and_proposals(self):
        names = set(state_change_names()) | set(jsapi.METHODS)
        self.assertTrue(http_routes.ROUTES)
        for route in http_routes.ROUTES:
            with self.subTest(route="/".join(route.path)):
                self.assertIn((route.kind, route.method), {("read", "GET"), ("read", "POST"), ("proposal", "POST")})
                if (route.kind, route.method) == ("read", "POST"):
                    # Section 14.1: name-propose and plan-validate are read-only calculations with a body.
                    self.assertIn("/".join(route.path), http_routes.READ_POSTS)
                if route.kind == "proposal":
                    self.assertIn(route.path, {("proposals",), ("questions",)})
                if route.path in APPLY_READS:
                    # Section 14.1 and UC5, UC7: these GET reads of the apply state start with "apply" and change nothing.
                    continue
                self.assertFalse(names & set(route.path), "A route path must not name a state change")

    def test_no_http_route_changes_session_state(self):
        created = self.devcenter.create({"display_name": "Route check"})
        self.devcenter.source_add({"base_revision": 1, "path": str(self.root / "SalesA/SalesA.pbip")})
        session_file = self.root / ".pbibrain" / "sessions" / created["session_id"] / "session.json"
        before = session_file.read_bytes()
        revision = self.devcenter.revision
        for name in state_change_names():
            for method in WRITE_METHODS:
                for path in (f"/api/devcenter/{name}", f"/api/devcenter/session/{name}", f"/api/{name}"):
                    with self.subTest(method=method, path=path):
                        body = json.dumps({"base_revision": revision, "display_name": "x", "session_id": created["session_id"]}).encode("utf-8")
                        status, _ = wsgi(self.app, method, path, body)
                        self.assertIn(status, {404, 405})
        for route in http_routes.ROUTES:
            if route.kind == "read" and route.method == "GET" and not any(part.startswith("{") for part in route.path):
                for method in WRITE_METHODS:
                    with self.subTest(method=method, route=route.path):
                        status, _ = wsgi(self.app, method, "/api/devcenter/" + "/".join(route.path), b"{}")
                        self.assertEqual(405, status)
                status, _ = wsgi(self.app, "GET", "/api/devcenter/" + "/".join(route.path))
                self.assertEqual(200, status)
        self.assertEqual(revision, self.devcenter.revision)
        self.assertEqual(before, session_file.read_bytes())

    def test_unknown_route_answers_404_before_the_session_check(self):
        for method in ("GET",) + WRITE_METHODS:
            with self.subTest(method=method):
                status, payload = wsgi(self.app, method, "/api/devcenter/session_create", b"{}")
                self.assertEqual(404, status)
                self.assertEqual("not_found", payload["error"]["code"])
        status, payload = self.app.handle("GET", "/api/devcenter/session")
        self.assertEqual((409, "session_not_open"), (status, payload["error"]["code"]))

    def test_desktop_host_with_no_project_gives_404_or_405(self):
        static = Path(self.temporary.name) / "dist"
        static.mkdir()
        (static / "index.html").write_text("<main></main>", encoding="utf-8")
        controller = DesktopController(static_dir=static, repository_factory=lambda path: GraphRepository(path, use_native=False),
                                       runtime_configurer=lambda: None, devcenter=DevCenterSessions(app_data_dir=None))
        try:
            host = DesktopApplication(controller)
            for name in state_change_names():
                for method in WRITE_METHODS:
                    with self.subTest(method=method, name=name):
                        status, _ = wsgi(host, method, f"/api/devcenter/{name}", b"{}")
                        self.assertIn(status, {404, 405})
            self.assertEqual(409, wsgi(host, "GET", "/api/devcenter/session")[0])
        finally:
            controller.shutdown()


if __name__ == "__main__":
    unittest.main()
