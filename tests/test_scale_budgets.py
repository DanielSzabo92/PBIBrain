"""Scale gate (adversarial review 22): the read routes the screens open with stay fast and small.

The fixture is the 660-object project of the MCP budget tests, so the suite stays quick; the budgets
are several times the measured values and catch a route that starts to scan or ship the whole graph.
"""

from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path

from backend.graph.repository import GraphRepository
from backend.mcp_snapshot import SnapshotClient
from backend.projects import ProjectService
from tests.fixtures.large_project import write_large_project


class ScaleBudgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        config = write_large_project(Path(cls.temporary.name))
        with GraphRepository(use_native=False) as repository:
            ProjectService(config).scan(repository)
        cls.client = SnapshotClient(config)
        cls.client.get("overview")  # the first read loads the project; budgets are for a loaded one

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def timed(self, path: str, **params):
        started = time.perf_counter()
        reply = self.client.get(path, **params)
        return reply, time.perf_counter() - started, len(json.dumps(reply, ensure_ascii=False))

    def test_overview_is_quick_and_small(self) -> None:
        reply, seconds, size = self.timed("overview")
        self.assertLess(seconds, 1.0)
        self.assertLess(size, 200_000)
        self.assertEqual(len(reply["top_measures"]), 5)
        hot = [item["target_id"] for item in reply["hot_unreviewed"]]
        self.assertEqual(len(hot), len(set(hot)), "one row per hot object")

    def test_search_answers_within_budget_and_pages(self) -> None:
        reply, seconds, size = self.timed("search", q="Measure 3", limit=50, kind="objects")
        self.assertLess(seconds, 1.5)
        self.assertLess(size, 400_000)
        self.assertLessEqual(len(reply["items"]), 50)
        self.assertFalse(any(item["id"].startswith("semantic:") for item in reply["items"]))

    def test_lineage_ships_every_object_without_formulas(self) -> None:
        started = time.perf_counter()
        status, reply = self.client.app.handle("GET", "/api/lineage")
        seconds, size = time.perf_counter() - started, len(json.dumps(reply, ensure_ascii=False))
        self.assertEqual(status, 200)
        self.assertLess(seconds, 3.0)
        self.assertFalse(reply.get("truncated"))
        per_node = size / max(1, len(reply["nodes"]) + len(reply["edges"]))
        self.assertLess(per_node, 600, "the compact payload carries no formulas or evidence")


if __name__ == "__main__":
    unittest.main()
