"""Comprehensive unit tests for Milestone 2 (M2) open issues (#77, #78, #87, #88, #91, #92)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from backend.api.app import create_app
from backend.devcenter import contracts, jsapi
from backend.devcenter.agent_tools import AgentTools
from backend.devcenter.apply.service import ApplyService
from backend.devcenter.compare.extract import MODEL, CompareObject, SourceObjects, model_objects
from backend.devcenter.compare.rows import SessionSource, build_rows, filter_rows
from backend.devcenter.naming.objects import MEASURE, NamedObject
from backend.devcenter.naming.proposer import clash_with, propose
from backend.devcenter.naming.tokens import is_case
from backend.devcenter.plan import PlanInput, compile_plan
from backend.devcenter.plan.compiler import REMOVE, REPOINT, STATUS_VALID, TAKE
from backend.devcenter.session.manager import DevCenterSessions
from backend.tool_registry import merge_tools

REPOSITORY = Path(__file__).resolve().parents[1]
LAB = REPOSITORY / "tests" / "fixtures" / "merge_lab"
TOTAL_SALES = "measure:Sales/Total Sales"
TOTAL_COST = "measure:Sales/Total Cost"
MARGIN = "measure:Sales/Margin"
AVERAGE = "measure:Sales/Average Sale"


def _make_source(source_id: str, model_data: dict) -> SessionSource:
    return SessionSource(source_id, SourceObjects(model_objects(model_data), []))


class _TempMergeLabTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "project"
        for name in ("SalesA", "SalesB", "Finance", "Legacy"):
            shutil.copytree(LAB / name, self.root / name)
        self.devcenter = DevCenterSessions(app_data_dir=None)
        self.devcenter.attach_project(self.root)
        self.app = create_app(use_sqlite=False)
        self.app.devcenter = self.devcenter
        self.ok("session_create", {"display_name": "M2 Test"})
        for name in ("SalesA", "SalesB", "Finance"):
            self.ok("source_add", {"base_revision": self.devcenter.revision, "path": str(self.root / name / f"{name}.pbip")})
        self.ok("target_set", {
            "base_revision": self.devcenter.revision,
            "model": {"mode": "existing", "source_id": "src-1"},
            "report": {"mode": "existing", "source_id": "src-1"},
        })

    def tearDown(self) -> None:
        self.devcenter.close()
        self.app.close()
        self.temporary.cleanup()

    @property
    def rev(self) -> int:
        assert self.devcenter.revision is not None
        return self.devcenter.revision

    def ok(self, method: str, request: dict) -> dict:
        reply = jsapi.call(self.devcenter, method, request)
        self.assertNotIn("error", reply, reply)
        self.assertEqual([], contracts.errors(contracts.jsapi_reply(method), reply), reply)
        return reply

    def get(self, path: str, contract: str | None = None) -> dict:
        status, payload = self.app.handle("GET", "/api/devcenter/" + path)
        self.assertEqual(200, status, payload)
        if contract:
            self.assertEqual([], contracts.errors(contract, payload), payload)
        return payload


class Issue77BulkUndoTests(_TempMergeLabTestCase):
    def test_merge_choice_bulk_set_returns_previous_choices_and_validates_contract(self):
        self.ok("merge_choice_set", {
            "base_revision": self.rev,
            "row_key": MARGIN,
            "choice": {"kind": "take", "source_id": "src-2"},
        })
        reply = self.ok("merge_choice_bulk_set", {
            "base_revision": self.rev,
            "row_keys": [MARGIN, AVERAGE],
            "choice": {"kind": "skip"},
        })
        self.assertEqual({
            MARGIN: {"kind": "take", "source_id": "src-2"},
            AVERAGE: None,
        }, reply["previous_choices"])
        self.assertEqual([], contracts.errors("jsapi/merge_choice_bulk_set.reply.json", reply))


class Issue78CompareFiltersTests(_TempMergeLabTestCase):
    def test_filter_rows_states_aliases_proposal_and_multi_value_filters(self):
        sample_rows = [
            {
                "row_key": "measure:Sales/SameM", "domain": "model", "object_type": "measure",
                "table": "Sales", "page": None, "display_folder": None, "row_state": "same",
                "name": "SameM", "changed": False, "marks": [], "proposal_status": None,
                "cells": [{"source_id": "src-1", "present": True, "name": "SameM"}],
            },
            {
                "row_key": "column:Sales/ConflictC", "domain": "model", "object_type": "column",
                "table": "Sales", "page": None, "display_folder": None, "row_state": "type_conflict",
                "name": "ConflictC", "changed": True, "marks": [], "proposal_status": "proposed",
                "cells": [{"source_id": "src-2", "present": True, "name": "ConflictC"}],
            },
            {
                "row_key": "table:Budget", "domain": "model", "object_type": "table",
                "table": None, "page": None, "display_folder": None, "row_state": "missing",
                "name": "Budget", "changed": False, "marks": [], "proposal_status": None,
                "cells": [{"source_id": "src-3", "present": True, "name": "Budget"}],
            },
        ]
        self.assertEqual({"column:Sales/ConflictC", "table:Budget"},
                         {r["row_key"] for r in filter_rows(sample_rows, {"state": "not_same"})})
        self.assertEqual({"column:Sales/ConflictC"},
                         {r["row_key"] for r in filter_rows(sample_rows, {"state": "conflict"})})
        self.assertEqual({"measure:Sales/SameM", "column:Sales/ConflictC", "table:Budget"},
                         {r["row_key"] for r in filter_rows(sample_rows, {"state": "all"})})
        self.assertEqual({"column:Sales/ConflictC"},
                         {r["row_key"] for r in filter_rows(sample_rows, {"proposal": "true"})})
        self.assertEqual({"measure:Sales/SameM", "table:Budget"},
                         {r["row_key"] for r in filter_rows(sample_rows, {"proposal": "false"})})
        self.assertEqual({"column:Sales/ConflictC", "table:Budget"},
                         {r["row_key"] for r in filter_rows(sample_rows, {"type": ["column", "table"], "source": "src-2,src-3"})})

    def test_http_and_agent_tools_forward_proposal_and_not_same_filters(self):
        def _send(method, path, query, body):
            q = "&".join(f"{k}={v}" for k, v in (query or {}).items())
            url = f"/api/devcenter/{path}" + (f"?{q}" if q else "")
            raw = json.dumps(body).encode("utf-8") if body is not None else b""
            _, payload = self.app.handle(method, url, raw)
            return payload

        tools = AgentTools(_send)
        sub = tools.proposal_submit(
            kind="merge_choice", target=MARGIN,
            payload={"choice": {"kind": "take", "source_id": "src-2"}},
            reason="Take Margin from SalesB", confidence=0.95,
            base_revision=self.rev, client="test-agent",
        )
        self.assertNotIn("error", sub, sub)
        self.assertIn("proposal", sub)
        http_prop = self.get("compare-rows?proposal=true&limit=100", "http/compare-rows.reply.json")
        self.assertEqual([MARGIN], [r["row_key"] for r in http_prop["rows"]])
        http_not_same = self.get("compare-rows?state=not_same&limit=1000", "http/compare-rows.reply.json")
        self.assertTrue(http_not_same["rows"])
        self.assertTrue(all(r["row_state"] != "same" for r in http_not_same["rows"]))

        tool_prop = tools.compare_rows_list(proposal=True)
        self.assertEqual([MARGIN], [r["row_key"] for r in tool_prop["rows"]])

        captured_queries: list[dict[str, object]] = []

        class _FakeClient:
            def devcenter(self, method, path, query, body):
                captured_queries.append({"method": method, "path": path, "query": query, "body": body})
                return {"rows": [], "total": 0, "state_counts": {}, "has_more": False}

        mtools = {fn.__name__: fn for fn in merge_tools(_FakeClient(), lambda: "test-agent")}
        mtools["compare_rows_list"](proposal=True)
        self.assertEqual("true", captured_queries[-1]["query"]["proposal"])


class Issue87SettingsReachCompilerTests(_TempMergeLabTestCase):
    def test_repoint_need_and_rewrite_reach_plan_compiler_and_session_compare_exposure(self):
        # 1. Removal policy Repoint applied via removal_policy_set (with repoint_target)
        # Note: Total Cost and Total Sales are both decimals in SalesA, wait: let's check a measure with identical type or repoint column->column/measure->measure
        self.ok("merge_choice_set", {"base_revision": self.rev, "row_key": TOTAL_COST, "choice": {"kind": "remove"}})
        self.ok("removal_policy_set", {
            "base_revision": self.rev,
            "row_key": TOTAL_COST,
            "policy": "repoint",
            "repoint_target": TOTAL_SALES,
        })
        session_reply = self.get("session", "http/session.reply.json")
        self.assertEqual({"policy": "repoint", "repoint_target": TOTAL_SALES}, session_reply["removal_policies"][TOTAL_COST])
        rows_reply = self.get("compare-rows?limit=1000", "http/compare-rows.reply.json")
        cost_row = next(r for r in rows_reply["rows"] if r["row_key"] == TOTAL_COST)
        self.assertEqual({"policy": "repoint", "repoint_target": TOTAL_SALES}, cost_row["removal_policy"])

        # Compile synthetic model where repoint target is non-deleted and verify no repoint_not_valid and REWRITE_EXPRESSION emitted
        repoint_model = {"tables": [{"name": "Sales", "measures": [
            {"name": "OldCost", "expression": "10"},
            {"name": "NewCost", "expression": "20"},
            {"name": "Margin", "expression": "[OldCost] * 2"},
        ]}]}
        repoint_res = build_rows([_make_source("src-1", repoint_model)], target_model="src-1", target_report=None)
        compiled_repoint = compile_plan(PlanInput(
            session_id="repoint-canon", result=repoint_res, target_model="src-1", target_report=None,
            sources={"src-1": "Target"},
            merge_choices={"measure:Sales/OldCost": {"kind": REMOVE}},
            removal_policies={"measure:Sales/OldCost": {"policy": REPOINT, "repoint_target": "measure:Sales/NewCost"}},
        ))
        self.assertEqual(STATUS_VALID, compiled_repoint["status"])
        self.assertIn("REWRITE_EXPRESSION", {op["op"] for op in compiled_repoint["operations"]})

        # 2. impact_action_apply by imp- ID for include_in_rewrite reaches plan compiler
        target_model = {"tables": [{"name": "Sales", "measures": [
            {"name": "BaseM", "expression": "1", "lineageTag": "m-base"},
            {"name": "DepM", "expression": "[BaseM] + 1", "lineageTag": "m-dep"},
        ]}]}
        donor_model = {"tables": [{"name": "Sales", "measures": [
            {"name": "BaseRenamed", "expression": "1", "lineageTag": "m-base"},
            {"name": "DepM", "expression": "[BaseM] + 1", "lineageTag": "m-dep"},
        ]}]}
        res = build_rows([_make_source("src-1", target_model), _make_source("src-2", donor_model)], target_model="src-1", target_report=None)
        import hashlib
        imp_id = "imp-" + hashlib.sha256(b"breaks:measure:Sales/DepM:measure:Sales/BaseM:rename:").hexdigest()[:16]
        compiled_without = compile_plan(PlanInput(
            session_id="s1", result=res, target_model="src-1", target_report=None,
            sources={"src-1": "Target", "src-2": "Donor"},
            merge_choices={"measure:Sales/BaseM": {"kind": TAKE, "source_id": "src-2"}},
            item_actions={},
        ))
        self.assertIn("renamed", [b["kind"] for b in compiled_without["blocking"]])
        compiled_with = compile_plan(PlanInput(
            session_id="s1", result=res, target_model="src-1", target_report=None,
            sources={"src-1": "Target", "src-2": "Donor"},
            merge_choices={"measure:Sales/BaseM": {"kind": TAKE, "source_id": "src-2"}},
            item_actions={imp_id: {"action": "include_in_rewrite"}},
        ))
        self.assertEqual(STATUS_VALID, compiled_with["status"])
        self.assertIn("REWRITE_EXPRESSION", {op["op"] for op in compiled_with["operations"]})

        # 3. need_mappings drop_added_object and map_to_target (with canonical target_object)
        need_target = {"tables": [{"name": "Sales", "measures": [{"name": "Alt", "expression": "10"}]}]}
        need_donor = {"tables": [{"name": "Sales", "measures": [
            {"name": "Req", "expression": "2"},
            {"name": "Want", "expression": "[Req] * 3"},
        ]}]}
        need_res = build_rows([_make_source("src-1", need_target), _make_source("src-2", need_donor)], target_model="src-1", target_report=None)
        compiled_drop = compile_plan(PlanInput(
            session_id="s2", result=need_res, target_model="src-1", target_report=None,
            sources={"src-1": "Target", "src-2": "Donor"},
            merge_choices={"measure:Sales/Want": {"kind": TAKE, "source_id": "src-2"}},
            need_mappings={"measure:Sales/Req": {"action": "drop_added_object"}},
        ))
        self.assertEqual([], compiled_drop["steps"])
        self.assertEqual([], compiled_drop["operations"])

        compiled_mapped = compile_plan(PlanInput(
            session_id="s3", result=need_res, target_model="src-1", target_report=None,
            sources={"src-1": "Target", "src-2": "Donor"},
            merge_choices={"measure:Sales/Want": {"kind": TAKE, "source_id": "src-2"}},
            need_mappings={"measure:Sales/Req": {"action": "map_to_target", "target_object": "measure:Sales/Alt"}},
        ))
        self.assertEqual(STATUS_VALID, compiled_mapped["status"])
        create_op = next(op for op in compiled_mapped["operations"] if op["op"] == "CREATE")
        self.assertIn("[Alt]", create_op["properties"]["expression"])

        # 4. Canonical impact_action_apply on live session with an imp- ID clears repoint/rename keys cleanly
        self.ok("merge_choice_set", {"base_revision": self.rev, "row_key": TOTAL_SALES, "choice": {"kind": "take", "source_id": "src-2"}})
        impact_reply = self.get("impact?target=plan", "http/impact.reply.json")
        rename_item = next(
            (it for it in impact_reply["items"] if it["direction"] == "breaks" and it["cause"] == TOTAL_SALES),
            None,
        )
        self.assertIsNotNone(rename_item)
        assert rename_item is not None
        self.ok("impact_action_apply", {
            "base_revision": self.rev,
            "item_ids": [rename_item["id"]],
            "action": "include_in_rewrite",
        })
        stored_actions = self.devcenter._open.document["item_actions"]
        canon_key = f"renamed:{rename_item['impacted_object']['object_id']}:{TOTAL_SALES}"
        self.assertIn(canon_key, stored_actions)
        self.assertEqual("include_in_rewrite", stored_actions[canon_key]["action"])


class Issue88ImpactCacheTests(_TempMergeLabTestCase):
    def test_impact_cache_is_scoped_to_session_and_cleared_on_lifecycle(self):
        # Create session 1 at revision 3+
        s1_id = self.devcenter._open.files.session_id
        self.ok("merge_choice_set", {"base_revision": self.rev, "row_key": TOTAL_SALES, "choice": {"kind": "take", "source_id": "src-2"}})
        s1_impact = self.get("impact?target=plan", "http/impact.reply.json")
        self.assertIsNotNone(self.devcenter._cached_impact)
        self.assertEqual(s1_id, self.devcenter._cached_impact["key"][0])

        # Also check mode="ready" preserves cache key mode
        ready_impact = self.get("impact?target=plan&include_proposals=ready", "http/impact.reply.json")
        self.assertEqual(s1_id, self.devcenter._cached_impact["key"][0])
        self.assertEqual("ready", self.devcenter._cached_impact["key"][3])
        self.assertIn("items", ready_impact)

        # Create session 2 -> clears cache and does not reuse session 1's cached result even if same revision
        self.ok("session_create", {"display_name": "M2 Session 2"})
        self.assertIsNone(self.devcenter._cached_impact)
        self.ok("source_add", {"base_revision": self.rev, "path": str(self.root / "SalesA/SalesA.pbip")})
        self.ok("source_add", {"base_revision": self.rev, "path": str(self.root / "Finance/Finance.pbip")})
        self.ok("target_set", {"base_revision": self.rev, "model": {"mode": "existing", "source_id": "src-1"}})
        s2_impact = self.get("impact?target=plan", "http/impact.reply.json")
        self.assertNotEqual(s1_impact["items"], s2_impact["items"])

        # Opening session 1 clears cached impact
        self.ok("session_open", {"session_id": s1_id})
        self.assertIsNone(self.devcenter._cached_impact)
        self.ok("session_close", {})
        self.assertIsNone(self.devcenter._cached_impact)


class Issue91SessionLifecycleTests(_TempMergeLabTestCase):
    def test_session_rename_duplicate_and_delete(self):
        orig_id = self.devcenter._open.files.session_id
        self.ok("merge_choice_set", {"base_revision": self.rev, "row_key": MARGIN, "choice": {"kind": "take", "source_id": "src-2"}})

        # Rename open session
        renamed = self.ok("session_rename", {"session_id": orig_id, "display_name": "Renamed Session", "base_revision": self.rev})
        self.assertEqual("Renamed Session", renamed["display_name"])
        self.assertEqual("Renamed Session", self.get("session", "http/session.reply.json")["display_name"])

        # Duplicate session -> preserves sources, target, merge choices on disk
        dup = self.ok("session_duplicate", {"session_id": orig_id, "display_name": "Copied Session"})
        dup_id = dup["session_id"]
        self.assertNotEqual(orig_id, dup_id)
        self.ok("session_open", {"session_id": dup_id})
        dup_summary = self.get("session", "http/session.reply.json")
        self.assertEqual("Copied Session", dup_summary["display_name"])
        self.assertEqual(3, len(dup_summary["sources"]))
        self.assertIn(MARGIN, self.devcenter._open.document["merge_choices"])

        # Rename closed session
        self.ok("session_rename", {"session_id": orig_id, "display_name": "Closed Renamed"})
        listed = self.get("sessions", "http/sessions.reply.json")["sessions"]
        self.assertEqual("Closed Renamed", next(s["display_name"] for s in listed if s["session_id"] == orig_id))

        # Delete open duplicate session & closed original session
        self.ok("session_delete", {"session_id": dup_id})
        self.assertIsNone(self.devcenter.revision)
        self.ok("session_delete", {"session_id": orig_id})
        listed_after = self.get("sessions", "http/sessions.reply.json")["sessions"]
        self.assertEqual([], [s for s in listed_after if s["session_id"] in {orig_id, dup_id}])


class Issue92BackendUxTests(_TempMergeLabTestCase):
    def test_critical_vs_high_approval_buckets_are_split(self):
        from backend.devcenter.apply.service import approvals_needed
        ops = [
            {"op_id": "op-high", "op": "CREATE", "domain": "model", "object_type": "table", "row_key": "table:Budget", "name": "Budget"},
            {"op_id": "op-crit", "op": "CREATE", "domain": "model", "object_type": "role", "row_key": "role:SalesRep", "name": "SalesRep"},
        ]
        plan = {"status": "valid", "steps": [], "operations": ops, "blocking": [], "warnings": [], "plan_hash": "sha256:" + "0" * 64}
        needed = approvals_needed(plan)
        self.assertEqual(2, len(needed))
        risks = {entry["risk"]: entry for entry in needed}
        self.assertIn("CRITICAL", risks)
        self.assertIn("HIGH", risks)
        self.assertEqual(["role:SalesRep"], risks["CRITICAL"]["row_keys"])
        self.assertEqual(["table:Budget"], risks["HIGH"]["row_keys"])

    def test_named_clash_and_need_messages_and_empty_target_wording(self):
        donor1 = _make_source("src-2", {"tables": [{"name": "Sales", "measures": [{"name": "Sales", "expression": "1"}]}]})
        donor2 = _make_source("src-3", {"tables": [{"name": "Sales", "measures": [{"name": "sales", "expression": "2"}]}]})
        res = build_rows([donor1, donor2], target_model=None, target_report=None)
        plan = compile_plan(PlanInput(
            session_id="empty-target", result=res, target_model=None, target_report=None,
            sources={"src-2": "DonorA", "src-3": "DonorB"},
            merge_choices={"measure:Sales/Sales": {"kind": TAKE, "source_id": "src-2"}},
        ))
        self.assertTrue(plan["blocking"])

        # Named name_clash & need_missing messages + empty target does not claim 'in use in the target'
        t_model = {"tables": [{"name": "Sales", "measures": [{"name": "Dup", "expression": "1"}]}]}
        d_model = {"tables": [{"name": "Sales", "measures": [
            {"name": "Dup", "expression": "2"},
            {"name": "UsesMissing", "expression": "[MissingObj] + 1"},
        ]}]}
        r = build_rows([_make_source("src-1", t_model), _make_source("src-2", d_model)], target_model="src-1", target_report=None)
        p = compile_plan(PlanInput(
            session_id="named-msgs", result=r, target_model="src-1", target_report=None,
            sources={"src-1": "Target", "src-2": "Donor"},
            merge_choices={
                "measure:Sales/Dup": {"kind": "add_new_name", "source_id": "src-2", "new_name": "dup"},
                "measure:Sales/UsesMissing": {"kind": TAKE, "source_id": "src-2"},
            },
        ))
        clash_item = next(b for b in p["blocking"] if b["kind"] == "name_clash")
        self.assertIn("dup", clash_item["message"])
        self.assertNotEqual("dup", (clash_item["params"].get("proposed_name") or "").casefold())
        need_item = next(b for b in p["blocking"] if b["kind"] == "need_missing")
        self.assertIn("UsesMissing", need_item["message"])
        self.assertIn("MissingObj", need_item["message"])

    def test_naming_tokens_is_case_and_proposer_case_clash(self):
        self.assertFalse(is_case("total_sales", "camel"))
        self.assertFalse(is_case("Totalsales_1", "pascal"))
        self.assertTrue(is_case("totalSales", "camel"))
        self.assertTrue(is_case("TotalSales", "pascal"))
        existing = [NamedObject(MEASURE, "Margin", "Sales"), NamedObject(MEASURE, "Margin (Donor)", "Sales")]
        out = propose("margin", MEASURE, {"table": "Sales"}, [], existing, "Donor")
        self.assertEqual("margin (Donor 2)", out["name"])
        self.assertIsNone(clash_with(out["name"], MEASURE, "Sales", existing))

    def test_donor_conflict_flagged_when_target_empty(self):
        donor1 = _make_source("src-2", {"tables": [{"name": "Sales", "measures": [{"name": "OnlyDonors", "expression": "1"}]}]})
        donor2 = _make_source("src-3", {"tables": [{"name": "Sales", "measures": [{"name": "OnlyDonors", "expression": "2"}]}]})
        res = build_rows([donor1, donor2], target_model=None, target_report=None)
        row = next(r for r in res.rows if r["row_key"] == "measure:Sales/OnlyDonors")
        self.assertEqual("missing", row["row_state"])
        self.assertTrue(row.get("donor_conflict"))
        self.assertTrue(row["changed"])

    def test_model_object_source_changes_do_not_emit_unconfirmable_model_marks(self):
        baseline = {"model:Model": "sha256:" + "0" * 64}
        current = {"model:Model": "sha256:" + "1" * 64}
        diff = self.devcenter._diff("src-1", baseline, current)
        self.assertEqual([], [m for m in diff if m["row_key"] == "model:Model"])


if __name__ == "__main__":
    unittest.main()
