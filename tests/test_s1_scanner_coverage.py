"""S1 scanner coverage: version 1 object types, new impact links, PBIR positions."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from backend.adapters.tabular_metadata import TabularMetadataAdapter
from backend.dax.analyzer import DaxAnalyzer
from backend.dax.parser import DaxSyntaxError, parse_dax_function
from backend.graph.loader import build_fact_graph
from backend.graph.migrations import migrate_payload
from backend.graph.repository import GraphRepository
from backend.graph.schema import GRAPH_SCHEMA_VERSION, OBJECT_TYPES, Node
from backend.impact.analyzer import analyze_impact
from backend.snapshots.scan import scan_snapshot

REPOSITORY = Path(__file__).resolve().parents[1]
LAB = REPOSITORY / "tests" / "fixtures" / "merge_lab"
EXPECTED = json.loads((LAB / "EXPECTED.json").read_text(encoding="utf-8"))
BRIDGE = REPOSITORY / "backend/adapters/tabular_metadata/dotnet/bin/Release/net8.0/TabularMetadata.dll"
NEW_TYPES = {"HIERARCHY", "LEVEL", "SECURITY_ROLE", "ROLE_FILTER", "OLS_PERMISSION", "REPORT_MEASURE", "PARTITION", "SHARED_EXPRESSION", "BOOKMARK"}


def as_tmsl(project: str, target: Path) -> Path:
    """Copy a merge lab project and replace its TMDL folder with a TMSL model.bim."""

    shutil.copytree(LAB / project, target / project)
    folder = target / project / (project + ".SemanticModel")
    database = TabularMetadataAdapter().read(folder / "definition")["database"]
    for table in database["model"]["tables"]:
        for column in table.get("columns", []):
            # The TOM JSON reader refuses relatedColumnDetails (see tools/build_merge_lab.py).
            column.pop("relatedColumnDetails", None)
    shutil.rmtree(folder / "definition")
    (folder / "model.bim").write_text(json.dumps(database, indent=2), encoding="utf-8")
    return target / project


class Graph:
    def __init__(self, result: dict) -> None:
        self.nodes = {node["id"]: node for node in result["graph"]["nodes"]}
        self.edges = result["graph"]["edges"]
        self.result = result

    def find(self, kind: str, name: str) -> dict:
        found = [node for node in self.nodes.values() if node["type"] == kind and node["name"] == name]
        if len(found) != 1:
            raise AssertionError(f"{kind} {name!r}: {len(found)} nodes")
        return found[0]

    def column(self, table: str, name: str) -> dict:
        table_id = self.find("TABLE", table)["id"]
        return next(node for node in self.nodes.values() if node["type"] == "COLUMN" and node["name"] == name and node["properties"].get("table_id") == table_id)

    def visual(self, name: str) -> dict:
        return next(node for node in self.nodes.values() if node["type"] == "VISUAL" and node["source_id"] == name)

    def has(self, edge_type: str, source: dict, target: dict) -> bool:
        return any(edge["type"] == edge_type and edge["from_id"] == source["id"] and edge["to_id"] == target["id"] for edge in self.edges)


@unittest.skipUnless(BRIDGE.is_file(), "Build the TOM bridge first")
class MergeLabCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        root = Path(cls.temporary.name)
        cls.graphs = {
            "TMDL": {project: Graph(scan_snapshot(LAB / project)) for project in ("SalesA", "Finance")},
            "TMSL": {project: Graph(scan_snapshot(as_tmsl(project, root / "tmsl"))) for project in ("SalesA", "Finance")},
        }

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_each_new_node_type_is_in_the_graph_from_tmdl_and_tmsl(self):
        self.assertTrue(NEW_TYPES <= OBJECT_TYPES)
        for source_format, graphs in self.graphs.items():
            with self.subTest(format=source_format):
                found = {node["type"] for graph in graphs.values() for node in graph.nodes.values()}
                self.assertTrue(NEW_TYPES <= found, NEW_TYPES - found)
                sales, finance = graphs["SalesA"], graphs["Finance"]
                for case in EXPECTED["hierarchies"]:
                    graph = graphs[case["model"]]
                    hierarchy = graph.find("HIERARCHY", case["name"])
                    levels = sorted((node for node in graph.nodes.values() if node["type"] == "LEVEL" and node["properties"]["hierarchy_id"] == hierarchy["id"]),
                                    key=lambda node: node["properties"]["ordinal"])
                    self.assertEqual(case["levels"], [node["name"] for node in levels])
                role = EXPECTED["roles"][0]
                self.assertEqual("read", sales.find("SECURITY_ROLE", role["name"])["properties"]["model_permission"])
                self.assertEqual(role["rls"][0]["filter"], sales.find("ROLE_FILTER", role["rls"][0]["table"])["properties"]["expression"])
                ols = role["ols"][0]
                self.assertEqual(ols["permission"], sales.find("OLS_PERMISSION", f"{ols['table']}[{ols['column']}]")["properties"]["permission"])
                self.assertEqual(EXPECTED["report_measures"][0]["entity"], sales.find("REPORT_MEASURE", "Sales Target")["properties"]["entity"])
                self.assertEqual("calculated", sales.find("PARTITION", "Metric Selector")["properties"]["source_type"])
                self.assertEqual("m", sales.find("PARTITION", "Sales")["properties"]["source_type"])
                self.assertTrue(finance.find("SHARED_EXPRESSION", "SalesRows")["properties"]["expression"].startswith("let"))
                bookmark = EXPECTED["bookmarks"][0]
                self.assertTrue(sales.find("BOOKMARK", bookmark["display_name"])["properties"]["read_only"])
                group = sales.find("CALCULATION_GROUP", "Time Intelligence")
                items = [node["name"] for node in sales.nodes.values() if node["type"] == "CALCULATION_ITEM" and node["properties"]["calculation_group_id"] == group["id"]]
                self.assertEqual(sorted(EXPECTED["calculation_groups"][0]["items"]), sorted(items))

    def test_each_new_link_exists_for_a_fixture_case(self):
        for source_format, graphs in self.graphs.items():
            with self.subTest(format=source_format):
                sales, finance = graphs["SalesA"], graphs["Finance"]
                # Hierarchy level to column.
                self.assertTrue(sales.has("REFERENCES", sales.find("LEVEL", "Year"), sales.column("Date", "Year")))
                # Visual to hierarchy.
                case = EXPECTED["visual_hierarchies"][0]
                self.assertTrue(sales.has("USES", sales.visual(case["visual"]), sales.find("HIERARCHY", case["hierarchy"])))
                # Role filter (DAX) to columns, measures, tables.
                role_filter = sales.find("ROLE_FILTER", "Store")
                self.assertTrue(sales.has("REFERENCES", role_filter, sales.column("Store", "Region")))
                self.assertTrue(sales.has("FILTERS", role_filter, sales.find("TABLE", "Store")))
                # OLS permission to table or column.
                self.assertTrue(sales.has("REFERENCES", sales.find("OLS_PERMISSION", "Store[Manager Email]"), sales.column("Store", "Manager Email")))
                # Report measure (DAX) to model objects.
                report_measure = sales.find("REPORT_MEASURE", "Sales Target")
                self.assertTrue(sales.has("DEPENDS_ON", report_measure, sales.find("MEASURE", "Total Sales")))
                # Visual to report measure.
                self.assertTrue(sales.has("USES", sales.visual("target"), report_measure))
                # Bookmark to page, visuals, filter fields.
                case = EXPECTED["bookmarks"][0]
                bookmark = sales.find("BOOKMARK", case["display_name"])
                self.assertTrue(sales.has("REFERENCES", bookmark, sales.find("PAGE", "Overview")))
                for name in case["visuals"]:
                    self.assertTrue(sales.has("REFERENCES", bookmark, sales.visual(name)))
                for field in case["filter_fields"]:
                    self.assertTrue(sales.has("REFERENCES", bookmark, sales.column(field["table"], field["column"])))
                # Partition (M) to shared expression.
                case = EXPECTED["shared_expressions"][0]
                partition = next(node for node in finance.nodes.values() if node["type"] == "PARTITION" and node["name"] == case["used_by_partitions"][0]["partition"]
                                 and node["properties"]["table_id"] == finance.find("TABLE", case["used_by_partitions"][0]["table"])["id"])
                self.assertTrue(finance.has("REFERENCES", partition, finance.find("SHARED_EXPRESSION", case["name"])))
                # A calculated partition (field parameter) gets its DAX dependencies.
                self.assertTrue(sales.has("DEPENDS_ON", sales.find("PARTITION", "Metric Selector"), sales.find("MEASURE", "Margin")))

    def test_visuals_and_pages_carry_positions(self):
        sales = self.graphs["TMDL"]["SalesA"]
        for node in sales.nodes.values():
            if node["type"] == "VISUAL":
                for key in ("x", "y", "z", "width", "height"):
                    self.assertIsInstance(node["properties"].get(key), int, (node["name"], key))
            if node["type"] == "PAGE":
                self.assertEqual((1280, 720), (node["properties"]["width"], node["properties"]["height"]))
        case = EXPECTED["visual_groups"][0]
        self.assertTrue(sales.visual(case["group"])["properties"]["is_group"])
        for name in case["visuals"]:
            self.assertEqual(case["group"], sales.visual(name)["properties"]["parentGroupName"])
        self.assertEqual({"x": 420, "y": 0, "z": 0, "width": 400, "height": 240},
                         {key: sales.visual("calendarmatrix")["properties"][key] for key in ("x", "y", "z", "width", "height")})

    def test_guarded_scan_is_complete_or_each_item_has_a_reason(self):
        reasons = EXPECTED["guarded_scan_gap_reasons"]
        for project in ("SalesA", "SalesB", "Finance", "Legacy"):
            for item in EXPECTED["guarded_scan_gaps"][project]:
                with self.subTest(project=project, item=item):
                    self.assertTrue(item in reasons or item.split(":")[0] in reasons or project in reasons)
        self.assertEqual(["RLS_OLS_RUNTIME_VERIFICATION_REQUIRED"], self.graphs["TMDL"]["SalesA"].result["completeness"]["blocking"])
        self.assertEqual("COMPLETE", self.graphs["TMDL"]["Finance"].result["completeness"]["status"])
        self.assertEqual([], self.graphs["TMSL"]["Finance"].result["completeness"]["blocking"])
        # PBIR-Legacy stays fail-closed.
        self.assertTrue(any(item.startswith("PBIR_SCHEMA_UNSUPPORTED:") for item in EXPECTED["guarded_scan_gaps"]["Legacy"]))

    def test_impact_follows_the_new_links(self):
        sales = self.graphs["TMDL"]["SalesA"]
        graph = sales.result["graph"]
        year = sales.column("Date", "Year")["id"]
        impacted = set(analyze_impact(graph, [year])["impacted_objects"])
        for node in (sales.find("LEVEL", "Year"), sales.find("HIERARCHY", "Calendar"), sales.visual("calendarmatrix")):
            self.assertIn(node["id"], impacted, node["name"])
        total = sales.find("MEASURE", "Total Sales")["id"]
        impacted = set(analyze_impact(graph, [total])["impacted_objects"])
        self.assertIn(sales.find("REPORT_MEASURE", "Sales Target")["id"], impacted)
        self.assertIn(sales.visual("target")["id"], impacted)
        manager = sales.column("Store", "Manager Email")["id"]
        report = analyze_impact(graph, [manager])
        self.assertIn(sales.find("SECURITY_ROLE", "West Region")["id"], set(report["impacted_objects"]))
        region = sales.column("Store", "Region")["id"]
        self.assertIn(sales.find("BOOKMARK", "YTD view")["id"], set(analyze_impact(graph, [region])["impacted_objects"]))

    def test_an_unknown_object_type_gives_a_not_checked_entry(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = as_tmsl("Finance", Path(temporary))
            path = project / "Finance.SemanticModel" / "model.bim"
            database = json.loads(path.read_text(encoding="utf-8"))
            # Perspectives are a later object type (technical design 3.1).
            database["model"]["perspectives"] = [{"name": "Finance view", "tables": [{"name": "Sales"}]}]
            path.write_text(json.dumps(database), encoding="utf-8")
            result = scan_snapshot(project)
        completeness = result["completeness"]
        self.assertEqual([], completeness["scanner_errors"])
        self.assertEqual(["model.perspectives"], [item["area"] for item in completeness["not_checked"]])
        self.assertEqual("The scanner does not read this object type.", completeness["not_checked"][0]["reason"])
        self.assertEqual(["IMPACT_METADATA_COVERAGE_INCOMPLETE"], completeness["blocking"])
        graph = Graph(result)
        report = analyze_impact(result["graph"], [graph.find("MEASURE", "Revenue")["id"]], completeness=completeness)
        self.assertEqual(completeness["not_checked"], report["completeness"]["not_checked"])
        self.assertEqual("INCOMPLETE", report["completeness"]["status"])


class NormalizerCoverageTests(unittest.TestCase):
    MODEL = {"id": "m1", "name": "Model", "tables": [
        {"name": "Sales", "lineageTag": "t-sales", "columns": [{"name": "Amount", "dataType": "decimal", "lineageTag": "c-amount"}],
         "measures": [{"name": "Total", "expression": "SUM(Sales[Amount])", "lineageTag": "m-total"}],
         "partitions": [{"name": "Sales", "source": {"type": "m", "expression": "let Source = #\"Base Rows\", Note = \"Base Rows\" in Source"}}]}],
        "expressions": [{"name": "Base Rows", "kind": "m", "expression": "let Source = 1 in Source"},
                        {"name": "Unused", "kind": "m", "expression": "1"}],
        "perspectives": [{"name": "P"}]}
    REPORT = {"id": "r1", "name": "Report", "model_id": "m1",
              "report_extensions": [{"name": "Sales", "measures": [{"name": "Target", "expression": "[Total] * 2"}, {"name": "Stretch", "expression": "[Target] * 2"}]}],
              "pages": [{"id": "p1", "name": "Page", "width": 1280, "height": 720, "visuals": [
                  {"id": "v1", "name": "v1", "position": {"x": 1, "y": 2, "z": 3, "width": 4, "height": 5},
                   "visual": {"visualType": "card", "query": {"queryState": {"Values": {"projections": [
                       {"field": {"Measure": {"Expression": {"SourceRef": {"Entity": "Sales"}}, "Property": "Target"}}, "queryRef": "Sales.Target"}]}}}},
                   "filterConfig": {"filters": [{"name": "f1", "field": {"Measure": {"Expression": {"SourceRef": {"Entity": "Sales"}}, "Property": "Stretch"}}}]}}]}]}

    def build(self):
        graph = build_fact_graph([self.MODEL], [self.REPORT], analyze_dax=True)
        return graph, {node.id: node for node in graph.nodes}

    def test_filter_and_report_measure_links(self):
        graph, nodes = self.build()
        by_name = {(node.type, node.name): node.id for node in graph.nodes}
        edges = {(edge.type, edge.from_id, edge.to_id) for edge in graph.edges}
        target, stretch = by_name[("REPORT_MEASURE", "Target")], by_name[("REPORT_MEASURE", "Stretch")]
        self.assertIn(("DEPENDS_ON", target, by_name[("MEASURE", "Total")]), edges)
        self.assertIn(("DEPENDS_ON", stretch, target), edges)
        self.assertIn(("USES", by_name[("VISUAL", "v1")], target), edges)
        visual_filter = next(node.id for node in graph.nodes if node.type == "VISUAL_FILTER")
        self.assertIn(("FILTERS", visual_filter, stretch), edges)
        self.assertEqual([], graph.diagnostics)
        self.assertEqual({"x": 1, "y": 2, "z": 3, "width": 4, "height": 5}, {key: nodes[by_name[("VISUAL", "v1")]].properties[key] for key in ("x", "y", "z", "width", "height")})

    def test_report_measure_wins_over_a_measure_of_another_model(self):
        other = {"id": "m2", "name": "Other", "tables": [{"name": "Sales", "lineageTag": "t-other", "measures": [{"name": "Target", "expression": "1", "lineageTag": "m-other-target"}]}]}
        graph = build_fact_graph([self.MODEL, other], [self.REPORT])
        by_name = {(node.type, node.name, node.model_id): node.id for node in graph.nodes}
        visual = next(node for node in graph.nodes if node.type == "VISUAL")
        target = by_name[("REPORT_MEASURE", "Target", "model:m1")]
        self.assertIn(target, visual.properties["field_ids"])
        self.assertNotIn(by_name[("MEASURE", "Target", "model:m2")], visual.properties["field_ids"])

    def test_role_filter_links_to_a_measure(self):
        model = json.loads(json.dumps(self.MODEL))
        model["roles"] = [{"name": "R", "tablePermissions": [{"name": "Sales", "filterExpression": "[Total] > 0 && [Amount] > 0"}]}]
        graph = build_fact_graph([model], [], analyze_dax=True)
        ids = {(node.type, node.name): node.id for node in graph.nodes}
        edges = {(edge.type, edge.from_id, edge.to_id) for edge in graph.edges}
        role_filter = ids[("ROLE_FILTER", "Sales")]
        self.assertIn(("DEPENDS_ON", role_filter, ids[("MEASURE", "Total")]), edges)
        self.assertIn(("REFERENCES", role_filter, ids[("COLUMN", "Amount")]), edges)
        self.assertEqual([], graph.diagnostics)

    def test_bookmarks_file_that_is_not_an_object_does_not_stop_the_read(self):
        from backend.scanner.pbip import _read_bookmarks
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / "definition" / "bookmarks"
            folder.mkdir(parents=True)
            (folder / "bookmarks.json").write_text("[]", encoding="utf-8")
            (folder / "b1.bookmark.json").write_text(json.dumps({"name": "b1"}), encoding="utf-8")
            self.assertEqual(["b1"], [item["id"] for item in _read_bookmarks(folder)])

    def test_m_reference_ignores_string_literals_and_unused_expressions(self):
        graph, _ = self.build()
        by_name = {(node.type, node.name): node.id for node in graph.nodes}
        edges = {(edge.type, edge.from_id, edge.to_id) for edge in graph.edges}
        partition = by_name[("PARTITION", "Sales")]
        self.assertIn(("REFERENCES", partition, by_name[("SHARED_EXPRESSION", "Base Rows")]), edges)
        self.assertNotIn(("REFERENCES", partition, by_name[("SHARED_EXPRESSION", "Unused")]), edges)
        # A string that only contains the name is not a reference.
        model = json.loads(json.dumps(self.MODEL))
        model["tables"][0]["partitions"][0]["source"]["expression"] = 'let Source = "Unused" in Source'
        other = build_fact_graph([model], [])
        ids = {(node.type, node.name): node.id for node in other.nodes}
        self.assertFalse(any(edge.type == "REFERENCES" and edge.to_id == ids[("SHARED_EXPRESSION", "Unused")] for edge in other.edges))

    def test_unknown_collection_is_not_an_error(self):
        graph, _ = self.build()
        self.assertFalse(any(node.type.casefold().startswith("perspective") for node in graph.nodes))
        self.assertEqual("MODEL", next(node.type for node in graph.nodes if node.name == "Model"))

    def test_role_members_stay_out_of_the_graph(self):
        model = json.loads(json.dumps(self.MODEL))
        model["roles"] = [{"name": "R", "members": [{"memberName": "someone"}], "tablePermissions": [{"name": "Sales", "filterExpression": "[Amount] > 0", "metadataPermission": "read"}]}]
        graph = build_fact_graph([model], [], analyze_dax=True)
        role = next(node for node in graph.nodes if node.type == "SECURITY_ROLE")
        self.assertNotIn("members", role.properties["raw_source"])
        self.assertEqual(1, role.properties["member_count"])
        self.assertNotIn("someone", json.dumps(graph.to_dict()))
        table_ols = next(node for node in graph.nodes if node.type == "OLS_PERMISSION")
        self.assertEqual(next(node.id for node in graph.nodes if node.type == "TABLE"), table_ols.properties["target_id"])


class FunctionParserTests(unittest.TestCase):
    def test_parse_udf_definition(self):
        source = "(amount : NUMERIC, rows : TABLE, factor : SCALAR NUMERIC EXPR, plain) =>\n    amount * factor + COUNTROWS(rows)"
        result = parse_dax_function(source)
        root = result.root
        self.assertEqual("function_definition", root.kind)
        self.assertEqual(["amount", "rows", "factor", "plain"], [item.name for item in root.parameters])
        self.assertEqual([("NUMERIC", None, None), ("TABLE", None, None), ("SCALAR", "NUMERIC", "EXPR"), (None, None, None)],
                         [(item.parameter_type, item.subtype, item.mode) for item in root.parameters])
        self.assertEqual("binary_operator", root.body.kind)
        # Body positions are positions in the full definition text.
        self.assertEqual(2, root.body.span.start_line)
        self.assertEqual(source.index("amount *"), root.body.span.start_offset)
        self.assertEqual("amount", source[root.parameters[0].span.start_offset:root.parameters[0].span.start_offset + 6])

    def test_parse_udf_without_parameters_and_plain_expression(self):
        self.assertEqual([], list(parse_dax_function("() => 1").root.parameters))
        self.assertEqual("function_call", parse_dax_function("SUM(Sales[Amount])").root.kind)
        with self.assertRaises(DaxSyntaxError):
            parse_dax_function("(a : NUMERIC) => a *")

    def test_analyzer_reads_udf_and_call(self):
        nodes = [
            Node(id="m", type="MODEL", name="M"),
            Node(id="t", type="TABLE", name="Sales", model_id="m"),
            Node(id="c", type="COLUMN", name="Amount", model_id="m", properties={"table_id": "t"}),
            Node(id="f", type="USER_DEFINED_FUNCTION", name="AddTax", model_id="m", properties={"expression": "(amount : NUMERIC) => amount * 1.2 + SUM(Sales[Amount])"}),
            Node(id="x", type="MEASURE", name="Taxed", model_id="m", properties={"table_id": "t", "expression": "AddTax(SUM(Sales[Amount]))"}),
        ]
        result = DaxAnalyzer(nodes).analyze()
        self.assertEqual([], result.diagnostics)
        edges = {(edge.from_id, edge.to_id) for edge in result.edges}
        self.assertIn(("f", "c"), edges)
        self.assertIn(("x", "f"), edges)


class SchemaMigrationTests(unittest.TestCase):
    def test_version_1_payload_moves_forward(self):
        payload = {"nodes": [{"id": "a", "type": "MEASURE", "name": "A"}], "edges": []}
        self.assertEqual(GRAPH_SCHEMA_VERSION, migrate_payload(payload)["schema_version"])
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "graph.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            repository = GraphRepository(path, use_native=False)
            self.assertEqual("A", repository.get_object("a").name)
            repository.replace([Node(id="b", type="BOOKMARK", name="B", source="report_metadata")], [])
            stored = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(GRAPH_SCHEMA_VERSION, stored["schema_version"])
            self.assertEqual("BOOKMARK", GraphRepository(path, use_native=False).get_object("b").type)

    def test_newer_payload_stops_the_load(self):
        with self.assertRaises(ValueError):
            migrate_payload({"schema_version": GRAPH_SCHEMA_VERSION + 1, "nodes": [], "edges": []})
        with self.assertRaises(ValueError):
            migrate_payload({"schema_version": "2"})


if __name__ == "__main__":
    unittest.main()
