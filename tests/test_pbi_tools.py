"""Tests for typed Power BI agent tools (pbi_find_object, pbi_lineage, etc.)."""

import unittest
from backend.tool_registry import build_pbi_tools, tool_schema


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def get(self, path: str, **params):
        self.calls.append(("GET", path, params))
        return {"path": path, "params": params}

    def post(self, path: str, payload):
        self.calls.append(("POST", path, payload))
        return {"path": path, "payload": payload}

    def devcenter(self, method, path, query, body):
        return {}

    def freshness(self):
        return {"source": "app"}


class PbiToolsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = FakeClient()
        self.tools = build_pbi_tools(self.client)

    def test_pbi_tools_registered(self) -> None:
        expected = {
            "pbi_find_object",
            "pbi_lineage",
            "pbi_impact",
            "pbi_visual_bindings",
            "pbi_rls_for",
            "pbi_context",
        }
        self.assertEqual(expected, set(self.tools))

    def test_tool_schemas_are_valid(self) -> None:
        for name, tool in self.tools.items():
            schema = tool_schema(tool)
            self.assertEqual(schema["name"], name)
            self.assertTrue(schema["description"], f"{name} must have a description")
            self.assertIn("input_schema", schema)
            self.assertEqual(schema["input_schema"]["type"], "object")

    def test_pbi_find_object_invokes_search(self) -> None:
        result = self.tools["pbi_find_object"](query="Revenue", object_type="MEASURE")
        self.assertEqual("search", result["path"])
        self.assertEqual("Revenue", result["params"]["q"])
        self.assertEqual("MEASURE", result["params"]["object_type"])

    def test_pbi_lineage_invokes_objects(self) -> None:
        result = self.tools["pbi_lineage"](object_id="model:m1/measure:sales")
        self.assertEqual("objects/model%3Am1%2Fmeasure%3Asales", result["path"])

    def test_pbi_impact_invokes_impact(self) -> None:
        result = self.tools["pbi_impact"](target_id="model:m1/column:c1")
        self.assertEqual("impact", result["path"])
        self.assertEqual("model:m1/column:c1", result["payload"]["target_id"])

    def test_pbi_visual_bindings_invokes_objects(self) -> None:
        result = self.tools["pbi_visual_bindings"](target_id="report:r1/page:p1/visual:v1")
        self.assertEqual("objects/report%3Ar1%2Fpage%3Ap1%2Fvisual%3Av1", result["path"])

    def test_pbi_rls_for_invokes_role_filter_search(self) -> None:
        result = self.tools["pbi_rls_for"](table_id_or_name="Sales")
        self.assertEqual("search", result["path"])
        self.assertEqual("Sales", result["params"]["q"])
        self.assertEqual("ROLE_FILTER", result["params"]["object_type"])

    def test_pbi_context_invokes_context(self) -> None:
        result = self.tools["pbi_context"](target="model:m1/table:t1", task="inspect")
        self.assertEqual("context", result["path"])
        self.assertEqual("model:m1/table:t1", result["params"]["target"])
        self.assertEqual("inspect", result["params"]["task"])


if __name__ == "__main__":
    unittest.main()
