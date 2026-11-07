"""Usage roles (#11): field-well role on USES edges, report links and the derived usage profile."""
import json
import tempfile
import unittest
from pathlib import Path

from backend.api.graph import get_lineage
from backend.api.objects import inspect_object
from backend.context.builder import build_context
from backend.context.schema import validate_context
from backend.graph.loader import build_fact_graph
from backend.graph.repository import GraphRepository
from backend.inference.usage_roles import usage_profile
from backend.validation.graph import validate_graph_integrity


def _column(table, name):
    return {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}}


def _measure(table, name):
    return {"Measure": {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}}


def _literal(text):
    return {"expr": {"Literal": {"Value": f"'{text}'"}}}


def _visual(name, visual_type, query_state, **extra):
    return {"id": name, "name": name, "visual": {"visualType": visual_type, "query": {"queryState": query_state}, **extra}}


def usage_sources():
    model = {"id": "m", "name": "Sales model", "tables": [
        {"id": "sales", "name": "Sales", "columns": [{"id": "amount", "name": "Amount"}],
         "measures": [{"id": "revenue", "name": "Revenue", "expression": "SUM(Sales[Amount])"},
                      {"id": "margin", "name": "Margin", "expression": "1"},
                      {"id": "target", "name": "Target", "expression": "1"},
                      {"id": "unused", "name": "Unused", "expression": "1"}]},
        {"id": "product", "name": "Product", "columns": [{"id": "category", "name": "Category"},
                                                         {"id": "color", "name": "Color"}]},
        {"id": "date", "name": "Date", "columns": [{"id": "year", "name": "Year"}]},
    ]}
    bar = _visual("bar", "clusteredBarChart", {
        "Category": {"projections": [{"field": _column("Product", "Category"), "queryRef": "Product.Category"}]},
        "Y": {"projections": [{"field": _measure("Sales", "Revenue"), "queryRef": "Sales.Revenue"},
                              {"field": {"Aggregation": {"Expression": _column("Sales", "Amount"), "Function": 0}},
                               "queryRef": "Sum(Sales.Amount)"}]},
        "Tooltips": {"projections": [{"field": _measure("Sales", "Margin"), "queryRef": "Sales.Margin"}]},
    }, objects={"dataPoint": [{"properties": {"fill": {"solid": {"color": {"expr": _measure("Sales", "Target")}}}}}]},
        visualContainerObjects={"visualTooltip": [{"properties": {"type": _literal("ReportPage"), "section": _literal("tip")}}]})
    bar["visual"]["query"]["sortDefinition"] = {"sort": [{"field": _measure("Sales", "Revenue"), "direction": "Descending"}]}
    card = _visual("card", "card", {"Values": {"projections": [{"field": _measure("Sales", "Revenue"), "queryRef": "Sales.Revenue"}]}})
    slicer_a = _visual("slicerA", "slicer", {"Values": {"projections": [{"field": _column("Date", "Year"), "queryRef": "Date.Year"}]}},
                       syncGroup={"groupName": "Year", "fieldChanges": True, "filterChanges": True})
    slicer_b = _visual("slicerB", "slicer", {"Values": {"projections": [{"field": _column("Date", "Year"), "queryRef": "Date.Year"}]}},
                       syncGroup={"groupName": "Year", "fieldChanges": True, "filterChanges": True})
    button = {"id": "go", "name": "go", "visual": {"visualType": "actionButton", "visualContainerObjects": {
        "visualLink": [{"properties": {"show": {"expr": {"Literal": {"Value": "true"}}}, "type": _literal("Drillthrough"),
                                       "drillthroughSection": _literal("detail")}}]}}}
    detail_table = _visual("detailtable", "tableEx", {"Values": {"projections": [
        {"field": _column("Product", "Color"), "queryRef": "Product.Color"}]}})
    tip_card = _visual("tipcard", "card", {"Values": {"projections": [{"field": _measure("Sales", "Margin"), "queryRef": "Sales.Margin"}]}})
    report = {"id": "r", "name": "Sales report", "modelId": "m", "pages": [
        {"id": "overview", "name": "overview", "displayName": "Overview", "visuals": [bar, card, slicer_a, button],
         "visualInteractions": [{"source": "slicerA", "target": "bar", "type": "NoFilter"},
                                {"source": "bar", "target": "card", "type": "HighlightFilter"}]},
        {"id": "detail", "name": "detail", "displayName": "Product detail", "type": "Drillthrough", "visibility": "HiddenInViewMode",
         "pageBinding": {"name": "b1", "type": "Drillthrough", "parameters": [
             {"name": "p1", "boundFilter": "f1", "fieldExpr": _column("Product", "Category")}]},
         "visuals": [detail_table, slicer_b]},
        {"id": "tip", "name": "tip", "displayName": "Margin tip", "type": "Tooltip",
         "pageBinding": {"name": "b2", "type": "Tooltip"}, "visuals": [tip_card]},
    ]}
    return model, report


