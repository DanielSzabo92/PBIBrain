"""Build step S10: the agent MCP tools, the proposal routes, and the user decisions on proposals (ticket 21).

Target SalesA (model and report), donor SalesB. The tests call the agent tools
through ``AgentTools`` with an in-process transport to ``BrainApp.handle``, so
each tool goes through the same route table as the MCP server.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from urllib.parse import urlencode

from backend.api.app import create_app
from backend.devcenter import contracts, http_routes, jsapi
from backend.devcenter.agent_tools import TOOL_ROUTES, AgentTools
from backend.devcenter.plan import service as plan_service
from backend.devcenter.session.manager import DevCenterSessions

LAB = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "merge_lab"
CLIENT = "Test agent"
MARGIN = "measure:Sales/Margin"
AVERAGE = "measure:Sales/Average Sale"
ORDERS = "measure:Sales/Orders Count"
TAKE_B = {"choice": {"kind": "take", "source_id": "src-2"}}


def route_of(method: str, path: str) -> http_routes.Route:
    parts = tuple(path.split("/"))
    return next(item for item in http_routes.ROUTES if item.method == method and item.path == parts)


class AgentToolsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "project"
        for name in ("SalesA", "SalesB"):
            shutil.copytree(LAB / name, self.root / name)
        self.devcenter = DevCenterSessions(app_data_dir=None)
        self.devcenter.attach_project(self.root)
        self.app = create_app(use_native=False)
        self.app.devcenter = self.devcenter
        self.ok("session_create", {"display_name": "Agent"})
        for name in ("SalesA", "SalesB"):
            self.ok("source_add", {"base_revision": self.rev, "path": str(self.root / name / f"{name}.pbip")})
        self.ok("target_set", {"base_revision": self.rev, "model": {"mode": "existing", "source_id": "src-1"},
                               "report": {"mode": "existing", "source_id": "src-1"}})
        self.status: list[int] = []
        self.tools = AgentTools(self.send)

    def tearDown(self) -> None:
        self.devcenter.close()
        self.app.close()
        self.temporary.cleanup()

    @property
    def rev(self) -> int:
        return self.devcenter.revision

    def send(self, method: str, path: str, query, body) -> dict:
        url = "/api/devcenter/" + path + (f"?{urlencode(query)}" if query else "")
        status, payload = self.app.handle(method, url, json.dumps(body).encode("utf-8") if body is not None else None)
        self.status.append(status)
        if "error" in payload:
            self.assertEqual([], contracts.errors(contracts.ERROR, payload), payload)
        else:
            self.assertEqual([], contracts.errors(route_of(method, path).contract, payload), payload)
        return payload

    def ok(self, method: str, request: dict) -> dict:
        reply = jsapi.call(self.devcenter, method, request)
        self.assertNotIn("error", reply, reply)
        self.assertEqual([], contracts.errors(contracts.jsapi_reply(method), reply), reply)
        return reply

    def failed(self, method: str, request: dict, code: str) -> dict:
        reply = jsapi.call(self.devcenter, method, request)
        self.assertEqual(code, reply.get("error", {}).get("code"), reply)
        return reply["error"]

    def get(self, path: str) -> dict:
        status, payload = self.app.handle("GET", "/api/devcenter/" + path)
        self.assertEqual(200, status, payload)
        return payload

    def propose(self, target: str = MARGIN, payload: dict | None = None, kind: str = "merge_choice", **extra) -> dict:
        values = {"kind": kind, "target": target, "payload": payload or TAKE_B, "confidence": 0.95,
                  "reason": "The donor has the newer expression.", "base_revision": self.rev, "client": CLIENT, **extra}
        return self.tools.proposal_submit(**values)

    def proposed(self, **values) -> dict:
        reply = self.propose(**values)
        self.assertNotIn("error", reply, reply)
        return reply["proposal"]

    def code(self, reply: dict) -> str | None:
        return reply.get("error", {}).get("code")

    def mark_margin(self) -> None:
        """Change the donor Margin measure, then check the sources: the Margin row gets a mark."""
        path = self.root / "SalesB" / "SalesB.SemanticModel" / "definition" / "tables" / "Sales.tmdl"
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace("[Sales Amount] - [Total Cost]", "[Sales Amount] - [Total Cost] * 2"), encoding="utf-8")
        self.ok("sources_check", {"base_revision": self.rev})
        self.assertIn(MARGIN, [mark["row_key"] for mark in self.devcenter.marks()])

    def log(self, query: str = "") -> dict:
        return self.get("log" + (f"?{query}" if query else ""))


class ToolContractTests(AgentToolsTestCase):
    def test_each_tool_returns_the_contract_shape(self):
        self.ok("naming_rule_edit", {"base_revision": self.rev, "object_type": "measure", "check": {"kind": "prefix", "value": "m_"}})
        replies = {
            "session_get": self.tools.session_get(),
            "compare_rows_list": self.tools.compare_rows_list(limit=5),
            "impact_get": self.tools.impact_get(limit=5),
            "naming_rules_get": self.tools.naming_rules_get(),
            "name_propose": self.tools.name_propose(name="Margin", object_type="measure", table="Sales", source_id="src-2"),
            "proposal_submit": self.propose(),
            "question_ask": self.tools.question_ask(
                target=AVERAGE, text="Add Average Sale from SalesB?", recommended_option="yes", reason="The target has no such measure.",
                base_revision=self.rev, client=CLIENT,
                options=[{"id": "yes", "label": "Add it", "proposal": {"kind": "merge_choice", "payload": TAKE_B}},
                         {"id": "no", "label": "Skip it"}]),
            "plan_validate": self.tools.plan_validate(),
        }
        self.assertEqual(set(TOOL_ROUTES), set(replies))
        for tool, reply in replies.items():
            with self.subTest(tool=tool):
                self.assertNotIn("error", reply, reply)
                method, path = TOOL_ROUTES[tool]
                self.assertEqual([], contracts.errors(route_of(method, path).contract, reply))
                self.assertIsInstance(reply["revision"], int)
        self.assertEqual({200}, set(self.status))

    def test_an_error_has_the_one_error_shape(self):
        self.devcenter.close()
        reply = self.tools.session_get()
        self.assertEqual("session_not_open", self.code(reply))
        self.assertEqual([], contracts.errors(contracts.ERROR, reply))


class AllowlistTests(AgentToolsTestCase):
    def test_no_tool_maps_to_a_route_outside_the_read_and_proposal_set(self):
        for tool, (method, path) in TOOL_ROUTES.items():
            with self.subTest(tool=tool):
                found = route_of(method, path)
                self.assertIn(found.kind, {http_routes.READ, http_routes.PROPOSAL})
                if found.kind == http_routes.PROPOSAL:
                    self.assertIn(path, {"proposals", "questions"})
                if method == "POST" and found.kind == http_routes.READ:
                    self.assertIn(path, http_routes.READ_POSTS)

    def test_no_http_route_for_an_accepted_state_write_or_apply_exists(self):
        names = set(jsapi.METHODS) | {"apply", "format_only_apply", "undo_apply", "accept", "reject"}
        for route in http_routes.ROUTES:
            with self.subTest(route="/".join(route.path)):
                self.assertIn((route.kind, route.method), {("read", "GET"), ("read", "POST"), ("proposal", "POST")})
                if route.path in {("apply", "preview"), ("apply", "progress"), ("apply", "last")}:
                    # Section 14.1, UC5, UC7 (ticket 23): GET reads of the apply state. They change nothing.
                    self.assertEqual(("read", "GET"), (route.kind, route.method))
                    continue
                self.assertFalse(names & set(route.path))
        for name in ("proposal_accept", "proposal_accept_all", "question_answer", "apply"):
            for method in ("GET", "POST", "PUT"):
                status, _ = self.app.handle(method, f"/api/devcenter/{name}", b"{}")
                self.assertIn(status, {404, 405})

    def test_the_mcp_client_refuses_a_route_outside_the_allowlist(self):
        from backend.mcp_server import BrainClient

        client = BrainClient("http://127.0.0.1:9")
        for method, path in (("POST", "merge_choice_set"), ("POST", "apply"), ("GET", "log"), ("POST", "session")):
            with self.subTest(path=path), self.assertRaises(ValueError):
                client.devcenter(method, path, None, {})

    @unittest.skipUnless(importlib.util.find_spec("mcp"), "optional MCP SDK is not installed")
    def test_the_server_registers_the_eight_tools(self):
        from backend.mcp_server import create_server

        names = {tool.name for tool in create_server("http://127.0.0.1:8766")._tool_manager.list_tools()}
        self.assertLessEqual(set(TOOL_ROUTES), names)
        self.assertEqual(8, len(names - {name for name in names if name.startswith("brain_")}))


class SubmitTests(AgentToolsTestCase):
    def test_confidence_reason_and_naming_rule_checks(self):
        revision = self.rev
        reply = self.propose(confidence=0.89)
        self.assertEqual("confidence_below_threshold", self.code(reply))
        self.assertEqual(0.9, reply["error"]["details"]["threshold"])
        self.assertEqual("reason_required", self.code(self.propose(reason="")))
        self.assertEqual("reason_required", self.code(self.propose(reason="   ")))
        rule = self.ok("naming_rule_edit", {"base_revision": self.rev, "object_type": "measure",
                                            "check": {"kind": "prefix", "value": "m_"}})["rule"]
        name = {"name": "Margin New", "object_type": "measure", "table": "Sales", "source_id": "src-2"}
        reply = self.propose(kind="name", payload=name)
        self.assertEqual("naming_rule_violation", self.code(reply))
        self.assertEqual([rule["rule_id"]], reply["error"]["details"]["rule_ids"])
        self.assertEqual(revision + 1, self.rev, "A refused proposal must not change the session")
        proposal = self.proposed(kind="name", payload={**name, "name": "m_Margin New"})
        self.assertEqual(("name", "proposed"), (proposal["kind"], proposal["status"]))
        self.assertEqual("invalid_payload", self.code(self.propose(kind="removal_policy", payload={"policy": "unknown"})))

    def test_stale_revision_user_choice_source_changed_and_replace(self):
        self.assertEqual("stale_revision", self.code(self.propose(base_revision=self.rev - 1)))
        first = self.proposed()
        second = self.propose(payload={"choice": "keep"})
        self.assertEqual([first["id"]], second["replaced_ids"])
        session = self.tools.session_get()
        self.assertEqual([second["proposal"]["id"]], [item["id"] for item in session["proposals"]["open"]])
        stored = {item["id"]: item for item in self.devcenter._open.document["proposals"]}
        self.assertEqual(("replaced", second["proposal"]["id"]), (stored[first["id"]]["status"], stored[first["id"]]["replaced_by"]))
        self.ok("merge_choice_set", {"base_revision": self.rev, "row_key": AVERAGE, "choice": {"kind": "skip"}})
        reply = self.propose(target=AVERAGE)
        self.assertEqual("user_choice_exists", self.code(reply))
        self.mark_margin()
        self.assertEqual("source_changed", self.code(self.propose()))


class IncludeProposalTests(AgentToolsTestCase):
    def test_include_proposals_true_and_false_give_different_plans_and_apply_ignores_them(self):
        accepted = self.get("plan")
        self.proposed(target=AVERAGE)
        without = self.get("plan?include_proposals=false")
        with_proposals = self.get("plan?include_proposals=true")
        self.assertEqual(accepted["plan_hash"], without["plan_hash"])
        self.assertNotEqual(without["plan_hash"], with_proposals["plan_hash"])
        self.assertGreater(len(with_proposals["steps"]), len(without["steps"]))
        validate_with = self.tools.plan_validate(include_proposals=True)
        validate_without = self.tools.plan_validate(include_proposals=False)
        self.assertEqual(with_proposals["plan_hash"], validate_with["plan_hash"])
        self.assertEqual(without["plan_hash"], validate_without["plan_hash"])
        self.assertNotEqual(self.tools.impact_get(include_proposals=True)["items"] + [None],
                            self.tools.impact_get(include_proposals=False)["items"] + [0])
        # Apply compiles the plan from accepted state only (section 13).
        document = self.devcenter._open.document
        self.assertEqual({}, document["merge_choices"])
        self.assertEqual(without["plan_hash"], plan_service.build_plan(self.devcenter, document)["plan_hash"])

    def test_uc11_ready_includes_only_what_accept_all_accepts(self):
        self.proposed(target=AVERAGE)
        self.proposed(target=ORDERS)
        self.proposed(target=MARGIN)
        self.ok("merge_choice_set", {"base_revision": self.rev, "row_key": ORDERS, "choice": {"kind": "skip"}})
        self.mark_margin()
        everything = self.get("plan?include_proposals=true")
        ready = self.get("plan?include_proposals=ready")
        ready_impact = self.get("impact?include_proposals=ready&limit=1000")
        self.assertNotEqual(everything["plan_hash"], ready["plan_hash"])
        self.ok("proposal_accept_all", {"base_revision": self.rev})
        self.assertEqual(ready["plan_hash"], self.get("plan")["plan_hash"])
        accepted_impact = self.get("impact?limit=1000")
        self.assertEqual(ready_impact["items"], accepted_impact["items"])
        self.assertEqual(ready_impact["total"], accepted_impact["total"])


class LogTests(AgentToolsTestCase):
    def test_each_proposal_and_question_writes_a_log_entry_with_the_client_name(self):
        proposal = self.proposed()
        question = self.tools.question_ask(target=AVERAGE, text="Add it?", options=[{"id": "a", "label": "Yes"}, {"id": "b", "label": "No"}],
                                           recommended_option="a", reason="It is new.", base_revision=self.rev, client=CLIENT)["question"]
        entries = self.log("author=agent")["entries"]
        self.assertEqual([("question_ask", question["id"]), ("proposal_submit", proposal["id"])],
                         [(item["action"], item["proposal_id"]) for item in entries])
        self.assertEqual({CLIENT}, {item["mcp_client"] for item in entries})
        self.assertEqual({"The donor has the newer expression.", "It is new."}, {item["reason"] for item in entries})

    def test_paging_with_has_more(self):
        first = self.tools.compare_rows_list(limit=5)
        self.assertTrue(first["has_more"])
        self.assertEqual(5, len(first["rows"]))
        rows = []
        offset = 0
        while True:
            page = self.tools.compare_rows_list(limit=50, offset=offset)
            rows += page["rows"]
            offset += 50
            if not page["has_more"]:
                break
        self.assertEqual(first["total"], len(rows))
        log = self.log("limit=2")
        self.assertTrue(log["has_more"])
        self.assertEqual(2, len(log["entries"]))
        last = self.log(f"limit=2&offset={log['total'] - 1}")
        self.assertFalse(last["has_more"])
        self.assertEqual(1, len(last["entries"]))

    def test_uc8_log_filters_apply_over_all_pages(self):
        proposal = self.proposed()
        for _ in range(3):
            self.ok("merge_choice_set", {"base_revision": self.rev, "row_key": ORDERS, "choice": {"kind": "skip"}})
        self.ok("proposal_accept", {"base_revision": self.rev, "proposal_id": proposal["id"]})
        total = self.log()["total"]
        self.assertGreater(total, 8)
        by_proposal = self.log(f"proposal_id={proposal['id']}&limit=1")
        self.assertEqual(2, by_proposal["total"])
        self.assertTrue(by_proposal["has_more"])
        self.assertEqual(["proposal_accept"], [item["action"] for item in by_proposal["entries"]])
        pages = by_proposal["entries"] + self.log(f"proposal_id={proposal['id']}&limit=1&offset=1")["entries"]
        self.assertEqual(["proposal_accept", "proposal_submit"], [item["action"] for item in pages])
        self.assertEqual(3, self.log("action=merge_choice_set&limit=1")["total"])
        self.assertEqual(3, self.log(f"target={ORDERS}")["total"])
        self.assertEqual(2, self.log(f"target={MARGIN}")["total"])
        self.assertEqual(1, self.log("author=agent")["total"])
        self.assertEqual(total - 1, self.log("author=user")["total"])
        self.assertEqual(400, self.app.handle("GET", "/api/devcenter/log?author=robot")[0])


class SessionViewTests(AgentToolsTestCase):
    def test_uc9_session_gives_each_field_and_the_blocked_state(self):
        ready = self.proposed(target=AVERAGE, target_name="Average Sale")
        conflict = self.proposed(target=ORDERS)
        marked = self.proposed(target=MARGIN)
        question = self.tools.question_ask(
            target=MARGIN, text="Which Margin?", recommended_option="b", reason="Both differ.", base_revision=self.rev, client=CLIENT,
            options=[{"id": "a", "label": "Keep target"}, {"id": "b", "label": "Take SalesB", "proposal": {"kind": "merge_choice", "payload": TAKE_B}}])["question"]
        other = self.tools.question_ask(target=AVERAGE, text="Add it?", options=[{"id": "a", "label": "Yes"}, {"id": "b", "label": "No"}],
                                        recommended_option="a", reason="It is new.", base_revision=self.rev, client=CLIENT)["question"]
        self.ok("merge_choice_set", {"base_revision": self.rev, "row_key": ORDERS, "choice": {"kind": "skip"}})
        self.ok("question_answer", {"base_revision": self.rev, "question_id": other["id"], "option_id": "b"})
        self.mark_margin()
        session = self.tools.session_get()
        views = {item["id"]: item for item in session["proposals"]["open"]}
        self.assertEqual({ready["id"]: None, conflict["id"]: "user_choice_conflict", marked["id"]: "source_changed"},
                         {key: item["blocked"] for key, item in views.items()})
        view = views[ready["id"]]
        for field in ("id", "kind", "target_id", "target_name", "summary", "confidence", "reason", "mcp_client", "created_utc", "payload"):
            self.assertIsNotNone(view[field], field)
        self.assertEqual(("Average Sale", CLIENT, 0.95, "Merge Choice take from SalesB"),
                         (view["target_name"], view["mcp_client"], view["confidence"], view["summary"]))
        self.assertEqual([(question["id"], "source_changed")], [(item["id"], item["blocked"]) for item in session["questions"]["open"]])
        answered = session["questions"]["answered"]
        self.assertEqual([(other["id"], "b")], [(item["id"], item["selected_option"]) for item in answered])
        self.assertRegex(answered[0]["answered_utc"], r"Z$")


class UserDecisionTests(AgentToolsTestCase):
    def test_uc10_accept_all(self):
        ready_one = self.proposed(target=AVERAGE)
        ready_two = self.proposed(target="measure:Sales/Sales With Tax")
        conflict = self.proposed(target=ORDERS)
        marked = self.proposed(target=MARGIN)
        self.ok("merge_choice_set", {"base_revision": self.rev, "row_key": ORDERS, "choice": {"kind": "skip"}})
        self.mark_margin()
        before = self.rev
        log_before = self.log()["total"]
        reply = self.ok("proposal_accept_all", {"base_revision": before})
        self.assertEqual(before + 1, reply["revision"])
        self.assertEqual([ready_one["id"], ready_two["id"]], reply["accepted_ids"])
        self.assertEqual([{"id": conflict["id"], "reason": "user_choice_conflict"}, {"id": marked["id"], "reason": "source_changed"}],
                         reply["skipped"])
        entries = self.log("action=proposal_accept_all")["entries"]
        self.assertEqual({ready_one["id"], ready_two["id"]}, {item["proposal_id"] for item in entries})
        self.assertEqual(log_before + 2, self.log()["total"])
        choices = self.devcenter._open.document["merge_choices"]
        self.assertEqual({"kind": "take", "source_id": "src-2"}, choices[AVERAGE])
        self.assertEqual({"kind": "skip"}, choices[ORDERS])
        self.assertEqual([conflict["id"], marked["id"]], [item["id"] for item in self.tools.session_get()["proposals"]["open"]])
        self.failed("proposal_accept_all", {"base_revision": before}, "stale_revision")

    def test_uc12_accept_replaces_a_user_choice_and_refuses_a_marked_row(self):
        proposal = self.proposed(target=AVERAGE)
        self.ok("merge_choice_set", {"base_revision": self.rev, "row_key": AVERAGE, "choice": {"kind": "skip"}})
        reply = self.ok("proposal_accept", {"base_revision": self.rev, "proposal_id": proposal["id"]})
        self.assertEqual([proposal["id"]], reply["accepted_ids"])
        self.assertEqual({"kind": "take", "source_id": "src-2"}, self.devcenter._open.document["merge_choices"][AVERAGE])
        entry = self.log("action=proposal_accept")["entries"][0]
        self.assertEqual(({"kind": "skip"}, {"kind": "take", "source_id": "src-2"}, "user", proposal["id"]),
                         (entry["before"], entry["after"], entry["author"], entry["proposal_id"]))
        self.failed("proposal_accept", {"base_revision": self.rev, "proposal_id": proposal["id"]}, "action_not_allowed")
        marked = self.proposed(target=MARGIN)
        self.mark_margin()
        error = self.failed("proposal_accept", {"base_revision": self.rev, "proposal_id": marked["id"]}, "source_changed")
        self.assertEqual(marked["id"], error["details"]["proposal_id"])
        self.ok("row_confirm", {"base_revision": self.rev, "row_keys": [MARGIN]})
        self.ok("proposal_accept", {"base_revision": self.rev, "proposal_id": marked["id"]})

    def test_reject_and_question_answer(self):
        proposal = self.proposed(target=AVERAGE)
        self.assertEqual([proposal["id"]], self.ok("proposal_reject", {"base_revision": self.rev, "proposal_id": proposal["id"]})["rejected_ids"])
        self.assertEqual([], self.tools.session_get()["proposals"]["open"])
        self.assertEqual({}, self.devcenter._open.document["merge_choices"])
        question = self.tools.question_ask(
            target=AVERAGE, text="Add it?", recommended_option="yes", reason="It is new.", base_revision=self.rev, client=CLIENT,
            options=[{"id": "yes", "label": "Add", "proposal": {"kind": "merge_choice", "payload": TAKE_B}}, {"id": "no", "label": "Skip"}])["question"]
        self.failed("question_answer", {"base_revision": self.rev, "question_id": question["id"], "option_id": "x"}, "not_found")
        reply = self.ok("question_answer", {"base_revision": self.rev, "question_id": question["id"], "option_id": "yes"})
        self.assertTrue(reply["applied"])
        self.assertEqual({"kind": "take", "source_id": "src-2"}, self.devcenter._open.document["merge_choices"][AVERAGE])
        self.failed("question_answer", {"base_revision": self.rev, "question_id": question["id"], "option_id": "no"}, "action_not_allowed")
        bad = self.tools.question_ask(target=AVERAGE, text="?", options=[{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
                                      recommended_option="c", reason="r", base_revision=self.rev, client=CLIENT)
        self.assertEqual("invalid_payload", self.code(bad))
        one = self.tools.question_ask(target=AVERAGE, text="?", options=[{"id": "a", "label": "A"}],
                                      recommended_option="a", reason="r", base_revision=self.rev, client=CLIENT)
        self.assertEqual("invalid_payload", self.code(one))

    def test_other_proposal_kinds_go_into_accepted_state(self):
        cases = [
            ("removal_policy", "measure:Sales/Total Cost", {"policy": "cascade"}, "removal_policies", {"policy": "cascade", "repoint_target": None}),
            ("need_mapping", "need-1", {"action": "map_to_target", "target_object": "measure:Sales/Margin"}, "need_mappings",
             {"action": "map_to_target", "target_object": "measure:Sales/Margin"}),
            ("impact_action", "item-1", {"action": "include_in_rewrite"}, "item_actions", {"action": "include_in_rewrite"}),
        ]
        for kind, target, payload, store, expected in cases:
            with self.subTest(kind=kind):
                proposal = self.proposed(kind=kind, target=target, payload=payload)
                self.ok("proposal_accept", {"base_revision": self.rev, "proposal_id": proposal["id"]})
                self.assertEqual(expected, self.devcenter._open.document[store][target])
                self.assertEqual("user_choice_exists", self.code(self.propose(kind=kind, target=target, payload=payload)))
        name = self.proposed(kind="name", target=AVERAGE, payload={"name": "Mean Sale", "object_type": "measure", "source_id": "src-2"})
        self.ok("proposal_accept", {"base_revision": self.rev, "proposal_id": name["id"]})
        self.assertEqual({"kind": "add_new_name", "source_id": "src-2", "new_name": "Mean Sale"},
                         self.devcenter._open.document["merge_choices"][AVERAGE])
        align = {"source_id": "src-2", "action": "reject_rename", "target_key": "measure:Sales/Total Sales", "donor_key": "measure:Sales/Sales Amount"}
        proposal = self.proposed(kind="alignment", target="measure:Sales/Total Sales", payload=align)
        self.ok("proposal_accept", {"base_revision": self.rev, "proposal_id": proposal["id"]})
        self.assertEqual([{"kind": "reject_rename", "target_key": align["target_key"], "donor_key": align["donor_key"]}],
                         self.devcenter._open.document["alignment_overrides"]["src-2"])


if __name__ == "__main__":
    unittest.main()
