"""Report hierarchy, PBIR fields and Inspector agree on canonical objects."""
import copy
import tempfile
import unittest
from pathlib import Path

from backend.api.graph import get_graph
from backend.api.objects import inspect_object
from backend.api.review import approve, get_review_queue
from backend.graph.loader import build_fact_graph
from backend.graph.repository import GraphRepository


def hierarchy_sources():
    column = {"Column": {"Expression": {"SourceRef": {"Entity": "Sales"}}, "Property": "Region"}}
    measure = {"Measure": {"Expression": {"SourceRef": {"Entity": "Sales"}}, "Property": "Revenue"}}
    calculation = {"NativeVisualCalculation": {"Name": "Running revenue", "Expression": "RUNNINGSUM([Revenue])", "Language": "dax"}}
    filter_config = {"filters": [{"name": "opaque-filter", "field": column, "type": "Categorical"}]}
    model = {"id": "m", "name": "Finance", "tables": [{"id": "s", "name": "Sales", "columns": [{"id": "region", "name": "Region"}, *[{"id": f"unused-{i}", "name": f"Unused {i}"} for i in range(150)]], "measures": [{"id": "revenue", "name": "Revenue", "description": "Invoiced revenue", "expression": "1"}]}]}
    report = {"id": "r", "name": "Revenue report", "modelId": "m", "filterConfig": filter_config, "pages": [{"id": "p", "name": "Summary", "filterConfig": filter_config, "visuals": [{"id": "1234567890abcdef1234", "name": "1234567890abcdef1234", "filterConfig": filter_config, "visual": {"visualType": "lineChart", "visualContainerObjects": {"title": [{"properties": {"text": {"expr": {"Literal": {"Value": "'Revenue trend'"}}}}}]}, "query": {"queryState": {"Values": {"projections": [{"field": measure, "queryRef": "Revenue"}, {"field": column, "queryRef": "Sales.Region"}, {"field": calculation, "queryRef": "Running revenue"}]}}}}}]}]}
    return model, report


class ReportHierarchyTests(unittest.TestCase):
    def setUp(self):
        self.model, self.report = hierarchy_sources()
        self.graph = build_fact_graph(self.model, self.report)
        self.repository = GraphRepository(use_native=False)
        self.graph.load(self.repository)
        self.addCleanup(self.repository.close)

    def test_complete_hierarchy_and_pbir_metadata(self):
        by_type = {node.type: node for node in self.graph.nodes}
        visual = by_type["VISUAL"]
        self.assertEqual(visual.name, "Revenue trend")
        self.assertEqual(visual.properties["visual_type"], "lineChart")
        self.assertEqual(visual.properties["unresolved_field_refs"], [])
        calc = by_type["VISUAL_CALCULATION"]
        self.assertEqual(calc.properties["expression"], "RUNNINGSUM([Revenue])")
        links = {(edge.type, edge.from_id, edge.to_id) for edge in self.graph.edges}
        self.assertIn(("USES_MODEL", by_type["REPORT"].id, by_type["MODEL"].id), links)
        self.assertNotIn(("CONTAINS", by_type["MODEL"].id, by_type["REPORT"].id), links)
        for owner, child in (("REPORT", "PAGE"), ("PAGE", "VISUAL"), ("REPORT", "REPORT_FILTER"), ("PAGE", "PAGE_FILTER"), ("VISUAL", "VISUAL_FILTER"), ("VISUAL", "VISUAL_CALCULATION")):
            self.assertIn(("CONTAINS", by_type[owner].id, by_type[child].id), links)
        for kind in ("REPORT_FILTER", "PAGE_FILTER", "VISUAL_FILTER"):
            self.assertEqual(by_type[kind].name, "Region")
            self.assertIn(("FILTERS", by_type[kind].id, by_type[kind].properties["target_id"]), links)
        changed = copy.deepcopy(self.report)
        changed["pages"][0]["visuals"][0]["visual"]["visualContainerObjects"]["title"][0]["properties"]["text"]["expr"]["Literal"]["Value"] = "'New title'"
        renamed = next(node for node in build_fact_graph(self.model, changed).nodes if node.type == "VISUAL")
        self.assertEqual(renamed.id, visual.id)

    def test_report_scope_includes_only_bound_model_fields_and_inspector_agrees(self):
        visual = next(node for node in self.graph.nodes if node.type == "VISUAL")
        details = inspect_object(self.repository, visual.id)
        bindings = details["visual_bindings"]
        self.assertEqual({key: len(values) for key, values in bindings.items()}, {key: 1 for key in bindings})
        for options in ({"artifact": "report"}, {"report_id": visual.report_id}):
            result = get_graph(self.repository, **options)
            ids = {node["id"] for node in result["nodes"]}
            self.assertTrue(all(node["id"] in ids for group in bindings.values() for node in group))
            self.assertFalse(any(node["name"].startswith("Unused") for node in result["nodes"]))
            self.assertTrue(any(node["type"] == "MEASURE" and node["artifact_group"] == "model" for node in result["nodes"]))
        limited = get_graph(self.repository, limit=12)
        self.assertIn(visual.id, {node["id"] for node in limited["nodes"]})
        self.assertTrue(limited["truncated"])

    def test_calculation_query_alias_is_not_a_missing_model_field(self):
        report = copy.deepcopy(self.report)
        projections = report["pages"][0]["visuals"][0]["visual"]["query"]["queryState"]["Values"]["projections"]
        projections[-1]["queryRef"] = "visual-calculation-alias"
        projections.append({"queryRef": "Unknown model field"})
        graph = build_fact_graph(self.model, report)
        visual = next(node for node in graph.nodes if node.type == "VISUAL")
        self.assertEqual([item["reference"] for item in visual.properties["unresolved_field_refs"]], ["Unknown model field"])
        self.assertEqual(sum(node.type == "VISUAL_CALCULATION" for node in graph.nodes), 1)

    def test_native_reopen_preserves_visual_calculations_and_bindings(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "brain.lbug"
            with GraphRepository(path) as repository:
                self.graph.load(repository)
            with GraphRepository(path) as repository:
                visual = next(node for node in repository.all_nodes() if node.type == "VISUAL")
                self.assertEqual(inspect_object(repository, visual.id)["visual_bindings"]["calculations"][0]["name"], "Running revenue")

    def test_review_queue_explains_source_and_decisions_remove_only_suggestion(self):
        graph = build_fact_graph(self.model, self.report, analyze_dax=True)
        graph.load(self.repository)
        items = get_review_queue(self.repository)
        described = next(item for item in items if item["source"] == "description")
        self.assertIn("Invoiced revenue", described["reason"])
        self.assertTrue(described["assertion_type"])
        self.assertTrue(described["candidate_id"])
        identities = [(item["target_id"], item["assertion_type"], str(item["value"])) for item in items]
        self.assertEqual(len(identities), len(set(identities)))
        factual = {node.id: node.to_dict() for node in self.repository.all_nodes() if node.status == "factual"}
        approve(self.repository, described["candidate_id"])
        self.assertNotIn(described["id"], {item["id"] for item in get_review_queue(self.repository)})
        self.assertEqual(factual, {node.id: node.to_dict() for node in self.repository.all_nodes() if node.status == "factual"})


if __name__ == "__main__":
    unittest.main()
