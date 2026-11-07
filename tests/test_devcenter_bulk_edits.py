"""Issue #12: in-place bulk edits of the target, with no donor (operation source "Edit target").

1. The ``edit`` Merge Choice compiles to RENAME and SET_PROPERTIES, and the plan rewrites the
   target references of an edited name without the "renamed" block.
2. Each bulk operation (rename by text or regex, set property, move folder, delete with a
   Removal Policy) on a scope of row keys or compare filters, with skipped rows and reasons.
3. ``POST edit-preview`` is a read: it changes no revision and lists every rewritten reference.
4. ``target_edit_apply`` is a JS API write only (ADR 0003), with no HTTP route.
5. Acceptance (with the TOM bridge): rename 20 measures by regex in one plan. The preview shows
   every rewritten reference (model and report), the real guard apply passes the rescan check,
   and undo restores byte-identical files.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from backend.api.app import create_app
from backend.devcenter import contracts, http_routes, jsapi
from backend.devcenter.apply import desktop as desktop_states
from backend.devcenter.apply.service import ApplyService
from backend.devcenter.compare.extract import MODEL, REPORT, CompareObject, SourceObjects, model_objects
from backend.devcenter.compare.rows import SessionSource, build_rows
from backend.devcenter.plan.compiler import EDIT, PlanInput, compile_plan
from backend.devcenter.session.manager import DevCenterSessions
from backend.snapshots.manifest import source_manifest

REPOSITORY = Path(__file__).resolve().parents[1]
LAB = REPOSITORY / "tests" / "fixtures" / "merge_lab"
BRIDGE = REPOSITORY / "backend/adapters/tabular_metadata/dotnet/bin/Release/net8.0/TabularMetadata.dll"
SALES = "SalesA.SemanticModel/definition/tables/Sales.tmdl"
RENAME_TOTALS = {"kind": "rename", "find": "^Total (.*)$", "replace": "$1 Total", "regex": True}


class _Desktop:
    """Power BI Desktop is not running."""

    def state(self, target_root):  # noqa: ANN001 - the shape of the apply service's desktop bridge
        return desktop_states.NOT_OPEN


def _plan(target_model: dict, choices: dict, report: list[CompareObject] | None = None) -> dict:
    source = SessionSource("src-1", SourceObjects(model_objects(target_model), report or []))
    result = build_rows([source], target_model="src-1", target_report="src-1")
    return compile_plan(PlanInput(session_id="s", result=result, target_model="src-1", target_report="src-1",
                                  sources={"src-1": "Target"}, merge_choices=choices))


MODEL_DATA = {
    "tables": [{
        "name": "Sales", "lineageTag": "t-sales",
        "columns": [{"name": "Amount", "dataType": "decimal", "lineageTag": "c-amount"}],
        "measures": [
            {"name": "Total Sales", "expression": "SUM(Sales[Amount])", "lineageTag": "m-total"},
            {"name": "Double", "expression": "[Total Sales] * 2", "lineageTag": "m-double"},
        ],
    }],
}


class EditChoiceCompilerTests(unittest.TestCase):
    def test_edit_choice_renames_sets_properties_and_rewrites_references(self) -> None:
        plan = _plan(MODEL_DATA, {"measure:Sales/Total Sales": {"kind": EDIT, "new_name": "Revenue",
                                                                "set": {"format_string": "#,0", "is_hidden": True}}})
        self.assertEqual("valid", plan["status"], plan["blocking"])
        ops = {(op["op"], op["row_key"]): op for op in plan["operations"]}
        self.assertEqual("Revenue", ops[("RENAME", "measure:Sales/Total Sales")]["new_name"])
        self.assertEqual({"format_string": "#,0", "is_hidden": True},
                         ops[("SET_PROPERTIES", "measure:Sales/Total Sales")]["properties"])
        # The edited name is rewritten in its dependent with no "renamed" block and no include action.
        self.assertEqual("[Revenue] * 2", ops[("REWRITE_EXPRESSION", "measure:Sales/Double")]["new_text"])
        self.assertEqual(1, plan["summary"]["model"]["renamed"]["total"])

    def test_a_value_equal_to_the_target_gives_no_operation_and_null_clears(self) -> None:
        plan = _plan(MODEL_DATA, {"measure:Sales/Double": {"kind": EDIT, "set": {"is_hidden": False}}})
        self.assertEqual([], plan["operations"])
        data = json.loads(json.dumps(MODEL_DATA))
        data["tables"][0]["measures"][1]["displayFolder"] = "KPI"
        plan = _plan(data, {"measure:Sales/Double": {"kind": EDIT, "set": {"display_folder": None}}})
        self.assertEqual({"display_folder": ""}, plan["operations"][0]["properties"])

    def test_invalid_edit_choices_block(self) -> None:
        report = [CompareObject(kind="page", subtype="page", domain=REPORT, source_key="page:P1", name="Page 1",
                                props={"display_name": "Page 1"}, extra={"page_id": "P1"})]
        cases = {
            "measure:Sales/Double": ({"kind": EDIT}, "no_edit"),
            "column:Sales/Amount": ({"kind": EDIT, "set": {"expression": "1"}}, "unknown_property"),
            "table:Sales": ({"kind": EDIT, "set": {"is_hidden": "yes"}}, "invalid_value"),
            "page:P1": ({"kind": EDIT, "new_name": "Other"}, "model_only"),
        }
        plan = _plan(MODEL_DATA, {key: choice for key, (choice, _) in cases.items()}, report)
        reasons = {item["row_key"]: item["params"]["reason"] for item in plan["blocking"] if item["kind"] == "choice_not_valid"}
        self.assertEqual({key: reason for key, (_, reason) in cases.items()}, reasons)

    def test_a_name_clash_of_an_edit_blocks(self) -> None:
        plan = _plan(MODEL_DATA, {"measure:Sales/Double": {"kind": EDIT, "new_name": "total sales"}})
        self.assertIn("name_clash", {item["kind"] for item in plan["blocking"]})


class _SessionCase(unittest.TestCase):
    """A session with a target and no donors, on a temp copy of the merge lab target."""

    def prepare(self) -> None:
        """Change the temp copy before the session reads it."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="i12-edit-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "project"
        shutil.copytree(LAB / "SalesA", self.root / "SalesA")
        self.prepare()
        self.devcenter = DevCenterSessions(app_data_dir=None)
        self.devcenter.attach_project(self.root)
        self.addCleanup(self.devcenter.close)
        self.app = create_app(use_native=False)
        self.app.devcenter = self.devcenter
        self.addCleanup(self.app.close)
        self.ok("session_create", {"display_name": "Edit target"})
        self.ok("source_add", {"base_revision": self.rev, "path": str(self.root / "SalesA" / "SalesA.pbip")})
        self.ok("target_set", {"base_revision": self.rev, "model": {"mode": "existing", "source_id": "src-1"},
                               "report": {"mode": "existing", "source_id": "src-1"}})

    @property
    def rev(self) -> int:
        return self.devcenter.revision

    def ok(self, method: str, request: dict) -> dict:
        reply = jsapi.call(self.devcenter, method, request)
        self.assertNotIn("error", reply, reply)
        self.assertEqual([], contracts.errors(contracts.jsapi_reply(method), reply), reply)
        return reply

    def preview(self, operation: dict, scope: dict, status: int = 200) -> dict:
        code, payload = self.app.handle("POST", "/api/devcenter/edit-preview", json.dumps({"operation": operation, "scope": scope}).encode())
        self.assertEqual(status, code, payload)
        if status == 200:
            self.assertEqual([], contracts.errors("http/edit-preview.reply.json", payload), payload)
        return payload

    def choices(self) -> dict:
        return self.devcenter._require_open().document["merge_choices"]


