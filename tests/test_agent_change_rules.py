"""Agents change more than measures, inside the app only, and every change says what it breaks.

1. ``object_edit`` reaches DAX user-defined functions, calculation items, shared M expressions and
   partition M queries, as well as measures, columns and tables. All of them are proposals the
   user accepts or rejects; apply writes them with the TOM bridge.
2. Each object edit runs the change rules (``change_rules``): a measure whose result type changes
   lists the visuals and measures it can break, a function signature change lists the callers with
   the wrong argument count, a partition query that drops a source column lists the columns.
   A rule that breaks puts the proposal in front of the user (``needs_review``).
3. A clearly broken M query is refused like a DAX parse error.
4. ``proposal_check`` runs the same checks and saves nothing.
5. ``brain_guide`` gives the syntax and the rules before the agent writes the change.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest
from types import SimpleNamespace

from backend.agent_knowledge import TOPICS, guide
from backend.devcenter.apply.service import ApplyService
from backend.devcenter.session.change_rules import (BOOLEAN, DATETIME, MIXED, NUMBER, TEXT, Inference, call_sites,
                                                    function_parameters, m_syntax_error)
from tests.test_agent_object_edits import BRIDGE, LAB, MARGIN, _AgentCase, _Desktop

ADD_TAX = "function:AddTax"
SALES_PARTITION = "partition:Sales/Sales"
YTD = "calculation_item:Time Intelligence/YTD"
MODEL = "SalesA/SalesA.SemanticModel/definition"
SALES_QUERY = '''let
    Source = #table({"OrderDate", "StoreKey", "Amount", "Cost"}, {}),
    Kept = Table.SelectRows(Source, each [Amount] <> null)
in
    Kept'''
NO_COST_QUERY = 'let\n    Source = #table({"OrderDate", "StoreKey", "Amount"}, {})\nin\n    Source'


def _measure(name: str, expression: str) -> SimpleNamespace:
    return SimpleNamespace(kind="measure", name=name, table="Sales", qualified_name=f"Sales/{name}",
                           props={"expression": expression})


class InferenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.inference = Inference([
            _measure("Total Sales", "SUM(Sales[Amount])"), _measure("Margin", "[Total Sales] - 1"),
            SimpleNamespace(kind="column", name="Region", table="Store", qualified_name="Store/Region", props={"data_type": "string"}),
            SimpleNamespace(kind="function", name="AddTax", table=None, qualified_name="AddTax",
                            props={"expression": "(amount : NUMERIC) => amount * 1.2"}),
        ])

    def test_result_kinds(self) -> None:
        cases = {
            "[Margin]": NUMBER, "FORMAT([Margin], \"0.0\")": TEXT, "[Margin] & \" EUR\"": TEXT, "[Margin] > 0": BOOLEAN,
            "VAR m = [Margin] RETURN IF(m > 0, \"up\", \"down\")": TEXT, "VAR m = [Margin] RETURN DIVIDE(m, 2)": NUMBER,
            "AddTax([Total Sales])": NUMBER, "TODAY() - 7": DATETIME, "SELECTEDVALUE(Store[Region])": TEXT,
            "IF([Margin] > 0, [Margin], \"none\")": MIXED, "CALCULATE([Margin], 'Store'[Region] = \"West\")": NUMBER,
            "IF([Margin] > 0, [Margin], BLANK())": NUMBER, "-- a comment\n[Margin] // more": NUMBER,
        }
        for text, kind in cases.items():
            with self.subTest(text=text):
                self.assertEqual(kind, self.inference.kind(text))

    def test_functions_and_m(self) -> None:
        self.assertEqual([("a", "SCALAR NUMERIC"), ("b", "")], function_parameters("(a : Scalar Numeric, b) => a + b"))
        self.assertIsNone(function_parameters("a + b"))
        self.assertEqual([1, 2], call_sites('AddTax([x]) + AddTax(1, "a, b") + Other.AddTax(3) + [AddTax]', "AddTax"))
        self.assertIsNone(m_syntax_error(SALES_QUERY))
        self.assertEqual("m_unbalanced_brackets", m_syntax_error("let a = Table.SelectRows(x in a"))
        self.assertEqual("m_unclosed_text", m_syntax_error('let a = "x in a'))
        self.assertEqual("m_let_without_in", m_syntax_error("let a = 1"))


class ChangeRuleTests(_AgentCase):
    def check(self, target: str, payload: dict) -> dict:
        reply = self.tools.proposal_check(kind="object_edit", target=target, payload=payload)
        self.assertTrue(reply["valid"], reply)
        return reply

    def test_a_measure_that_turns_into_text_lists_the_visuals_it_breaks(self) -> None:
        proposal = self.proposed("object_edit", MARGIN, {"set": {"expression": 'FORMAT([Total Sales] - [Total Cost], "#,0")'}})
        [rule] = [item for item in proposal["check"]["rules"] if item["rule"] == "result_type_change"]
        self.assertEqual("breaks", rule["level"])
        self.assertIn("number", rule["message"])
        self.assertIn("visual marginbymonth", rule["objects"])
        self.assertTrue(proposal["needs_review"])
        # The same result type has no rule.
        same = self.check(MARGIN, {"set": {"expression": "[Total Sales] - [Total Cost] * 1.1"}})
        self.assertEqual([], same["check"]["rules"])

    def test_a_function_signature_change_lists_the_callers_it_breaks(self) -> None:
        reply = self.check(ADD_TAX, {"set": {"expression": "(amount : NUMERIC, rate : NUMERIC) => amount * (1 + rate)"}})
        [rule] = reply["check"]["rules"]
        self.assertEqual(("function_signature", "breaks"), (rule["rule"], rule["level"]))
        self.assertEqual(["measure Sales/Sales With Tax"], rule["objects"])
        self.assertTrue(reply["needs_review"])
        text = self.check(ADD_TAX, {"set": {"expression": '(amount : NUMERIC) => FORMAT(amount * 1.2, "0")'}})
        self.assertEqual(["function_result_type"], [item["rule"] for item in text["check"]["rules"]])

    def test_a_calculation_item_without_the_measure_is_a_warning(self) -> None:
        reply = self.check(YTD, {"set": {"expression": "CALCULATE([Total Sales], DATESYTD('Date'[Date]))"}})
        self.assertEqual([("calc_item_without_measure", "warning")], [(item["rule"], item["level"]) for item in reply["check"]["rules"]])
        # A warning alone does not force a review; the expression change's own Breaks still do.
        self.assertEqual(reply["check"]["breaks"] > 0, reply["needs_review"])

    def test_a_query_that_drops_a_source_column_breaks_the_column_and_a_broken_query_is_refused(self) -> None:
        reply = self.check(SALES_PARTITION, {"set": {"expression": NO_COST_QUERY}})
        [rule] = reply["check"]["rules"]
        self.assertEqual(("source_column_dropped", "breaks"), (rule["rule"], rule["level"]))
        self.assertEqual(["column Sales/Cost (source column Cost)"], rule["objects"])
        self.assertEqual([], self.check(SALES_PARTITION, {"set": {"expression": SALES_QUERY}})["check"]["rules"])
        details = self.refused("object_edit", SALES_PARTITION, {"set": {"expression": "let Source = #table({\"A\"}, {}"}})
        self.assertEqual(("m_unbalanced_brackets", "expression"), (details["reason"], details["property"]))

    def test_the_dry_run_saves_nothing_and_returns_the_submit_error(self) -> None:
        document = self.devcenter._require_open().document
        before = (self.rev, len(document.get("proposals", [])))
        reply = self.tools.proposal_check(kind="object_edit", target=MARGIN, payload={"set": {"expression": "[Nope] + 1"}})
        self.assertFalse(reply["valid"])
        self.assertEqual(("invalid_payload", "proposal_not_valid"), (reply["refusal"]["code"], reply["refusal"]["details"]["reason"]))
        self.check(MARGIN, {"set": {"description": "Sales minus cost"}})
        reply = self.tools.proposal_check(kind="object_edit", target="measure:Sales/Nope", payload={"set": {"description": "x"}})
        self.assertEqual("not_found", reply["refusal"]["code"])
        document = self.devcenter._require_open().document
        self.assertEqual(before, (self.rev, len(document.get("proposals", []))))


class GuideTests(unittest.TestCase):
    def test_every_topic_has_syntax_practice_and_impact(self) -> None:
        for name in TOPICS:
            with self.subTest(topic=name):
                reply = guide(name)
                for field in ("payload", "syntax", "best_practice", "impact", "workflow"):
                    self.assertTrue(reply[field], field)
        self.assertEqual("function", guide("UDF")["topic"])
        self.assertEqual("m_query", guide("partition")["topic"])
        self.assertEqual(set(TOPICS), set(guide()["topics"]))
        self.assertEqual("nonsense", guide("nonsense")["unknown_topic"])


@unittest.skipUnless(BRIDGE.is_file(), "Build the TOM bridge first")
class FunctionAndQueryApplyTests(_AgentCase):
    """A function edit and a partition query edit go from proposal to TMDL through the real apply."""

    def prepare(self) -> None:
        from backend.adapters.tabular_metadata import TabularMetadataAdapter

        temporary = tempfile.TemporaryDirectory(prefix="rules-model-")
        self.addCleanup(temporary.cleanup)
        output = Path(temporary.name) / "model"
        TabularMetadataAdapter().write_model(LAB / "SalesA" / "SalesA.SemanticModel", output, [])
        # The model library writes the canonical files, so the apply is not blocked by the format check.
        for name in ("tables/Sales.tmdl", "functions.tmdl"):
            if (output / name).is_file():
                shutil.copyfile(output / name, self.root / MODEL / name)

    def test_the_user_accepts_and_apply_writes_the_function_and_the_query(self) -> None:
        function = self.proposed("object_edit", ADD_TAX, {"set": {"expression": "(amount : NUMERIC) => amount * 1.25"}})
        query = self.proposed("object_edit", SALES_PARTITION, {"set": {"expression": SALES_QUERY}})
        self.assertEqual([], function["check"]["rules"] + query["check"]["rules"])
        self.accept(function)
        self.accept(query)
        self.devcenter.apply_service = ApplyService(self.devcenter, desktop=_Desktop())
        code, preview = self.app.handle("GET", "/api/devcenter/apply/preview")
        self.assertEqual(200, code, preview)
        self.assertTrue(preview["ready"], preview)
        reply = self.ok("apply", {"base_revision": self.rev, "plan_hash": preview["plan_hash"],
                                  "approvals": sorted(item["purpose"] for item in preview["approvals_needed"])})
        self.assertEqual([], reply["rescan_differences"])
        self.assertIn("amount * 1.25", (self.root / MODEL / "functions.tmdl").read_text(encoding="utf-8"))
        self.assertIn("Table.SelectRows(Source, each [Amount] <> null)",
                      (self.root / MODEL / "tables/Sales.tmdl").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
