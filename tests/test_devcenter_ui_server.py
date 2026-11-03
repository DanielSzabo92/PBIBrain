"""Acceptance tests of the Development Center fake server and the test shim (UI design step U0)."""

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from tests import devcenter_ui_server as fake

ROOT = Path(__file__).resolve().parents[1]
# The session IDs of the fixtures (S2: 32 hexadecimal characters).
MAIN_SESSION = "5e55a1f0c0de4b6a9d2e7f3a1b8c4d90"
BUDGET_SESSION = "b0d6e7a2c4f84e1d8a3b5c7d9e1f2a34"


class FakeServerCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dist = tempfile.TemporaryDirectory(prefix="pbibrain-devcenter-dist-")
        index = Path(cls.dist.name) / "index.html"
        index.write_text(
            '<!doctype html><html><head><script src="/theme-init.js"></script>'
            '<script type="module" crossorigin src="/assets/index.js"></script></head>'
            '<body><div id="root"></div></body></html>',
            encoding="utf-8",
        )
        (Path(cls.dist.name) / "assets").mkdir()
        (Path(cls.dist.name) / "assets" / "index.js").write_bytes(b"export {};\n")
        cls.server = fake.create_server(0, dist=Path(cls.dist.name))
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.dist.cleanup()

    def setUp(self) -> None:
        self.post("/__test__/scenario", {"name": "default"})

    def request(self, method: str, path: str, body: dict | None = None) -> tuple[int, object, bytes]:
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = Request(self.base + path, data=data, method=method, headers={"Content-Type": "application/json"} if data else {})
        try:
            with urlopen(request, timeout=10) as response:
                raw = response.read()
                status = response.status
                kind = response.headers.get("Content-Type", "")
        except HTTPError as error:
            raw, status, kind = error.read(), error.code, error.headers.get("Content-Type", "")
        return status, json.loads(raw) if kind.startswith("application/json") else None, raw

    def get(self, path: str) -> object:
        status, value, _ = self.request("GET", path)
        self.assertEqual(status, 200, value)
        return value

    def post(self, path: str, body: dict) -> object:
        status, value, _ = self.request("POST", path, body)
        self.assertEqual(status, 200, value)
        return value

    def call(self, method: str, payload: dict | None = None) -> dict:
        return self.post(f"/__test__/jsapi/{method}", payload or {})

    def revision(self) -> int:
        return self.get("/__test__/health")["revision"]


