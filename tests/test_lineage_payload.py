import unittest

from backend.api.graph import get_graph, get_lineage
from backend.graph.loader import build_fact_graph
from backend.graph.repository import GraphRepository
from tests.test_report_hierarchy import hierarchy_sources


class LineagePayloadTests(unittest.TestCase):
    def setUp(self):
        model, report = hierarchy_sources()
        self.repository = GraphRepository(use_native=False)
        build_fact_graph(model, report).load(self.repository)
        self.addCleanup(self.repository.close)

    def test_whole_scope_without_an_object_limit_in_compact_form(self):
        result = get_lineage(self.repository)
        full = get_graph(self.repository, status="factual")
        self.assertFalse(result["truncated"])
        self.assertEqual({node["id"] for node in result["nodes"]}, {node["id"] for node in full["nodes"]})
        self.assertGreater(len(result["nodes"]), 150, "more objects than one limited page of the graph")
        for node in result["nodes"]:
            self.assertNotIn("raw_source", node)
            self.assertNotIn("dax_ast", node)
            self.assertTrue({"id", "type", "name"} <= set(node))
        visual = next(node for node in result["nodes"] if node["type"] == "VISUAL")
        self.assertIn("parent_id", visual)
        self.assertIn("definition_hash", visual)
        self.assertTrue({edge["type"] for edge in result["edges"]} <= {"CONTAINS", "BELONGS_TO", "HAS_OPTION", "DEPENDS_ON", "REFERENCES", "USES", "USES_MODEL", "FILTERS",
                                                                       "MODIFIES_FILTER", "CONTROLLED_BY", "ACTIVATES_RELATIONSHIP", "MODIFIES_RELATIONSHIP"})

    def test_report_scope(self):
        visual = next(node for node in get_lineage(self.repository)["nodes"] if node["type"] == "VISUAL")
        scoped = get_lineage(self.repository, report_id=visual["report_id"])
        self.assertFalse(any(node["name"].startswith("Unused") for node in scoped["nodes"]))


if __name__ == "__main__":
    unittest.main()
