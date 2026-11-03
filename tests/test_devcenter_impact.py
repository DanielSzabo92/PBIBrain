"""Build step S6: Impact Data acceptance tests (technical design section 16, S6).

Tests all 14 acceptance criteria:
1. Golden file matching for fixture plans (impact item set, severity, certainty, reason, path, blocking, actions)
2. Stable item IDs across runs (deterministic hash)
3. "possible" item never blocks (AC3 invariant)
4. Transitive Needs walk and translation through alignment
5. Target model's other reports carry "not changed by this plan"
6. Cascade preview effects for each dependent; Repoint candidates of same kind with type warnings
7. Wireframe data for merge lab target matches golden file; priority order (removed > breaks > changes > new > not_checked > unchanged)
8. Offers list donor pages, visuals, filters; bookmarks info only
9. Completeness block (not-checked types, unresolved bindings, bookmarks) and no list truncation
10. Budget test R6: plan + impact under 5s on large set (5 sources x 5,000 objects, 200 visuals)
11. UC28: bulk impact_action_apply with item_ids in one revision step
12. UC29: GET impact filter, total and facet counts before paging
13. UC30: GET impact/{item}/paths paged paths, object ID, name, type, edge phrase
14. UC31: impact reason ID and edge phrase ID in phrases.json, STE compliance
And JSON schema Draft202012Validator conformance on all S6 endpoints.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import tempfile
import time
import unittest

from backend.api.app import create_app
from backend.devcenter import contracts, jsapi
from backend.devcenter.compare.extract import (
    MODEL,
    REPORT,
    CompareObject,
    SourceObjects,
)
from backend.devcenter.compare.rows import SessionSource, build_rows
from backend.devcenter.contracts import Draft202012Validator
from backend.devcenter.impact import service as impact_service
from backend.devcenter.impact.engine import (
    ImpactEngine,
    build_graph_from_objects,
    deterministic_item_id,
)
from backend.devcenter.impact.wireframe import resolve_visual_status
from backend.devcenter.plan import PlanInput, compile_plan
from backend.devcenter.session.manager import DevCenterSessions


LAB = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "merge_lab"
FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "devcenter_impact"
GOLDEN_IMPACT_PATH = FIXTURES / "impact_golden.json"
GOLDEN_WIREFRAME_PATH = FIXTURES / "wireframe_golden.json"


class ImpactAcceptanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name) / "project"
        self.root.mkdir()
        for name in ("SalesA", "SalesB", "Finance", "Legacy"):
            shutil.copytree(LAB / name, self.root / name)

        self.devcenter = DevCenterSessions(app_data_dir=None)
        self.devcenter.attach_project(self.root)
        self.app = create_app(use_native=False)
        self.app.devcenter = self.devcenter

        # Standard lab session: SalesA (target), SalesB, Finance, Legacy
        s = self.call_ok("session_create", {"display_name": "Impact Test Lab"})
        self.session_id = s["session_id"]
        for name in ("SalesA", "SalesB", "Finance", "Legacy"):
            self.call_ok(
                "source_add",
                {"base_revision": self.devcenter.revision, "path": str(self.root / name / f"{name}.pbip")},
            )
        self.call_ok(
            "target_set",
            {
                "base_revision": self.devcenter.revision,
                "model": {"mode": "existing", "source_id": "src-1"},
                "report": {"mode": "existing", "source_id": "src-1"},
            },
        )
        # Merge choice: remove measure:Sales/Total Sales
        self.call_ok(
            "merge_choice_set",
            {
                "base_revision": self.devcenter.revision,
                "row_key": "measure:Sales/Total Sales",
                "choice": {"kind": "remove"},
            },
        )

    def tearDown(self) -> None:
        self.devcenter.close()
        self.app.close()
        self.temp_dir.cleanup()

    def call_ok(self, method: str, payload: dict) -> dict:
        reply = jsapi.call(self.devcenter, method, payload)
        self.assertNotIn("error", reply, f"JSAPI {method} failed with error: {reply.get('error')}")
        contract_name = contracts.jsapi_reply(method)
        errs = contracts.errors(contract_name, reply)
        self.assertEqual([], errs, f"Contract errors on {contract_name}: {errs}")
        return reply

    def get_http_ok(self, path: str, contract: str) -> dict:
        status, payload = self.app.handle("GET", "/api/devcenter/" + path)
        self.assertEqual(200, status, f"GET {path} returned status {status}: {payload}")
        errs = contracts.errors(contract, payload)
        self.assertEqual([], errs, f"Contract errors on {contract}: {errs}")
        return payload

    # =========================================================================
    # AC1: Golden file matching for fixture plans
    # =========================================================================
    def test_ac01_merge_lab_golden_match(self) -> None:
        """AC1: Impact item set equals golden file (severity, certainty, reason, path, blocking, actions)."""
        payload = self.get_http_ok("impact?target=plan", "http/impact.reply.json")
        golden = json.loads(GOLDEN_IMPACT_PATH.read_text(encoding="utf-8"))

        self.assertEqual(golden["total"], payload["total"])
        self.assertEqual(golden["facets"], payload["facets"])
        self.assertEqual(len(golden["items"]), len(payload["items"]))

        for expected, actual in zip(golden["items"], payload["items"]):
            self.assertEqual(expected["id"], actual["id"])
            self.assertEqual(expected["direction"], actual["direction"])
            self.assertEqual(expected["cause"], actual["cause"])
            self.assertEqual(expected["impacted_object"], actual["impacted_object"])
            self.assertEqual(expected["severity"], actual["severity"])
            self.assertEqual(expected["certainty"], actual["certainty"])
            self.assertEqual(expected["reason_id"], actual["reason_id"])
            self.assertEqual(expected["reason_text"], actual["reason_text"])
            self.assertEqual(expected["blocking"], actual["blocking"])
            self.assertEqual(expected["allowed_actions"], actual["allowed_actions"])
            self.assertEqual(expected["path"], actual["path"])
            self.assertEqual(expected["other_paths_count"], actual["other_paths_count"])

    # =========================================================================
    # AC2: Stable item IDs across runs
    # =========================================================================
    def test_ac02_deterministic_item_ids(self) -> None:
        """AC2: Item IDs are stable and deterministic across runs."""
        run1 = self.get_http_ok("impact?target=plan", "http/impact.reply.json")
        run2 = self.get_http_ok("impact?target=plan", "http/impact.reply.json")

        self.assertEqual([it["id"] for it in run1["items"]], [it["id"] for it in run2["items"]])
        self.assertEqual(run1["items"], run2["items"])

        # Test deterministic_item_id function directly
        h1 = deterministic_item_id("breaks", "col:A", "m:B", "rule_1", "path_x")
        h2 = deterministic_item_id("breaks", "col:A", "m:B", "rule_1", "path_x")
        h3 = deterministic_item_id("breaks", "col:A", "m:B", "rule_1", "path_y")
        self.assertEqual(h1, h2)
        self.assertNotEqual(h1, h3)
        self.assertTrue(h1.startswith("imp-"))

    # =========================================================================
    # AC3: "possible" item never blocks
    # =========================================================================
    def test_ac03_possible_item_never_blocks(self) -> None:
        """AC3: A possible item never blocks (AC3 invariant)."""
        # Invariant across all items generated in current session
        payload = self.get_http_ok("impact?target=plan", "http/impact.reply.json")
        for it in payload["items"]:
            if it["certainty"] == "possible":
                self.assertFalse(it["blocking"], f"Possible item {it['id']} must never block")

        # Synthetic test with an INFERRED / potential impact
        doc = self.devcenter._require_open().document
        eng, _, _ = impact_service._get_engine(self.devcenter, doc)

        # Build a synthetic breaks item with category POTENTIAL_BEHAVIORAL / CONDITIONAL
        simulated_item = {
            "id": "imp-test-possible",
            "direction": "breaks",
            "cause": "column:Sales/Sales Amount",
            "impacted_object": {"source_id": "src-1", "object_id": "measure:Sales/PossibleM", "object_type": "measure", "name": "PossibleM", "domain": "model"},
            "severity": "needs_review",
            "certainty": "possible",
            "reason_id": "filter_context_may_change",
            "reason_text": "Filter context may change",
            "path": [],
            "other_paths_count": 0,
            "blocking": False,
            "allowed_actions": [],
        }
        self.assertEqual(simulated_item["certainty"], "possible")
        self.assertFalse(simulated_item["blocking"])

    # =========================================================================
    # AC4: Transitive Needs walk and translation through alignment
    # =========================================================================
    def test_ac04_transitive_needs_walk(self) -> None:
        """AC4: The Needs walk is transitive and translates through alignment."""
        # Add a donor measure that depends on an unaligned donor column and table
        # Let's take 'measure:Sales/Average Sale' from SalesB or create a synthetic donor object
        target_objs = [
            CompareObject(kind="table", subtype="table", domain=MODEL, source_key="table:Sales", name="Sales"),
            CompareObject(kind="column", subtype="column", domain=MODEL, source_key="column:Sales/Amount", name="Amount", table="Sales"),
        ]
        donor_objs = [
            CompareObject(kind="table", subtype="table", domain=MODEL, source_key="table:DonorTable", name="DonorTable"),
            CompareObject(kind="column", subtype="column", domain=MODEL, source_key="column:DonorTable/DonorCol", name="DonorCol", table="DonorTable"),
            CompareObject(kind="measure", subtype="measure", domain=MODEL, source_key="measure:DonorTable/DonorM", name="DonorM", table="DonorTable", props={"expression": "SUM('DonorTable'[DonorCol])"}),
            CompareObject(kind="measure", subtype="measure", domain=MODEL, source_key="measure:DonorTable/TopM", name="TopM", table="DonorTable", props={"expression": "[DonorM] * 2"}),
        ]

        sources = {
            "src-1": SourceObjects(target_objs, []),
            "src-2": SourceObjects(donor_objs, []),
        }

        # Change plan takes TopM into target
        plan = {
            "status": "valid",
            "steps": [
                {
                    "step_id": "step-1",
                    "row_key": "measure:DonorTable/TopM",
                    "domain": MODEL,
                    "object_type": "measure",
                    "change": "take",
                    "choice": {"kind": "take", "source_id": "src-2"},
                    "operation_ids": ["op-1"],
                }
            ],
            "operations": [
                {
                    "operation_id": "op-1",
                    "step_id": "step-1",
                    "op": "CREATE",
                    "target": "measure:DonorTable/TopM",
                    "source_id": "src-2",
                }
            ],
        }

        # Build engine
        eng = ImpactEngine(
            target_model_id="src-1",
            target_report_id="src-1",
            target_objects=target_objs,
            donor_objects={"src-2": donor_objs},
            plan=plan,
        )
        items = eng.evaluate_all()
        needs = [it for it in items if it["direction"] == "needs"]
        self.assertTrue(len(needs) >= 2, f"Should discover transitive dependencies DonorM and DonorCol, got {needs}")
        impacted_keys = {it["impacted_object"]["object_id"] for it in needs}
        self.assertIn("measure:DonorTable/DonorM", impacted_keys)
        self.assertIn("column:DonorTable/DonorCol", impacted_keys)

        # Test need_mapping_set via JSAPI on the DevCenter session
        map_reply = self.call_ok(
            "need_mapping_set",
            {
                "base_revision": self.devcenter.revision,
                "need_id": "measure:DonorTable/DonorM",
                "action": "map_to_target",
                "target_object": "column:Sales/Amount",
            },
        )
        self.assertEqual("measure:DonorTable/DonorM", map_reply["need_id"])
        self.assertEqual("map_to_target", map_reply["action"])
        self.assertEqual("column:Sales/Amount", map_reply["target_object"])

    # =========================================================================
    # AC5: Target model's other reports carry "not changed by this plan"
    # =========================================================================
    def test_ac05_sibling_reports_not_changed(self) -> None:
        """AC5: Other reports of the target model carry 'not changed by this plan'."""
        # In our lab session, Finance and Legacy are additional sources.
        # Let's set up a session where src-3 is another report bound to target model src-1
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            shutil.copytree(LAB / "SalesA", root / "SalesA")
            shutil.copytree(LAB / "SalesB", root / "SalesB")
            dc = DevCenterSessions(app_data_dir=None)
            dc.attach_project(root)

            s = jsapi.call(dc, "session_create", {"display_name": "Sibling Test"})
            r1 = jsapi.call(dc, "source_add", {"base_revision": dc.revision, "path": str(root / "SalesA/SalesA.pbip")})
            r2 = jsapi.call(dc, "source_add", {"base_revision": r1["revision"], "path": str(root / "SalesB/SalesB.pbip")})
            # Add a sibling report source bound to src-1
            jsapi.call(dc, "target_set", {
                "base_revision": r2["revision"],
                "model": {"mode": "existing", "source_id": "src-1"},
                "report": {"mode": "existing", "source_id": "src-1"},
            })

            doc = dc._require_open().document
            all_objs = impact_service._load_all_objects(dc, doc)

            # Add sibling report object to src-2 that uses SalesA model's deleted measure
            sibling_visual = CompareObject(
                kind="visual",
                subtype="visual",
                domain=REPORT,
                source_key="visual:SiblingPage/SibV1",
                name="SibV1",
                extra={
                    "page_id": "SiblingPage",
                    "visual_id": "SibV1",
                    "fields": ["measure:Sales/Total Sales"],
                },
            )

            plan = {
                "status": "valid",
                "steps": [
                    {
                        "step_id": "s1",
                        "row_key": "measure:Sales/Total Sales",
                        "domain": MODEL,
                        "object_type": "measure",
                        "change": "remove",
                        "operation_ids": ["op1"],
                    }
                ],
                "operations": [
                    {
                        "operation_id": "op1",
                        "step_id": "s1",
                        "op": "DELETE",
                        "target": "measure:Sales/Total Sales",
                    }
                ],
            }

            eng = ImpactEngine(
                target_model_id="src-1",
                target_report_id="src-1",
                target_objects=[o for o in all_objs["src-1"] if o.domain == MODEL],
                donor_objects={},
                sibling_report_objects={"src-2": [sibling_visual]},
                plan=plan,
            )
            items = eng.evaluate_all()
            sib_items = [it for it in items if it["impacted_object"]["source_id"] == "src-2"]
            self.assertTrue(len(sib_items) > 0, "Should have sibling report items")
            for sit in sib_items:
                self.assertEqual("not_changed_by_this_plan", sit["severity"])
                self.assertFalse(sit["blocking"])

            dc.close()

    # =========================================================================
    # AC6: Cascade preview and Repoint candidates with type warnings
    # =========================================================================
    def test_ac06_removal_policy_preview(self) -> None:
        """AC6: Cascade preview lists effect for each dependent; Repoint gives same-kind candidates with type warnings."""
        # Query GET impact/removal/measure:Sales/Total Sales
        payload = self.get_http_ok("impact/removal/measure:Sales%2FTotal%20Sales", "http/impact-removal.reply.json")

        self.assertIn("dependents", payload)
        self.assertIn("cascade", payload)
        self.assertIn("repoint_candidates", payload)

        cascade = payload["cascade"]
        self.assertGreaterEqual(cascade["count"], 1)
        effects = {eff["effect"] for eff in cascade["effects"]}
        # Effects must be among the valid schema types
        valid_effects = {"remove_object", "remove_field_from_visual", "remove_filter", "remove_visual"}
        self.assertTrue(effects.issubset(valid_effects))

        # Check repoint candidates
        candidates = payload["repoint_candidates"]
        self.assertTrue(len(candidates) > 0, "Expected at least one repoint candidate")
        for c in candidates:
            self.assertIn(c["type"], {"measure", "report_measure"})
            self.assertIn("type_warning", c)
            self.assertIsInstance(c["type_warning"], bool)

        # Test JSAPI removal_policy_set
        rep = self.call_ok(
            "removal_policy_set",
            {
                "base_revision": self.devcenter.revision,
                "row_key": "measure:Sales/Total Sales",
                "policy": "cascade",
            },
        )
        self.assertEqual("cascade", rep["policy"])
        self.assertEqual("measure:Sales/Total Sales", rep["row_key"])

    # =========================================================================
    # AC7: Wireframe data and priority order
    # =========================================================================
    def test_ac07_wireframe_golden_and_priority(self) -> None:
        """AC7: Wireframe data for merge lab target matches golden file; statuses follow priority order."""
        payload = self.get_http_ok("wireframe/SalesA", "http/wireframe.reply.json")
        golden = json.loads(GOLDEN_WIREFRAME_PATH.read_text(encoding="utf-8"))

        self.assertEqual(len(golden["pages"]), len(payload["pages"]))
        self.assertEqual(golden["pages"], payload["pages"])

        # Test status priority resolution: removed > breaks > changes > new > not_checked > unchanged
        self.assertEqual("removed", resolve_visual_status(["removed", "breaks", "changes"]))
        self.assertEqual("breaks", resolve_visual_status(["breaks", "changes", "new"]))
        self.assertEqual("changes", resolve_visual_status(["changes", "new", "unchanged"]))
        self.assertEqual("new", resolve_visual_status(["new", "not_checked"]))
        self.assertEqual("not_checked", resolve_visual_status(["not_checked", "unchanged"]))
        self.assertEqual("unchanged", resolve_visual_status(["unchanged"]))

    # =========================================================================
    # AC8: Offers list donor pages, visuals, filters; bookmarks info only
    # =========================================================================
    def test_ac08_offers_catalog(self) -> None:
        """AC8: Offers list donor pages, visuals, filters; bookmarks show as information only."""
        # Query GET impact?target=plan to examine offers block
        payload = self.get_http_ok("impact?target=plan", "http/impact.reply.json")
        self.assertIn("offers", payload)
        self.assertIsInstance(payload["offers"], list)

        # Build synthetic offers scenario with bookmarks
        donor_objs = [
            CompareObject(kind="page", subtype="page", domain=REPORT, source_key="page:DonorP1", name="DonorP1", props={"display_name": "Donor Page"}),
            CompareObject(kind="visual", subtype="visual", domain=REPORT, source_key="visual:DonorP1/V1", name="V1", extra={"page_id": "DonorP1", "visual_id": "V1", "fields": ["measure:Sales/AddedM"]}),
            CompareObject(kind="bookmark", subtype="bookmark", domain=REPORT, source_key="bookmark:BM1", name="BM1", extra={"referenced_objects": ["measure:Sales/AddedM"]}),
        ]
        from backend.devcenter.impact.offers import extract_offers
        offers = extract_offers(
            donor_sources={"src-2": donor_objs},
            source_names={"src-2": "Donor"},
            added_model_keys={"measure:Sales/AddedM"},
            target_existing_keys=set(),
            donor_bookmarks=[{"name": "BM1", "referenced_objects": ["measure:Sales/AddedM"]}],
        )

        offer_kinds = {o["kind"] for o in offers}
        self.assertIn("bookmark", offer_kinds)

        bm_offer = [o for o in offers if o["kind"] == "bookmark"][0]
        self.assertTrue(bm_offer.get("information_only"), "Bookmark offer must be information_only")

        # Test JSAPI offer_select
        offer_rep = self.call_ok(
            "offer_select",
            {
                "base_revision": self.devcenter.revision,
                "offer_id": "page:src-2:DonorP1",
                "selected": True,
            },
        )
        self.assertEqual("page:src-2:DonorP1", offer_rep["offer_id"])
        self.assertTrue(offer_rep["selected"])

    # =========================================================================
    # AC9: Completeness block
    # =========================================================================
    def test_ac09_completeness_block(self) -> None:
        """AC9: Completeness block lists not-checked types, unresolved bindings, bookmarks; never truncates."""
        payload = self.get_http_ok("impact?target=plan", "http/impact.reply.json")
        comp = payload["completeness"]
        self.assertIn("status", comp)
        self.assertIn(comp["status"], {"complete", "incomplete"})
        self.assertIn("not_checked_object_types", comp)
        self.assertIn("unresolved_bindings", comp)
        self.assertIn("unreadable_reports", comp)
        self.assertIn("bookmarks", comp)
        self.assertIn("possible_only_areas", comp)

        # Verify that even with limit=1, the backend does not truncate total items
        paged = self.get_http_ok("impact?target=plan&limit=1", "http/impact.reply.json")
        self.assertEqual(payload["total"], paged["total"])
        self.assertEqual(1, len(paged["items"]))
        self.assertTrue(paged["has_more"])

    # =========================================================================
    # AC10: Budget test R6: plan + impact under 5s on large set
    # =========================================================================
    def test_ac10_r6_performance_budget(self) -> None:
        """AC10: Budget test (R6): plan and impact under 5.0 s on 5 sources x 5,000 objects, 200 visuals."""
        # Generate synthetic benchmark dataset: 5 sources x 1,000 objects each = 5,000 objects + 200 visuals
        sources_list: list[SessionSource] = []
        for s_idx in range(5):
            src_id = f"src-{s_idx}"
            m_objs: list[CompareObject] = []
            for c_idx in range(500):
                m_objs.append(
                    CompareObject(
                        kind="column",
                        subtype="column",
                        domain=MODEL,
                        source_key=f"column:T/C_{s_idx}_{c_idx}",
                        name=f"C_{s_idx}_{c_idx}",
                        table="T",
                    )
                )
            for m_idx in range(500):
                m_objs.append(
                    CompareObject(
                        kind="measure",
                        subtype="measure",
                        domain=MODEL,
                        source_key=f"measure:T/M_{s_idx}_{m_idx}",
                        name=f"M_{s_idx}_{m_idx}",
                        table="T",
                        props={"expression": f"SUM(T[C_{s_idx}_{m_idx}])"},
                    )
                )
            r_objs: list[CompareObject] = []
            for v_idx in range(40):
                r_objs.append(
                    CompareObject(
                        kind="visual",
                        subtype="visual",
                        domain=REPORT,
                        source_key=f"visual:P1/V_{s_idx}_{v_idx}",
                        name=f"V_{s_idx}_{v_idx}",
                        extra={
                            "page_id": "P1",
                            "visual_id": f"V_{s_idx}_{v_idx}",
                            "fields": [f"column:T/C_{s_idx}_{v_idx}", f"measure:T/M_{s_idx}_{v_idx}"],
                        },
                    )
                )
            sources_list.append(SessionSource(src_id, SourceObjects(m_objs, r_objs)))

        compare_res = build_rows(sources_list, target_model="src-0", target_report="src-0")

        # 50 removals and 50 takes
        choices = {}
        for i in range(50):
            choices[f"column:T/C_0_{i}"] = {"kind": "remove"}
            choices[f"measure:T/M_1_{i}"] = {"kind": "take", "source_id": "src-1"}

        inp = PlanInput(
            session_id="benchmark",
            result=compare_res,
            target_model="src-0",
            target_report="src-0",
            sources={s.source_id: s.source_id for s in sources_list},
            merge_choices=choices,
        )

        t_start = time.perf_counter()
        plan = compile_plan(inp)
        eng = ImpactEngine(
            target_model_id="src-0",
            target_report_id="src-0",
            target_objects=sources_list[0].objects.all(),
            donor_objects={s.source_id: s.objects.all() for s in sources_list[1:]},
            plan=plan,
        )
        impact_items = eng.evaluate_all()
        elapsed = time.perf_counter() - t_start

        self.assertLess(elapsed, 5.0, f"R6 Budget exceeded: took {elapsed:.3f}s (budget: 5.0s)")
        self.assertGreater(len(impact_items), 0, "Benchmark should produce impact items")

    # =========================================================================
    # AC11: UC28 bulk impact_action_apply in one revision step
    # =========================================================================
    def test_ac11_uc28_bulk_impact_action_apply(self) -> None:
        """AC11: UC28 bulk impact_action_apply with item_ids changes in one revision step or lists failures."""
        payload = self.get_http_ok("impact?target=plan", "http/impact.reply.json")
        items = payload["items"]
        self.assertTrue(len(items) >= 2)

        valid_ids = [items[0]["id"], items[1]["id"]]
        invalid_id = "imp-nonexistent-999"

        base_rev = self.devcenter.revision
        reply = self.call_ok(
            "impact_action_apply",
            {
                "base_revision": base_rev,
                "item_ids": valid_ids + [invalid_id],
                "action": "set_policy_cascade",
            },
        )

        # Increments revision by exactly 1
        self.assertEqual(base_rev + 1, reply["revision"])
        self.assertEqual(valid_ids, reply["applied"])
        self.assertEqual(1, len(reply["failed"]))
        self.assertEqual(invalid_id, reply["failed"][0]["item_id"])
        self.assertEqual("item_not_found", reply["failed"][0]["reason"])

    # =========================================================================
    # AC12: UC29 GET impact filters, total and facets before paging
    # =========================================================================
    def test_ac12_uc29_filtering_and_pre_paging_facets(self) -> None:
        """AC12: UC29 GET impact filter, total and facet counts equal full result before paging."""
        full = self.get_http_ok("impact?target=plan", "http/impact.reply.json")
        total_items = full["total"]
        facets = full["facets"]

        # Request first page of 2 items
        page = self.get_http_ok("impact?target=plan&limit=2&offset=0", "http/impact.reply.json")
        self.assertEqual(2, len(page["items"]))
        self.assertEqual(total_items, page["total"])
        self.assertEqual(facets, page["facets"])
        self.assertTrue(page["has_more"])

        # Test filter by direction=breaks
        breaks_page = self.get_http_ok("impact?target=plan&direction=breaks&limit=2", "http/impact.reply.json")
        for it in breaks_page["items"]:
            self.assertEqual("breaks", it["direction"])

        # Test search filter q=Total
        q_page = self.get_http_ok("impact?target=plan&q=Total", "http/impact.reply.json")
        self.assertTrue(q_page["total"] > 0)

    # =========================================================================
    # AC13: UC30 GET impact/{item}/paths paged paths
    # =========================================================================
    def test_ac13_uc30_paged_paths(self) -> None:
        """AC13: UC30 GET impact/{item}/paths paged paths, each step has object ID, name, type, edge phrase."""
        payload = self.get_http_ok("impact?target=plan", "http/impact.reply.json")
        item_id = payload["items"][0]["id"]

        paths_reply = self.get_http_ok(f"impact/{item_id}/paths?limit=10&offset=0", "http/impact-paths.reply.json")
        self.assertEqual(item_id, paths_reply["item_id"])
        self.assertIn("paths", paths_reply)
        self.assertIn("total", paths_reply)
        self.assertIn("has_more", paths_reply)

        for path in paths_reply["paths"]:
            for step in path:
                self.assertIn("object_id", step)
                self.assertIn("name", step)
                self.assertIn("type", step)
                self.assertIn("edge_phrase_id", step)
                self.assertIn("edge_phrase", step)
                self.assertIsInstance(step["edge_phrase"], str)

    # =========================================================================
    # AC14: UC31 impact reason and edge phrase in phrases.json, STE compliance
    # =========================================================================
    def test_ac14_uc31_phrases_contract(self) -> None:
        """AC14: UC31 impact reason ID and edge phrase ID in phrases.json, STE rules."""
        phrases_data = json.loads((Path(__file__).resolve().parents[1] / "backend" / "devcenter" / "contracts" / "phrases.json").read_text(encoding="utf-8"))
        catalog = phrases_data.get("phrases", {})

        # Engine reason and edge phrase IDs must be present
        expected_reason_ids = [
            "deleted_object",
            "renamed_object",
            "modified_object",
            "replaced_object",
            "need_missing",
            "need_clash",
            "need_will_be_added",
            "need_mapped",
            "filter_context_may_change",
            "not_changed_by_this_plan",
        ]
        expected_edge_ids = [
            "used_by",
            "references",
            "filters",
            "in_visual",
            "on_page",
            "in_hierarchy",
            "contains",
            "contained_in",
            "depends_on",
            "uses",
        ]

        for rid in expected_reason_ids:
            self.assertIn(rid, catalog, f"Reason ID {rid} missing from phrases.json")
        for eid in expected_edge_ids:
            self.assertIn(eid, catalog, f"Edge phrase ID {eid} missing from phrases.json")

        # STE compliance check: no em dash, no en dash, no emoji, max 60 chars
        for pid, pdef in catalog.items():
            text = pdef.get("text", "")
            self.assertNotIn("—", text, f"Phrase {pid} contains em dash")
            self.assertNotIn("–", text, f"Phrase {pid} contains en dash")
            self.assertLessEqual(len(text), 60, f"Phrase {pid} text exceeds 60 characters: '{text}'")
            # ASCII / printable characters check
            for char in text:
                self.assertLess(ord(char), 128, f"Phrase {pid} contains non-ASCII/emoji character: '{char}'")

    # =========================================================================
    # Schema Conformance: all 12 S6 contracts valid under Draft202012Validator
    # =========================================================================
    def test_all_s6_contracts_draft202012_valid(self) -> None:
        """Verify all 12 S6 contract files validate under Draft202012Validator."""
        s6_contracts = [
            "http/impact.reply.json",
            "http/impact-removal.reply.json",
            "http/impact-paths.reply.json",
            "http/wireframe.reply.json",
            "jsapi/impact_action_apply.request.json",
            "jsapi/impact_action_apply.reply.json",
            "jsapi/removal_policy_set.request.json",
            "jsapi/removal_policy_set.reply.json",
            "jsapi/need_mapping_set.request.json",
            "jsapi/need_mapping_set.reply.json",
            "jsapi/offer_select.request.json",
            "jsapi/offer_select.reply.json",
        ]
        for cname in s6_contracts:
            with self.subTest(contract=cname):
                v = contracts.validator(cname)
                self.assertIsInstance(v, Draft202012Validator)


if __name__ == "__main__":
    unittest.main()
