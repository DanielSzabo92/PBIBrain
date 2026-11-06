"""Step U10: the apply calls of the fake Development Center server match the S9 contracts.

The e2e spec frontend/e2e/devcenter-apply.spec.js uses these replies and the /__test__/apply control.
"""

from __future__ import annotations

import unittest

from backend.devcenter import contracts
from tests import devcenter_ui_server as fake


class FakeApplyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = fake.FakeDevCenter(sleep=lambda _seconds: None)
        self.state.load("apply-ready")

    def call(self, method: str, payload: dict | None = None) -> dict:
        request = {"base_revision": self.state.revision, **(payload or {})}
        self.assertEqual([], contracts.errors(contracts.jsapi_request(method), request), request)
        reply = self.state.call(method, request)
        self.assertEqual([], contracts.errors(contracts.jsapi_reply(method), reply), reply)
        return reply

    def last(self) -> dict:
        reply = self.state.read("GET", "/api/devcenter/apply/last", {}, {})
        self.assertEqual([], contracts.errors("http/apply-last.reply.json", reply), reply)
        return reply

    def test_apply_undo_and_report_replies_match_the_contracts_and_change_apply_last(self) -> None:
        self.assertFalse(self.last()["backup_present"])
        applied = self.call("apply", {"plan_hash": "plan-0012", "approvals": []})
        self.assertEqual("apply", applied["kind"])
        last = self.last()
        self.assertTrue(last["backup_present"])
        self.assertEqual(applied["apply_id"], last["apply_id"])
        report = self.call("change_report_write", {"apply_id": applied["apply_id"], "file_name": "Merge change report 2026-11-06.md"})
        self.assertTrue(report["path"].endswith("Merge change report 2026-11-06.md"))
        undone = self.call("undo_apply", {"apply_id": applied["apply_id"]})
        self.assertEqual(applied["apply_id"], undone["apply_id"])
        self.assertFalse(self.last()["backup_present"])
        self.assertTrue(self.last()["undone"])

    def test_format_only_clears_the_non_canonical_files(self) -> None:
        self.state.set_apply({"apply-preview": {"non_canonical_files": ["a.tmdl"]}})
        reply = self.call("format_only_apply")
        self.assertEqual("format_only", reply["kind"])
        self.assertEqual([], self.state.read("GET", "/api/devcenter/apply/preview", {}, {})["non_canonical_files"])

    def test_the_test_control_changes_the_reply_fields_and_the_reads(self) -> None:
        self.state.set_apply({
            "replies": {"apply": {"notices": ["apply_external_changes"], "desktop_state": "open_saved",
                                  "rescan_differences": [{"object": "Sales/Margin", "expected": "a", "found": "b"}]}},
            "apply-progress": {"state": "running", "step": "rescan", "step_index": 10},
        })
        progress = self.state.read("GET", "/api/devcenter/apply/progress", {}, {})
        self.assertEqual([], contracts.errors("http/apply-progress.reply.json", progress), progress)
        self.assertEqual(10, progress["step_index"])
        reply = self.call("apply", {"plan_hash": "plan-0012", "approvals": []})
        self.assertEqual(["apply_external_changes"], reply["notices"])
        self.assertEqual(1, len(reply["rescan_differences"]))


if __name__ == "__main__":
    unittest.main()