class BulkEditSessionTests(_SessionCase):

    def test_preview_is_a_read_and_lists_every_rewritten_reference(self) -> None:
        revision = self.rev
        reply = self.preview(RENAME_TOTALS, {"filter": {"type": "measure"}})
        self.assertEqual(revision, self.rev)
        self.assertEqual({}, self.choices())
        self.assertEqual({"Total Sales": "Sales Total", "Total Cost": "Cost Total"},
                         {item["name"]: item["change"]["new_name"] for item in reply["changes"]})
        self.assertEqual({"no_match"}, {item["reason"] for item in reply["skipped"]})
        found = {(item["kind"], item["domain"], item["row_key"]) for item in reply["references"]}
        self.assertEqual({
            ("expression", MODEL, "measure:Sales/Margin"),
            ("expression", MODEL, "measure:Sales/Sales With Tax"),
            ("expression", MODEL, "table:Metric Selector"),  # the field parameter (NAMEOF)
            ("expression", REPORT, "report_measure:Sales/Sales Target"),
            ("binding", REPORT, "visual:overview/totalsales"),
            ("binding", REPORT, "visual:detail/calendarmatrix"),
        }, found)
        margin = next(item for item in reply["references"] if item["row_key"] == "measure:Sales/Margin")
        self.assertEqual("[Sales Total] - [Cost Total]", margin["new_text"])
        self.assertEqual("valid", reply["plan"]["status"])

    def test_apply_stores_edit_choices_and_operations_combine_on_a_row(self) -> None:
        reply = self.ok("target_edit_apply", {"base_revision": self.rev, "operation": RENAME_TOTALS,
                                              "scope": {"row_keys": ["measure:Sales/Total Sales", "measure:Sales/Margin"]}})
        self.assertEqual(["measure:Sales/Total Sales"], reply["row_keys"])
        self.assertEqual([{"row_key": "measure:Sales/Margin", "reason": "no_match"}], reply["skipped"])
        self.ok("target_edit_apply", {"base_revision": self.rev, "operation": {"kind": "move_folder", "folder": " KPIs "},
                                      "scope": {"filter": {"type": "measure", "q": "sales"}}})
        self.assertEqual({"kind": EDIT, "new_name": "Sales Total", "set": {"display_folder": "KPIs"}},
                         self.choices()["measure:Sales/Total Sales"])
        # A second rename starts from the planned name.
        self.ok("target_edit_apply", {"base_revision": self.rev, "operation": {"kind": "rename", "find": "Sales", "replace": "Revenue"},
                                      "scope": {"row_keys": ["measure:Sales/Total Sales"]}})
        self.assertEqual("Revenue Total", self.choices()["measure:Sales/Total Sales"]["new_name"])
        log = [json.loads(line) for line in self.devcenter._require_open().files.log_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual("target_edit_apply", log[-1]["action"])

    def test_set_property_skips_and_delete_sets_the_removal_policy(self) -> None:
        reply = self.preview({"kind": "set_property", "property": "summarize_by", "value": "none"},
                             {"filter": {"type": "column", "table": "Sales"}})
        self.assertIn({"row_key": "column:Sales/Store Key", "reason": "no_change"}, reply["skipped"])
        self.assertIn("column:Sales/Amount", {item["row_key"] for item in reply["changes"]})
        reply = self.preview({"kind": "move_folder", "folder": "X"}, {"row_keys": ["table:Sales", "page:overview"]})
        self.assertEqual([{"row_key": "table:Sales", "reason": "no_folder"}, {"row_key": "page:overview", "reason": "no_target_object"}],
                         reply["skipped"])
        self.ok("target_edit_apply", {"base_revision": self.rev, "operation": {"kind": "delete", "policy": "cascade"},
                                      "scope": {"row_keys": ["measure:Sales/Total Cost"]}})
        document = self.devcenter._require_open().document
        self.assertEqual({"kind": "remove"}, document["merge_choices"]["measure:Sales/Total Cost"])
        self.assertEqual({"policy": "cascade"}, document["removal_policies"]["measure:Sales/Total Cost"])

    def test_apply_naming_rules_renames_only_the_objects_that_break_a_confirmed_rule(self) -> None:
        rule = {"rule_id": "rule-prefix", "object_type": "measure", "scope": {}, "status": "confirmed",
                "check": {"kind": "prefix", "value": "m "}, "origin": "user"}
        with mock.patch("backend.devcenter.plan.service._load_naming_rules", return_value=[rule]):
            reply = self.preview({"kind": "apply_naming_rules"}, {"filter": {"type": "measure"}})
            self.assertEqual({"m Total Sales", "m Total Cost", "m Margin", "m Sales With Tax"},
                             {item["change"]["new_name"] for item in reply["changes"]})
            self.assertEqual(["rule-prefix"], reply["changes"][0]["change"]["rule_ids"])
            self.assertIn("measure:Sales/Margin", {item["row_key"] for item in reply["references"]})
        with mock.patch("backend.devcenter.plan.service._load_naming_rules", return_value=[]):
            self.assertEqual("no_confirmed_rule", self.preview({"kind": "apply_naming_rules"}, {"filter": {}}, 400)
                             ["error"]["details"]["reason"])

    def test_bad_requests(self) -> None:
        self.assertEqual("invalid_regex", self.preview({"kind": "rename", "find": "(", "regex": True},
                                                       {"filter": {}}, 400)["error"]["details"]["reason"])
        self.assertEqual("invalid_payload", self.preview({"kind": "explode"}, {"filter": {}}, 400)["error"]["code"])
        self.assertEqual(404, self.app.handle("POST", "/api/devcenter/edit-preview", json.dumps(
            {"operation": RENAME_TOTALS, "scope": {"row_keys": ["measure:Sales/Nope"]}}).encode())[0])
        error = jsapi.call(self.devcenter, "target_edit_apply", {"base_revision": self.rev, "operation": RENAME_TOTALS,
                                                                 "scope": {"row_keys": ["measure:Sales/Margin"]}})["error"]
        self.assertEqual("no_change", error["details"]["reason"])

    def test_no_http_route_writes_an_edit(self) -> None:
        routes = {(route.method, "/".join(route.path)): route.kind for route in http_routes.ROUTES}
        self.assertEqual(http_routes.READ, routes[("POST", "edit-preview")])
        self.assertNotIn("target_edit_apply", {path for _, path in routes})
        code, _ = self.app.handle("POST", "/api/devcenter/target_edit_apply", b"{}")
        self.assertNotEqual(200, code)


@unittest.skipUnless(BRIDGE.is_file(), "Build the TOM bridge first")
class BulkRenameAcceptanceTests(_SessionCase):
    """The acceptance of issue #12 with the real plan, the real guard, and the real promotion."""

    def prepare(self) -> None:
        from backend.adapters.tabular_metadata import TabularMetadataAdapter

        temporary = tempfile.TemporaryDirectory(prefix="i12-model-")
        self.addCleanup(temporary.cleanup)
        source = LAB / "SalesA" / "SalesA.SemanticModel"
        operations = [{"op": "CREATE", "object_type": "measure", "subtype": "measure", "table": "Sales", "name": f"KPI {number:02}",
                       "lineage_tag": f"m-kpi-{number:02}",
                       "properties": {"expression": "[Total Sales] * 2" if number == 1 else f"[KPI {number - 1:02}] + [Total Cost]"}}
                      for number in range(1, 20)]
        output = Path(temporary.name) / "model"
        TabularMetadataAdapter().write_model(source, output, operations)
        # The model library writes the canonical file, so the apply is not blocked by the format check.
        shutil.copyfile(output / "tables" / "Sales.tmdl", self.root / "SalesA" / SALES)

    def test_rename_20_measures_by_regex_apply_rescan_and_undo(self) -> None:
        operation = {"kind": "rename", "find": r"^(KPI \d+|Total Sales)$", "replace": "$1 (A)", "regex": True}
        scope = {"filter": {"type": "measure", "table": "Sales"}}
        preview = self.preview(operation, scope)
        self.assertEqual(20, len(preview["changes"]))
        self.assertEqual("valid", preview["plan"]["status"], preview["plan"]["blocking"])
        rewritten = {item["row_key"]: item for item in preview["references"]}
        # Every model dependent of a renamed measure, in DAX and the field parameter.
        for number in range(2, 20):
            self.assertIn(f"measure:Sales/KPI {number:02}", rewritten)
        self.assertEqual("[KPI 01 (A)] + [Total Cost]", rewritten["measure:Sales/KPI 02"]["new_text"])
        for key in ("measure:Sales/Margin", "measure:Sales/Sales With Tax", "table:Metric Selector",
                    "report_measure:Sales/Sales Target", "visual:overview/totalsales", "visual:detail/calendarmatrix"):
            self.assertIn(key, rewritten)
        self.assertEqual(preview["references_total"], len(preview["references"]))

        self.ok("target_edit_apply", {"base_revision": self.rev, "operation": operation, "scope": scope})
        self.devcenter.apply_service = ApplyService(self.devcenter, desktop=_Desktop())
        original = {item["path"]: (self.root / "SalesA" / item["path"]).read_bytes() for item in source_manifest(self.root / "SalesA")}
        code, apply_preview = self.app.handle("GET", "/api/devcenter/apply/preview")
        self.assertEqual(200, code, apply_preview)
        self.assertTrue(apply_preview["ready"], apply_preview)
        self.assertEqual(preview["plan"]["plan_hash"], apply_preview["plan_hash"])
        reply = self.ok("apply", {"base_revision": self.rev, "plan_hash": apply_preview["plan_hash"],
                                  "approvals": sorted(item["purpose"] for item in apply_preview["approvals_needed"])})
        self.assertEqual([], reply["rescan_differences"])
        text = (self.root / "SalesA" / SALES).read_text(encoding="utf-8")
        self.assertIn("measure 'KPI 02 (A)' = [KPI 01 (A)] + [Total Cost]", text)
        self.assertNotIn("'KPI 19'", text)
        undo = self.ok("undo_apply", {"base_revision": self.rev})
        self.assertEqual([], undo["rescan_differences"])
        restored = {item["path"]: (self.root / "SalesA" / item["path"]).read_bytes() for item in source_manifest(self.root / "SalesA")}
        self.assertEqual(original, restored)


@unittest.skipUnless(BRIDGE.is_file(), "Build the TOM bridge first")
class SetPropertyGuardTests(_SessionCase):
    """Mark a date table (data category and key column) and describe columns, through the real guard."""

    def test_mark_date_table_and_describe_columns(self) -> None:
        for operation, scope in (
            ({"kind": "set_property", "property": "data_category", "value": "Time"}, {"row_keys": ["table:Date"]}),
            ({"kind": "set_property", "property": "is_key", "value": True}, {"row_keys": ["column:Date/Date"]}),
            ({"kind": "set_property", "property": "description", "value": "Money"}, {"filter": {"type": "column", "table": "Sales", "q": "o"}}),
            ({"kind": "set_property", "property": "is_hidden", "value": True}, {"filter": {"type": "column", "q": "key"}}),
        ):
            self.ok("target_edit_apply", {"base_revision": self.rev, "operation": operation, "scope": scope})
        self.devcenter.apply_service = ApplyService(self.devcenter, desktop=_Desktop())
        code, preview = self.app.handle("GET", "/api/devcenter/apply/preview")
        self.assertTrue(preview["ready"], preview)
        reply = self.ok("apply", {"base_revision": self.rev, "plan_hash": preview["plan_hash"],
                                  "approvals": sorted(item["purpose"] for item in preview["approvals_needed"])})
        self.assertEqual([], reply["rescan_differences"])
        date = (self.root / "SalesA" / "SalesA.SemanticModel/definition/tables/Date.tmdl").read_text(encoding="utf-8")
        self.assertIn("dataCategory: Time", date)
        self.assertIn("isKey", date)
        sales = (self.root / "SalesA" / SALES).read_text(encoding="utf-8")
        self.assertIn("/// Money", sales)
        self.assertIn("isHidden", sales)


if __name__ == "__main__":
    unittest.main()
