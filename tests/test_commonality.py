"""Project-wide common / divergent / unique objects overview (#14)."""
import json
import unittest

from backend.api.app import create_app
from backend.commonality import build_commonality, get_commonality
from backend.graph.loader import build_fact_graph
from backend.graph.repository import GraphRepository

from backend.mcp_budget import TOOL_BUDGETS

MCP_BUDGET_CHARS = TOOL_BUDGETS["brain_commonality"]["compact"]  # 12,000 characters, about 3,000 tokens


def model(model_id, measures, *, columns=("Amount", "DateKey"), extra_tables=()):
    """A dict model with a Sales table; ``measures`` is a list of (name, expression, format)."""

    tables = [{"id": f"{model_id}-sales", "name": "Sales",
               "columns": [{"id": f"{model_id}-{name}", "name": name, "dataType": "decimal", "sourceColumn": name} for name in columns],
               "measures": [{"id": f"{model_id}-m-{index}", "name": name, "expression": expression, "formatString": fmt}
                            for index, (name, expression, fmt) in enumerate(measures)]}]
    tables += [{"id": f"{model_id}-{name}", "name": name, "columns": [{"id": f"{model_id}-{name}-key", "name": "Key", "dataType": "int64"}]}
               for name in extra_tables]
    return {"id": model_id, "name": model_id.title(), "tables": tables}


def three_models():
    """Shared, drifted, renamed and unique measures over three models."""

    alpha = model("alpha", [
        ("Total Sales", "SUM(Sales[Amount])", "#,##0"),                     # shared, identical in all 3
        ("Margin", "DIVIDE([Profit], [Total Sales])", "0.0%"),              # drifted: beta changes the format, gamma the DAX
        ("Order Count", "COUNTROWS(Sales)", "0"),                           # renamed in gamma
        ("Alpha Only", "MAX(Sales[DateKey])", "0"),                          # unique
    ], extra_tables=("Budget",))
    beta = model("beta", [
        ("Total Sales", "SUM ( Sales[Amount] )", "#,##0"),                   # whitespace only: still identical
        ("Margin", "DIVIDE([Profit], [Total Sales])", "0.00%"),
        ("Order Count", "COUNTROWS(Sales)", "0"),
    ])
    gamma = model("gamma", [
        ("Total Sales", "SUM(Sales[Amount])", "#,##0"),
        ("Margin", "DIVIDE([Profit], [Total Sales], 0)", "0.0%"),
        ("Number of Orders", "COUNTROWS ( Sales )", "0"),
        ("Sales Copy", "SUM(Sales[Amount])", "#,##0"),                       # duplicate logic inside gamma
    ])
    return [alpha, beta, gamma]


def nodes():
    return build_fact_graph(three_models()).nodes


def measure_group(result, name):
    return next(group for group in result["groups"] if group["type"] == "MEASURE" and name in (group.get("names") or {group["in"][0]: group["name"]}).values())


class CommonalityBucketTests(unittest.TestCase):
    def setUp(self):
        self.result = build_commonality(nodes())
        self.refs = {source["name"]: source["ref"] for source in self.result["sources"]}

    def test_sources_get_short_refs(self):
        self.assertEqual(self.refs, {"Alpha": "m1", "Beta": "m2", "Gamma": "m3"})
        self.assertFalse(self.result["incomplete"])

    def test_shared_measure_is_identical_in_all_three(self):
        group = measure_group(self.result, "Total Sales")
        self.assertEqual((group["bucket"], group["present"], group["of"]), ("identical", 3, 3))
        self.assertNotIn("differs", group)

    def test_drifted_measure_lists_the_properties_that_differ(self):
        group = measure_group(self.result, "Margin")
        self.assertEqual(group["bucket"], "differs")
        self.assertEqual(group["differs"], ["expression", "format_string"])
        self.assertEqual(group["variants"], 3)

    def test_renamed_measure_is_one_group_with_each_name(self):
        group = measure_group(self.result, "Number of Orders")
        self.assertEqual(group["bucket"], "renamed")
        self.assertEqual(group["names"], {"m1": "Order Count", "m2": "Order Count", "m3": "Number of Orders"})
        self.assertEqual(group["present"], 3)
        self.assertFalse(any(item["bucket"] == "unique" and item["name"] in {"Order Count", "Number of Orders"} for item in self.result["groups"]))

    def test_unique_objects(self):
        self.assertEqual(measure_group(self.result, "Alpha Only")["in"], ["m1"])
        self.assertEqual(measure_group(self.result, "Alpha Only")["bucket"], "unique")
        budget = next(group for group in self.result["groups"] if group["type"] == "TABLE" and group["name"] == "Budget")
        self.assertEqual((budget["bucket"], budget["in"]), ("unique", ["m1"]))
        self.assertEqual(measure_group(self.result, "Sales Copy")["bucket"], "unique")

    def test_counts_per_type(self):
        self.assertEqual(self.result["counts"]["MEASURE"], {"differs": 1, "renamed": 1, "identical": 1, "unique": 2})
        self.assertEqual(self.result["counts"]["COLUMN"]["identical"], 2)

    def test_duplicate_logic_across_and_inside_models(self):
        by_names = {tuple(sorted(member["name"] for member in item["members"])): item for item in self.result["duplicate_logic"]}
        self.assertIn(("Sales Copy", "Total Sales", "Total Sales", "Total Sales"), by_names)
        self.assertIn(("Number of Orders", "Order Count", "Order Count"), by_names)
        self.assertFalse(any(item["type"] != "MEASURE" for item in self.result["duplicate_logic"]))

    def test_same_input_same_result(self):
        self.assertEqual(build_commonality(nodes()), self.result)


