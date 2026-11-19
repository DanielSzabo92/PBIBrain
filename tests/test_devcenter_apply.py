"""Tests for S9 local apply, format-only apply, undo, change report, and UC5/UC6/UC7/UC32."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import tempfile
import time
import types
import unittest
from unittest.mock import patch

from backend.adapters.pbir import PBIRWriteError
from backend.adapters.tabular_metadata import TabularMetadataAdapter
from backend.devcenter import contracts
from backend.devcenter.compare import service as compare_service
from backend.devcenter.http_routes import dispatch as devcenter_dispatch
from backend.devcenter.jsapi import call as jsapi_call
from backend.devcenter.session.manager import DevCenterSessions
from change_guard.merge import MergeGuardError, dir_file_hashes

REPOSITORY = Path(__file__).resolve().parents[1]
LAB = REPOSITORY / "tests" / "fixtures" / "merge_lab"
BRIDGE = REPOSITORY / "backend/adapters/tabular_metadata/dotnet/bin/Release/net8.0/TabularMetadata.dll"


def _http_get(dc: DevCenterSessions, *parts: str) -> tuple[int, dict]:
    app = types.SimpleNamespace(devcenter=dc)
    status, payload = devcenter_dispatch(app, "GET", list(parts), {}, b"")
    return status, payload


@unittest.skipUnless(BRIDGE.is_file(), "Build the TOM bridge first")
class DevCenterApplyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="pbibrain-s9-")
        self.root = Path(self.tmp.name)
        self.project_root = self.root / "project"
        self.project_root.mkdir()
        shutil.copytree(LAB / "SalesA", self.project_root / "SalesA")
        shutil.copytree(LAB / "SalesB", self.project_root / "SalesB")
        shutil.copytree(LAB / "Finance", self.project_root / "Finance")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _open_sales_session(self) -> tuple[DevCenterSessions, str, str]:
        dc = DevCenterSessions(app_data_dir=self.root / "appdata")
        dc.attach_project(self.project_root)
        dc.create({"display_name": "S9 Sales Merge"})
        s1 = dc.source_add({"base_revision": 1, "path": str(self.project_root / "SalesA/SalesA.pbip")})
        s2 = dc.source_add({"base_revision": s1["revision"], "path": str(self.project_root / "SalesB/SalesB.pbip")})
        target_id = s1["source"]["source_id"]
        donor_id = s2["source"]["source_id"]
        ts = dc.target_set({
            "base_revision": s2["revision"],
            "model": {"mode": "existing", "source_id": target_id},
            "report": {"mode": "existing", "source_id": target_id},
        })
        _ = ts
        return dc, target_id, donor_id

    def _select_new_measure_and_modify(
        self,
        dc: DevCenterSessions,
        donor_id: str,
        *,
        include_report_page: bool = False,
    ) -> int:
        rev = dc._require_open().document["revision"]
        rows = compare_service.compare_rows(dc, {"source": [donor_id]})["rows"]
        m_new = next((r for r in rows if r["object_type"] == "measure" and r["name"] == "NewMeasure"), None)
        if m_new is not None:
            r = jsapi_call(dc, "merge_choice_set", {
                "base_revision": rev,
                "row_key": m_new["row_key"],
                "choice": {"kind": "take", "source_id": donor_id},
            })
            self.assertNotIn("error", r)
            rev = r["revision"]
        m_diff = next(
            (r for r in rows if r["object_type"] == "measure" and any(c["source_id"] == donor_id and c.get("present") and c["state"] == "different" for c in r["cells"])),
            None,
        )
        if m_diff is not None:
            r = jsapi_call(dc, "merge_choice_set", {
                "base_revision": rev,
                "row_key": m_diff["row_key"],
                "choice": {"kind": "take", "source_id": donor_id},
            })
            self.assertNotIn("error", r)
            rev = r["revision"]
        if include_report_page:
            missing_page = next(
                (r for r in rows if r["object_type"] == "page" and r["row_state"] == "missing_in_target"),
                None,
            )
            if missing_page is None:
                missing_page = next((r for r in rows if r["object_type"] == "page"), None)
            if missing_page is not None:
                r = jsapi_call(dc, "merge_choice_set", {
                    "base_revision": rev,
                    "row_key": missing_page["row_key"],
                    "choice": {"kind": "take", "source_id": donor_id},
                })
                if "error" not in r:
                    rev = r["revision"]
        return rev

    def test_01_end_to_end_merge_lab_apply_rescan_marks_report_undo(self) -> None:
        """End-to-end apply on merge lab: rescan 0 diffs, budget recorded, 0 source_changed marks, change report, byte-equal undo."""
        dc, _target_id, donor_id = self._open_sales_session()
        rev = self._select_new_measure_and_modify(dc, donor_id, include_report_page=True)

        target_model_def = self.project_root / "SalesA" / "SalesA.SemanticModel" / "definition"
        target_report_dir = self.project_root / "SalesA" / "SalesA.Report"
        pre_model_hashes = dir_file_hashes(target_model_def)
        pre_report_hashes = dir_file_hashes(target_report_dir)

        progress_trace: list[dict] = []
        dc._on_apply_progress = lambda snap: progress_trace.append(dict(snap))

        # UC6 preview check before apply
        st, preview = _http_get(dc, "apply", "preview")
        self.assertEqual(st, 200)
        self.assertEqual(contracts.errors("http/apply-preview.reply.json", preview), [])
        self.assertTrue(preview["ready"], preview)
        self.assertEqual(preview["desktop_state"], "not_open")
        self.assertGreater(preview["summary"]["add"] + preview["summary"]["change"], 0)

        t0 = time.perf_counter()
        applied = jsapi_call(dc, "apply", {"base_revision": rev, "approved": True})
        elapsed = time.perf_counter() - t0
        self.assertNotIn("error", applied, applied)
        self.assertEqual(applied["rescan_differences"], [])
        self.assertTrue(applied["backup_present"])
        self.assertGreater(applied["file_count"], 0)
        # End-to-end merge-lab regression budget: under 45 seconds even on cold .NET bridge
        self.assertLess(elapsed, 45.0)

        # UC5 progress trace order and completion state
        running_steps = [p for p in progress_trace if p["state"] == "running"]
        self.assertEqual([p["step_index"] for p in running_steps], list(range(1, len(running_steps) + 1)))
        self.assertEqual(progress_trace[-1]["state"], "done")
        st_prog, prog_reply = _http_get(dc, "apply", "progress")
        self.assertEqual(st_prog, 200)
        self.assertEqual(contracts.errors("http/apply-progress.reply.json", prog_reply), [])
        self.assertEqual(prog_reply["state"], "done")

        # After apply: zero source_changed marks and immediate sources_check reports 0 marks
        summary = dc.session_summary()
        self.assertEqual(summary["counts"]["marks"], 0)
        checked = jsapi_call(dc, "sources_check", {"base_revision": applied["revision"]})
        self.assertEqual(checked["mark_count"], 0)

        # Change report includes plan summary and writes locally
        report_res = jsapi_call(dc, "change_report_write", {"base_revision": checked["revision"]})
        self.assertNotIn("error", report_res, report_res)
        self.assertIn("## Plan Summary", report_res["markdown"])
        self.assertIn(applied["plan_hash"], report_res["markdown"])
        self.assertTrue(Path(report_res["path"]).is_file())

        # UC7 apply/last check before undo
        st_last, last_reply = _http_get(dc, "apply", "last")
        self.assertEqual(st_last, 200)
        self.assertEqual(contracts.errors("http/apply-last.reply.json", last_reply), [])
        self.assertEqual(last_reply["apply_id"], applied["apply_id"])
        self.assertTrue(last_reply["backup_present"])
        self.assertFalse(last_reply["target_changed"])

        # Undo restores all files byte-equal to backup
        undo_res = jsapi_call(dc, "undo_apply", {"base_revision": report_res["revision"]})
        self.assertNotIn("error", undo_res, undo_res)
        self.assertEqual(dir_file_hashes(target_model_def), pre_model_hashes)
        self.assertEqual(dir_file_hashes(target_report_dir), pre_report_hashes)

        st_last_after, last_after = _http_get(dc, "apply", "last")
        self.assertEqual(st_last_after, 200)
        self.assertFalse(last_after["backup_present"])

    def test_02_report_write_failure_and_mid_promotion_fault_are_atomic(self) -> None:
        """Report write failure and mid-promotion fault leave target model + report byte-unchanged."""
        dc, _target_id, donor_id = self._open_sales_session()
        rev = self._select_new_measure_and_modify(dc, donor_id, include_report_page=True)

        target_model_def = self.project_root / "SalesA" / "SalesA.SemanticModel" / "definition"
        target_report_dir = self.project_root / "SalesA" / "SalesA.Report"
        pre_model_hashes = dir_file_hashes(target_model_def)
        pre_report_hashes = dir_file_hashes(target_report_dir)

        # Case A: failure inside write_report
        with patch(
            "backend.devcenter.apply.service.write_report",
            side_effect=PBIRWriteError("schema_validation_failed", "Simulated report failure"),
        ):
            failed_a = jsapi_call(dc, "apply", {"base_revision": rev, "approved": True})
        self.assertIn("error", failed_a)
        self.assertEqual(failed_a["error"]["details"]["step"], "write_candidate")
        self.assertEqual(failed_a["error"]["details"]["check"], "pbir")
        self.assertEqual(dir_file_hashes(target_model_def), pre_model_hashes)
        self.assertEqual(dir_file_hashes(target_report_dir), pre_report_hashes)

        # Case B: mid-promotion failure on report after model files were already promoted
        def _fault_on_report(root_name: str, _rel: str) -> None:
            if root_name == "report":
                raise OSError("Simulated disk error during report promotion")

        dc._promotion_fault = _fault_on_report
        failed_b = jsapi_call(dc, "apply", {"base_revision": rev, "approved": True})
        dc._promotion_fault = None
        self.assertIn("error", failed_b)
        self.assertEqual(failed_b["error"]["details"]["step"], "promote")
        self.assertEqual(failed_b["error"]["details"]["check"], "write")
        self.assertEqual(dir_file_hashes(target_model_def), pre_model_hashes)
        self.assertEqual(dir_file_hashes(target_report_dir), pre_report_hashes)

    def test_03_desktop_bridge_states_preview_and_warnings(self) -> None:
        """Fake Desktop bridge: open_unsaved blocks; open_saved & not_reachable warn and allow."""
        dc, _target_id, donor_id = self._open_sales_session()
        rev = self._select_new_measure_and_modify(dc, donor_id)

        dc.set_desktop_bridge(lambda _root: "open_unsaved")
        st, prev = _http_get(dc, "apply", "preview")
        self.assertEqual(st, 200)
        self.assertEqual(prev["desktop_state"], "open_unsaved")
        self.assertFalse(prev["ready"])

        err = jsapi_call(dc, "apply", {"base_revision": rev, "approved": True})
        self.assertIn("error", err)
        self.assertEqual(err["error"]["code"], "action_not_allowed")
        self.assertEqual(err["error"]["details"]["step"], "desktop_check")
        self.assertEqual(err["error"]["details"]["check"], "policy")

        dc.set_desktop_bridge(lambda _root: "not_reachable")
        _st2, prev2 = _http_get(dc, "apply", "preview")
        self.assertEqual(prev2["desktop_state"], "not_reachable")
        self.assertIsInstance(prev2["desktop_warning"], str)
        ok_not_reach = jsapi_call(dc, "apply", {"base_revision": rev, "approved": True})
        self.assertNotIn("error", ok_not_reach)
        self.assertIn("Could not check", ok_not_reach["desktop_warning"])

        # Undo and apply again under open_saved
        undone = jsapi_call(dc, "undo_apply", {"base_revision": ok_not_reach["revision"]})
        dc.set_desktop_bridge(lambda _root: "open_saved")
        ok_saved = jsapi_call(dc, "apply", {"base_revision": undone["revision"], "approved": True})
        self.assertNotIn("error", ok_saved)
        self.assertIn("Apply external changes", ok_saved["desktop_warning"])

    def test_04_unconfirmed_marks_and_unaccepted_proposals(self) -> None:
        """Unconfirmed source marks block; confirming unblocks; unaccepted proposals do not affect applied files."""
        dc, _target_id, donor_id = self._open_sales_session()
        rev = self._select_new_measure_and_modify(dc, donor_id)

        # Inject an unaccepted agent proposal touching a different measure ("Bonus")
        with dc._lock:
            cur = dc._require_open()
            draft = copy.deepcopy(cur.document)
            draft["proposals"] = [{
                "id": "p-unaccepted",
                "status": "proposed",
                "kind": "merge_choice",
                "target_id": "measure:Sales/Bonus",
                "payload": {"choice": "remove"},
                "confidence": 0.99,
                "reason": "Unaccepted agent suggestion",
                "mcp_client": "TestAgent",
            }]
            dc._commit(cur, draft, "proposal_seed", "p-unaccepted", None, None)
            rev = cur.document["revision"]

        # Modify Orders Count cleanly in donor SalesB so an unconfirmed mark appears without breaking TMDL
        sales_b_tmdl = self.project_root / "SalesB" / "SalesB.SemanticModel" / "definition" / "tables" / "Sales.tmdl"
        sales_b_tmdl.write_text(
            sales_b_tmdl.read_text(encoding="utf-8").replace("COUNTROWS(Sales)", "COUNTROWS(Sales) + 0"),
            encoding="utf-8",
        )
        checked = jsapi_call(dc, "sources_check", {"base_revision": rev})
        rev = checked["revision"]
        self.assertGreater(checked["mark_count"], 0)

        st, prev = _http_get(dc, "apply", "preview")
        self.assertEqual(st, 200)
        self.assertGreater(prev["unconfirmed_marks"]["count"], 0)
        self.assertFalse(prev["ready"])

        blocked = jsapi_call(dc, "apply", {"base_revision": rev, "approved": True})
        self.assertIn("error", blocked)
        self.assertEqual(blocked["error"]["code"], "source_changed")
        self.assertEqual(blocked["error"]["details"]["step"], "source_check")
        self.assertEqual(blocked["error"]["details"]["check"], "scope")

        # Confirm marked rows
        confirmed = jsapi_call(dc, "row_confirm", {
            "base_revision": rev,
            "row_keys": prev["unconfirmed_marks"]["row_keys"],
        })
        self.assertEqual(confirmed["mark_count"], 0)

        # Apply succeeds and unaccepted proposal was ignored
        target_sales_tmdl = self.project_root / "SalesA" / "SalesA.SemanticModel" / "definition" / "tables" / "Sales.tmdl"
        had_bonus_before = "Bonus" in target_sales_tmdl.read_text(encoding="utf-8")
        res = jsapi_call(dc, "apply", {"base_revision": confirmed["revision"], "approved": True})
        self.assertNotIn("error", res, res)
        if had_bonus_before:
            self.assertIn("Bonus", target_sales_tmdl.read_text(encoding="utf-8"))

    def test_05_non_canonical_format_only_apply_and_uc5_progress(self) -> None:
        """UC6 non_canonical_files detects Budget.tmdl, blocks apply, format_only_apply fixes it & logs UC5 progress."""
        dc = DevCenterSessions(app_data_dir=self.root / "appdata")
        dc.attach_project(self.project_root)
        dc.create({"display_name": "Finance Format Test"})
        s1 = dc.source_add({"base_revision": 1, "path": str(self.project_root / "Finance/Finance.pbip")})
        fin_id = s1["source"]["source_id"]
        ts = dc.target_set({
            "base_revision": s1["revision"],
            "model": {"mode": "existing", "source_id": fin_id},
            "report": {"mode": "new_empty"},
        })
        rev = ts["revision"]

        st, prev = _http_get(dc, "apply", "preview")
        self.assertEqual(st, 200)
        self.assertIn("tables/Budget.tmdl", prev["non_canonical_files"])
        self.assertFalse(prev["ready"])

        err = jsapi_call(dc, "apply", {"base_revision": rev, "approved": True})
        self.assertIn("error", err)
        self.assertEqual(err["error"]["code"], "action_not_allowed")
        self.assertEqual(err["error"]["details"]["step"], "canonical_check")
        self.assertEqual(err["error"]["details"]["check"], "canonical")

        fmt_steps: list[dict] = []
        dc._on_apply_progress = lambda snap: fmt_steps.append(dict(snap))
        fmt_res = jsapi_call(dc, "format_only_apply", {"base_revision": rev})
        self.assertNotIn("error", fmt_res, fmt_res)
        self.assertIn("tables/Budget.tmdl", fmt_res["changed_files"])
        self.assertEqual(fmt_steps[-1]["state"], "done")
        self.assertEqual([s["step_index"] for s in fmt_steps if s["state"] == "running"], [1, 2, 3, 4, 5, 6, 7])

        # After format_only_apply, non_canonical_files is empty and 0 marks remain
        _st2, prev2 = _http_get(dc, "apply", "preview")
        self.assertEqual(prev2["non_canonical_files"], [])
        self.assertEqual(prev2["unconfirmed_marks"]["count"], 0)
        self.assertTrue(prev2["ready"])

        # Undo format-only works too and reports UC5 progress
        undo_steps: list[dict] = []
        dc._on_apply_progress = lambda snap: undo_steps.append(dict(snap))
        undo_res = jsapi_call(dc, "undo_apply", {"base_revision": fmt_res["revision"]})
        self.assertNotIn("error", undo_res)
        self.assertEqual(undo_steps[-1]["state"], "done")

    def test_06_uc7_external_edit_detection_undo_refusal_and_rescan_diffs(self) -> None:
        """UC7: external target edit shows target_changed=True & file list and blocks undo; rescan diffs list object/expected/found."""
        dc, _target_id, donor_id = self._open_sales_session()
        rev = self._select_new_measure_and_modify(dc, donor_id)

        dc._rescan_hook = lambda **_kw: [
            {"object": "measure:Sales/NewMeasure", "expected": "NewMeasure", "found": "mismatch"},
        ]
        applied = jsapi_call(dc, "apply", {"base_revision": rev, "approved": True})
        dc._rescan_hook = None
        self.assertNotIn("error", applied)
        self.assertEqual(len(applied["rescan_differences"]), 1)

        st_last, last_res = _http_get(dc, "apply", "last")
        self.assertEqual(st_last, 200)
        self.assertEqual(last_res["rescan_differences"][0]["object"], "measure:Sales/NewMeasure")
        self.assertEqual(last_res["rescan_differences"][0]["expected"], "NewMeasure")
        self.assertEqual(last_res["rescan_differences"][0]["found"], "mismatch")

        # Externally edit target TMDL on disk
        target_sales_tmdl = self.project_root / "SalesA" / "SalesA.SemanticModel" / "definition" / "tables" / "Sales.tmdl"
        target_sales_tmdl.write_text(target_sales_tmdl.read_text(encoding="utf-8") + "\n// user edit\n", encoding="utf-8")

        st_last2, last_changed = _http_get(dc, "apply", "last")
        self.assertEqual(st_last2, 200)
        self.assertEqual(contracts.errors("http/apply-last.reply.json", last_changed), [])
        self.assertTrue(last_changed["target_changed"])
        self.assertIn("tables/Sales.tmdl", last_changed["changed_files"])

        # Undo refuses cleanly when target files changed externally
        refused = jsapi_call(dc, "undo_apply", {"base_revision": applied["revision"]})
        self.assertIn("error", refused)
        self.assertEqual(refused["error"]["code"], "action_not_allowed")
        self.assertEqual(refused["error"]["details"]["step"], "verify_target")
        self.assertEqual(refused["error"]["details"]["check"], "scope")

    def test_07_uc32_guard_rejection_details_cover_all_checks(self) -> None:
        """UC32: every guard/apply rejection includes details.step and details.check."""
        dc, _target_id, donor_id = self._open_sales_session()
        rev = self._select_new_measure_and_modify(dc, donor_id)
        # Add a REMOVE merge choice on an existing target measure so policy classifies risk as HIGH
        rows = compare_service.compare_rows(dc, {})["rows"]
        m_remove = next(
            (r for r in rows if r["object_type"] == "measure" and r["name"] == "Sales With Tax"),
            None,
        )
        self.assertIsNotNone(m_remove)
        r_rem = jsapi_call(dc, "merge_choice_set", {
            "base_revision": rev,
            "row_key": m_remove["row_key"],
            "choice": {"kind": "remove"},
        })
        self.assertNotIn("error", r_rem, r_rem)
        rev = r_rem["revision"]
        rp = jsapi_call(dc, "removal_policy_set", {
            "base_revision": rev,
            "row_key": m_remove["row_key"],
            "policy": "cascade",
        })
        self.assertNotIn("error", rp, rp)
        rev = rp["revision"]

        # Approval check (high risk change without approved=True)
        no_app = jsapi_call(dc, "apply", {"base_revision": rev})
        self.assertIn("error", no_app)
        self.assertEqual(no_app["error"]["details"]["step"], "approval")
        self.assertEqual(no_app["error"]["details"]["check"], "approval")

        # MergeGuard failures for scope, tree_compare, pbir, policy
        for raw_check, expected_check in (
            ("scope", "scope"),
            ("tree_compare", "tree_compare"),
            ("pbir", "pbir"),
            ("policy", "policy"),
        ):
            with self.subTest(raw_check=raw_check):
                with patch(
                    "backend.devcenter.apply.service.MergeGuard.validate",
                    side_effect=MergeGuardError("SIM_ERR", f"Simulated {raw_check}", check=raw_check),
                ):
                    err = jsapi_call(dc, "apply", {"base_revision": rev, "approved": True})
                self.assertIn("error", err)
                self.assertEqual(err["error"]["details"]["step"], "guard_verify")
                self.assertEqual(err["error"]["details"]["check"], expected_check)

        # Rescan error check
        def _boom(**_kw):
            raise RuntimeError("rescan read error")

        dc._rescan_hook = _boom
        err_rescan = jsapi_call(dc, "apply", {"base_revision": rev, "approved": True})
        dc._rescan_hook = None
        self.assertIn("error", err_rescan)
        self.assertEqual(err_rescan["error"]["details"]["step"], "rescan")
        self.assertEqual(err_rescan["error"]["details"]["check"], "rescan")


if __name__ == "__main__":
    unittest.main()
