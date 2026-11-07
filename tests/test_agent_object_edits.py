"""Issue #13: agent object edits through MCP, behind the safety layer.

1. New proposal kinds ``object_edit``, ``object_rename``, ``object_delete`` and ``object_create``
   go through the ``proposal_submit`` agent tool (the existing ``POST proposals`` route).
2. Each is checked on submit against the plan with it: a DAX parse error, a missing object, a
   name clash or a value the target cannot take is refused (``proposal_not_valid``) so the agent
   can fix it; otherwise the reply carries the plan blocking items and the Breaks/Needs impact.
3. Destructive kinds (a delete, a rename with Breaks, an expression change with Breaks) have
   ``needs_review``: "Accept all" skips them. Accept stays a JS API call (ADR 0003).
4. Acceptance (with the TOM bridge): the agent proposes a DAX change and a new measure, gets the
   impact back, the user accepts, apply writes TMDL and the rescan matches. A delete of a used
   measure is blocked until a Removal Policy is chosen.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest
from urllib.parse import urlencode

from backend.api.app import create_app
from backend.devcenter import contracts, jsapi
from backend.devcenter.agent_tools import AgentTools
from backend.devcenter.apply import desktop as desktop_states
from backend.devcenter.apply.service import ApplyService
from backend.devcenter.plan import service as plan_service
from backend.devcenter.plan.compiler import EDIT, PlanInput, compile_plan
from backend.devcenter.session.manager import DevCenterSessions
from tests.test_devcenter_agent_tools import route_of
from tests.test_devcenter_bulk_edits import MODEL_DATA, SessionSource, SourceObjects, build_rows, model_objects

REPOSITORY = Path(__file__).resolve().parents[1]
LAB = REPOSITORY / "tests" / "fixtures" / "merge_lab"
BRIDGE = REPOSITORY / "backend/adapters/tabular_metadata/dotnet/bin/Release/net8.0/TabularMetadata.dll"
SALES = "SalesA.SemanticModel/definition/tables/Sales.tmdl"
MARGIN = "measure:Sales/Margin"
TOTAL = "measure:Sales/Total Sales"
NEW_MARGIN_TEXT = "[Total Sales] - [Total Cost] * 1.1"
RATIO = {"object_type": "measure", "table": "Sales", "name": "Margin %",
         "properties": {"expression": "DIVIDE([Margin], [Total Sales])", "format_string": "0.0%"}}


class _Desktop:
    def state(self, target_root):  # noqa: ANN001 - the shape of the apply service's desktop bridge
        return desktop_states.NOT_OPEN


def _plan(choices: dict, created: dict | None = None) -> dict:
    source = SessionSource("src-1", SourceObjects(model_objects(MODEL_DATA), []))
    result = build_rows([source], target_model="src-1", target_report="src-1")
    return compile_plan(PlanInput(session_id="s", result=result, target_model="src-1", target_report="src-1",
                                  sources={"src-1": "Target"}, merge_choices=choices, created_objects=created or {}))


class CompilerTests(unittest.TestCase):
    def test_an_expression_edit_is_a_rewrite_resolved_against_the_target(self) -> None:
        plan = _plan({"measure:Sales/Double": {"kind": EDIT, "set": {"expression": "[Total Sales] * 3"}}})
        self.assertEqual("valid", plan["status"], plan["blocking"])
        [operation] = plan["operations"]
        self.assertEqual(("REWRITE_EXPRESSION", "[Total Sales] * 2", "[Total Sales] * 3"),
                         (operation["op"], operation["old_text"], operation["new_text"]))
        plan = _plan({"measure:Sales/Double": {"kind": EDIT, "set": {"expression": "[Nope] * 3"}}})
        self.assertEqual(["need_missing"], [item["kind"] for item in plan["blocking"]])

    def test_a_created_object_is_one_create_and_follows_a_rename_of_the_plan(self) -> None:
        created = {"new:measure:Sales/Triple": {"object_type": "measure", "table": "Sales", "name": "Triple",
                                                "properties": {"expression": "[Total Sales] * 3", "format_string": "0"}}}
        plan = _plan({"measure:Sales/Total Sales": {"kind": EDIT, "new_name": "Revenue"}}, created)
        self.assertEqual("valid", plan["status"], plan["blocking"])
        create = next(op for op in plan["operations"] if op["op"] == "CREATE")
        self.assertEqual(("measure", "Sales", "Triple"), (create["object_type"], create["table"], create["name"]))
        self.assertEqual({"expression": "[Revenue] * 3", "format_string": "0"}, create["properties"])
        self.assertTrue(create["lineage_tag"])
        rename = next(op for op in plan["operations"] if op["op"] == "RENAME")
        self.assertLess(rename["order"], create["order"])
        self.assertEqual("created", next(step for step in plan["steps"] if step["row_key"] == "new:measure:Sales/Triple")["change"])

    def test_a_created_object_with_a_clash_or_no_table_blocks(self) -> None:
        clash = {"new:measure:Sales/double": {"object_type": "measure", "table": "Sales", "name": "double",
                                              "properties": {"expression": "1"}}}
        self.assertIn("name_clash", {item["kind"] for item in _plan({}, clash)["blocking"]})
        nowhere = {"new:measure:Nope/X": {"object_type": "measure", "table": "Nope", "name": "X", "properties": {"expression": "1"}}}
        [item] = _plan({}, nowhere)["blocking"]
        self.assertEqual(("choice_not_valid", "no_table"), (item["kind"], item["params"]["reason"]))


class _AgentCase(unittest.TestCase):
    """A session with the SalesA target and no donor; the agent tools use an in-process transport."""

    def prepare(self) -> None:
        """Change the temp copy before the session reads it."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="i13-agent-")
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
        self.ok("session_create", {"display_name": "Agent edits"})
        self.ok("source_add", {"base_revision": self.rev, "path": str(self.root / "SalesA" / "SalesA.pbip")})
        self.ok("target_set", {"base_revision": self.rev, "model": {"mode": "existing", "source_id": "src-1"},
                               "report": {"mode": "existing", "source_id": "src-1"}})
        self.tools = AgentTools(self.send)

    @property
    def rev(self) -> int:
        return self.devcenter.revision

    def send(self, method: str, path: str, query, body) -> dict:
        url = "/api/devcenter/" + path + (f"?{urlencode(query)}" if query else "")
        _, payload = self.app.handle(method, url, json.dumps(body).encode("utf-8") if body is not None else None)
        contract = contracts.ERROR if "error" in payload else route_of(method, path).contract
        self.assertEqual([], contracts.errors(contract, payload), payload)
        return payload

    def ok(self, method: str, request: dict) -> dict:
        reply = jsapi.call(self.devcenter, method, request)
        self.assertNotIn("error", reply, reply)
        self.assertEqual([], contracts.errors(contracts.jsapi_reply(method), reply), reply)
        return reply

    def propose(self, kind: str, target: str, payload: dict) -> dict:
        return self.tools.proposal_submit(kind=kind, target=target, payload=payload, confidence=0.95,
                                          reason="The user asked for it.", base_revision=self.rev, client="Test agent")

    def proposed(self, kind: str, target: str, payload: dict) -> dict:
        reply = self.propose(kind, target, payload)
        self.assertNotIn("error", reply, reply)
        return reply["proposal"]

    def refused(self, kind: str, target: str, payload: dict) -> dict:
        reply = self.propose(kind, target, payload)
        self.assertEqual("invalid_payload", reply.get("error", {}).get("code"), reply)
        return reply["error"]["details"]

    def accept(self, proposal: dict) -> None:
        self.ok("proposal_accept", {"base_revision": self.rev, "proposal_id": proposal["id"]})

    def plan(self) -> dict:
        return plan_service.build_plan(self.devcenter, self.devcenter._require_open().document)