class CommonalityFilterTests(unittest.TestCase):
    def test_type_bucket_and_scope(self):
        reply = get_commonality(nodes(), object_type="measure", bucket="differs")
        self.assertEqual([group["name"] for group in reply["groups"]], ["Margin"])
        self.assertEqual(list(reply["counts"]), ["MEASURE"])
        scoped = get_commonality(nodes(), object_type="MEASURE", scope="m1,m2")
        self.assertEqual([source["name"] for source in scoped["sources"]], ["Alpha", "Beta"])
        names = {group["name"]: group["bucket"] for group in scoped["groups"]}
        self.assertEqual(names["Margin"], "differs")
        self.assertEqual(names["Order Count"], "identical", "the rename lives in gamma, which is out of scope")
        with self.assertRaises(ValueError):
            get_commonality(nodes(), scope="nope")
        with self.assertRaises(ValueError):
            get_commonality(nodes(), bucket="similar")

    def test_paging_and_group_detail(self):
        first = get_commonality(nodes(), limit=2)
        self.assertEqual(len(first["groups"]), 2)
        self.assertTrue(first["has_more"])
        self.assertEqual(first["next_offset"], 2)
        second = get_commonality(nodes(), limit=2, offset=2)
        self.assertNotEqual(first["groups"][0]["id"], second["groups"][0]["id"])
        detail = get_commonality(nodes(), group_id=first["groups"][0]["id"])
        self.assertEqual(detail["group"]["id"], first["groups"][0]["id"])
        self.assertTrue(all(isinstance(value, str) for value in detail["group"]["objects"].values()))
        duplicate = get_commonality(nodes(), group_id=first["duplicate_logic"][0]["id"])
        self.assertIn("object_id", duplicate["duplicate"]["members"][0])

    def test_compact_reply_has_no_object_ids(self):
        reply = get_commonality(nodes(), compact=True)
        self.assertTrue(all("objects" not in group for group in reply["groups"]))
        self.assertTrue(all("object_id" not in member for item in reply["duplicate_logic"] for member in item["members"]))


class CommonalityBudgetTests(unittest.TestCase):
    def test_three_model_reply_stays_under_the_budget(self):
        reply = get_commonality(nodes(), compact=True, limit=25, max_chars=MCP_BUDGET_CHARS)
        self.assertLessEqual(len(json.dumps(reply, ensure_ascii=False)), MCP_BUDGET_CHARS)
        self.assertFalse(reply["has_more"])

    def test_large_project_is_trimmed_to_the_budget_and_pages_on(self):
        models = [model(f"m{index:02d}", [(f"Measure {number}", f"SUM(Sales[Amount]) * {number + index}", "0") for number in range(60)])
                  for index in range(8)]
        graph_nodes = build_fact_graph(models).nodes
        reply = get_commonality(graph_nodes, compact=True, limit=200, max_chars=MCP_BUDGET_CHARS)
        self.assertLessEqual(len(json.dumps(reply, ensure_ascii=False)), MCP_BUDGET_CHARS)
        self.assertTrue(reply["has_more"])
        self.assertGreater(reply["returned"], 0)
        following = get_commonality(graph_nodes, compact=True, limit=200, offset=reply["next_offset"], max_chars=MCP_BUDGET_CHARS)
        self.assertNotEqual(following["groups"][0]["id"], reply["groups"][0]["id"])


class CommonalityReportTests(unittest.TestCase):
    def test_copied_report_pages_and_visuals_align(self):
        import tempfile
        from pathlib import Path
        from tests.fixtures.pbip_sources import write_pbip_project

        with tempfile.TemporaryDirectory() as folder:
            graph = build_fact_graph(write_pbip_project(Path(folder), include_extra=True))
        result = build_commonality(graph.nodes, scope="reports")
        self.assertEqual([source["domain"] for source in result["sources"]], ["report"])
        self.assertEqual({group["type"] for group in result["groups"]}, {"PAGE", "VISUAL"})
        self.assertTrue(all(group["bucket"] == "unique" for group in result["groups"]))
        self.assertEqual(result["duplicate_logic"], [])


class CommonalityRouteTests(unittest.TestCase):
    def test_route(self):
        repository = GraphRepository(use_native=False)
        self.addCleanup(repository.close)
        build_fact_graph(three_models()).load(repository)
        app = create_app(repository)
        status, reply = app.handle("GET", "/api/commonality?type=MEASURE&bucket=renamed")
        self.assertEqual(status, 200)
        self.assertEqual(reply["groups"][0]["names"]["m3"], "Number of Orders")
        status, reply = app.handle("GET", "/api/commonality?bucket=bad")
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
