"""Agent retrieval quality contracts."""

from __future__ import annotations

import unittest

from backend.api.objects import search_objects
from backend.api.retrieval import resolve_object, retrieve_objects
from backend.context import get_context
from backend.graph.repository import GraphRepository
from backend.graph.schema import Edge, Node


MODEL_A = "model:finance"
MODEL_B = "model:sales"
REPORT_A = "report:finance"


def _nodes() -> list[Node]:
    return [
        Node(MODEL_A, "MODEL", "Finance"),
        Node(MODEL_B, "MODEL", "Sales"),
        Node(REPORT_A, "REPORT", "Finance report", model_id=MODEL_A),
        Node(
            f"{MODEL_A}/measure:revenue",
            "MEASURE",
            "Revenue",
            model_id=MODEL_A,
            source_id="revenue",
            properties={"raw_source": {"description": "Net booked sales"}},
        ),
        Node(
            f"{MODEL_B}/measure:revenue",
            "MEASURE",
            "Revenue",
            model_id=MODEL_B,
            source_id="revenue",
        ),
        Node(
            f"{MODEL_A}/measure:revenue-growth",
            "MEASURE",
            "Revenue Growth",
            model_id=MODEL_A,
            source_id="revenue-growth",
        ),
        Node(
            f"{MODEL_A}/measure:margin",
            "MEASURE",
            "Margin",
            model_id=MODEL_A,
            source_id="margin",
            description="Margin calculated from revenue",
        ),
    ]


class RetrievalQualityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = GraphRepository(use_native=False)
        self.repository.replace(
            _nodes(),
            [
                Edge("edge:report-model", "USES_MODEL", REPORT_A, MODEL_A, evidence=["report model binding"]),
            ],
        )

    def tearDown(self) -> None:
        self.repository.close()

    def test_ranking_prefers_exact_identity_then_prefix_then_description(self) -> None:
        result = retrieve_objects(self.repository, "Revenue", object_type="measure")
        items = result["items"]
        self.assertEqual(
            [item["name"] for item in items],
            ["Revenue", "Revenue", "Revenue Growth", "Margin"],
        )
        self.assertTrue(all(item["match"]["evidence"] for item in items))
        self.assertTrue(all("properties" not in item for item in items))
        self.assertEqual(items[0]["match"]["kind"], "exact_source_id")
        self.assertGreater(items[1]["match"]["score"], items[2]["match"]["score"])
        self.assertGreater(items[2]["match"]["score"], items[3]["match"]["score"])

    def test_duplicate_names_are_ambiguous_until_scoped(self) -> None:
        unscoped = retrieve_objects(self.repository, "Revenue", object_type="MEASURE")
        self.assertEqual(unscoped["ambiguity"]["reason"], "duplicate_exact_name_across_scopes")
        self.assertEqual(len(unscoped["ambiguity"]["candidate_ids"]), 2)
        self.assertEqual(resolve_object(self.repository, "Revenue")["status"], "ambiguous")

        scoped = resolve_object(self.repository, "Revenue", model_id=MODEL_A)
        self.assertEqual(scoped["status"], "resolved")
        self.assertEqual(scoped["object"]["id"], f"{MODEL_A}/measure:revenue")

    def test_canonical_id_resolution_is_safe_despite_duplicate_source_ids(self) -> None:
        identifier = f"{MODEL_B}/measure:revenue"
        result = resolve_object(self.repository, identifier)
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["object"]["id"], identifier)
        self.assertEqual(result["match"]["kind"], "exact_id")

    def test_pagination_reports_exact_total_and_next_offset(self) -> None:
        first = retrieve_objects(self.repository, "", object_type="MEASURE", limit=2, offset=0)
        self.assertEqual(first["total"], 4)
        self.assertEqual(first["pagination"]["total"], 4)
        self.assertEqual(first["pagination"]["returned"], 2)
        self.assertTrue(first["has_more"])
        self.assertEqual(first["next_offset"], 2)

        last = retrieve_objects(self.repository, "", object_type="MEASURE", limit=2, offset=2)
        self.assertEqual(last["pagination"]["returned"], 2)
        self.assertFalse(last["has_more"])
        self.assertIsNone(last["next_offset"])
        first_ids = {item["id"] for item in first["items"]}
        last_ids = {item["id"] for item in last["items"]}
        self.assertFalse(first_ids & last_ids)

    def test_scope_is_case_normalized(self) -> None:
        result = retrieve_objects(
            self.repository,
            "Revenue",
            object_type="measure",
            status="FACTUAL",
            model_id=MODEL_B,
        )
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["id"], f"{MODEL_B}/measure:revenue")

    def test_invalid_pagination_and_scope_are_rejected(self) -> None:
        invalid = (
            {"limit": 0},
            {"limit": 101},
            {"limit": True},
            {"offset": -1},
            {"offset": "0"},
            {"model_id": []},
        )
        for kwargs in invalid:
            with self.subTest(kwargs=kwargs), self.assertRaises((TypeError, ValueError)):
                retrieve_objects(self.repository, "Revenue", **kwargs)

    def test_legacy_search_keeps_list_shape_but_uses_ranked_order(self) -> None:
        results = search_objects(self.repository, "Revenue", object_type="MEASURE")
        self.assertIsInstance(results, list)
        self.assertEqual([item["name"] for item in results[:3]], ["Revenue", "Revenue", "Revenue Growth"])

    def test_context_scope_contains_target_ids_and_evidence_has_subject(self) -> None:
        report_context = get_context(self.repository, REPORT_A, task="lineage")
        self.assertIn(REPORT_A, report_context["scope"]["report_ids"])
        self.assertIn(MODEL_A, report_context["scope"]["model_ids"])
        self.assertTrue(report_context["evidence"])
        record = report_context["evidence"][0]
        self.assertEqual(record["subject_kind"], "edge")
        self.assertEqual(record["subject_id"], "edge:report-model")
        self.assertEqual(record["value"], "report model binding")

        model_context = get_context(self.repository, MODEL_B, task="lineage")
        self.assertIn(MODEL_B, model_context["scope"]["model_ids"])


if __name__ == "__main__":
    unittest.main()
