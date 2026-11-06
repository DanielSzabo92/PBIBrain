"""Step U8 (ticket 22): the Impact replies of the fake server follow the S6 contract schemas.

The UI e2e specs run on the fake server, so its GET impact, paths, removal, and wireframe replies and its
impact_action_apply, offer_select, and need_mapping_set calls must have the S6 shapes and rules:
facets and total before paging (UC29), one revision step for a bulk action with the failed items (UC28),
and the blocking rule of a removal policy.
"""

from __future__ import annotations

import unittest

from tests import devcenter_ui_server as fake
from tests.test_devcenter_ui_contract import _contract_validator


class FakeImpactContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.state = fake.FakeDevCenter()

    def validate(self, name: str, value: object) -> None:
        errors = sorted(_contract_validator(name).iter_errors(value), key=lambda error: list(error.path))
        self.assertEqual([f"{list(error.path)}: {error.message}"[:300] for error in errors], [], name)

    def get(self, path: str, query: dict[str, list[str]] | None = None) -> dict:
        return self.state.read("GET", f"/api/devcenter/{path}", query or {}, {})

    def call(self, method: str, payload: dict) -> dict:
        request = {"base_revision": self.state.revision, **payload}
        self.validate(f"jsapi/{method}.request.json", request)
        reply = self.state.call(method, request)
        self.validate(f"jsapi/{method}.reply.json", reply)
        return reply

    def test_get_impact_follows_the_schema_and_counts_facets_before_paging(self) -> None:
        for scenario in ("default", "large-5000-rows"):
            with self.subTest(scenario=scenario):
                self.state.load(scenario)
                full = self.get("impact", {"limit": ["10000"]})
                self.validate("http/impact.reply.json", full)
                page = self.get("impact", {"limit": ["2"], "direction": ["breaks"]})
                self.validate("http/impact.reply.json", page)
                self.assertEqual(len(page["items"]), 2)
                breaks = [item for item in full["items"] if item["direction"] == "breaks"]
                self.assertEqual(page["total"], len(breaks))
                self.assertEqual(page["facets"]["direction"]["breaks"], len(breaks))
                self.assertEqual(page["facets"]["blocking"]["true"], sum(item["blocking"] for item in breaks))

    def test_each_filter_gives_the_expected_items(self) -> None:
        cases = {
            "blocking": (["true"], {"imp-b01", "imp-b02", "imp-b03", "imp-b04", "imp-n01", "imp-n02"}),
            "certainty": (["possible"], {"imp-b06"}),
            "severity": (["missing"], {"imp-n01", "imp-n02"}),
            "object_type": (["column"], {"imp-n01", "imp-n04"}),
            "source": (["src-4"], {"imp-b01", "imp-b04", "imp-b06"}),
            "q": (["margin"], {"imp-b03", "imp-b04"}),
        }
        for name, (value, expected) in cases.items():
            with self.subTest(filter=name):
                reply = self.get("impact", {name: value, "limit": ["500"]})
                self.assertEqual({item["id"] for item in reply["items"]}, expected)

    def test_proposal_items_show_only_with_include_proposals(self) -> None:
        without = {item["id"] for item in self.get("impact", {"limit": ["500"]})["items"]}
        with_proposals = self.get("impact", {"limit": ["500"], "include_proposals": ["true"]})
        self.validate("http/impact.reply.json", with_proposals)
        self.assertNotIn("imp-p01", without)
        self.assertIn("imp-p01", {item["id"] for item in with_proposals["items"]})

    def test_paths_removal_and_wireframe_replies_follow_the_schemas(self) -> None:
        paths = self.get("impact/imp-b01/paths", {"limit": ["2"]})
        self.validate("http/impact-paths.reply.json", paths)
        self.assertEqual((paths["total"], len(paths["paths"]), paths["has_more"]), (3, 2, True))
        self.validate("http/impact-paths.reply.json", self.get("impact/imp-b05/paths"))
        removal = self.get("impact/removal/row-budget")
        self.validate("http/impact-removal.reply.json", removal)
        self.assertEqual((len(removal["dependents"]), removal["cascade"]["count"]), (3, 3))
        self.assertEqual([candidate["type_warning"] for candidate in removal["repoint_candidates"]], [False, True])
        self.validate("http/impact-removal.reply.json", self.get("impact/removal/row-other"))
        for report in ("target", "src-1"):
            with self.subTest(report=report):
                wireframe = self.get(f"wireframe/{report}")
                self.validate("http/wireframe.reply.json", wireframe)
        statuses = {visual["status"] for page in self.get("wireframe/target")["pages"] for visual in page["visuals"]}
        self.assertEqual(statuses, {"removed", "breaks", "changes", "new", "not_checked", "unchanged"})

    def test_bulk_action_is_one_revision_step_and_lists_the_failed_items(self) -> None:
        before = self.state.revision
        reply = self.call("impact_action_apply", {"item_ids": ["imp-b03", "imp-b04", "imp-b01"], "action": "include_in_rewrite"})
        self.assertEqual(self.state.revision, before + 1)
        self.assertEqual(reply["applied"], ["imp-b03", "imp-b04"])
        self.assertEqual(reply["failed"], [{"item_id": "imp-b01", "reason": "action_not_allowed"}])
        blocking = {item["id"] for item in self.get("impact", {"blocking": ["true"], "limit": ["500"]})["items"]}
        self.assertEqual(blocking, {"imp-b01", "imp-b02", "imp-n01", "imp-n02"})
        reply = self.call("impact_action_apply", {"item_ids": ["imp-n01"], "action": "add_from_donor"})
        self.assertEqual(reply["applied"], ["imp-n01"])

    def test_a_removal_policy_other_than_block_resolves_the_items_of_the_row(self) -> None:
        # The fake compare rows use short row keys ("row-budget"), not the S3 key form, so the schemas are not checked here.
        self.state.call("removal_policy_set", {"base_revision": self.state.revision, "row_key": "row-budget", "policy": "cascade", "repoint_target": None})
        blocking = {item["id"] for item in self.get("impact", {"blocking": ["true"], "limit": ["500"]})["items"]}
        self.assertFalse(blocking & {"imp-b01", "imp-b02"})
        self.state.call("removal_policy_set", {"base_revision": self.state.revision, "row_key": "row-budget", "policy": "block", "repoint_target": None})
        blocking = {item["id"] for item in self.get("impact", {"blocking": ["true"], "limit": ["500"]})["items"]}
        self.assertTrue({"imp-b01", "imp-b02"} <= blocking)

    def test_offer_select_and_need_mapping_set_follow_the_schemas(self) -> None:
        offer_id = "visual:Sales report/Overview/Top products"
        reply = self.call("offer_select", {"offer_id": offer_id, "selected": True})
        self.assertTrue(reply["selected"])
        offers = {offer["id"]: offer for offer in self.get("impact")["offers"]}
        self.assertTrue(offers[offer_id]["selected"])
        with self.assertRaises(fake.FakeError) as raised:
            self.call("offer_select", {"offer_id": "bookmark:Finance report/Year end", "selected": True})
        self.assertEqual(raised.exception.code, "action_not_allowed")
        self.call("need_mapping_set", {"need_id": "imp-n02", "action": "map_to_target", "target_object": "table:Rates"})
        item = next(item for item in self.get("impact", {"limit": ["500"]})["items"] if item["id"] == "imp-n02")
        self.assertEqual((item["blocking"], item["severity"]), (False, "mapped"))

    def test_the_large_scenario_has_a_graph_of_150_nodes_or_fewer_for_possible_items(self) -> None:
        self.state.load("large-5000-rows")
        reply = self.get("impact", {"certainty": ["possible"], "limit": ["500"]})
        self.assertEqual(reply["total"], 100)
        nodes = {step["object_id"] for item in reply["items"] for step in item["path"]}
        self.assertLessEqual(len(nodes), 150)
        self.assertEqual(self.get("impact", {"limit": ["50"]})["total"], 5000)


if __name__ == "__main__":
    unittest.main()
