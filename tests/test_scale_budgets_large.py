"""Scale gate on the enterprise-size project of the product review (adversarial review 22).

``tools.large_project`` writes 8 models, 24 reports and 13,731 objects. The budgets are several
times the values measured when the fixes were made, so a slow machine passes and a route that
goes back to scanning or shipping the whole graph does not.
"""

from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from urllib.parse import quote

from backend.api.app import create_app
from backend.projects import ProjectService
from tools.large_project import write_project


class LargeProjectBudgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        root = Path(cls.temporary.name)
        config = write_project(root)
        cls.app = create_app(database_path=root / "brain.db", overrides_path=root / "overrides.json", use_native=False)
        cls.app.project = ProjectService(config)
        status, reply = cls.app.handle("POST", "/api/scan")
        assert status == 200, reply

    @classmethod
    def tearDownClass(cls) -> None:
        cls.app.close()
        cls.temporary.cleanup()

    def timed(self, method: str, path: str, body: dict | None = None):
        started = time.perf_counter()
        status, reply = self.app.handle(method, path, body)
        seconds = time.perf_counter() - started
        self.assertEqual(status, 200, reply if status != 200 else None)
        return reply, seconds

    def test_the_fixture_has_the_size_of_the_review(self) -> None:
        overview, _ = self.timed("GET", "/api/overview")
        self.assertEqual(overview["counts"], {"nodes": 13731, "edges": 41942})
        self.assertEqual(overview["review_count"], 11528)

    def test_overview_and_one_object(self) -> None:
        overview, seconds = self.timed("GET", "/api/overview")
        self.assertLess(seconds, 20.0)  # measured 3 s cold; the server builds it once, before the first request
        self.assertLess(len(json.dumps(overview)), 300_000)
        self.assertLessEqual(len(overview["validation_issues"]), 50, "issues are listed in part and counted")
        _, seconds = self.timed("GET", "/api/object/" + quote("model:model-0/table:model-0-t0/measure:model-0-t0-m1", safe=""))
        self.assertLess(seconds, 3.0)

    def test_review_opens_from_pages(self) -> None:
        # Finding 01: the queue was a 163 MB download; it is now counted on the server and read a page at a time.
        summary, seconds = self.timed("GET", "/api/review/page?grouping=pattern&rows=0")
        self.assertLess(seconds, 30.0)  # the first request builds the index of the graph state
        self.assertEqual(summary["matching"], 11528)
        self.assertLess(len(json.dumps(summary)), 100_000)
        page, seconds = self.timed("GET", "/api/review/page?section=standard&limit=25")
        self.assertLess(seconds, 1.0)
        self.assertEqual(len(page["items"]), 25)
        self.assertLess(len(json.dumps(page, ensure_ascii=False)), 100_000)
        biggest = max(summary["groups"], key=lambda group: group["count"])
        one, seconds = self.timed("GET", "/api/review/page?limit=25&pattern=" + quote(biggest["key"], safe=""))
        self.assertLess(seconds, 1.0)
        self.assertEqual(one["total"], biggest["count"])

    def test_search_and_whole_project_lineage(self) -> None:
        found, seconds = self.timed("GET", "/api/search?q=total%20orders&limit=50&kind=objects")
        self.assertLess(seconds, 5.0)
        self.assertLessEqual(len(found["items"]), 50)
        lineage, seconds = self.timed("GET", "/api/lineage")
        self.assertLess(seconds, 15.0)
        self.assertFalse(lineage.get("truncated"))
        self.assertLess(len(json.dumps(lineage)) / (len(lineage["nodes"]) + len(lineage["edges"])), 600)
        seen = {}
        environ = {"REQUEST_METHOD": "GET", "PATH_INFO": "/api/lineage", "QUERY_STRING": "", "HTTP_HOST": "127.0.0.1", "HTTP_ACCEPT_ENCODING": "gzip"}
        sent = b"".join(self.app(environ, lambda status, headers: seen.update(headers=dict(headers))))
        self.assertEqual("gzip", seen["headers"]["Content-Encoding"])
        self.assertLess(len(sent), 600_000, "the whole-project lineage transfers under 600 kB (review 04)")

    def test_zz_one_bulk_decision_over_every_suggestion_and_its_undo(self) -> None:
        # Last (by name): it changes the graph, which empties the answers the other tests may reuse.
        reply, seconds = self.timed("POST", "/api/review", {"action": "approve", "filter": {}, "reply": "summary"})
        self.assertLess(seconds, 20.0)  # measured 2 s; comparing every record with every identifier took minutes
        self.assertGreaterEqual(reply["result"]["count"], 11528)
        queue, _ = self.timed("GET", "/api/review")
        self.assertEqual(len(queue), 0)
        _, seconds = self.timed("POST", "/api/review", {"action": "undo", "token": reply["result"]["undo_token"], "reply": "summary"})
        self.assertLess(seconds, 20.0)
        queue, _ = self.timed("GET", "/api/review")
        self.assertEqual(len(queue), 11528)


if __name__ == "__main__":
    unittest.main()