class SubmitCheckTests(_AgentCase):
    def test_an_expression_change_returns_its_impact_and_changes_no_accepted_state(self) -> None:
        proposal = self.proposed("object_edit", MARGIN, {"set": {"expression": NEW_MARGIN_TEXT, "format_string": "0.00"}})
        check = proposal["check"]
        self.assertEqual(set(check), {"plan_status", "blocking", "breaks", "needs", "items", "items_total"})
        self.assertEqual([], [item for item in check["blocking"] if item["row_key"] == MARGIN])
        for item in check["items"]:
            self.assertIn(item["direction"], {"breaks", "needs"})
            self.assertIn(item["certainty"], {"certain", "possible"})
        self.assertEqual(proposal["needs_review"], check["breaks"] > 0)
        self.assertEqual("Edit expression, format string", proposal["summary"])
        self.assertNotIn(MARGIN, self.devcenter._require_open().document["merge_choices"])

    def test_dax_errors_missing_objects_and_bad_values_are_refused(self) -> None:
        details = self.refused("object_edit", MARGIN, {"set": {"expression": "[Total Sales] - [No Such Measure]"}})
        self.assertEqual("proposal_not_valid", details["reason"])
        self.assertEqual(["need_missing"], [item["kind"] for item in details["blocking"]])
        self.assertEqual("No Such Measure", details["blocking"][0]["params"]["needed"]["name"])
        details = self.refused("object_edit", "column:Sales/Amount", {"set": {"expression": "1"}})
        self.assertEqual("proposal_not_valid", details["reason"])
        self.assertEqual("not_calculated", details["blocking"][0]["params"]["reason"])
        details = self.refused("object_edit", "table:Sales", {"set": {"format_string": "0"}})
        self.assertEqual(("unknown_property", "format_string"), (details["reason"], details["property"]))
        self.assertEqual("invalid_payload", self.propose("object_edit", MARGIN, {"set": {"colour": "red"}})["error"]["code"])
        self.assertEqual("not_found", self.propose("object_delete", "measure:Sales/Nope", {})["error"]["code"])
        self.assertEqual("no_change", self.refused("object_rename", MARGIN, {"new_name": "Margin"})["reason"])
        details = self.refused("object_rename", MARGIN, {"new_name": "total sales"})
        self.assertEqual(["name_clash"], [item["kind"] for item in details["blocking"]])

    def test_a_rename_of_a_used_measure_needs_review_and_rewrites_its_dependents(self) -> None:
        proposal = self.proposed("object_rename", TOTAL, {"new_name": "Revenue"})
        self.assertGreater(proposal["check"]["breaks"], 0)
        self.assertTrue(proposal["needs_review"])
        self.assertEqual("Rename to Revenue", proposal["summary"])
        self.accept(proposal)
        plan = self.plan()
        self.assertEqual([], [item for item in plan["blocking"] if item["kind"] == "renamed"])
        rewritten = {op["row_key"]: op["new_text"] for op in plan["operations"] if op["op"] == "REWRITE_EXPRESSION"}
        self.assertEqual("[Revenue] - [Total Cost]", rewritten[MARGIN])

    def test_create_derives_its_row_key_and_refuses_a_clash_or_a_missing_table(self) -> None:
        proposal = self.proposed("object_create", "new", RATIO)
        self.assertEqual("new:measure:Sales/Margin %", proposal["target_id"])
        self.assertFalse(proposal["needs_review"])
        self.assertEqual("Create measure Margin % in Sales", proposal["summary"])
        clash = dict(RATIO, name="margin")
        self.assertEqual(["name_clash"], [item["kind"] for item in self.refused("object_create", "new", clash)["blocking"]])
        nowhere = dict(RATIO, table="Nope")
        self.assertEqual("no_table", self.refused("object_create", "new", nowhere)["blocking"][0]["params"]["reason"])
        broken = dict(RATIO, properties={"expression": "DIVIDE([Margin], [Nope])"})
        self.assertEqual(["need_missing"], [item["kind"] for item in self.refused("object_create", "new", broken)["blocking"]])

    def test_an_edit_and_a_rename_of_one_object_combine(self) -> None:
        self.accept(self.proposed("object_rename", MARGIN, {"new_name": "Gross Margin"}))
        edit = self.proposed("object_edit", MARGIN, {"set": {"description": "Sales minus cost"}})
        self.assertIsNone(edit["blocked"])
        self.accept(edit)
        choice = self.devcenter._require_open().document["merge_choices"][MARGIN]
        self.assertEqual({"kind": "edit", "new_name": "Gross Margin", "set": {"description": "Sales minus cost"}}, choice)
        # A second edit of the same property would replace a user choice.
        again = self.propose("object_edit", MARGIN, {"set": {"description": "Other"}})
        self.assertEqual("user_choice_exists", again["error"]["code"])