class HealthAndScenarioTest(FakeServerCase):
    def test_health_answers_and_the_default_port_is_8766(self) -> None:
        self.assertEqual(fake.DEFAULT_PORT, 8766)
        health = self.get("/__test__/health")
        self.assertEqual(health["ok"], True)
        self.assertEqual(health["scenario"], "default")
        self.assertEqual(health["scenarios"], list(fake.SCENARIOS))

    def test_the_scenarios_are_the_list_of_section_10_and_each_has_a_fixture_folder(self) -> None:
        self.assertEqual(fake.SCENARIOS, (
            "default", "no-project", "no-sessions", "locked", "newer-schema", "damaged",
            "sources-changed", "source-missing", "plan-invalid", "apply-ready", "large-5000-rows",
        ))
        folders = {path.name for path in fake.FIXTURES.iterdir() if path.is_dir()}
        self.assertEqual(folders, set(fake.SCENARIOS))

    def test_each_scenario_loads_and_a_second_load_resets_the_state(self) -> None:
        for name in fake.SCENARIOS:
            with self.subTest(scenario=name):
                loaded = self.post("/__test__/scenario", {"name": name})
                self.assertEqual(loaded["scenario"], name)
                first = loaded["revision"]
                desktop = self.post("/__test__/desktop/get_session", {"args": []})
                self.assertEqual(desktop["ok"], True)
                status, sessions, _ = self.request("GET", "/api/devcenter/sessions")
                status_session, session, _ = self.request("GET", "/api/devcenter/session")
                if name == "no-project":
                    self.assertEqual((status, sessions["error"]["details"]), (409, {"reason": "no_project"}))
                else:
                    # GET sessions has a null revision when no session is open (S2 schema).
                    self.assertEqual(sessions["revision"], first if status_session == 200 else None)
                status = status_session
                if status == 200:
                    self.assertEqual(session["revision"], first)
                    self.post("/__test__/agent-proposal", {"target_id": "row-date", "target_name": "Date"})
                    self.assertEqual(self.revision(), first + 1)
                else:
                    self.assertEqual(session["error"]["code"], "session_not_open")
                self.post("/__test__/fault", {"method": "sources_check", "code": "unknown"})
                again = self.post("/__test__/scenario", {"name": name})
                self.assertEqual(again["revision"], first)
                reply = self.call("sources_check", {"base_revision": first})
                self.assertNotEqual(reply.get("error", {}).get("code"), "unknown", "the reload must clear the fault")

    def test_an_unknown_scenario_is_not_found(self) -> None:
        status, value, _ = self.request("POST", "/__test__/scenario", {"name": "no-such-scenario"})
        self.assertEqual(status, 404)
        self.assertEqual(value["error"]["code"], "not_found")

    def test_the_scenario_states(self) -> None:
        self.post("/__test__/scenario", {"name": "no-project"})
        self.assertIsNone(self.post("/__test__/desktop/get_session", {"args": []})["project"])
        status, refused, _ = self.request("GET", "/api/devcenter/sessions")
        self.assertEqual((status, refused["error"]["code"]), (409, "action_not_allowed"))
        self.post("/__test__/scenario", {"name": "no-sessions"})
        self.assertEqual(self.get("/api/devcenter/sessions")["sessions"], [])
        for name, state in (("newer-schema", "newer"), ("damaged", "damaged")):
            self.post("/__test__/scenario", {"name": name})
            self.assertEqual(self.get("/api/devcenter/sessions")["sessions"][0]["schema_state"], state)
            refused = self.call("session_open", {"session_id": MAIN_SESSION})
            self.assertEqual(refused["error"]["code"], "action_not_allowed")
        self.post("/__test__/scenario", {"name": "sources-changed"})
        marked = self.get("/api/devcenter/compare-rows?marks=true")
        self.assertEqual(marked["total"], 3)
        self.post("/__test__/scenario", {"name": "source-missing"})
        self.assertEqual(self.get("/api/devcenter/session")["sources"][0]["status"], "missing")
        self.post("/__test__/scenario", {"name": "plan-invalid"})
        self.assertEqual(self.get("/api/devcenter/plan")["status"], "invalid")
        self.post("/__test__/scenario", {"name": "apply-ready"})
        self.assertEqual(self.get("/api/devcenter/apply/preview")["ready"], True)
        self.post("/__test__/scenario", {"name": "large-5000-rows"})
        page = self.get("/api/devcenter/compare-rows")
        self.assertEqual((page["total"], len(page["rows"]), page["has_more"]), (5000, 200, True))
        self.assertEqual(len(self.get("/api/devcenter/session")["sources"]), 5)
        self.assertEqual(self.get("/api/devcenter/impact?limit=50")["total"], 5000)


class JsApiTest(FakeServerCase):
    def test_a_wrong_base_revision_returns_stale_revision(self) -> None:
        current = self.revision()
        for base in (current - 1, current + 1, None):
            with self.subTest(base_revision=base):
                payload = {} if base is None else {"base_revision": base}
                reply = self.call("merge_choice_set", {**payload, "row_key": "row-net-sales", "choice": {"choice": "keep"}})
                self.assertEqual(reply["error"]["code"], "stale_revision")
                self.assertEqual(reply["error"]["details"]["revision"], current)
                self.assertEqual(set(reply["error"]), {"code", "message", "details"})
        self.assertEqual(self.revision(), current, "a refused call must not change the revision")

    def test_a_good_call_changes_the_state_that_the_reads_show(self) -> None:
        current = self.revision()
        reply = self.call("merge_choice_set", {"base_revision": current, "row_key": "row-net-sales", "choice": {"choice": "keep"}})
        self.assertEqual(reply["revision"], current + 1)
        rows = self.get("/api/devcenter/compare-rows?q=net")
        self.assertEqual(rows["revision"], current + 1)
        self.assertEqual(rows["rows"][0]["merge_choice"], {"choice": "keep"})
        self.assertEqual(self.get("/api/devcenter/log")["entries"][0]["action"], "merge_choice_set")

    def test_each_method_answers(self) -> None:
        for method in fake.JSAPI_METHODS:
            with self.subTest(method=method):
                self.post("/__test__/scenario", {"name": "default"})
                reply = self.call(method, {"base_revision": self.revision()})
                if "error" in reply:
                    self.assertIn(reply["error"]["code"], {"invalid_payload", "not_found"}, reply)
                else:
                    self.assertIsInstance(reply["revision"], int)

    def test_an_unknown_method_is_not_found(self) -> None:
        self.assertEqual(self.call("no_such_method", {"base_revision": 0})["error"]["code"], "not_found")

    def test_a_locked_session_refuses_a_change(self) -> None:
        self.post("/__test__/scenario", {"name": "locked"})
        reply = self.call("merge_choice_set", {"base_revision": self.revision(), "row_key": "row-net-sales", "choice": None})
        self.assertEqual(reply["error"]["code"], "action_not_allowed")
        self.assertEqual(reply["error"]["details"], {"reason": "session_locked"})

    def test_no_open_session_gives_session_not_open(self) -> None:
        self.post("/__test__/scenario", {"name": "no-sessions"})
        self.assertEqual(self.call("sources_check", {"base_revision": 0})["error"]["code"], "session_not_open")
        status, value, _ = self.request("GET", "/api/devcenter/compare-rows")
        self.assertEqual((status, value["error"]["code"]), (409, "session_not_open"))