class UsageRoleTests(unittest.TestCase):
    def setUp(self):
        self.model, self.report = usage_sources()
        self.graph = build_fact_graph(self.model, self.report)
        self.nodes = {node.id: node for node in self.graph.nodes}
        self.repository = GraphRepository(use_native=False)
        self.graph.load(self.repository)
        self.addCleanup(self.repository.close)

    def _id(self, node_type, name):
        return next(node.id for node in self.graph.nodes if node.type == node_type and (node.name == name or node.source_id == name))

    def _edges(self, edge_type):
        return [edge for edge in self.graph.edges if edge.type == edge_type]

    def test_measure_on_bar_y_and_card_has_two_uses_edges_with_roles(self):
        revenue = self._id("MEASURE", "Revenue")
        uses = {self.nodes[edge.from_id].source_id: edge for edge in self._edges("USES") if edge.to_id == revenue}
        self.assertEqual(set(uses), {"bar", "card"})
        self.assertEqual(uses["bar"].properties["role"], "value")
        self.assertEqual(uses["bar"].properties["projection"], "Y")
        self.assertEqual(uses["bar"].properties["visual_type"], "clusteredBarChart")
        self.assertEqual(uses["bar"].properties["sort_direction"], "Descending")
        self.assertEqual([item["role"] for item in uses["bar"].properties["roles"]], ["value", "sort"])
        self.assertEqual(uses["card"].properties["role"], "value")
        self.assertEqual(uses["card"].properties["visual_type"], "card")
        amount = next(edge for edge in self._edges("USES") if edge.to_id == self._id("COLUMN", "Amount"))
        self.assertEqual(amount.properties["aggregation"], "Sum")
        category = next(edge for edge in self._edges("USES") if edge.to_id == self._id("COLUMN", "Category") and self.nodes[edge.from_id].type == "VISUAL")
        self.assertEqual(category.properties["role"], "category")
        margin = next(edge for edge in self._edges("USES") if edge.to_id == self._id("MEASURE", "Margin") and self.nodes[edge.from_id].source_id == "bar")
        self.assertEqual(margin.properties["role"], "tooltip")
        year = {edge.properties["role"] for edge in self._edges("USES") if edge.to_id == self._id("COLUMN", "Year")}
        self.assertEqual(year, {"slicer_field"})

    def test_report_links_are_traversable_facts(self):
        bar, card, slicer_a, slicer_b, go = (self._id("VISUAL", name) for name in ("bar", "card", "slicerA", "slicerB", "go"))
        detail, tip = self._id("PAGE", "detail"), self._id("PAGE", "tip")
        links = {(edge.type, edge.from_id, edge.to_id): edge for edge in self.graph.edges}
        self.assertEqual(links[("DRILLS_THROUGH_TO", bar, detail)].properties["via"], "field")
        self.assertEqual(links[("DRILLS_THROUGH_TO", bar, detail)].properties["matched_field_ids"], [self._id("COLUMN", "Category")])
        self.assertEqual(links[("DRILLS_THROUGH_TO", go, detail)].properties["via"], "button")
        self.assertNotIn(("DRILLS_THROUGH_TO", card, detail), links)
        self.assertIn(("TOOLTIP_PAGE", bar, tip), links)
        self.assertEqual(links[("INTERACTS_WITH", slicer_a, bar)].properties["interaction"], "none")
        self.assertEqual(links[("INTERACTS_WITH", bar, card)].properties["interaction"], "highlight")
        synced = links[("SYNCED_WITH", *sorted((slicer_a, slicer_b)))]
        self.assertEqual(synced.properties["group_name"], "Year")
        self.assertIn(("FORMATS_BY", bar, self._id("MEASURE", "Target")), links)
        drill_field = links[("USES", detail, self._id("COLUMN", "Category"))]
        self.assertEqual(drill_field.properties["role"], "drillthrough_field")
        self.assertEqual(self.nodes[detail].properties["page_type"], "Drillthrough")
        self.assertTrue(self.nodes[detail].properties["hidden"])
        self.assertTrue(all(edge.evidence_class == "FACT" and edge.status == "factual" for edge in self.graph.edges
                            if edge.type in {"DRILLS_THROUGH_TO", "TOOLTIP_PAGE", "INTERACTS_WITH", "SYNCED_WITH", "FORMATS_BY"}))
        issues = [issue for issue in validate_graph_integrity(self.graph.to_dict()).issues if issue.severity == "ERROR"]
        self.assertEqual(issues, [])

    def test_usage_profile_facts_are_inferred(self):
        edges = self.graph.edges
        revenue = usage_profile(self.nodes, edges, self._id("MEASURE", "Revenue"))
        self.assertEqual(revenue["evidence_class"], "INFERRED")
        self.assertEqual(revenue["visual_count"], 2)
        codes = {item["code"]: item for item in revenue["facts"]}
        self.assertEqual(codes["KPI_VALUE"]["text"], "Used as KPI value on 1 card or KPI visual")
        year = {item["code"] for item in usage_profile(self.nodes, edges, self._id("COLUMN", "Year"))["facts"]}
        self.assertIn("SLICER_DIMENSION", year)
        color = {item["code"] for item in usage_profile(self.nodes, edges, self._id("COLUMN", "Color"))["facts"]}
        self.assertIn("ONLY_HIDDEN_PAGES", color)
        category = {item["code"] for item in usage_profile(self.nodes, edges, self._id("COLUMN", "Category"))["facts"]}
        self.assertIn("DRILLTHROUGH_FIELD", category)
        target = {item["code"] for item in usage_profile(self.nodes, edges, self._id("MEASURE", "Target"))["facts"]}
        self.assertIn("FORMATTING_OR_SORT_ONLY", target)
        unused = [item["code"] for item in usage_profile(self.nodes, edges, self._id("MEASURE", "Unused"))["facts"]]
        self.assertEqual(unused, ["UNUSED_IN_REPORTS"])
        page = usage_profile(self.nodes, edges, self._id("PAGE", "detail"))
        self.assertEqual({item["visual_id"] for item in page["incoming_links"]}, {self._id("VISUAL", "bar"), self._id("VISUAL", "go")})

    def test_brain_context_and_inspector_return_the_role_summary(self):
        revenue = self._id("MEASURE", "Revenue")
        context = build_context(self.repository, revenue)
        self.assertEqual(validate_context(context), [])
        self.assertEqual(context["usage_roles"]["roles"][0]["role"], "value")
        roles = {edge["properties"].get("role") for edge in context["usage"] if edge["type"] == "USES" and edge["to_id"] == revenue}
        self.assertEqual(roles, {"value"})
        bar = self._id("VISUAL", "bar")
        visual = build_context(self.repository, bar)
        self.assertIn("DRILLS_THROUGH_TO", {edge["type"] for edge in visual["usage"]})
        self.assertIn("TOOLTIP_PAGE", {link["type"] for link in visual["usage_roles"]["links"]})
        lineage = build_context(self.repository, revenue, "lineage")
        self.assertNotIn("usage_roles", lineage)
        details = inspect_object(self.repository, revenue)
        self.assertEqual(details["usage_roles"]["visual_count"], 2)
        lineage_payload = get_lineage(self.repository, model_id=self.nodes[revenue].model_id)
        self.assertIn("value", {edge.get("role") for edge in lineage_payload["edges"] if edge["to_id"] == revenue})

    def test_pbip_page_and_visual_files_carry_roles_and_links(self):
        with tempfile.TemporaryDirectory() as folder:
            report = Path(folder) / "Sales.Report"
            pages = report / "definition" / "pages"
            for page in self.report["pages"]:
                page_dir = pages / page["id"]
                (page_dir / "visuals").mkdir(parents=True)
                payload = {key: value for key, value in page.items() if key not in {"id", "visuals"}}
                (page_dir / "page.json").write_text(json.dumps(payload), encoding="utf-8")
                for visual in page["visuals"]:
                    (page_dir / "visuals" / visual["name"]).mkdir()
                    (page_dir / "visuals" / visual["name"] / "visual.json").write_text(
                        json.dumps({key: value for key, value in visual.items() if key != "id"}), encoding="utf-8")
            (pages / "pages.json").write_text(json.dumps({"pageOrder": ["overview", "detail", "tip"]}), encoding="utf-8")
            from backend.scanner.pbip import _read_report

            read = _read_report(report, {}, Path(folder))
            scanned = build_fact_graph(self.model, {**read, "model_id": "m"})
        types = {edge.type for edge in scanned.edges}
        self.assertTrue({"DRILLS_THROUGH_TO", "TOOLTIP_PAGE", "INTERACTS_WITH", "SYNCED_WITH", "FORMATS_BY"} <= types)


