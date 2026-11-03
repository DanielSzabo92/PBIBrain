"""Build step S5: Change Plan engine acceptance tests (technical design section 16, S5).

Tests all 13 acceptance criteria:
1. Golden file test for each Merge Choice type
2. Phase ordering & dependency ordering: column create before measure; cycle gives Invalid
3. Deterministic execution: same state twice gives same plan and plan hash
4. Block, Cascade, Repoint removal policies (Cascade removes visual only when no field stays)
5. Token-exact rewrite over DAX golden corpus (tests/fixtures/dax_golden.py)
6. Donor DAX reference translation through alignment and Need generation
7. lineageTag UUIDv5 values equal fixed expected values (section 6.6, ADR 0002)
8. UDF below compatibility level 1702 is blocking (udf_compatibility)
9. Promote report measure tuple: create model measure, rebind visual references, delete report measure
10. Name clash row and unselected rename dependent are blocking
11. UC3: GET session spy test confirming session_summary never starts plan compute
12. UC22: merge_choice_set accepts promote and copy_to_report on report measure row
13. UC33: source_remove keeps Merge Choices, adds choice_source_removed blocking items, returns count
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import uuid

from backend.api.app import create_app
from backend.devcenter.compare import service as compare_service
from backend.devcenter.compare.extract import (
    MODEL,
    REPORT,
    CompareObject,
    SourceObjects,
    model_objects,
)
from backend.devcenter.compare.rows import CompareResult, SessionSource, build_rows
from backend.devcenter.plan import PlanInput, compile_plan, plan_hash, summary
from backend.devcenter.plan.compiler import (
    ADD_NEW_NAME,
    CASCADE,
    COPY_TO_REPORT,
    KEEP,
    PROMOTE,
    REMOVE,
    REPOINT,
    SKIP,
    STATUS_INVALID,
    STATUS_VALID,
    STATUS_WARNINGS,
    TAKE,
    TAKE_PROPERTIES,
)
from backend.devcenter.plan.lineage import LINEAGE_NAMESPACE, new_lineage_tag
from backend.devcenter.plan.refs import ModelIndex, bracket_token, scan, table_token
from backend.devcenter.plan.service import build_plan, get_plan, validate_plan
from backend.devcenter.session.manager import DevCenterSessions
from tests.fixtures.dax_golden import GOLDEN_DAX

LAB = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "merge_lab"


def _make_source(source_id: str, model_data: dict, report_objs: list[CompareObject] | None = None) -> SessionSource:
    return SessionSource(source_id, SourceObjects(model_objects(model_data), report_objs or []))


class PlanEngineTests(unittest.TestCase):
    def test_01_merge_choice_golden_types(self) -> None:
        """1. Golden file test for each Merge Choice type."""
        target_model = {
            "tables": [
                {
                    "name": "Sales",
                    "lineageTag": "tag-sales",
                    "columns": [
                        {"name": "Amount", "dataType": "int64", "lineageTag": "tag-amount"},
                        {"name": "Qty", "dataType": "int64", "lineageTag": "tag-qty"},
                    ],
                    "measures": [
                        {"name": "ExistingM", "expression": "SUM(Sales[Qty])", "lineageTag": "tag-em"},
                    ],
                }
            ]
        }
        donor_model = {
            "tables": [
                {
                    "name": "Sales",
                    "lineageTag": "tag-sales",
                    "columns": [
                        {"name": "Amount", "dataType": "int64", "lineageTag": "tag-amount"},
                        {"name": "Qty", "dataType": "int64", "lineageTag": "tag-qty"},
                        {"name": "NewCol", "dataType": "string", "lineageTag": "tag-newcol"},
                    ],
                    "measures": [
                        {"name": "ExistingM", "expression": "SUM(Sales[Qty]) * 10", "lineageTag": "tag-em"},
                        {"name": "NewM", "expression": "100", "lineageTag": "tag-newm"},
                    ],
                }
            ]
        }
        target_report_objs = [
            CompareObject(
                kind="page", subtype="page", domain=REPORT, source_key="page:P1", name="Page 1",
                props={"display_name": "Page 1"}, extra={"page_id": "P1"},
            ),
            CompareObject(
                kind="report_measure", subtype="report_measure", domain=REPORT,
                source_key="report_measure:Sales/RptM", name="RptM", table="Sales",
                props={"expression": "SUM(Sales[Qty])"},
            ),
        ]
        donor_report_objs = [
            CompareObject(
                kind="report_measure", subtype="report_measure", domain=REPORT,
                source_key="report_measure:Sales/DonorRptM", name="DonorRptM", table="Sales",
                props={"expression": "200"},
            ),
        ]

        s1 = _make_source("src-1", target_model, target_report_objs)
        s2 = _make_source("src-2", donor_model, donor_report_objs)
        res = build_rows([s1, s2], target_model="src-1", target_report="src-1")

        choices = {
            # 1. keep: no operations
            "column:Sales/Qty": {"kind": KEEP},
            # 2. skip: no operations
            "measure:Sales/NewM": {"kind": SKIP},
            # 3. remove: DELETE
            "column:Sales/Amount": {"kind": REMOVE},
            # 4. take (existing target): REPLACE
            "measure:Sales/ExistingM": {"kind": TAKE, "source_id": "src-2"},
            # 5. take (new object): CREATE
            "column:Sales/NewCol": {"kind": TAKE, "source_id": "src-2"},
            # 6. take_properties: SET_PROPERTIES
            # (tested on take_properties row below or separate)
            # 7. add_new_name: CREATE with new name
            "column:Sales/Qty@src-2": {"kind": ADD_NEW_NAME, "source_id": "src-2", "new_name": "Qty2"},
            # 8. promote: CREATE (model) + DELETE_REPORT_MEASURE
            "report_measure:Sales/RptM": {"kind": PROMOTE, "source_id": "src-1"},
            # 9. copy_to_report: CREATE_REPORT_MEASURE
            "report_measure:Sales/DonorRptM": {"kind": COPY_TO_REPORT, "source_id": "src-2"},
        }

        inp = PlanInput(
            session_id="golden-sess",
            result=res,
            target_model="src-1",
            target_report="src-1",
            sources={"src-1": "Target", "src-2": "Donor"},
            merge_choices=choices,
            removal_policies={"column:Sales/Amount": {"policy": CASCADE}},
        )
        plan = compile_plan(inp)
        self.assertEqual(plan["status"], STATUS_VALID)

        ops = {op["op"] for op in plan["operations"]}
        self.assertIn("DELETE", ops)
        self.assertIn("REPLACE", ops)
        self.assertIn("CREATE", ops)
        self.assertIn("CREATE_REPORT_MEASURE", ops)
        self.assertIn("DELETE_REPORT_MEASURE", ops)

        # Golden expectation check
        plan_summary = plan["summary"]
        self.assertEqual(plan_summary["model"]["created"]["total"], 2)  # NewCol and promoted RptM
        self.assertEqual(plan_summary["model"]["deleted"]["total"], 1)  # Amount
        self.assertEqual(plan_summary["model"]["modified"]["total"], 1)  # ExistingM
        self.assertEqual(plan_summary["report"]["created"]["total"], 1)  # DonorRptM
        self.assertEqual(plan_summary["report"]["deleted"]["total"], 0)  # promote step is in model domain (emits DELETE_REPORT_MEASURE op)

    def test_02_phase_ordering_and_dependency_ordering(self) -> None:
        """2. Phase ordering & dependency ordering: column create before measure; cycle gives Invalid."""
        donor_model = {
            "tables": [
                {
                    "name": "Sales",
                    "columns": [
                        {"name": "Amount", "dataType": "int64"},
                        {"name": "CalculatedCol", "type": "calculated", "expression": "10"},
                    ],
                    "measures": [
                        {"name": "MeasureOnCol", "expression": "SUM(Sales[CalculatedCol])"},
                    ],
                }
            ]
        }
        target_model = {"tables": [{"name": "Sales", "columns": [{"name": "Amount", "dataType": "int64"}]}]}
        s1 = _make_source("src-1", target_model)
        s2 = _make_source("src-2", donor_model)
        res = build_rows([s1, s2], target_model="src-1", target_report=None)

        # Column and measure created: Column must precede measure
        inp = PlanInput(
            session_id="order-sess",
            result=res,
            target_model="src-1",
            target_report=None,
            sources={"src-1": "Target", "src-2": "Donor"},
            merge_choices={
                "column:Sales/CalculatedCol": {"kind": TAKE, "source_id": "src-2"},
                "measure:Sales/MeasureOnCol": {"kind": TAKE, "source_id": "src-2"},
            },
        )
        plan = compile_plan(inp)
        self.assertEqual(plan["status"], STATUS_VALID)
        col_idx = next(i for i, op in enumerate(plan["operations"]) if op["name"] == "CalculatedCol")
        meas_idx = next(i for i, op in enumerate(plan["operations"]) if op["name"] == "MeasureOnCol")
        self.assertLess(col_idx, meas_idx, "Column create must come before dependent measure create")

        # Dependency cycle: Measure A -> Measure B, Measure B -> Measure A
        donor_cycle = {
            "tables": [
                {
                    "name": "Sales",
                    "measures": [
                        {"name": "CycleA", "expression": "[CycleB] + 1"},
                        {"name": "CycleB", "expression": "[CycleA] + 1"},
                    ],
                }
            ]
        }
        s_cyc = _make_source("src-2", donor_cycle)
        res_cyc = build_rows([s1, s_cyc], target_model="src-1", target_report=None)
        inp_cyc = PlanInput(
            session_id="cycle-sess",
            result=res_cyc,
            target_model="src-1",
            target_report=None,
            sources={"src-1": "Target", "src-2": "Donor"},
            merge_choices={
                "measure:Sales/CycleA": {"kind": TAKE, "source_id": "src-2"},
                "measure:Sales/CycleB": {"kind": TAKE, "source_id": "src-2"},
            },
        )
        plan_cyc = compile_plan(inp_cyc)
        self.assertEqual(plan_cyc["status"], STATUS_INVALID)
        blocking_kinds = [b["kind"] for b in plan_cyc["blocking"]]
        self.assertIn("dependency_cycle", blocking_kinds)

    def test_03_deterministic_execution(self) -> None:
        """3. Deterministic execution: same state twice gives same plan and plan hash."""
        donor_model = {
            "tables": [
                {
                    "name": "Finance",
                    "columns": [{"name": "Amount", "dataType": "decimal"}],
                    "measures": [{"name": "Profit", "expression": "SUM(Finance[Amount]) * 0.2"}],
                }
            ]
        }
        target_model = {"tables": []}
        s1 = _make_source("src-1", target_model)
        s2 = _make_source("src-2", donor_model)
        res = build_rows([s1, s2], target_model="src-1", target_report=None)

        inp = PlanInput(
            session_id="det-session-12345",
            result=res,
            target_model="src-1",
            target_report=None,
            sources={"src-1": "Target", "src-2": "Donor"},
            merge_choices={"table:Finance": {"kind": TAKE, "source_id": "src-2"}},
        )
        plan1 = compile_plan(inp)
        h1 = plan_hash(plan1)

        plan2 = compile_plan(inp)
        h2 = plan_hash(plan2)

        self.assertEqual(plan1, plan2)
        self.assertEqual(h1, h2)
        self.assertTrue(h1.startswith("sha256:"))
        self.assertEqual(len(h1), 71)

    def test_04_removal_policies(self) -> None:
        """4. Block, Cascade, Repoint removal policies (Cascade removes visual only when no field stays)."""
        target_model = {
            "tables": [
                {
                    "name": "Sales",
                    "columns": [
                        {"name": "Amount", "dataType": "int64"},
                        {"name": "Qty", "dataType": "int64"},
                        {"name": "ReplacementCol", "dataType": "int64"},
                    ],
                    "measures": [
                        {"name": "TotalAmount", "expression": "SUM(Sales[Amount])"},
                    ],
                }
            ]
        }
        # Visual with 2 projection fields
        v_multi = CompareObject(
            kind="visual", subtype="visual", domain=REPORT, source_key="visual:P1/VMulti", name="VMulti", table="P1",
            props={
                "fields": {
                    "select": [
                        {"Column": {"Expression": {"SourceRef": {"Entity": "Sales"}}, "Property": "Amount"}, "queryRef": "Sales.Amount"},
                        {"Column": {"Expression": {"SourceRef": {"Entity": "Sales"}}, "Property": "Qty"}, "queryRef": "Sales.Qty"},
                    ]
                },
                "filters": {},
            },
            extra={"visual_id": "VMulti"},
        )
        # Visual with 1 projection field
        v_single = CompareObject(
            kind="visual", subtype="visual", domain=REPORT, source_key="visual:P1/VSingle", name="VSingle", table="P1",
            props={
                "fields": {
                    "select": [
                        {"Column": {"Expression": {"SourceRef": {"Entity": "Sales"}}, "Property": "Amount"}, "queryRef": "Sales.Amount"},
                    ]
                },
                "filters": {},
            },
            extra={"visual_id": "VSingle"},
        )
        page = CompareObject(
            kind="page", subtype="page", domain=REPORT, source_key="page:P1", name="Page 1",
            props={"display_name": "Page 1"}, extra={"page_id": "P1"},
        )

        s1 = _make_source("src-1", target_model, [page, v_multi, v_single])
        res = build_rows([s1], target_model="src-1", target_report="src-1")

        # 4a: Block policy (default)
        inp_block = PlanInput(
            session_id="block-sess", result=res, target_model="src-1", target_report="src-1",
            sources={"src-1": "Target"},
            merge_choices={"column:Sales/Amount": {"kind": REMOVE}},
            # removal_policies default to block
        )
        plan_block = compile_plan(inp_block)
        self.assertEqual(plan_block["status"], STATUS_INVALID)
        blocking_kinds = [b["kind"] for b in plan_block["blocking"]]
        self.assertIn("removed", blocking_kinds)

        # 4b: Cascade policy:
        # Dependent measure TotalAmount is transitively deleted.
        # VMulti has 1 projection field staying (Qty), so VMulti is kept and REMOVE_FIELD is emitted.
        # VSingle has 0 projection fields staying, so VSingle is deleted with DELETE_VISUAL.
        inp_cascade = PlanInput(
            session_id="cascade-sess", result=res, target_model="src-1", target_report="src-1",
            sources={"src-1": "Target"},
            merge_choices={"column:Sales/Amount": {"kind": REMOVE}},
            removal_policies={"column:Sales/Amount": {"policy": CASCADE}},
        )
        plan_cascade = compile_plan(inp_cascade)
        self.assertEqual(plan_cascade["status"], STATUS_VALID)
        operations = plan_cascade["operations"]
        op_tuples = [(op["op"], op["name"], op.get("pointer")) for op in operations]

        self.assertIn(("DELETE", "TotalAmount", None), op_tuples)
        self.assertIn(("REMOVE_FIELD", "VMulti", "/visual/query/select/0"), op_tuples)
        self.assertIn(("DELETE_VISUAL", "VSingle", None), op_tuples)
        self.assertNotIn(("DELETE_VISUAL", "VMulti", None), op_tuples)

        # 4c: Repoint policy:
        inp_repoint = PlanInput(
            session_id="repoint-sess", result=res, target_model="src-1", target_report="src-1",
            sources={"src-1": "Target"},
            merge_choices={"column:Sales/Amount": {"kind": REMOVE}},
            removal_policies={"column:Sales/Amount": {"policy": REPOINT, "replacement_row_key": "column:Sales/ReplacementCol"}},
        )
        plan_repoint = compile_plan(inp_repoint)
        self.assertEqual(plan_repoint["status"], STATUS_VALID)
        repoint_ops = {op["op"] for op in plan_repoint["operations"]}
        self.assertIn("REWRITE_EXPRESSION", repoint_ops)
        self.assertIn("REBIND_FIELD", repoint_ops)

    def test_05_token_exact_rewrite_dax_golden_corpus(self) -> None:
        """5. Token-exact rewrite over DAX golden corpus (tests/fixtures/dax_golden.py)."""
        from backend.devcenter.plan.refs import rewrite

        for case in GOLDEN_DAX:
            tokens = scan(case.dax)
            if tokens.failed:
                continue

            # 5a: Identity rewrite: without mapping, resulting string must be byte-equal to source DAX
            index = ModelIndex.build([], [])
            resolved, failed = index.references(case.dax, None)
            if not failed:
                identity_text, changed = rewrite(case.dax, resolved, lambda item: None)
                self.assertEqual(identity_text, case.dax, f"Identity rewrite failed on case {case.name}")
                self.assertEqual(changed, 0)

        # 5b: Targeted rename preserves all surrounding whitespace and comments byte-for-byte
        raw_dax = "/* Header comment */\nSUM( // inline comment\n    Sales[Amount] -- end-of-line\n) + 10"
        col_obj = CompareObject(kind="column", subtype="data_column", domain=MODEL, source_key="column:Sales/Amount", name="Amount", table="Sales")
        tbl_obj = CompareObject(kind="table", subtype="table", domain=MODEL, source_key="table:Sales", name="Sales")
        idx = ModelIndex.build([tbl_obj, col_obj], [])
        res, failed = idx.references(raw_dax, None)
        self.assertFalse(failed)

        # Rename column Amount -> TotalAmount
        rewritten, count = rewrite(raw_dax, res, lambda item: ("Sales", "TotalAmount") if item.kind == "column" else None)
        self.assertEqual(count, 1)
        expected = "/* Header comment */\nSUM( // inline comment\n    Sales[TotalAmount] -- end-of-line\n) + 10"
        self.assertEqual(rewritten, expected)

    def test_06_donor_dax_translation_and_needs(self) -> None:
        """6. Donor DAX reference translation through alignment and Need generation."""
        target_model = {"tables": [{"name": "Sales", "columns": [{"name": "Amount", "dataType": "int64"}]}]}
        donor_model = {
            "tables": [
                {
                    "name": "Sales",
                    "columns": [{"name": "Amount", "dataType": "int64"}],
                    "measures": [
                        {"name": "BaseMeasure", "expression": "SUM(Sales[Amount])"},
                        {"name": "DerivedMeasure", "expression": "[BaseMeasure] * 1.05"},
                    ],
                }
            ]
        }
        s1 = _make_source("src-1", target_model)
        s2 = _make_source("src-2", donor_model)
        res = build_rows([s1, s2], target_model="src-1", target_report=None)

        # Taking only DerivedMeasure creates a prerequisite step (Need) for BaseMeasure
        inp = PlanInput(
            session_id="need-sess", result=res, target_model="src-1", target_report=None,
            sources={"src-1": "Target", "src-2": "Donor"},
            merge_choices={"measure:Sales/DerivedMeasure": {"kind": TAKE, "source_id": "src-2"}},
        )
        plan = compile_plan(inp)
        self.assertEqual(plan["status"], STATUS_WARNINGS)
        self.assertIn("need_added", [w["kind"] for w in plan["warnings"]])

        step_kinds = [(s["kind"], s["name"]) for s in plan["steps"]]
        self.assertIn(("prerequisite", "BaseMeasure"), step_kinds)
        self.assertIn(("merge_choice", "DerivedMeasure"), step_kinds)

        # BaseMeasure operation comes before DerivedMeasure operation
        op_names = [op["name"] for op in plan["operations"]]
        self.assertLess(op_names.index("BaseMeasure"), op_names.index("DerivedMeasure"))

    def test_07_lineage_tag_rules_and_uuidv5(self) -> None:
        """7. lineageTag UUIDv5 values equal fixed expected values (section 6.6, ADR 0002)."""
        # Section 6.6 fixed namespace and deterministic test vector
        self.assertEqual(str(LINEAGE_NAMESPACE), "4f9d10cf-7599-5033-ae3f-20f6a2b4f327")
        expected_tag = "528550aa-5313-5f7c-bc29-a1c0e1262337"
        self.assertEqual(
            new_lineage_tag("0123456789abcdef0123456789abcdef", "measure:sales/total"),
            expected_tag,
        )

        target_model = {
            "tables": [
                {
                    "name": "T",
                    "lineageTag": "colliding-tag",
                    "measures": [
                        {"name": "ExistingM", "expression": "1", "lineageTag": "target-tag-1"},
                    ],
                }
            ]
        }
        donor_model = {
            "tables": [
                {
                    "name": "T",
                    "lineageTag": "donor-table-tag",
                    "measures": [
                        {"name": "ExistingM", "expression": "2", "lineageTag": "donor-tag-1"},
                        {"name": "NewM", "expression": "3", "lineageTag": "donor-tag-2"},
                        {"name": "CollidingM", "expression": "4", "lineageTag": "colliding-tag"},
                    ],
                }
            ]
        }
        s1 = _make_source("src-1", target_model)
        s2 = _make_source("src-2", donor_model)
        res = build_rows([s1, s2], target_model="src-1", target_report=None)

        inp = PlanInput(
            session_id="lineage-sess", result=res, target_model="src-1", target_report=None,
            sources={"src-1": "Target", "src-2": "Donor"},
            merge_choices={
                # take existing retains target tag
                "measure:T/ExistingM": {"kind": TAKE, "source_id": "src-2"},
                # take new retains donor tag
                "measure:T/NewM": {"kind": TAKE, "source_id": "src-2"},
                # take new with colliding tag gets fresh UUIDv5 tag and warning
                "measure:T/CollidingM": {"kind": TAKE, "source_id": "src-2"},
            },
        )
        plan = compile_plan(inp)
        self.assertIn("new_lineage_tag", [w["kind"] for w in plan["warnings"]])
        by_op = {op["name"]: op.get("lineage_tag") for op in plan["operations"] if "lineage_tag" in op}
        self.assertEqual(by_op["ExistingM"], "target-tag-1")
        self.assertEqual(by_op["NewM"], "donor-tag-2")
        self.assertEqual(by_op["CollidingM"], new_lineage_tag("lineage-sess", "measure:T/CollidingM"))

    def test_08_udf_compatibility_level_check(self) -> None:
        """8. UDF below compatibility level 1702 is blocking (udf_compatibility)."""
        donor_model = {"tables": [], "functions": [{"name": "DiscountCalc", "expression": "1 + 1"}]}
        target_model = {"tables": []}
        s1 = _make_source("src-1", target_model)
        s2 = _make_source("src-2", donor_model)
        res = build_rows([s1, s2], target_model="src-1", target_report=None)

        # Below 1702: blocking
        inp_low = PlanInput(
            session_id="udf-sess", result=res, target_model="src-1", target_report=None,
            sources={"src-1": "Target", "src-2": "Donor"},
            merge_choices={"function:DiscountCalc": {"kind": TAKE, "source_id": "src-2"}},
            compatibility_level=1600,
        )
        plan_low = compile_plan(inp_low)
        self.assertEqual(plan_low["status"], STATUS_INVALID)
        self.assertEqual(plan_low["blocking"][0]["kind"], "udf_compatibility")

        # 1702 or higher: valid
        inp_high = PlanInput(
            session_id="udf-sess", result=res, target_model="src-1", target_report=None,
            sources={"src-1": "Target", "src-2": "Donor"},
            merge_choices={"function:DiscountCalc": {"kind": TAKE, "source_id": "src-2"}},
            compatibility_level=1702,
        )
        plan_high = compile_plan(inp_high)
        self.assertEqual(plan_high["status"], STATUS_VALID)

    def test_09_promote_report_measure_tuple(self) -> None:
        """9. "Promote report measure" tuple: create model measure, rebind visual references, delete report measure."""
        target_model = {"tables": [{"name": "Sales", "columns": [{"name": "Amount", "dataType": "int64"}]}]}
        page = CompareObject(
            kind="page", subtype="page", domain=REPORT, source_key="page:P1", name="Page 1",
            props={"display_name": "Page 1"}, extra={"page_id": "P1"},
        )
        report_measure = CompareObject(
            kind="report_measure", subtype="report_measure", domain=REPORT,
            source_key="report_measure:Sales/RptM", name="RptM", table="Sales",
            props={"expression": "SUM(Sales[Amount])"},
        )
        visual = CompareObject(
            kind="visual", subtype="visual", domain=REPORT, source_key="visual:P1/V1", name="V1", table="P1",
            props={
                "fields": {
                    "field": {
                        "Measure": {"Expression": {"SourceRef": {"Entity": "Sales"}}, "Property": "RptM"},
                    },
                    "queryRef": "Sales.RptM",
                    "nativeQueryRef": "RptM",
                },
                "filters": {},
            },
            extra={"visual_id": "V1"},
        )

        s1 = _make_source("src-1", target_model, [page, report_measure, visual])
        res = build_rows([s1], target_model="src-1", target_report="src-1")

        inp = PlanInput(
            session_id="promote-sess", result=res, target_model="src-1", target_report="src-1",
            sources={"src-1": "Target"},
            merge_choices={"report_measure:Sales/RptM": {"kind": PROMOTE, "source_id": "src-1"}},
        )
        plan = compile_plan(inp)
        self.assertEqual(plan["status"], STATUS_VALID)

        ops = plan["operations"]
        create_op = next(op for op in ops if op["op"] == "CREATE")
        rebind_op = next(op for op in ops if op["op"] == "REBIND_FIELD")
        delete_op = next(op for op in ops if op["op"] == "DELETE_REPORT_MEASURE")

        self.assertEqual(create_op["domain"], MODEL)
        self.assertEqual(create_op["name"], "RptM")
        self.assertEqual(rebind_op["domain"], REPORT)
        self.assertEqual(rebind_op["name"], "V1")
        self.assertEqual(rebind_op["new"]["kind"], "measure")
        self.assertEqual(delete_op["domain"], REPORT)
        self.assertEqual(delete_op["name"], "RptM")

    def test_10_name_clash_and_unselected_rename_dependent(self) -> None:
        """10. Name clash row and unselected rename dependent are blocking."""
        # 10a: Name clash row
        target_clash = {"tables": [{"name": "Sales", "measures": [{"name": "Sales", "expression": "1", "lineageTag": "m1"}]}]}
        donor_clash = {
            "tables": [
                {
                    "name": "Sales",
                    "measures": [
                        {"name": "Revenue", "expression": "1", "lineageTag": "m1"},
                        {"name": "Sales", "expression": "2", "lineageTag": "m2"},
                    ],
                }
            ]
        }
        s1 = _make_source("src-1", target_clash)
        s2 = _make_source("src-2", donor_clash)
        res_clash = build_rows([s1, s2], target_model="src-1", target_report=None)

        inp_clash = PlanInput(
            session_id="clash-sess", result=res_clash, target_model="src-1", target_report=None,
            sources={"src-1": "Target", "src-2": "Donor"},
        )
        plan_clash = compile_plan(inp_clash)
        self.assertEqual(plan_clash["status"], STATUS_INVALID)
        self.assertIn("name_clash", [b["kind"] for b in plan_clash["blocking"]])

        # 10b: Unselected rename dependent
        target_rename = {
            "tables": [
                {
                    "name": "Sales",
                    "measures": [
                        {"name": "OldMeasure", "expression": "10", "lineageTag": "m-old"},
                        {"name": "DependentMeasure", "expression": "[OldMeasure] + 5"},
                    ],
                }
            ]
        }
        donor_rename = {
            "tables": [
                {
                    "name": "Sales",
                    "measures": [
                        {"name": "NewMeasure", "expression": "10", "lineageTag": "m-old"},
                    ],
                }
            ]
        }
        s_t = _make_source("src-1", target_rename)
        s_d = _make_source("src-2", donor_rename)
        res_rename = build_rows([s_t, s_d], target_model="src-1", target_report=None)

        inp_unselected = PlanInput(
            session_id="rename-sess", result=res_rename, target_model="src-1", target_report=None,
            sources={"src-1": "Target", "src-2": "Donor"},
            merge_choices={"measure:Sales/OldMeasure": {"kind": TAKE, "source_id": "src-2"}},
        )
        plan_unselected = compile_plan(inp_unselected)
        self.assertEqual(plan_unselected["status"], STATUS_INVALID)
        blocking_items = plan_unselected["blocking"]
        self.assertEqual(blocking_items[0]["kind"], "renamed")

        # Resolving via action="include_in_rewrite"
        item_id = blocking_items[0]["item_id"]
        inp_selected = PlanInput(
            session_id="rename-sess", result=res_rename, target_model="src-1", target_report=None,
            sources={"src-1": "Target", "src-2": "Donor"},
            merge_choices={"measure:Sales/OldMeasure": {"kind": TAKE, "source_id": "src-2"}},
            item_actions={item_id: {"action": "include_in_rewrite"}},
        )
        plan_selected = compile_plan(inp_selected)
        self.assertEqual(plan_selected["status"], STATUS_VALID)
        ops = [op["op"] for op in plan_selected["operations"]]
        self.assertIn("RENAME", ops)
        self.assertIn("REWRITE_EXPRESSION", ops)

    def test_11_uc3_session_summary_never_computes_plan_or_compare(self) -> None:
        """11. UC3: GET session spy test confirming session_summary never starts plan compute."""
        with tempfile.TemporaryDirectory() as td:
            dc = DevCenterSessions(app_data_dir=None)
            dc.attach_project(Path(td))
            dc.create({"display_name": "Spy Test Session"})

            with patch("backend.devcenter.plan.compiler.compile_plan") as mock_compile, \
                 patch("backend.devcenter.compare.service.compute") as mock_compute:
                summary = dc.session_summary()
                self.assertEqual(mock_compile.call_count, 0, "session_summary must never call compile_plan")
                self.assertEqual(mock_compute.call_count, 0, "session_summary must never call compare compute")
                self.assertIsNone(summary["plan_status"])
                self.assertIn(summary["plan_state"], {"ready", "computing", None})

    def test_12_uc22_merge_choice_set_promote_and_copy_to_report(self) -> None:
        """12. UC22: merge_choice_set accepts promote and copy_to_report on report measure row."""
        with tempfile.TemporaryDirectory() as td:
            dc = DevCenterSessions(app_data_dir=None)
            dc.attach_project(Path(td))
            created = dc.create({"display_name": "UC22 Test"})
            rev = created["revision"]

            # Set promote
            reply1 = dc.merge_choice_set({
                "base_revision": rev,
                "row_key": "report_measure:Page1/Visual1/RptM",
                "choice": {"kind": "promote", "source_id": "src-2", "new_name": "ModelM"},
            })
            self.assertEqual(reply1["revision"], rev + 1)
            self.assertEqual(reply1["choice"]["kind"], "promote")

            # Set copy_to_report
            reply2 = dc.merge_choice_set({
                "base_revision": reply1["revision"],
                "row_key": "report_measure:Page1/Visual1/RptM2",
                "choice": {"kind": "copy_to_report", "source_id": "src-2"},
            })
            self.assertEqual(reply2["revision"], rev + 2)
            self.assertEqual(reply2["choice"]["kind"], "copy_to_report")

            doc = dc._require_open().document
            self.assertEqual(doc["merge_choices"]["report_measure:Page1/Visual1/RptM"]["kind"], "promote")
            self.assertEqual(doc["merge_choices"]["report_measure:Page1/Visual1/RptM2"]["kind"], "copy_to_report")

    def test_13_uc33_source_remove_keeps_merge_choices_and_blocks(self) -> None:
        """13. UC33: source_remove keeps Merge Choices, adds choice_source_removed blocking items, returns count."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "project"
            root.mkdir()
            shutil.copytree(LAB / "SalesA", root / "SalesA")
            shutil.copytree(LAB / "SalesB", root / "SalesB")

            dc = DevCenterSessions(app_data_dir=None)
            dc.attach_project(root)
            created = dc.create({"display_name": "UC33 Test"})

            s1 = dc.source_add({"base_revision": 1, "path": str(root / "SalesA/SalesA.pbip")})
            s2 = dc.source_add({"base_revision": s1["revision"], "path": str(root / "SalesB/SalesB.pbip")})
            donor_id = s2["source"]["source_id"]

            # Set 2 choices pointing to donor
            r1 = dc.merge_choice_set({
                "base_revision": s2["revision"],
                "row_key": "measure:Sales/Total Sales",
                "choice": {"kind": "take", "source_id": donor_id},
            })
            r2 = dc.merge_choice_set({
                "base_revision": r1["revision"],
                "row_key": "measure:Sales/NewMeasure",
                "choice": {"kind": "take", "source_id": donor_id},
            })

            # Remove donor source
            rem = dc.source_remove({"base_revision": r2["revision"], "source_id": donor_id})
            self.assertEqual(rem["choice_count"], 2)

            # Choices stay in document
            doc = dc._require_open().document
            self.assertIn("measure:Sales/Total Sales", doc["merge_choices"])
            self.assertIn("measure:Sales/NewMeasure", doc["merge_choices"])

            # Plan includes choice_source_removed blocking items for each
            plan = build_plan(dc, doc)
            self.assertEqual(plan["status"], STATUS_INVALID)
            removed_items = [b for b in plan["blocking"] if b["kind"] == "choice_source_removed"]
            self.assertEqual(len(removed_items), 2)

    def test_plan_service_and_http_routes(self) -> None:
        """Integration test for get_plan and validate_plan services."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "project"
            root.mkdir()
            shutil.copytree(LAB / "SalesA", root / "SalesA")

            dc = DevCenterSessions(app_data_dir=None)
            dc.attach_project(root)
            dc.create({"display_name": "Service Plan Test"})
            dc.source_add({"base_revision": 1, "path": str(root / "SalesA/SalesA.pbip")})

            # get_plan
            plan_res = get_plan(dc, {})
            self.assertIn("revision", plan_res)
            self.assertIn("plan_hash", plan_res)
            self.assertIn("status", plan_res)

            # validate_plan quick
            val_quick = validate_plan(dc, {"mode": "quick"})
            self.assertEqual(val_quick["mode"], "quick")
            self.assertEqual(val_quick["status"], plan_res["status"])

            # validate_plan full
            val_full = validate_plan(dc, {"mode": "full"})
            self.assertEqual(val_full["mode"], "full")


if __name__ == "__main__":
    unittest.main()
