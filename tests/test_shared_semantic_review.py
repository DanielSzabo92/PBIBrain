"""Independent decisions for targets linked to one canonical meaning."""

import tempfile
import unittest
from pathlib import Path

from backend.api.objects import inspect_object
from backend.api.review import OverrideStore, approve, reject, edit, get_review_queue
from backend.context.builder import build_context
from backend.graph.repository import GraphRepository
from backend.scanner.pipeline import Scanner


SOURCE = {"id": "shared-model", "name": "Shared", "tables": [{
    "id": "sales", "name": "Sales", "measures": [
        {"id": "a", "name": "Revenue", "expression": "1"},
        {"id": "b", "name": "Revenue", "expression": "2"},
    ],
}]}


class SharedSemanticReviewTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "brain.lbug"
        self.repository = GraphRepository(self.path)
        Scanner(repository=self.repository).scan(SOURCE)
        self.shared = next(n for n in self.repository.all_nodes() if n.properties.get("candidate_ids"))
        self.rows = [r for r in get_review_queue(self.repository) if r["value"] == "Revenue"]
        self.assertEqual(len(self.rows), 2)
        self.assertEqual(len({r["target_id"] for r in self.rows}), 2)

    def tearDown(self):
        self.repository.close()
        self.directory.cleanup()

    def semantic(self, target, store=None):
        return next(r for r in inspect_object(self.repository, target, store=store)["semantics"]
                    if r["type"] == "BUSINESS_CONCEPT")

    def test_approve_reject_reopen_and_rescan_keep_decisions_independent(self):
        a, b = self.rows
        facts = [n.to_dict() for n in self.repository.all_nodes() if n.status == "factual"]
        approve(self.repository, a["candidate_id"])
        pending = [r for r in get_review_queue(self.repository) if r["value"] == "Revenue"]
        self.assertEqual([r["candidate_id"] for r in pending], [b["candidate_id"]])
        self.assertEqual(self.semantic(a["target_id"])["status"], "approved")
        self.assertEqual(self.semantic(b["target_id"])["status"], "candidate")
        reject(self.repository, b["candidate_id"])
        self.repository.close()
        self.repository = GraphRepository(self.path)
        Scanner(repository=self.repository).scan(SOURCE)
        self.assertFalse([r for r in get_review_queue(self.repository) if r["value"] == "Revenue"])
        self.assertEqual(self.semantic(a["target_id"])["status"], "approved")
        self.assertEqual(self.semantic(b["target_id"])["status"], "rejected")
        assertions = inspect_object(self.repository, self.shared.id)["semantics"]
        self.assertEqual(len(assertions), 2)
        self.assertEqual({r["status"] for r in assertions}, {"approved", "rejected"})
        self.assertEqual([n.to_dict() for n in self.repository.all_nodes() if n.status == "factual"], facts)
        self.assertEqual(len([n for n in self.repository.all_nodes() if n.name == "Revenue" and n.type == "BUSINESS_CONCEPT"]), 1)

    def test_edit_is_local_in_queue_inspector_and_agent_context(self):
        # Exercise the original primary ID and the additional ID separately.
        for row in self.rows:
            with self.subTest(candidate=row["candidate_id"]):
                store = OverrideStore(Path(self.directory.name) / f"{row['candidate_id'].rsplit(':', 1)[-1]}.json")
                edit(self.repository, row["candidate_id"], {"meaning": "Reviewed revenue"}, store=store)
                other = next(r for r in self.rows if r != row)
                pending = [r for r in get_review_queue(self.repository, store) if r["value"] == "Revenue"]
                self.assertEqual([r["candidate_id"] for r in pending], [other["candidate_id"]])
                self.assertEqual(self.semantic(row["target_id"], store)["meaning"], "Reviewed revenue")
                self.assertEqual(self.semantic(other["target_id"], store)["status"], "candidate")
                context = build_context(self.repository, row["target_id"], store=store)
                assertion = next(r for r in context["semantics"] if r.get("properties", {}).get("candidate_id") == row["candidate_id"])
                self.assertEqual(assertion["meaning"], "Reviewed revenue")
                self.assertEqual(assertion["semantic_node"]["status"], "overridden")
                store.remove(row["candidate_id"])
                self.assertEqual(len([r for r in get_review_queue(self.repository, store) if r["value"] == "Revenue"]), 2)

    def test_shared_identity_cannot_approve_every_target(self):
        with self.assertRaisesRegex(ValueError, "individual suggestion"):
            approve(self.repository, self.shared.id)
        self.assertEqual(len([r for r in get_review_queue(self.repository) if r["value"] == "Revenue"]), 2)


if __name__ == "__main__":
    unittest.main()
