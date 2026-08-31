"""Phase 1 contract tests that do not need a graph backend."""

import unittest

from backend.graph.schema import (
    EDGE_TYPES,
    EVIDENCE_CLASSES,
    OBJECT_TYPES,
    STATUS_VALUES,
    Edge,
    Node,
    serialize_edges,
    serialize_nodes,
)


V1_OBJECT_TYPES = {
    "MODEL",
    "TABLE",
    "COLUMN",
    "MEASURE",
    "RELATIONSHIP",
    "FIELD_PARAMETER",
    "SHARED_EXPRESSION",
    "USER_DEFINED_FUNCTION",
    "CALCULATION_GROUP",
    "CALCULATION_ITEM",
    "REPORT",
    "PAGE",
    "VISUAL",
    "VISUAL_FILTER",
    "PAGE_FILTER",
    "REPORT_FILTER",
    "BUSINESS_CONCEPT",
    "SELECTOR",
    "SELECTOR_OPTION",
}

V1_EDGE_TYPES = {
    "CONTAINS",
    "BELONGS_TO",
    "DEPENDS_ON",
    "REFERENCES",
    "USES",
    "RELATES_TO",
    "FILTERS",
    "USES_MODEL",
    "CONTROLLED_BY",
    "HAS_OPTION",
    "DEFAULTS_TO",
    "SEMANTICALLY_MAPS_TO",
    "SIMILAR_TO",
    "OBSERVED_WITH",
}


class SchemaContractTests(unittest.TestCase):
    def test_object_and_edge_ontologies_cover_v1(self):
        self.assertTrue(V1_OBJECT_TYPES <= OBJECT_TYPES)
        self.assertTrue(V1_EDGE_TYPES <= EDGE_TYPES)
        self.assertTrue({"FACT", "INFERRED", "OBSERVED"} <= EVIDENCE_CLASSES)
        self.assertTrue({"factual", "candidate", "approved", "rejected", "overridden"} <= STATUS_VALUES)

    def test_node_exposes_universal_contract_and_object_properties(self):
        node = Node(
            id="model:m1/table:t1",
            type="TABLE",
            name="Sales",
            description="Invoice facts.",
            model_id="model:m1",
            report_id=None,
            source_id="t1",
            properties={"hidden": False, "row_count": 3},
        )

        value = node.to_dict()
        self.assertEqual(
            {
                "id",
                "type",
                "name",
                "description",
                "model_id",
                "report_id",
                "source_id",
                "status",
            } <= value.keys(),
            True,
        )
        self.assertEqual(value["status"], "factual")
        self.assertEqual(value["hidden"], False)
        self.assertEqual(value["properties"]["row_count"], 3)
        self.assertEqual(node["id"], "model:m1/table:t1")

    def test_edge_exposes_universal_contract_and_fact_class(self):
        edge = Edge(
            id="edge:e1",
            type="CONTAINS",
            from_id="model:m1",
            to_id="model:m1/table:t1",
            source="model_metadata",
            evidence=["source table membership"],
        )

        value = edge.to_dict()
        self.assertEqual(
            {
                "id",
                "type",
                "from_id",
                "to_id",
                "source",
                "confidence",
                "status",
                "evidence",
            } <= value.keys(),
            True,
        )
        self.assertEqual(value["status"], "factual")
        self.assertEqual(value["evidence_class"], "FACT")
        self.assertEqual(value["evidence"], ["source table membership"])

    def test_invalid_lifecycle_values_are_rejected(self):
        with self.assertRaises(ValueError):
            Node(id="n", type="TABLE", status="guess")
        with self.assertRaises(ValueError):
            Edge(id="e", type="USES", from_id="a", to_id="b", confidence=1.1)
        with self.assertRaises(ValueError):
            Edge(id="e", type="USES", from_id="a", to_id="b", evidence_class="guess")

    def test_serialization_is_sorted_by_stable_id(self):
        nodes = [
            Node(id="model:m/table:z", type="TABLE"),
            Node(id="model:m/table:a", type="TABLE"),
        ]
        edges = [
            Edge(id="edge:z", type="CONTAINS", from_id="m", to_id="z"),
            Edge(id="edge:a", type="CONTAINS", from_id="m", to_id="a"),
        ]

        self.assertEqual([item["id"] for item in serialize_nodes(nodes)], ["model:m/table:a", "model:m/table:z"])
        self.assertEqual([item["id"] for item in serialize_edges(edges)], ["edge:a", "edge:z"])


if __name__ == "__main__":
    unittest.main()