class DeleteAndReviewTests(_AgentCase):
    def test_a_delete_of_a_used_measure_is_blocked_until_a_removal_policy_is_chosen(self) -> None:
        proposal = self.proposed("object_delete", TOTAL, {})
        self.assertTrue(proposal["needs_review"])
        self.assertIn("removed", {item["kind"] for item in proposal["check"]["blocking"]})
        self.assertTrue(any(item["direction"] == "breaks" and item["blocking"] for item in proposal["check"]["items"]))
        # "Accept all" skips it: the user reviews a delete one by one.
        reply = self.ok("proposal_accept_all", {"base_revision": self.rev})
        self.assertEqual([{"id": proposal["id"], "reason": "needs_review"}], reply["skipped"])
        self.accept(proposal)
        self.assertEqual({"kind": "remove"}, self.devcenter._require_open().document["merge_choices"][TOTAL])
        plan = self.plan()
        self.assertEqual("invalid", plan["status"])
        self.assertIn("removed", {item["kind"] for item in plan["blocking"]})
        self.ok("removal_policy_set", {"base_revision": self.rev, "row_key": TOTAL, "policy": "cascade"})
        plan = self.plan()
        self.assertNotIn("removed", {item["kind"] for item in plan["blocking"]})
        deleted = {op["row_key"] for op in plan["operations"] if op["op"] == "DELETE"}
        self.assertTrue({TOTAL, MARGIN} <= deleted, deleted)

    def test_a_plain_property_edit_goes_into_accept_all(self) -> None:
        proposal = self.proposed("object_edit", MARGIN, {"set": {"display_folder": "KPI"}})
        self.assertFalse(proposal["needs_review"])
        reply = self.ok("proposal_accept_all", {"base_revision": self.rev})
        self.assertEqual([proposal["id"]], reply["accepted_ids"])


