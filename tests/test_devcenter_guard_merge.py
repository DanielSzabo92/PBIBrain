"""Tests for S8 Change Guard merge profile, mutation rejections, approvals, and real PBIP models."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from backend.adapters.pbir import write_report
from backend.adapters.tabular_metadata import TabularMetadataAdapter
from backend.snapshots.manifest import canonical_json
from change_guard.contracts import validate_contract
from change_guard.contracts.schema import ContractError
from change_guard.merge import (
    MergeGuard,
    build_merge_contract,
    build_write_record,
    dir_file_hashes,
)
from change_guard.policy import Policy
from tests.helpers.mock_pbip import dir_sha256_manifest, has_mock_data, mock_data_root, copy_mock_project

REPOSITORY = Path(__file__).resolve().parents[1]
LAB = REPOSITORY / "tests" / "fixtures" / "merge_lab"
BRIDGE = REPOSITORY / "backend/adapters/tabular_metadata/dotnet/bin/Release/net8.0/TabularMetadata.dll"


@unittest.skipUnless(BRIDGE.is_file(), "Build the TOM bridge first")
class DevCenterGuardMergeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.adapter = TabularMetadataAdapter(BRIDGE)
        self.guard = MergeGuard(self.root / "guard_state", adapter=self.adapter)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _prepare_sales_merge(self) -> tuple[Path, Path, Path, Path, dict, dict]:
        base_model = self.root / "baseline" / "SalesA.SemanticModel" / "definition"
        cand_model = self.root / "candidate" / "SalesA.SemanticModel" / "definition"
        base_report = self.root / "baseline" / "SalesA.Report"
        cand_report = self.root / "candidate" / "SalesA.Report"
        shutil.copytree(LAB / "SalesA" / "SalesA.SemanticModel" / "definition", base_model)
        shutil.copytree(LAB / "SalesA" / "SalesA.Report", base_report)

        plan = {
            "plan_hash": "sha256:plan-sales-merge-1",
            "operations": [
                {
                    "op_id": "op-1",
                    "op": "CREATE",
                    "guard_op": "CREATE_OBJECT",
                    "domain": "model",
                    "object_type": "measure",
                    "row_key": "measure:Sales/Guard Bonus",
                    "table": "Sales",
                    "name": "Guard Bonus",
                    "lineage_tag": "m-guard-bonus-tag",
                    "properties": {"expression": "SUM(Sales[Amount]) * 0.1", "format_string": "#,0.00"},
                },
                {
                    "op_id": "op-2",
                    "op": "SET_PROPERTIES",
                    "guard_op": "SET_PROPERTY",
                    "domain": "model",
                    "object_type": "measure",
                    "row_key": "measure:Sales/Total Sales",
                    "table": "Sales",
                    "name": "Total Sales",
                    "properties": {"format_string": "$#,0.00"},
                },
            ],
        }
        model_write = self.adapter.write_model(base_model, cand_model, plan["operations"])
        report_write = write_report(base_report, cand_report, [])

        spec = build_merge_contract(
            project_id="sales-proj",
            session_id="sess-001",
            baseline_snapshot_id="snap-base-1",
            plan=plan,
            expected_created_definitions={
                "measure:Sales/Guard Bonus": {
                    "object_type": "measure",
                    "table": "Sales",
                    "name": "Guard Bonus",
                    "properties": {"format_string": "#,0.00"},
                }
            },
        )
        write_record = build_write_record(
            contract_hash=spec["contract_hash"],
            plan_hash=plan["plan_hash"],
            mode="apply",
            baseline_model_hashes=dir_file_hashes(base_model),
            candidate_model_hashes=dir_file_hashes(cand_model),
            model_write=model_write,
            baseline_report_hashes=dir_file_hashes(base_report),
            candidate_report_hashes=dir_file_hashes(cand_report),
            report_write=report_write,
        )
        return base_model, cand_model, base_report, cand_report, spec, write_record

    def test_01_valid_candidate_requires_high_approval_then_passes(self) -> None:
        base_m, cand_m, base_r, cand_r, spec, wr = self._prepare_sales_merge()

        # Without explicit HIGH_RISK_PROMOTION approval -> APPROVAL_REQUIRED
        unapproved = self.guard.validate(
            merge_spec=spec,
            write_record=wr,
            baseline_model_dir=base_m,
            candidate_model_dir=cand_m,
            baseline_report_dir=base_r,
            candidate_report_dir=cand_r,
        )
        self.assertEqual(unapproved["decision"], "APPROVAL_REQUIRED")
        self.assertFalse(unapproved["eligible_for_promotion"])
        self.assertIn("HIGH_RISK_PROMOTION", unapproved["approval_reasons"])

        # With explicit HIGH_RISK_PROMOTION -> ALLOW + signed approval record
        approved = self.guard.validate(
            merge_spec=spec,
            write_record=wr,
            baseline_model_dir=base_m,
            candidate_model_dir=cand_m,
            baseline_report_dir=base_r,
            candidate_report_dir=cand_r,
            approvals=["HIGH_RISK_PROMOTION"],
            operation_id="op-merge-1",
        )
        self.assertEqual(approved["decision"], "ALLOW")
        self.assertTrue(approved["eligible_for_promotion"])
        self.assertEqual(len(approved["approval_records"]), 1)
        self.assertTrue((self.root / "guard_state" / "op-merge-1" / "approval-HIGH_RISK_PROMOTION.json").is_file())

    def test_02_missing_or_wrong_write_record_rejects(self) -> None:
        base_m, cand_m, base_r, cand_r, spec, wr = self._prepare_sales_merge()

        missing = self.guard.validate(
            merge_spec=spec,
            write_record=None,
            baseline_model_dir=base_m,
            candidate_model_dir=cand_m,
            baseline_report_dir=base_r,
            candidate_report_dir=cand_r,
            approvals=["HIGH_RISK_PROMOTION"],
        )
        self.assertEqual(missing["decision"], "REJECT")
        self.assertFalse(missing["eligible_for_promotion"])
        self.assertEqual(missing["checks"]["write_record"]["failure"]["code"], "MISSING_WRITE_RECORD")

        tampered = {**wr, "write_record_hash": "sha256:" + "0" * 64}
        wrong = self.guard.validate(
            merge_spec=spec,
            write_record=tampered,
            baseline_model_dir=base_m,
            candidate_model_dir=cand_m,
            baseline_report_dir=base_r,
            candidate_report_dir=cand_r,
            approvals=["HIGH_RISK_PROMOTION"],
        )
        self.assertEqual(wrong["decision"], "REJECT")
        self.assertEqual(wrong["checks"]["write_record"]["failure"]["code"], "WRITE_RECORD_HASH_MISMATCH")

    def test_03_extra_and_removed_file_rejects(self) -> None:
        base_m, cand_m, base_r, cand_r, spec, wr = self._prepare_sales_merge()

        # Extra file inside candidate model
        (cand_m / "extra.tmdl").write_text("table Extra\n", encoding="utf-8")
        res_extra = self.guard.validate(
            merge_spec=spec,
            write_record=wr,
            baseline_model_dir=base_m,
            candidate_model_dir=cand_m,
            baseline_report_dir=base_r,
            candidate_report_dir=cand_r,
            approvals=["HIGH_RISK_PROMOTION"],
        )
        self.assertEqual(res_extra["decision"], "REJECT")
        self.assertEqual(res_extra["checks"]["write_record"]["failure"]["code"], "EXTRA_FILE")

        (cand_m / "extra.tmdl").unlink()
        # Removed file
        target_tbl = next((cand_m / "tables").glob("*.tmdl"))
        target_tbl.unlink()
        res_rem = self.guard.validate(
            merge_spec=spec,
            write_record=wr,
            baseline_model_dir=base_m,
            candidate_model_dir=cand_m,
            baseline_report_dir=base_r,
            candidate_report_dir=cand_r,
            approvals=["HIGH_RISK_PROMOTION"],
        )
        self.assertEqual(res_rem["decision"], "REJECT")
        self.assertEqual(res_rem["checks"]["write_record"]["failure"]["code"], "REMOVED_FILE")

    def test_04_extra_model_property_perspective_identity_and_non_canonical_reject(self) -> None:
        base_m, cand_m, base_r, cand_r, spec, _ = self._prepare_sales_merge()

        # Re-serialize a candidate that also adds an unplanned perspective & extra property
        sales_tmdl = cand_m / "tables" / "Sales.tmdl"
        sales_text = sales_tmdl.read_text(encoding="utf-8")
        # Change Total Cost format or inject extra perspective while keeping write_record matching files
        cand2_m = self.root / "candidate2" / "SalesA.SemanticModel" / "definition"
        shutil.copytree(cand_m, cand2_m)
        (cand2_m / "perspectives.tmdl").write_text(
            "perspective 'Secret Perspective'\r\n\r\n\tperspectiveTable Sales\r\n",
            encoding="utf-8",
        )
        wr2 = build_write_record(
            contract_hash=spec["contract_hash"],
            plan_hash=spec["plan_hash"],
            mode="apply",
            baseline_model_hashes=dir_file_hashes(base_m),
            candidate_model_hashes=dir_file_hashes(cand2_m),
            model_write={"changed_files": ["tables/Sales.tmdl"], "added_files": ["perspectives.tmdl"], "removed_files": []},
            baseline_report_hashes=dir_file_hashes(base_r),
            candidate_report_hashes=dir_file_hashes(cand_r),
            report_write={"changed_files": [], "added_files": [], "removed_files": []},
        )
        res_persp = self.guard.validate(
            merge_spec=spec,
            write_record=wr2,
            baseline_model_dir=base_m,
            candidate_model_dir=cand2_m,
            baseline_report_dir=base_r,
            candidate_report_dir=cand_r,
            approvals=["HIGH_RISK_PROMOTION"],
        )
        self.assertEqual(res_persp["decision"], "REJECT")
        self.assertEqual(res_persp["checks"]["tree_compare"]["failure"]["code"], "UNPLANNED_MODEL_CHANGE")

        # Non-canonical candidate file (LF line endings) rejects canonical gate
        cand3_m = self.root / "candidate3" / "SalesA.SemanticModel" / "definition"
        shutil.copytree(cand_m, cand3_m)
        st = cand3_m / "tables" / "Sales.tmdl"
        st.write_bytes(st.read_bytes().replace(b"\r\n", b"\n"))
        wr3 = build_write_record(
            contract_hash=spec["contract_hash"],
            plan_hash=spec["plan_hash"],
            mode="apply",
            baseline_model_hashes=dir_file_hashes(base_m),
            candidate_model_hashes=dir_file_hashes(cand3_m),
            model_write={"changed_files": ["tables/Sales.tmdl"], "added_files": [], "removed_files": []},
            baseline_report_hashes=dir_file_hashes(base_r),
            candidate_report_hashes=dir_file_hashes(cand_r),
            report_write={"changed_files": [], "added_files": [], "removed_files": []},
        )
        res_nc = self.guard.validate(
            merge_spec=spec,
            write_record=wr3,
            baseline_model_dir=base_m,
            candidate_model_dir=cand3_m,
            baseline_report_dir=base_r,
            candidate_report_dir=cand_r,
            approvals=["HIGH_RISK_PROMOTION"],
        )
        self.assertEqual(res_nc["decision"], "REJECT")
        self.assertEqual(res_nc["checks"]["canonical"]["failure"]["code"], "NON_CANONICAL_CANDIDATE")

        # Extra unplanned property edit on a measure via clean canonical write
        extra_cand = self.root / "candidate4" / "SalesA.SemanticModel" / "definition"
        mw4 = self.adapter.write_model(
            base_m,
            extra_cand,
            [
                {
                    "op": "CREATE",
                    "object_type": "measure",
                    "table": "Sales",
                    "name": "Guard Bonus",
                    "lineage_tag": "m-guard-bonus-tag",
                    "properties": {"expression": "SUM(Sales[Amount]) * 0.1", "format_string": "#,0.00"},
                },
                {
                    "op": "SET_PROPERTIES",
                    "object_type": "measure",
                    "table": "Sales",
                    "name": "Total Sales",
                    "properties": {"format_string": "$#,0.00", "is_hidden": True},
                },
            ],
        )
        wr4 = build_write_record(
            contract_hash=spec["contract_hash"],
            plan_hash=spec["plan_hash"],
            mode="apply",
            baseline_model_hashes=dir_file_hashes(base_m),
            candidate_model_hashes=dir_file_hashes(extra_cand),
            model_write=mw4,
            baseline_report_hashes=dir_file_hashes(base_r),
            candidate_report_hashes=dir_file_hashes(cand_r),
            report_write={"changed_files": [], "added_files": [], "removed_files": []},
        )
        res_prop = self.guard.validate(
            merge_spec=spec,
            write_record=wr4,
            baseline_model_dir=base_m,
            candidate_model_dir=extra_cand,
            baseline_report_dir=base_r,
            candidate_report_dir=cand_r,
            approvals=["HIGH_RISK_PROMOTION"],
        )
        self.assertEqual(res_prop["decision"], "REJECT")
        self.assertEqual(res_prop["checks"]["tree_compare"]["failure"]["code"], "UNPLANNED_MODEL_CHANGE")

    def test_05_rename_pair_with_second_property_change_and_unplanned_identity_reject(self) -> None:
        base_doc = {
            "contract_version": 1,
            "task_id": "rename-pair-test",
            "project_id": "sales-proj",
            "profile": "merge",
            "mode": "apply",
            "baseline": {"snapshot_id": "snap-1", "source_revision": None},
            "intent": {"description": "Rename pair check", "category": "MERGE_PLAN"},
            "targets": [{"object_id": "measure:Sales/Total Sales", "object_type": "measure"}],
            "allowed_mutations": [{
                "object_id": "measure:Sales/Total Sales",
                "operation": "RENAME_PAIR",
                "property": "name",
                "expected_before": {"name": "Total Sales", "properties": {"expression": "SUM(Sales[Amount])"}},
                "expected_after": {"name": "Gross Sales", "properties": {"expression": "SUM(Sales[Amount]) * 2"}},
            }],
            "forbidden": {"allow_unlisted_mutations": False, "allow_object_creation": True, "allow_object_deletion": True, "allow_identity_changes": False},
            "behavior": {"permitted_effects": [], "invariants": []},
            "validation": {"require_static_validation": True, "require_runtime_validation": False, "require_impact_analysis": True, "require_complete_dependency_coverage": False},
            "approval": {"scope_expansion": "EXPLICIT", "unexpected_behavior": "EXPLICIT", "high_risk_promotion": "EXPLICIT"},
        }
        with self.assertRaises(ContractError):
            validate_contract(base_doc)

    def test_06_extra_pbir_property_rejects(self) -> None:
        base_m, cand_m, base_r, cand_r, spec, _ = self._prepare_sales_merge()
        overview_page = cand_r / "definition" / "pages" / "overview" / "page.json"
        if not overview_page.is_file():
            overview_page = next((cand_r / "definition" / "pages").rglob("page.json"))
        doc = json.loads(overview_page.read_text(encoding="utf-8"))
        doc["displayName"] = "Tampered Name"
        overview_page.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

        wr = build_write_record(
            contract_hash=spec["contract_hash"],
            plan_hash=spec["plan_hash"],
            mode="apply",
            baseline_model_hashes=dir_file_hashes(base_m),
            candidate_model_hashes=dir_file_hashes(cand_m),
            model_write={"changed_files": ["tables/Sales.tmdl"], "added_files": [], "removed_files": []},
            baseline_report_hashes=dir_file_hashes(base_r),
            candidate_report_hashes=dir_file_hashes(cand_r),
            report_write={"changed_files": [overview_page.relative_to(cand_r).as_posix()], "added_files": [], "removed_files": []},
        )
        res = self.guard.validate(
            merge_spec=spec,
            write_record=wr,
            baseline_model_dir=base_m,
            candidate_model_dir=cand_m,
            baseline_report_dir=base_r,
            candidate_report_dir=cand_r,
            approvals=["HIGH_RISK_PROMOTION"],
        )
        self.assertEqual(res["decision"], "REJECT")
        self.assertEqual(res["checks"]["pbir"]["failure"]["code"], "UNPLANNED_PBIR_CHANGE")

    def test_07_format_only_and_not_checked_approval(self) -> None:
        fin_model = self.root / "fin_base" / "Finance.SemanticModel" / "definition"
        fin_cand = self.root / "fin_cand" / "Finance.SemanticModel" / "definition"
        shutil.copytree(LAB / "Finance" / "Finance.SemanticModel" / "definition", fin_model)

        # Baseline Finance has non-canonical tables/Budget.tmdl -> normal apply must block
        normal_spec = build_merge_contract(
            project_id="fin",
            session_id="s-fin",
            baseline_snapshot_id="snap-fin",
            plan={"plan_hash": "sha256:p-fin", "operations": []},
            mode="apply",
        )
        mw_clean = self.adapter.write_model(fin_model, fin_cand, [])
        wr_norm = build_write_record(
            contract_hash=normal_spec["contract_hash"],
            plan_hash=normal_spec["plan_hash"],
            mode="apply",
            baseline_model_hashes=dir_file_hashes(fin_model),
            candidate_model_hashes=dir_file_hashes(fin_cand),
            model_write=mw_clean,
        )
        blocked_base = self.guard.validate(
            merge_spec=normal_spec,
            write_record=wr_norm,
            baseline_model_dir=fin_model,
            candidate_model_dir=fin_cand,
            approvals=["HIGH_RISK_PROMOTION"],
        )
        self.assertEqual(blocked_base["decision"], "REJECT")
        self.assertEqual(blocked_base["checks"]["canonical"]["failure"]["code"], "NON_CANONICAL_BASELINE")
        self.assertIn("tables/Budget.tmdl", blocked_base["checks"]["canonical"]["failure"]["files"])

        # Format-only passes with empty tree compare
        fmt_spec = build_merge_contract(
            project_id="fin",
            session_id="s-fin",
            baseline_snapshot_id="snap-fin",
            plan={"plan_hash": "sha256:p-fmt", "operations": []},
            mode="format_only",
        )
        wr_fmt = build_write_record(
            contract_hash=fmt_spec["contract_hash"],
            plan_hash=fmt_spec["plan_hash"],
            mode="format_only",
            baseline_model_hashes=dir_file_hashes(fin_model),
            candidate_model_hashes=dir_file_hashes(fin_cand),
            model_write=mw_clean,
        )
        ok_fmt = self.guard.validate(
            merge_spec=fmt_spec,
            write_record=wr_fmt,
            baseline_model_dir=fin_model,
            candidate_model_dir=fin_cand,
        )
        self.assertEqual(ok_fmt["decision"], "ALLOW")
        self.assertTrue(ok_fmt["eligible_for_promotion"])

        # Format-only rejects if tree compare is NOT empty
        bad_fmt_cand = self.root / "fin_bad_fmt" / "Finance.SemanticModel" / "definition"
        mw_bad = self.adapter.write_model(
            fin_model,
            bad_fmt_cand,
            [{"op": "CREATE", "object_type": "measure", "table": "Budget", "name": "Sneaky", "properties": {"expression": "1"}}],
        )
        wr_bad_fmt = build_write_record(
            contract_hash=fmt_spec["contract_hash"],
            plan_hash=fmt_spec["plan_hash"],
            mode="format_only",
            baseline_model_hashes=dir_file_hashes(fin_model),
            candidate_model_hashes=dir_file_hashes(bad_fmt_cand),
            model_write=mw_bad,
        )
        rej_fmt = self.guard.validate(
            merge_spec=fmt_spec,
            write_record=wr_bad_fmt,
            baseline_model_dir=fin_model,
            candidate_model_dir=bad_fmt_cand,
        )
        self.assertEqual(rej_fmt["decision"], "REJECT")
        self.assertEqual(rej_fmt["checks"]["tree_compare"]["failure"]["code"], "FORMAT_ONLY_SEMANTIC_CHANGE")

    def test_08_old_policy_profile_unchanged(self) -> None:
        standard = Policy()
        self.assertEqual(standard.profile, "standard")
        merge_p = Policy(version="guard-policy-merge-1", profile="merge")
        self.assertNotEqual(standard.policy_hash, merge_p.policy_hash)

    @unittest.skipUnless(has_mock_data(), "Mock data PBIP folder not present")
    def test_09_real_mock_pbip_models_pass_guard_without_mutating_source(self) -> None:
        src_root = mock_data_root()
        before_finance = dir_sha256_manifest(src_root / "1_finance_Aevum")
        before_sales = dir_sha256_manifest(src_root / "2_sales_Veloce")
        try:
            proj_dir, _ = copy_mock_project("sales", self.root)
            base_m = proj_dir / "Sales.SemanticModel" / "definition"
            base_r = proj_dir / "Sales.Report"
            cand_m = self.root / "real_cand" / "Sales.SemanticModel" / "definition"

            # Canonicalize baseline first on temp copy if desktop wrote non-canonical bytes
            if not self.adapter.canonical_check(base_m)["is_canonical"]:
                norm_cand = self.root / "norm" / "Sales.SemanticModel" / "definition"
                mw0 = self.adapter.write_model(base_m, norm_cand, [])
                fmt_spec = build_merge_contract(
                    project_id="veloce",
                    session_id="s-veloce",
                    baseline_snapshot_id="snap-v0",
                    plan={"plan_hash": "sha256:fmt-v", "operations": []},
                    mode="format_only",
                )
                wr0 = build_write_record(
                    contract_hash=fmt_spec["contract_hash"],
                    plan_hash=fmt_spec["plan_hash"],
                    mode="format_only",
                    baseline_model_hashes=dir_file_hashes(base_m),
                    candidate_model_hashes=dir_file_hashes(norm_cand),
                    model_write=mw0,
                )
                res0 = self.guard.validate(
                    merge_spec=fmt_spec,
                    write_record=wr0,
                    baseline_model_dir=base_m,
                    candidate_model_dir=norm_cand,
                )
                self.assertEqual(res0["decision"], "ALLOW")
                shutil.rmtree(base_m)
                shutil.copytree(norm_cand, base_m)

            # Now run a real model mutation against the real Veloce Sales model
            tom = self.adapter.read(base_m)
            first_table = tom["database"]["model"]["tables"][0]["name"]
            plan = {
                "plan_hash": "sha256:veloce-op-1",
                "operations": [{
                    "op_id": "op-v1",
                    "op": "CREATE",
                    "guard_op": "CREATE_OBJECT",
                    "domain": "model",
                    "object_type": "measure",
                    "row_key": f"measure:{first_table}/Guard Prod Check",
                    "table": first_table,
                    "name": "Guard Prod Check",
                    "lineage_tag": "m-guard-prod-check",
                    "properties": {"expression": "1 + 1", "format_string": "#,0"},
                }],
            }
            mw = self.adapter.write_model(base_m, cand_m, plan["operations"])
            spec = build_merge_contract(
                project_id="veloce",
                session_id="s-veloce",
                baseline_snapshot_id="snap-v1",
                plan=plan,
                not_checked_items=[{"area": "bookmarks", "count": 1}],
            )
            wr = build_write_record(
                contract_hash=spec["contract_hash"],
                plan_hash=plan["plan_hash"],
                mode="apply",
                baseline_model_hashes=dir_file_hashes(base_m),
                candidate_model_hashes=dir_file_hashes(cand_m),
                model_write=mw,
                baseline_report_hashes=dir_file_hashes(base_r),
                candidate_report_hashes=dir_file_hashes(base_r),
            )
            res = self.guard.validate(
                merge_spec=spec,
                write_record=wr,
                baseline_model_dir=base_m,
                candidate_model_dir=cand_m,
                baseline_report_dir=base_r,
                candidate_report_dir=base_r,
                approvals=["HIGH_RISK_PROMOTION", "NOT_CHECKED_ITEMS"],
                operation_id="op-veloce-1",
            )
            self.assertEqual(res["decision"], "ALLOW", res)
            self.assertTrue(res["eligible_for_promotion"])
        finally:
            self.assertEqual(dir_sha256_manifest(src_root / "1_finance_Aevum"), before_finance)
            self.assertEqual(dir_sha256_manifest(src_root / "2_sales_Veloce"), before_sales)


if __name__ == "__main__":
    unittest.main()