class LegacyUsageRoleTests(unittest.TestCase):
    def test_legacy_projections_map_query_refs_to_roles(self):
        model = {"id": "m", "name": "M", "tables": [{"id": "s", "name": "Sales", "columns": [{"id": "c", "name": "Region"}],
                                                      "measures": [{"id": "v", "name": "Revenue", "expression": "1"}]}]}
        config = {"name": "legacy", "singleVisual": {
            "visualType": "columnChart",
            "projections": {"Category": [{"queryRef": "Sales.Region"}], "Y": [{"queryRef": "Sales.Revenue"}]},
            "prototypeQuery": {"From": [{"Name": "s", "Entity": "Sales"}], "Select": [
                {"Column": {"Expression": {"SourceRef": {"Source": "s"}}, "Property": "Region"}, "Name": "Sales.Region"},
                {"Measure": {"Expression": {"SourceRef": {"Source": "s"}}, "Property": "Revenue"}, "Name": "Sales.Revenue"}],
                "OrderBy": [{"Direction": 2, "Expression": {"Measure": {"Expression": {"SourceRef": {"Source": "s"}}, "Property": "Revenue"}}}]}}}
        report = {"id": "r", "name": "R", "modelId": "m", "sections": [{"name": "s1", "displayName": "Page",
                                                                         "visualContainers": [{"config": json.dumps(config)}]}]}
        graph = build_fact_graph(model, report)
        roles = {edge.to_id.rsplit("/", 1)[-1]: edge.properties for edge in graph.edges if edge.type == "USES"}
        by_name = {node.id: node.name for node in graph.nodes}
        named = {by_name[edge.to_id]: edge.properties for edge in graph.edges if edge.type == "USES"}
        self.assertTrue(roles)
        self.assertEqual(named["Region"]["role"], "category")
        self.assertEqual(named["Revenue"]["role"], "value")
        self.assertEqual(named["Revenue"]["sort_direction"], "Descending")


if __name__ == "__main__":
    unittest.main()