@unittest.skipUnless(BRIDGE.is_file(), "Build the TOM bridge first")
class AgentEditAcceptanceTests(_AgentCase):
    """The acceptance of issue #13 with the real plan, the real guard, and the real promotion."""

    def prepare(self) -> None:
        from backend.adapters.tabular_metadata import TabularMetadataAdapter

        temporary = tempfile.TemporaryDirectory(prefix="i13-model-")
        self.addCleanup(temporary.cleanup)
        output = Path(temporary.name) / "model"
        TabularMetadataAdapter().write_model(LAB / "SalesA" / "SalesA.SemanticModel", output, [])
        # The model library writes the canonical file, so the apply is not blocked by the format check.
        shutil.copyfile(output / "tables" / "Sales.tmdl", self.root / "SalesA" / SALES)

    def test_agent_proposes_a_dax_change_and_a_measure_user_accepts_apply_writes_tmdl_and_rescan_matches(self) -> None:
        edit = self.proposed("object_edit", MARGIN, {"set": {"expression": NEW_MARGIN_TEXT}})
        create = self.proposed("object_create", "new", RATIO)
        self.assertIn("check", edit)
        self.accept(edit)
        self.accept(create)
        self.devcenter.apply_service = ApplyService(self.devcenter, desktop=_Desktop())
        code, preview = self.app.handle("GET", "/api/devcenter/apply/preview")
        self.assertEqual(200, code, preview)
        self.assertTrue(preview["ready"], preview)
        reply = self.ok("apply", {"base_revision": self.rev, "plan_hash": preview["plan_hash"],
                                  "approvals": sorted(item["purpose"] for item in preview["approvals_needed"])})
        self.assertEqual([], reply["rescan_differences"])
        text = (self.root / "SalesA" / SALES).read_text(encoding="utf-8")
        self.assertIn(f"measure Margin = {NEW_MARGIN_TEXT}", text)
        self.assertIn("measure 'Margin %' = DIVIDE([Margin], [Total Sales])", text)
        self.assertIn("formatString: 0.0%", text)