class TestControlTest(FakeServerCase):
    def test_a_fault_changes_only_the_next_reply_of_the_method(self) -> None:
        self.post("/__test__/fault", {"method": "sources_check", "code": "action_not_allowed", "message": "Injected.", "details": {"why": "test"}})
        current = self.revision()
        other = self.call("compare_mode_set", {"base_revision": current, "mode": "names"})
        self.assertNotIn("error", other, "a fault is only for its method")
        failed = self.call("sources_check", {"base_revision": other["revision"]})
        self.assertEqual(failed, {"error": {"code": "action_not_allowed", "message": "Injected.", "details": {"why": "test"}}})
        passed = self.call("sources_check", {"base_revision": other["revision"]})
        self.assertEqual(passed["revision"], other["revision"] + 1)

    def test_a_fault_that_is_not_once_stays_until_it_is_cleared(self) -> None:
        self.post("/__test__/fault", {"method": "sources_check", "code": "unknown", "once": False})
        for _ in range(2):
            self.assertEqual(self.call("sources_check", {"base_revision": self.revision()})["error"]["code"], "unknown")
        self.post("/__test__/fault", {"method": "sources_check", "code": None})
        self.assertNotIn("error", self.call("sources_check", {"base_revision": self.revision()}))

    def test_a_network_fault_is_an_http_failure_and_a_read_fault_uses_the_path(self) -> None:
        self.post("/__test__/fault", {"method": "sources_check", "code": "network"})
        status, value, _ = self.request("POST", "/__test__/jsapi/sources_check", {"base_revision": self.revision()})
        self.assertEqual((status, value["error"]["code"]), (503, "network"))
        self.post("/__test__/fault", {"path": "/api/devcenter/plan", "code": "unknown", "status": 500})
        status, value, _ = self.request("GET", "/api/devcenter/plan")
        self.assertEqual((status, value["error"]["code"]), (500, "unknown"))
        self.assertEqual(self.get("/api/devcenter/plan")["status"], "valid_with_warnings")

    def test_a_delay_slows_the_reply_and_the_server_still_answers_other_calls(self) -> None:
        # The upper limits are wide, because a busy test PC is slow. The delay is longer than each limit.
        self.post("/__test__/delay", {"method": "sources_check", "ms": 1500, "once": True})
        result: dict = {}

        def slow() -> None:
            started = time.monotonic()
            result["reply"] = self.call("sources_check", {"base_revision": self.revision()})
            result["seconds"] = time.monotonic() - started

        worker = threading.Thread(target=slow)
        worker.start()
        time.sleep(0.05)
        started = time.monotonic()
        self.get("/__test__/health")
        self.assertLess(time.monotonic() - started, 1.0, "the health route must not wait for the delay")
        worker.join(5)
        self.assertGreaterEqual(result["seconds"], 1.5)
        self.assertIn("revision", result["reply"])
        started = time.monotonic()
        self.call("sources_check", {"base_revision": self.revision()})
        self.assertLess(time.monotonic() - started, 1.0, "a once delay is only for the next call")

    def test_a_delay_on_a_read_path(self) -> None:
        self.post("/__test__/delay", {"path": "/api/devcenter/compare-rows", "ms": 1500})
        started = time.monotonic()
        self.get("/api/devcenter/compare-rows")
        self.assertGreaterEqual(time.monotonic() - started, 1.5)
        self.post("/__test__/delay", {"path": "/api/devcenter/compare-rows", "ms": 0})
        started = time.monotonic()
        self.get("/api/devcenter/compare-rows")
        self.assertLess(time.monotonic() - started, 1.0)

    def test_an_agent_proposal_increments_the_revision_and_shows_in_the_session(self) -> None:
        current = self.revision()
        added = self.post("/__test__/agent-proposal", {"target_id": "row-customer", "target_name": "Customer", "summary": "Rename to Customers"})
        self.assertEqual(added["revision"], current + 1)
        session = self.get("/api/devcenter/session")
        self.assertEqual(session["revision"], current + 1)
        self.assertEqual([item["target_id"] for item in session["proposals"]["open"]], ["row-net-sales", "row-customer"])
        replaced = self.post("/__test__/agent-proposal", {"target_id": "row-customer", "summary": "Rename to Client"})
        proposals = self.get("/api/devcenter/session")["proposals"]["open"]
        self.assertEqual([item["id"] for item in proposals], ["p-1", replaced["proposal"]["id"]])
        self.assertEqual(proposals[1]["summary"], "Rename to Client")
        stale = self.call("proposal_accept", {"base_revision": current, "proposal_id": "p-1"})
        self.assertEqual(stale["error"]["code"], "stale_revision", "a call with the revision from before the poll is stale")

    def test_bad_control_bodies_are_invalid_payload(self) -> None:
        for path, body in (("/__test__/fault", {"code": "unknown"}), ("/__test__/delay", {"method": "apply", "ms": -1})):
            status, value, _ = self.request("POST", path, body)
            self.assertEqual((status, value["error"]["code"]), (400, "invalid_payload"))


