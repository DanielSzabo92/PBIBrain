"""The review queue answered a page at a time (finding 01): rows, counts and patterns come from the server."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.api.app import create_app
from backend.api.review_page import ReviewIndex, is_low_evidence, item_impact
from backend.projects import ProjectService
from tests.fixtures.large_project import write_large_project


class ReviewPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        root = Path(cls.temporary.name) / "project"
        root.mkdir()
        config = write_large_project(root)
        cls.app = create_app(database_path=root / "brain.db", overrides_path=root / "overrides.json", use_sqlite=False)
        cls.app.project = ProjectService(config)
        status, _ = cls.app.handle("POST", "/api/scan")
        assert status == 200

    @classmethod
    def tearDownClass(cls) -> None:
        cls.app.close()
        cls.temporary.cleanup()

    def page(self, query: str = "") -> dict:
        status, answer = self.app.handle("GET", f"/api/review/page?{query}")
        self.assertEqual(status, 200, answer)
        return answer

    def test_a_page_is_small_and_counts_the_whole_queue(self) -> None:
        first = self.page("limit=30")
        self.assertEqual(len(first["items"]), 30)
        self.assertTrue(first["has_more"])
        self.assertGreater(first["matching"], 1000)
        self.assertEqual(first["matching"], first["standard_total"] + first["low_total"])
        self.assertLess(len(json.dumps(first, ensure_ascii=False)), 100_000, "a page carries its rows, not the project")
        targets = {item.get("target") or item.get("target_id") for item in first["items"]}
        self.assertTrue(targets <= {node["id"] for node in first["nodes"]}, "every row's object is in the page")
        second = self.page("limit=30&offset=30")
        self.assertFalse({item.get("key") or item["id"] for item in first["items"]} & {item.get("key") or item["id"] for item in second["items"]})
        confidences = [item.get("confidence") or 0 for item in first["items"] + second["items"]]
        self.assertEqual(confidences, sorted(confidences, reverse=True))

    def test_filters_patterns_and_sections_are_applied_on_the_server(self) -> None:
        whole = self.page("rows=0&grouping=pattern")
        self.assertNotIn("items", whole)
        groups = whole["groups"]
        self.assertEqual(sum(group["count"] for group in groups), whole["matching"])
        biggest = max((group for group in groups if group["bulk"]), key=lambda group: group["count"])
        one = self.page(f"pattern={biggest['key']}&limit=20")
        self.assertEqual(one["total"], biggest["count"])
        self.assertTrue(all(item["pattern"] == biggest["key"] for item in one["items"]))
        object_type = whole["facets"]["types"][0]
        typed = self.page(f"object_type={object_type}&limit=500")
        self.assertTrue(typed["items"])
        nodes = {node["id"]: node for node in typed["nodes"]}
        self.assertTrue(all(nodes[item.get("target") or item.get("target_id")]["type"] == object_type for item in typed["items"]))
        low = self.page("section=low&limit=10")
        self.assertEqual(low["total"], whole["low_total"])
        self.assertTrue(all(item["low_evidence"] for item in low["items"]))
        status, answer = self.app.handle("GET", "/api/review/page?sort=sideways")
        self.assertEqual(status, 400, answer)

    def test_a_bulk_decision_by_view_decides_what_the_page_shows(self) -> None:
        groups = self.page("rows=0&grouping=pattern")["groups"]
        small = min((group for group in groups if group["bulk"]), key=lambda group: group["count"])
        status, reply = self.app.handle("POST", "/api/review", {"action": "reject", "view": {"pattern": small["key"]}, "reply": "summary"})
        self.assertEqual(status, 200, reply)
        self.assertGreaterEqual(reply["result"]["count"], small["count"], "each suggestion writes at least one record")
        self.assertEqual(self.page(f"pattern={small['key']}")["total"], 0)
        after = self.page("tab=reviewed&limit=5")
        self.assertGreaterEqual(after["total"], small["count"])
        status, undone = self.app.handle("POST", "/api/review", {"action": "undo", "token": reply["result"]["undo_token"]})
        self.assertEqual(status, 200, undone)
        self.assertEqual(self.page(f"pattern={small['key']}")["total"], small["count"])
        status, refused = self.app.handle("POST", "/api/review", {"action": "approve", "view": {"colour": "red"}})
        self.assertEqual(status, 400, refused)


class ReviewRuleTests(unittest.TestCase):
    """The rules the page used to apply itself: low evidence and patterns."""

    def test_name_only_tautologies_are_low_evidence_whatever_the_quoting(self) -> None:
        node = {"id": "model:sales/table:Sales", "name": "Sales"}
        for value in ("Sales", " 'Sales' "):
            self.assertTrue(is_low_evidence({"target": node["id"], "value": value, "source": "object_name", "confidence": 0.3}, node))
        self.assertFalse(is_low_evidence({"target": node["id"], "value": "Transactions recorded from POS and web",
                                          "source": "description", "confidence": 0.96}, node))

    def test_an_alias_equal_to_the_name_is_low_evidence_and_conflicts_never_are(self) -> None:
        node = {"id": "model:sales/column:Revenue", "name": "Revenue"}
        self.assertTrue(is_low_evidence({"target": node["id"], "value": "Revenue", "evidence": [{"source": "object_name"}], "confidence": 0.97}, node))
        for issue in ("conflict", "stale"):
            self.assertFalse(is_low_evidence({"issue": issue, "target": "t1", "value": "t1"}, None))

    def test_impact_ranks_words_and_numbers(self) -> None:
        self.assertEqual([item_impact({"impact": word}) for word in ("critical", "high", "normal", "low")], [4, 3, 2, 1])
        self.assertEqual(item_impact({"properties": {"impact_score": {"score": 7}}}), 7)

    def test_patterns_group_by_rule_basis_and_type_and_conflicts_come_first(self) -> None:
        nodes = [{"id": "m1", "type": "MEASURE", "name": "Sales"}, {"id": "m2", "type": "MEASURE", "name": "Sales"}, {"id": "c1", "type": "COLUMN", "name": "Key"}]
        items = [
            {"id": "a", "target_id": "c1", "assertion_type": "BUSINESS_CONCEPT", "confidence": 0.3, "item": {"properties": {"candidate_source": "object_name"}}},
            {"id": "b", "target_id": "m1", "assertion_type": "ALIAS", "source": "description", "confidence": 0.97},
            {"id": "c", "target_id": "m2", "assertion_type": "ALIAS", "source": "description", "confidence": 0.9},
            {"id": "d", "target_id": "m1", "issue_type": "conflict"},
        ]
        index = ReviewIndex({"nodes": nodes, "edges": [], "review_items": items})
        groups = index.groups(index.matching())
        self.assertEqual([group["title"] for group in groups], ["Conflicts", "Other name from the description", "Meaning from the name"])
        self.assertFalse(groups[0]["bulk"])
        alias = groups[1]
        self.assertEqual((alias["scope"], alias["count"], alias["names"], alias["low"], alias["high"]), ("measures", 2, 1, 0.9, 0.97))


if __name__ == "__main__":
    unittest.main()
