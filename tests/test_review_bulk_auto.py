"""Bulk review decisions on the server (one write, one undo token) and the auto-accept setting."""

from __future__ import annotations

import shutil
import tempfile
import time
import unittest
from collections import Counter
from pathlib import Path

from backend.api.app import create_app
from backend.projects import ProjectConfigError, ProjectService
from tests.fixtures.large_project import write_large_project


class ReviewBulkAndAutoAcceptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # One scan for the class (13 s); each test works on its own copy of the scanned project.
        cls.template = tempfile.TemporaryDirectory()
        root = Path(cls.template.name) / "project"
        root.mkdir()
        cls.config_name = write_large_project(root).relative_to(root)
        app = create_app(database_path=root / "brain.db", overrides_path=root / "overrides.json", use_native=False)
        app.project = ProjectService(root / cls.config_name)
        status, _ = app.handle("POST", "/api/scan")
        app.close()
        assert status == 200

    @classmethod
    def tearDownClass(cls) -> None:
        cls.template.cleanup()

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name) / "project"
        shutil.copytree(Path(self.template.name) / "project", root)
        self.config = root / self.config_name
        self.app = create_app(database_path=root / "brain.db", overrides_path=root / "overrides.json", use_native=False)
        self.addCleanup(self.app.close)
        self.app.project = ProjectService(self.config)

    def queue(self) -> list[dict]:
        status, items = self.app.handle("GET", "/api/review")
        self.assertEqual(status, 200)
        return items

    def post(self, body: dict) -> dict:
        status, reply = self.app.handle("POST", "/api/review", body)
        self.assertEqual(status, 200, reply)
        return reply

    def test_bulk_decision_by_ids_is_one_quick_write_with_an_undo_token(self) -> None:
        before = self.queue()
        ids = [item["candidate_id"] or item["id"] for item in before if item["issue_type"] == "candidate"]
        self.assertGreater(len(ids), 100)
        started = time.perf_counter()
        reply = self.post({"action": "approve", "items": ids, "reply": "summary"})
        self.assertLess(time.perf_counter() - started, 5.0)
        self.assertNotIn("snapshot", reply, "a summary reply does not ship the snapshot")
        self.assertNotIn("nodes", reply["result"])
        self.assertGreaterEqual(reply["result"]["count"], len(ids))
        self.assertFalse([item for item in self.queue() if item["issue_type"] == "candidate"])

        undone = self.post({"action": "undo", "token": reply["result"]["undo_token"], "reply": "summary"})
        self.assertEqual(undone["result"]["count"], reply["result"]["count"])
        self.assertEqual(len(self.queue()), len(before))
        status, _ = self.app.handle("POST", "/api/review", {"action": "undo", "token": reply["result"]["undo_token"]})
        self.assertEqual(status, 404, "a token undoes its decision once")

    def test_undo_puts_back_the_earlier_decisions_not_just_open(self) -> None:
        first, second = [item["candidate_id"] or item["id"] for item in self.queue() if item["issue_type"] == "candidate"][:2]
        self.post({"action": "reject", "items": [first], "reply": "summary"})
        reply = self.post({"action": "approve", "items": [first, second], "reply": "summary"})
        self.post({"action": "undo", "token": reply["result"]["undo_token"], "reply": "summary"})
        open_ids = {item["candidate_id"] or item["id"] for item in self.queue()}
        self.assertIn(second, open_ids)
        self.assertNotIn(first, open_ids, "the rejection made before the bulk decision is kept")

    def test_bulk_decision_by_filter_chooses_on_the_server(self) -> None:
        before = self.queue()
        types = Counter(item["object_type"] for item in before if item["issue_type"] == "candidate")
        object_type, expected = types.most_common(1)[0]
        self.post({"action": "reject", "filter": {"object_type": object_type}, "reply": "summary"})
        after = self.queue()
        self.assertEqual(len(before) - len(after), expected)
        self.assertFalse([item for item in after if item["object_type"] == object_type and item["issue_type"] == "candidate"])
        status, _ = self.app.handle("POST", "/api/review", {"action": "approve", "filter": {"name": "x"}})
        self.assertEqual(status, 400)

    def test_auto_accept_takes_suggestions_out_of_the_queue_and_marks_them(self) -> None:
        before = self.queue()
        covered = [
            item for item in before
            if item["issue_type"] == "candidate" and item["confidence"] >= 0.5
            and (item["item"].get("properties") or {}).get("candidate_source") in {"object_name", "description"}
        ]
        self.assertTrue(covered, "the fixture has suggestions from names or descriptions")
        config = ProjectService(self.config).get_config()
        status, saved = self.app.handle("POST", "/api/config", {**config, "review": {"auto_accept": True, "auto_accept_threshold": 0.5}})
        self.assertEqual(status, 200, saved)
        after = self.queue()
        self.assertEqual(len(before) - len(after), len(covered))
        auto, offset = [], 0
        while True:  # the decided list, a page at a time
            status, reviewed = self.app.handle("GET", f"/api/review/page?tab=reviewed&limit=500&offset={offset}")
            auto += [item for item in reviewed["items"] if item.get("decided_by") == "auto"]
            if not reviewed["has_more"]:
                break
            offset += 500
        self.assertEqual(len(auto), len(covered))
        self.assertTrue(all(item["status"] == "approved" for item in auto))

        # A person reopens one: it is back in the queue and the next scan leaves it there.
        one = auto[0]["id"]
        self.post({"action": "reopen", "candidate_id": one})
        self.assertIn(one, {item["candidate_id"] or item["id"] for item in self.queue()})
        self.app.handle("POST", "/api/scan")
        ids = {item["candidate_id"] or item["id"] for item in self.queue()}
        self.assertIn(one, ids)
        self.assertEqual(len(ids), len(after) + 1, "the scan keeps the automatic decisions")

        # Turning the setting off returns the automatic decisions, and only those, to the queue.
        two = next(item["candidate_id"] or item["id"] for item in self.queue() if (item["candidate_id"] or item["id"]) != one and item["issue_type"] == "candidate")
        self.post({"action": "approve", "candidate_id": two})
        self.app.handle("POST", "/api/config", {**config, "review": {"auto_accept": False}})
        self.assertEqual(len(self.queue()), len(before) - 1)

    def test_review_settings_are_validated(self) -> None:
        service = ProjectService(self.config)
        config = service.get_config()
        for bad in ({"auto_accept": "yes"}, {"auto_accept_threshold": 0.2}, {"other": 1}):
            with self.assertRaises(ProjectConfigError):
                service.save_config({**config, "review": bad})


if __name__ == "__main__":
    unittest.main()