class ReadAndShimTest(FakeServerCase):
    def test_each_read_carries_the_revision(self) -> None:
        current = self.revision()
        for path in ("session", "sessions", "compare-rows", "compare-rows/row-net-sales/diff?source=src-2", "plan",
                     "impact", "impact/removal/row-budget", "wireframe/report-1", "naming-rules", "apply/preview",
                     "apply/progress", "apply/last", "log", "display-folders"):
            with self.subTest(path=path):
                self.assertEqual(self.get(f"/api/devcenter/{path}")["revision"], current)
        for path, body in (("name-propose", {"candidate": "net sales"}), ("plan-validate", {"mode": "full"})):
            with self.subTest(path=path):
                self.assertEqual(self.post(f"/api/devcenter/{path}", body)["revision"], current)

    def test_compare_rows_filter_sort_and_page(self) -> None:
        page = self.get("/api/devcenter/compare-rows?type=table&sort=name:desc&limit=2&offset=0")
        self.assertEqual([row["name"] for row in page["rows"]], ["Date", "Customer"])
        self.assertEqual((page["total"], page["has_more"]), (3, True))
        self.assertEqual(page["state_counts"], {"missing": 1, "renamed": 1, "same": 1})

    def test_the_proposal_endpoint_checks_the_agent_rules(self) -> None:
        current = self.revision()
        for body, code in (({"base_revision": current - 1, "reason": "x", "confidence": 0.95}, "stale_revision"),
                           ({"base_revision": current, "reason": "", "confidence": 0.95}, "reason_required"),
                           ({"base_revision": current, "reason": "x", "confidence": 0.5}, "confidence_below_threshold")):
            with self.subTest(code=code):
                status, value, _ = self.request("POST", "/api/devcenter/proposals", body)
                self.assertEqual(value["error"]["code"], code)
                self.assertEqual(status, fake.ERROR_STATUS[code])
        self.assertEqual(self.post("/api/devcenter/proposals", {"base_revision": current, "reason": "Match.", "confidence": 0.95})["revision"], current + 1)

    def test_the_index_page_has_the_shim_tag_before_the_app_module(self) -> None:
        for path in ("/", "/devcenter/compare"):
            with self.subTest(path=path):
                status, _, raw = self.request("GET", path)
                html = raw.decode("utf-8")
                self.assertEqual(status, 200)
                self.assertEqual(html.count(fake.SHIM_TAG), 1)
                self.assertLess(html.index(fake.SHIM_TAG), html.index('type="module"'))
        status, _, raw = self.request("GET", "/assets/index.js")
        self.assertEqual((status, raw), (200, b"export {};\n"))

    def test_the_shim_script_has_the_method_lists(self) -> None:
        status, _, raw = self.request("GET", fake.SHIM_PATH)
        self.assertEqual(status, 200)
        text = raw.decode("utf-8")
        prefix = "self.__DEVCENTER_FAKE_METHODS__ = "
        self.assertTrue(text.startswith(prefix))
        lists = json.loads(text[len(prefix):text.index(";\n")])
        self.assertEqual(lists, {"jsapi": list(fake.JSAPI_METHODS), "desktop": list(fake.DESKTOP_METHODS)})
        self.assertIn("pywebviewready", text)

    def test_the_jsapi_list_is_section_14_2_plus_the_change_requests(self) -> None:
        design = (ROOT / "docs" / "DEV_CENTER_TECHNICAL_DESIGN.md").read_text(encoding="utf-8")
        section = design[design.index("### 14.2"):design.index("### 14.3")]
        listed = section.split("\n\n")[1]
        names = [part.strip().strip("`").split("`")[0] for part in listed.split(",")]
        self.assertEqual(list(fake.JSAPI_METHODS), names + ["cloud_items_list"])


if __name__ == "__main__":
    unittest.main()
