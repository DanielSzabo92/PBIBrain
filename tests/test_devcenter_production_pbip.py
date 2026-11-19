"""Production-grade DevCenter merge & apply proof against real copied PBIP models from Mock data."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from backend.devcenter import contracts
from backend.devcenter.compare import service as compare_service
from backend.devcenter.http_routes import dispatch as devcenter_dispatch
from backend.devcenter.jsapi import call as jsapi_call
from backend.devcenter.plan.service import get_plan
from backend.devcenter.session.manager import DevCenterSessions
from tests.helpers.mock_pbip import (
    copy_mock_project,
    has_mock_data,
    pbip_sha256_manifest,
    resolve_mock_project,
)

REPOSITORY = Path(__file__).resolve().parents[1]
BRIDGE = REPOSITORY / "backend/adapters/tabular_metadata/dotnet/bin/Release/net8.0/TabularMetadata.dll"


def _http_get(dc: DevCenterSessions, *parts: str) -> tuple[int, dict]:
    class _App:
        devcenter = dc

    return devcenter_dispatch(_App(), "GET", list(parts), {}, b"")


@unittest.skipUnless(BRIDGE.is_file() and has_mock_data(), "Requires built TOM bridge and Mock data PBIPs")
class DevCenterProductionPBIPTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="pbibrain-prod-pbip-")
        self.root = Path(self.tmp.name)
        src_fin_dir, _ = resolve_mock_project("finance")
        src_sales_dir, _ = resolve_mock_project("sales")
        self._orig_fin_manifest = pbip_sha256_manifest(src_fin_dir)
        self._orig_sales_manifest = pbip_sha256_manifest(src_sales_dir)

    def tearDown(self) -> None:
        src_fin_dir, _ = resolve_mock_project("finance")
        src_sales_dir, _ = resolve_mock_project("sales")
        self.assertEqual(pbip_sha256_manifest(src_fin_dir), self._orig_fin_manifest, "Mock data finance mutated!")
        self.assertEqual(pbip_sha256_manifest(src_sales_dir), self._orig_sales_manifest, "Mock data sales mutated!")
        self.tmp.cleanup()

    def test_real_mock_pbip_format_merge_apply_rescan_report_and_undo(self) -> None:
        """Full DevCenter session on copied real PBIP models: preview -> format_only -> apply -> rescan -> report -> undo -> external edit safety."""
        proj_root = self.root / "workspace"
        proj_root.mkdir()
        sales_dir, sales_pbip = copy_mock_project("sales", proj_root)
        _fin_dir, fin_pbip = copy_mock_project("finance", proj_root)

        dc = DevCenterSessions(app_data_dir=self.root / "appdata")
        dc.attach_project(proj_root)
        dc.create({"display_name": "Prod Sales + Finance"})

        s_sales = dc.source_add({"base_revision": 1, "path": str(sales_pbip)})
        s_fin = dc.source_add({"base_revision": s_sales["revision"], "path": str(fin_pbip)})
        target_id = s_sales["source"]["source_id"]
        donor_id = s_fin["source"]["source_id"]
        ts = dc.target_set({
            "base_revision": s_fin["revision"],
            "model": {"mode": "existing", "source_id": target_id},
            "report": {"mode": "existing", "source_id": target_id},
        })
        rev = ts["revision"]

        rows = compare_service.compare_rows(dc, {"limit": ["500"]})["rows"]
        sales_tables = {
            r["name"].casefold()
            for r in rows
            if r["object_type"] == "table" and any(c["source_id"] == target_id and c["present"] for c in r["cells"])
        }

        # Pick candidates (prefer a missing measure in an existing table; fall back safely if plan has unmet Needs)
        candidates = [
            (r["row_key"], {"kind": "take", "source_id": donor_id})
            for r in rows
            if r["object_type"] == "measure"
            and r["row_state"] == "missing_in_target"
            and (r.get("table") or "").casefold() in sales_tables
        ]
        # Add add_new_name on an existing measure (self-contained, always valid cross-model merge test)
        existing_measure = next(
            (r for r in rows if r["object_type"] == "measure" and any(c["source_id"] == target_id and c["present"] for c in r["cells"])),
            None,
        )
        self.assertIsNotNone(existing_measure, "Expected at least one target measure in real Sales PBIP")
        # Also include donor table take or valid missing measure if dependency-free
        candidates.append((
            existing_measure["row_key"],
            {"kind": "add_new_name", "source_id": donor_id, "new_name": f"{existing_measure['name']} Finance Copy"},
        ))

        selected_row = None
        for rk, choice in candidates:
            if choice["kind"] == "add_new_name":
                # Ensure donor has an object for that row, else find any donor measure and take_new into target table or rename
                row_obj = next((r for r in rows if r["row_key"] == rk), None)
                if not row_obj or not any(c["source_id"] == donor_id and c["present"] for c in row_obj["cells"]):
                    continue
            mc = jsapi_call(dc, "merge_choice_set", {"base_revision": rev, "row_key": rk, "choice": choice})
            if "error" in mc:
                continue
            rev = mc["revision"]
            plan = get_plan(dc, {})
            if plan["status"] != "invalid" and plan["steps"]:
                selected_row = rk
                break
            cleared = jsapi_call(dc, "merge_choice_set", {"base_revision": rev, "row_key": rk, "choice": None})
            rev = cleared["revision"]

        if selected_row is None:
            # Guaranteed valid real cross-model take: find first missing donor table (takes table + columns + self-contained children) or missing donor measure
            for r in rows:
                if r["object_type"] == "table" and r["row_state"] == "missing_in_target":
                    mc = jsapi_call(dc, "merge_choice_set", {
                        "base_revision": rev,
                        "row_key": r["row_key"],
                        "choice": {"kind": "take", "source_id": donor_id},
                    })
                    if "error" in mc:
                        continue
                    rev = mc["revision"]
                    plan = get_plan(dc, {})
                    if plan["status"] != "invalid" and plan["steps"]:
                        selected_row = r["row_key"]
                        break
                    cleared = jsapi_call(dc, "merge_choice_set", {"base_revision": rev, "row_key": r["row_key"], "choice": None})
                    rev = cleared["revision"]

        if selected_row is None:
            # Final fallback: add_new_name from any Finance measure that also exists in Sales or take format_string property
            donor_any = next(
                r for r in rows
                if r["object_type"] == "measure" and any(c["source_id"] == donor_id and c["present"] for c in r["cells"])
            )
            mc = jsapi_call(dc, "merge_choice_set", {
                "base_revision": rev,
                "row_key": existing_measure["row_key"],
                "choice": {"kind": "take_properties", "source_id": donor_id, "properties": ["display_folder"], "display_folder": "Merged Metrics"},
            }) if any(c["source_id"] == donor_id and c["present"] for c in existing_measure["cells"]) else jsapi_call(
                dc,
                "merge_choice_set",
                {"base_revision": rev, "row_key": donor_any["row_key"], "choice": {"kind": "take", "source_id": donor_id}},
            )
            self.assertNotIn("error", mc, mc)
            rev = mc["revision"]
            selected_row = mc["row_key"]

        st, preview = _http_get(dc, "apply", "preview")
        self.assertEqual(st, 200)
        self.assertEqual(contracts.errors("http/apply-preview.reply.json", preview), [])

        if preview["non_canonical_files"]:
            fmt = jsapi_call(dc, "format_only_apply", {"base_revision": rev})
            self.assertNotIn("error", fmt, fmt)
            rev = fmt["revision"]
            st, preview = _http_get(dc, "apply", "preview")
            self.assertEqual(st, 200)
            self.assertEqual(preview["non_canonical_files"], [])

        post_format_manifest = pbip_sha256_manifest(sales_dir)
        self.assertTrue(preview["ready"], f"Expected real Mock PBIP apply preview ready; got {preview}")

        applied = jsapi_call(dc, "apply", {"base_revision": rev, "approved": True})
        self.assertNotIn("error", applied, applied)
        self.assertGreater(applied["file_count"], 0)
        self.assertEqual(applied["rescan_differences"], [])
        self.assertTrue(applied["backup_present"])

        # Zero source_changed marks immediately after apply
        checked = jsapi_call(dc, "sources_check", {"base_revision": applied["revision"]})
        self.assertEqual(checked["mark_count"], 0)

        # Change report
        report = jsapi_call(dc, "change_report_write", {"base_revision": checked["revision"]})
        self.assertNotIn("error", report, report)
        self.assertIn("## Plan Summary", report["markdown"])
        self.assertTrue(Path(report["path"]).is_file())

        # Undo restores byte-equal pre-apply baseline
        undone = jsapi_call(dc, "undo_apply", {"base_revision": report["revision"]})
        self.assertNotIn("error", undone, undone)
        self.assertEqual(pbip_sha256_manifest(sales_dir), post_format_manifest)

        # Re-apply, externally modify target, verify target_changed=True and undo refuses safely
        applied2 = jsapi_call(dc, "apply", {"base_revision": undone["revision"], "approved": True})
        self.assertNotIn("error", applied2, applied2)

        sales_model_tmdl = sales_dir / "Sales.SemanticModel" / "definition" / "model.tmdl"
        sales_model_tmdl.write_text(sales_model_tmdl.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        st_last, last_info = _http_get(dc, "apply", "last")
        self.assertEqual(st_last, 200)
        self.assertTrue(last_info["target_changed"])
        refused = jsapi_call(dc, "undo_apply", {"base_revision": applied2["revision"]})
        self.assertIn("error", refused)
        self.assertEqual(refused["error"]["details"]["reason"], "target_changed")


if __name__ == "__main__":
    unittest.main()
