"""Build step S8: guard for merge (technical design sections 8 and 16 S8, ADR 0001).

Acceptance tests:
1. A candidate from the S7 writers for each fixture plan gets PASS.
2. Mutation tests: one extra changed property, one extra file, one removed file, a
   non-canonical changed file, an unplanned identity-map entry, a rename pair with a
   second property change, an extra PBIR property, and a changed perspective each
   give a reject with the expected code.
3. A missing or wrong write record hash rejects.
4. HIGH risk without approval does not promote; with the approval record it promotes.
5. "Format only" passes only with an empty tree compare.
6. The old guard profiles are unchanged (the old guard test modules stay green).
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

import jsonschema

from backend.adapters.tabular_metadata import TabularMetadataAdapter
from backend.devcenter.compare.extract import load_objects
from backend.devcenter.compare.rows import SessionSource, build_rows
from backend.devcenter.plan.compiler import GUARD_OPERATIONS, PlanInput, compile_plan
from backend.devcenter.sources.kinds import detect_local_source
from backend.snapshots.manifest import content_hash, source_manifest
from change_guard.contracts import validate_contract
from change_guard.contracts.schema import ContractError
from change_guard.merge import build_merge_proposal, verify_merge_candidate, write_merge_files, write_record
from change_guard.orchestrator import ChangeGuard, GuardError
from change_guard.policy import Policy, evaluate_candidate, merge_policy
from change_guard.contracts import authorize_contract

REPOSITORY = Path(__file__).resolve().parents[1]
LAB = REPOSITORY / "tests" / "fixtures" / "merge_lab"
BRIDGE = REPOSITORY / "backend/adapters/tabular_metadata/dotnet/bin/Release/net8.0/TabularMetadata.dll"
SCHEMA = json.loads((REPOSITORY / "change_guard/contracts/contract-v1.schema.json").read_text(encoding="utf-8"))
SALES_A_MODEL = "SalesA.SemanticModel/definition"
SALES_A_REPORT = "SalesA.Report"
DONORS = {"src-a": str(LAB / "SalesA" / "SalesA.Report"), "src-b": str(LAB / "SalesB" / "SalesB.Report")}


def compiled_plan() -> dict:
    """Fixture plan 1: the compiled merge of SalesB into SalesA (model and report operations)."""
    a = detect_local_source(LAB / "SalesA" / "SalesA.pbip")
    b = detect_local_source(LAB / "SalesB" / "SalesB.pbip")
    rows = build_rows([SessionSource("src-a", load_objects(a)), SessionSource("src-b", load_objects(b))], target_model="src-a", target_report="src-a")
    rewrites = {f"renamed:{key}:measure:Sales/Total Sales": {"action": "include_in_rewrite"}
                for key in ("measure:Sales/Margin", "measure:Sales/Sales With Tax", "table:Metric Selector")}
    plan = compile_plan(PlanInput(session_id="ses-guard-merge", result=rows, target_model="src-a", target_report="src-a",
                                  sources={"src-a": "SalesA", "src-b": "SalesB"}, item_actions=rewrites,
                                  merge_choices={"page:summary": {"kind": "take", "source_id": "src-b"},
                                                 "measure:Sales/Total Sales": {"kind": "take", "source_id": "src-b"},
                                                 "report_measure:Sales/Sales Target": {"kind": "promote", "source_id": "src-a", "new_name": "Promoted Target"}}))
    assert plan["status"] in {"valid", "valid_with_warnings"}, plan["blocking"]
    return plan


def model_op(index: int, op: str, object_type: str, name: str, table: str | None = None, **values) -> dict:
    row_key = f"{object_type}:{table}/{name}" if table else f"{object_type}:{name}"
    return {"op_id": f"op-fixture-{index:02d}", "op": op, "guard_op": GUARD_OPERATIONS[op], "domain": "model", "object_type": object_type,
            "row_key": row_key, "table": table, "name": name, **values}


def model_plan() -> dict:
    """Fixture plan 2: model operations with a create, a delete, renames, a rename pair, and a rewrite."""
    return {"plan_hash": "fixture-model-plan", "operations": [
        model_op(1, "CREATE", "column", "DiscountPercent", "Sales", lineage_tag="c-sales-discount",
                 properties={"data_type": "decimal", "source_column": "Discount"}),
        model_op(2, "DELETE", "measure", "Sales With Tax", "Sales"),
        model_op(3, "RENAME", "measure", "Total Cost", "Sales", old_name="Total Cost", new_name="Cost Total"),
        model_op(4, "REWRITE_EXPRESSION", "measure", "Margin", "Sales", property="expression",
                 old_text="[Total Sales] - [Total Cost]", new_text="[Total Sales] - [Cost Total]"),
        model_op(5, "SET_PROPERTIES", "measure", "Average Sale", "Sales", properties={"format_string": "#,0.00"}),
        model_op(6, "RENAME", "table", "Store", old_name="Store", new_name="StoreMaster"),
        model_op(7, "RENAME_PAIR", "role", "West Region", old_name="West Region", new_name="West Sales", pair_id="pair-fixture"),
    ]}


@unittest.skipUnless(BRIDGE.is_file(), "Build the TOM bridge first")
class MergeGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.adapter = TabularMetadataAdapter(BRIDGE)
        cls.temp = tempfile.TemporaryDirectory(prefix="t20-guard-")
        root = Path(cls.temp.name)
        cls.sales = shutil.copytree(LAB / "SalesA", root / "SalesA")
        cls.finance = shutil.copytree(LAB / "Finance", root / "Finance")
        baseline = {"snapshot_id": "fixture-baseline", "source_revision": None}
        cls.compiled = build_merge_proposal(cls.sales, compiled_plan(), project_id="sales-a", baseline=baseline, model_path=SALES_A_MODEL,
                                            report_path=SALES_A_REPORT, adapter=cls.adapter, donor_paths=DONORS)
        cls.model_only = build_merge_proposal(cls.sales, model_plan(), project_id="sales-a", baseline=baseline, model_path=SALES_A_MODEL,
                                              report_path=SALES_A_REPORT, adapter=cls.adapter)
        cls.format_only = build_merge_proposal(cls.finance, {"plan_hash": "format-only", "operations": []}, project_id="finance", baseline=baseline,
                                               model_path="Finance.SemanticModel/definition", report_path=None, adapter=cls.adapter, format_only=True)
        cls.candidates = {}
        for key, (source, doc) in {"compiled": (cls.sales, cls.compiled), "model": (cls.sales, cls.model_only), "format": (cls.finance, cls.format_only)}.items():
            candidate = shutil.copytree(source, root / ("candidate-" + key))
            files = write_merge_files(source, candidate, doc["merge"], cls.adapter, root / ("work-" + key))
            cls.candidates[key] = (source, doc, candidate, write_record(content_hash(doc), source_manifest(source), files))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp.cleanup()

    # Helpers -----------------------------------------------------------------------

    def copy_candidate(self, key: str) -> tuple[Path, dict, Path, dict]:
        source, doc, candidate, record = self.candidates[key]
        work = Path(tempfile.mkdtemp(prefix="t20-mutation-"))
        self.addCleanup(shutil.rmtree, work, True)
        return source, doc, shutil.copytree(candidate, work / "candidate"), record

    def verify(self, source: Path, doc: dict, candidate: Path, record: dict | None) -> dict:
        return verify_merge_candidate(doc, content_hash(doc), source, candidate, record, self.adapter)

    def rerecord(self, source: Path, doc: dict, candidate: Path) -> dict:
        """A write record that also holds the mutation, so that only the plan proof can find it."""
        old = {item["path"]: item["hash"] for item in source_manifest(source)}
        new = {item["path"]: item["hash"] for item in source_manifest(candidate)}
        return write_record(content_hash(doc), source_manifest(source), {key: new.get(key) for key in set(old) | set(new) if old.get(key) != new.get(key)})

    def apply_model(self, model: Path, operations: list[dict]) -> None:
        """Write more model operations into a candidate model in canonical TMDL (a mutation that TOM accepts)."""
        with tempfile.TemporaryDirectory() as work:
            output = Path(work) / "model"
            result = self.adapter.write_model(model, output, operations)
            for name in [*result["changed_files"], *result["added_files"]]:
                (model / name).parent.mkdir(parents=True, exist_ok=True)
                (model / name).write_bytes((output / name).read_bytes())
            for name in result["removed_files"]:
                (model / name).unlink()

    def assert_reject(self, result: dict, code: str) -> list[dict]:
        found = [item for item in result["violations"] if item["code"] == code]
        self.assertTrue(found, f"expected {code}, got {[item['code'] for item in result['violations']]}")
        return found

    # 1. Each fixture plan passes ---------------------------------------------------

    def test_01_candidate_from_writers_passes_for_each_fixture_plan(self) -> None:
        for key in ("compiled", "model", "format"):
            with self.subTest(plan=key):
                source, doc, candidate, record = self.candidates[key]
                result = self.verify(source, doc, candidate, record)
                self.assertEqual(result["violations"], [])
                self.assertEqual((result["security"]["status"], result["source"]["status"], result["scope"]["status"]), ("PASSED", "PASSED", "PASSED"))
        operations = {item["op"] for item in self.compiled["merge"]["operations"]}
        self.assertTrue({"CREATE", "RENAME", "REWRITE_EXPRESSION", "COPY_PAGE", "REBIND_FIELD", "DELETE_REPORT_MEASURE"} <= operations, operations)
        self.assertTrue(self.compiled["merge"]["report_files"]["created"])
        self.assertTrue(self.compiled["merge"]["report_files"]["changed"])

    def test_02_contract_validates_and_matches_json_schema(self) -> None:
        for doc in (self.compiled, self.model_only, self.format_only):
            jsonschema.validate(doc, SCHEMA)
            validate_contract(doc, {})
        record = self.candidates["compiled"][3]
        jsonschema.validate(record, {**SCHEMA["$defs"]["write_record"], "$defs": SCHEMA["$defs"]})
        pair = [item for item in self.model_only["allowed_mutations"] if item["operation"] == "RENAME_PAIR"]
        self.assertEqual([item["property"] for item in pair], ["name"])
        broken = json.loads(json.dumps(self.model_only))
        broken["merge"]["report_path"] = "../outside"
        with self.assertRaises(ContractError):
            validate_contract(broken)
        standard = json.loads(json.dumps(self.model_only))
        del standard["merge"]
        with self.assertRaises(ContractError):
            validate_contract(standard)

    # 2. Mutations --------------------------------------------------------------------

    def test_03_extra_changed_property_rejects(self) -> None:
        source, doc, candidate, _ = self.copy_candidate("model")
        self.apply_model(candidate / SALES_A_MODEL, [model_op(90, "SET_PROPERTIES", "measure", "Total Sales", "Sales", properties={"description": "Not planned"})])
        result = self.verify(source, doc, candidate, self.rerecord(source, doc, candidate))
        self.assertEqual(result["security"]["status"], "PASSED")
        found = self.assert_reject(result, "UNPLANNED_MODEL_CHANGE")
        self.assertEqual((found[0]["difference"]["object_name"], found[0]["difference"]["property"]), ("Total Sales", "description"))
        self.assert_reject(result, "MODEL_NOT_PLAN_OUTPUT")
        self.assertEqual(result["scope"]["status"], "REJECTED_SCOPE")

    def test_04_extra_file_rejects(self) -> None:
        source, doc, candidate, _ = self.copy_candidate("compiled")
        extra = candidate / SALES_A_REPORT / "definition/pages/summary/notes.json"
        extra.write_text('{"note": "not planned"}', encoding="utf-8")
        result = self.verify(source, doc, candidate, self.rerecord(source, doc, candidate))
        self.assertEqual(self.assert_reject(result, "UNPLANNED_FILE_CREATED")[0]["file"], SALES_A_REPORT + "/definition/pages/summary/notes.json")
        self.assertEqual(result["source"]["status"], "FAILED")

    def test_05_removed_file_rejects(self) -> None:
        source, doc, candidate, _ = self.copy_candidate("compiled")
        (candidate / SALES_A_REPORT / "definition/version.json").unlink()
        result = self.verify(source, doc, candidate, self.rerecord(source, doc, candidate))
        self.assertEqual(self.assert_reject(result, "UNPLANNED_FILE_DELETED")[0]["file"], SALES_A_REPORT + "/definition/version.json")

    def test_06_non_canonical_changed_file_rejects(self) -> None:
        source, doc, candidate, _ = self.copy_candidate("compiled")
        changed = candidate / SALES_A_MODEL / "tables/Store.tmdl"
        self.assertNotEqual(changed.read_bytes(), (source / SALES_A_MODEL / "tables/Store.tmdl").read_bytes())
        changed.write_bytes(changed.read_bytes().replace(b"\r\n", b"\n"))
        result = self.verify(source, doc, candidate, self.rerecord(source, doc, candidate))
        found = self.assert_reject(result, "NON_CANONICAL_MODEL_FILE")
        self.assertEqual(found[0]["file"], "tables/Store.tmdl")
        self.assertEqual(result["scope"]["status"], "PASSED")

    def test_07_unplanned_identity_entry_rejects(self) -> None:
        source, doc, candidate, _ = self.copy_candidate("model")
        self.apply_model(candidate / SALES_A_MODEL, [model_op(91, "SET_PROPERTIES", "column", "DiscountPercent", "Sales", lineage_tag="c-not-planned")])
        result = self.verify(source, doc, candidate, self.rerecord(source, doc, candidate))
        self.assertEqual(self.assert_reject(result, "UNPLANNED_IDENTITY_ENTRY")[0]["lineage_tag"], "c-not-planned")

    def test_08_rename_pair_with_second_property_change_rejects(self) -> None:
        source, doc, candidate, _ = self.copy_candidate("model")
        self.apply_model(candidate / SALES_A_MODEL, [model_op(92, "SET_PROPERTIES", "role", "West Sales", properties={"model_permission": "ReadRefresh"})])
        result = self.verify(source, doc, candidate, self.rerecord(source, doc, candidate))
        found = self.assert_reject(result, "RENAME_PAIR_PROPERTY_CHANGED")
        self.assertEqual((found[0]["old_name"], found[0]["new_name"]), ("West Region", "West Sales"))

    def test_09_extra_pbir_property_rejects(self) -> None:
        source, doc, candidate, _ = self.copy_candidate("compiled")
        relative = SALES_A_REPORT + "/definition/pages/detail/visuals/target/visual.json"
        self.assertIn(relative, doc["merge"]["report_files"]["changed"])
        path = candidate / relative
        visual = json.loads(path.read_text(encoding="utf-8"))
        visual["position"]["z"] = 5000
        path.write_text(json.dumps(visual, indent=2), encoding="utf-8")
        result = self.verify(source, doc, candidate, self.rerecord(source, doc, candidate))
        found = self.assert_reject(result, "UNPLANNED_REPORT_PROPERTY")
        self.assertEqual((found[0]["file"], found[0]["pointer"]), (relative, "/position/z"))

    def test_10_changed_perspective_rejects(self) -> None:
        source, doc, candidate, _ = self.copy_candidate("compiled")
        model = candidate / SALES_A_MODEL
        (model / "perspectives.tmdl").write_text("perspective 'Sales Leadership'\n\n\tperspectiveTable Sales\n", encoding="utf-8", newline="\r\n")
        self.apply_model(model, [])
        result = self.verify(source, doc, candidate, self.rerecord(source, doc, candidate))
        found = self.assert_reject(result, "UNPLANNED_MODEL_CHANGE")
        self.assertIn(("perspective", "Sales Leadership", "ADDED"),
                      {(item["difference"]["object_type"], item["difference"]["object_name"], item["difference"]["change_type"]) for item in found})

    # 3. Write record -----------------------------------------------------------------

    def test_11_missing_or_wrong_write_record_rejects(self) -> None:
        source, doc, candidate, record = self.copy_candidate("compiled")
        self.assert_reject(self.verify(source, doc, candidate, None), "WRITE_RECORD_MISSING")
        tampered = {**record, "files": {**record["files"], SALES_A_REPORT + "/definition/version.json": "0" * 64}}
        self.assert_reject(self.verify(source, doc, candidate, tampered), "WRITE_RECORD_HASH_MISMATCH")
        other = write_record("another-contract", source_manifest(source), record["files"])
        result = self.verify(source, doc, candidate, other)
        self.assert_reject(result, "WRITE_RECORD_HASH_MISMATCH")
        self.assertEqual(result["security"]["status"], "FAILED")
        # A file change after the write step does not match the record.
        (candidate / SALES_A_REPORT / "definition/pages/summary/page.json").write_text('{"name": "summary"}', encoding="utf-8")
        found = self.assert_reject(self.verify(source, doc, candidate, record), "WRITE_RECORD_FILE_MISMATCH")
        self.assertEqual(found[0]["changed_files"], [SALES_A_REPORT + "/definition/pages/summary/page.json"])

    # 5. Format only ------------------------------------------------------------------

    def test_12_format_only_passes_only_with_empty_tree_compare(self) -> None:
        source, doc, candidate, record = self.copy_candidate("format")
        self.assertEqual(sorted(record["files"]), ["Finance.SemanticModel/definition/tables/Budget.tmdl"])
        self.assertEqual(self.verify(source, doc, candidate, record)["violations"], [])
        self.apply_model(candidate / "Finance.SemanticModel/definition", [model_op(93, "SET_PROPERTIES", "measure", "Revenue", "Sales", properties={"description": "Changed"})])
        result = self.verify(source, doc, candidate, self.rerecord(source, doc, candidate))
        found = self.assert_reject(result, "FORMAT_ONLY_MODEL_CHANGED")
        self.assertEqual(found[0]["difference"]["object_name"], "Revenue")

    def test_13_non_canonical_baseline_blocks_a_plan_and_names_the_file(self) -> None:
        plan = {"plan_hash": "finance-plan", "operations": [model_op(1, "SET_PROPERTIES", "measure", "Revenue", "Sales", properties={"description": "Revenue"})]}
        doc = build_merge_proposal(self.finance, plan, project_id="finance", baseline={"snapshot_id": "fixture-baseline", "source_revision": None},
                                   model_path="Finance.SemanticModel/definition", report_path=None, adapter=self.adapter)
        work = Path(tempfile.mkdtemp(prefix="t20-finance-"))
        self.addCleanup(shutil.rmtree, work, True)
        candidate = shutil.copytree(self.finance, work / "candidate")
        files = write_merge_files(self.finance, candidate, doc["merge"], self.adapter, work / "write")
        result = self.verify(self.finance, doc, candidate, write_record(content_hash(doc), source_manifest(self.finance), files))
        found = self.assert_reject(result, "NON_CANONICAL_BASELINE_FILE")
        self.assertEqual(found[0]["file"], "tables/Budget.tmdl")
        self.assertIn("LF line ends", found[0]["differences"])

    # 4. Policy profile ---------------------------------------------------------------

    def test_14_merge_policy_needs_approval_for_high_risk_and_unchecked_items(self) -> None:
        contract = authorize_contract(self.model_only, "tester", "guard-policy-merge-1", objects={})
        passed = {name: {"status": "PASSED"} for name in ("security", "scope", "baseline", "source", "static")}
        decision = evaluate_candidate(contract, passed, merge_policy())
        self.assertEqual((decision["decision"], decision["risk"]), ("APPROVAL_REQUIRED", "CRITICAL"))
        self.assertEqual(decision["approval_reasons"], ["HIGH_RISK_PROMOTION"])
        self.assertEqual(evaluate_candidate(contract, {**passed, "valid_approval_operations": ["HIGH_RISK_PROMOTION"]}, merge_policy())["decision"], "ALLOW")
        for gate, status in (("scope", "REJECTED_SCOPE"), ("source", "FAILED"), ("security", "NOT_RUN"), ("static", "INCONCLUSIVE")):
            with self.subTest(gate=gate):
                result = evaluate_candidate(contract, {**passed, gate: {"status": status}, "valid_approval_operations": ["HIGH_RISK_PROMOTION"]}, merge_policy())
                self.assertEqual(result["decision"], "REJECT")
        unchecked = json.loads(json.dumps(self.model_only))
        unchecked["merge"]["unchecked_items"] = [{"kind": "not_checked", "row_key": "table:Metric Selector"}]
        contract = authorize_contract(unchecked, "tester", "guard-policy-merge-1", objects={})
        self.assertEqual(evaluate_candidate(contract, passed, merge_policy())["approval_reasons"], ["HIGH_RISK_PROMOTION", "UNCHECKED_IMPACT"])
        # The merge profile never accepts a contract without a merge section.
        standard = json.loads(json.dumps(self.format_only))
        del standard["merge"]
        contract = authorize_contract(standard, "tester", "guard-policy-merge-1", objects=None)
        self.assertEqual(evaluate_candidate(contract, passed, merge_policy())["blocking_reasons"][0]["code"], "PROFILE_MISMATCH")
        # The standard profile keeps its old hash.
        self.assertEqual(Policy().policy_hash, content_hash({"version": "guard-policy-1", "risk_overrides": "{}", "retry_limit": 3, "retain_results": False}))
        self.assertNotEqual(merge_policy().policy_hash, Policy().policy_hash)


@unittest.skipUnless(BRIDGE.is_file(), "Build the TOM bridge first")
class MergeGuardOrchestratorTests(unittest.TestCase):
    """The full guard flow with the app write step: prepare, authorize, write, validate, approve, promote."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="t20-flow-")
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.source = shutil.copytree(LAB / "SalesA", root / "SalesA")
        self.guard = ChangeGuard(self.source, root / "state", "sales-a", policy=merge_policy())

    def prepare(self, plan: dict) -> tuple[str, dict]:
        baseline = self.guard.capture_baseline().to_dict()
        doc = build_merge_proposal(self.source, plan, project_id="sales-a", adapter=self.guard.adapter, donor_paths=DONORS,
                                   baseline={"snapshot_id": baseline["snapshot_id"], "source_revision": baseline["source_revision"]},
                                   model_path=SALES_A_MODEL, report_path=SALES_A_REPORT)
        operation = self.guard.prepare_change(doc)["operation_id"]
        self.guard.authorize(operation, "CONTRACT")
        return operation, doc

    def test_15_high_risk_needs_approval_record_then_promotes(self) -> None:
        operation, _ = self.prepare(compiled_plan())
        with self.assertRaises(GuardError) as error:
            self.guard.run_agent(operation, None, ["agent"])
        self.assertEqual(error.exception.code, "PROFILE_MISMATCH")
        self.guard.write_merge_candidate(operation)
        state = self.guard.validate_candidate(operation)
        evidence = self.guard.review(operation)["verification"]
        self.assertEqual((evidence["security"]["status"], evidence["scope"]["status"], evidence["source"]["status"]), ("PASSED", "PASSED", "PASSED"),
                         json.dumps(evidence["scope"])[:2000])
        self.assertEqual(evidence["static"]["status"], "PASSED", json.dumps(evidence["static"])[:2000])
        self.assertEqual(state["decision"]["decision"], "APPROVAL_REQUIRED")
        self.assertIn("HIGH_RISK_PROMOTION", state["decision"]["approval_reasons"])
        with self.assertRaises(GuardError) as error:
            self.guard.promote_candidate(operation)
        self.assertEqual(error.exception.code, "PROMOTION_NOT_AUTHORIZED")
        binding = self.guard.review(operation)["review_binding"]
        with self.assertRaises(GuardError) as error:
            self.guard.accept_candidate(operation, binding, ["PROMOTE"])
        self.assertEqual(error.exception.code, "MISSING_APPROVAL")
        accepted = self.guard.accept_candidate(operation, binding, ["HIGH_RISK_PROMOTION", "PROMOTE"])
        self.assertTrue(accepted["promotion_authorized"])
        approvals = sorted(item["authorized_operation"] for item in accepted["approvals"])
        self.assertEqual(approvals, ["HIGH_RISK_PROMOTION", "PROMOTE"])
        promoted = self.guard.promote_candidate(operation)
        self.assertEqual(promoted["state"], "POST_PROMOTION_VERIFIED")
        self.assertTrue((self.source / SALES_A_REPORT / "definition/pages/summary/page.json").is_file())
        self.assertEqual(source_manifest(self.source), source_manifest(promoted["candidate_root"]))

    def test_16_changed_candidate_after_write_rejects_and_profiles_do_not_mix(self) -> None:
        operation, doc = self.prepare(compiled_plan())
        self.guard.write_merge_candidate(operation)
        candidate = Path(self.guard.candidate_status(operation)["candidate_root"])
        (candidate / SALES_A_REPORT / "definition/version.json").unlink()
        state = self.guard.validate_candidate(operation)
        self.assertEqual(state["decision"]["decision"], "REJECT")
        codes = {item["gate"] for item in state["decision"]["blocking_reasons"]}
        self.assertTrue({"security", "source"} <= codes, codes)
        other = ChangeGuard(self.source, Path(self.temp.name) / "state-standard", "sales-a")
        baseline = other.capture_baseline().to_dict()
        proposal = {**doc, "baseline": {"snapshot_id": baseline["snapshot_id"], "source_revision": baseline["source_revision"]}}
        operation = other.prepare_change(proposal)["operation_id"]
        other.authorize(operation, "CONTRACT")
        with self.assertRaises(GuardError) as error:
            other.write_merge_candidate(operation)
        self.assertEqual(error.exception.code, "PROFILE_MISMATCH")
        with self.assertRaises(GuardError) as error:
            other.validate_candidate(operation)
        self.assertEqual(error.exception.code, "PROFILE_MISMATCH")


if __name__ == "__main__":
    unittest.main()
