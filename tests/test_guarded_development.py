from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from backend.adapters.tabular_metadata import TabularMetadataAdapter, MetadataUnavailable
from backend.api.app import BrainAPI, BrainApp
from backend.context.builder import build_context
from backend.diff import compare_snapshots, compare_properties
from backend.graph.loader import build_fact_graph
from backend.graph.repository import GraphRepository
from backend.impact import analyze_impact
from backend.impact.cache import SnapshotImpactCache
from backend.snapshots import Snapshot, capture_snapshot, source_manifest, content_hash
from backend.snapshots.manifest import safe_path, SourceIntegrityError
from backend.snapshots.scan import scan_snapshot
from change_guard.audit import AuditStore, AuditIntegrityError
from change_guard.contracts import authorize_contract, enforce_scope, validate_contract
from change_guard.contracts.schema import ContractError
from change_guard.orchestrator import ChangeGuard, GuardError
from change_guard.policy import Policy, evaluate_candidate
from change_guard.promotion import LocalPromotion, PromotionError
from change_guard.promotion.git import create_review_revision
from change_guard.regression import compare_results, RegressionTest, ExecutionContext, execute_regression_plan
from change_guard.regression.query_coverage import query_targets
from change_guard.regression.adapters import TestDouble, UnavailableAdapter
from change_guard.service import GuardService
from change_guard.workspace import create_candidate, assert_candidate_integrity, DockerIsolation
from tests.guarded_fixture import reference_project


def proposal(snapshot: Snapshot, *, property_name: str = "from_column_id", new_value=None) -> dict:
    value = snapshot.to_dict()
    relation = next(item for item in value["analysis"]["objects"].values() if item["object_type"] == "RELATIONSHIP")
    if new_value is None:
        new_value = next(key for key, item in value["analysis"]["objects"].items() if item["object_type"] == "COLUMN" and item["properties"]["name"] == "ShipDateKey")
    return {"contract_version": 1, "task_id": "date-change", "project_id": value["project_id"],
            "baseline": {"snapshot_id": value["snapshot_id"], "source_revision": value["source_revision"]},
            "intent": {"description": "Change sales from OrderDate to ShipDate", "category": "RELATIONSHIP_MODIFICATION"},
            "targets": [{"object_id": relation["object_id"], "object_type": "RELATIONSHIP"}],
            "allowed_mutations": [{"object_id": relation["object_id"], "operation": "SET_PROPERTY", "property": property_name,
                                   "expected_before": relation["properties"][property_name], "expected_after": new_value}],
            "forbidden": {"allow_unlisted_mutations": False, "allow_object_creation": False, "allow_object_deletion": False, "allow_identity_changes": False},
            "behavior": {"permitted_effects": [], "invariants": []},
            "validation": {"require_static_validation": True, "require_runtime_validation": True, "require_impact_analysis": True, "require_complete_dependency_coverage": True},
            "approval": {"scope_expansion": "EXPLICIT", "unexpected_behavior": "EXPLICIT", "high_risk_promotion": "EXPLICIT"}}


def modify_bim(root: Path, action):
    path = root / "Sales.SemanticModel/model.bim"
    document = json.loads(path.read_text(encoding="utf-8"))
    action(document["model"])
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


class ReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not TabularMetadataAdapter().bridge.is_file():
            raise unittest.SkipTest("Build trusted TOM bridge to run authoritative integration tests")

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        reference_project(self.source)
        self.guard = ChangeGuard(self.source, self.root / "trusted", "project-sales")
        self.baseline = self.guard.capture_baseline()
        self.contract = proposal(self.baseline)

    def candidate(self):
        state = self.guard.prepare_change(self.contract)
        state = self.guard.authorize(state["operation_id"], "CONTRACT")
        return state["operation_id"], Path(state["candidate_root"])

    def test_deterministic_snapshot_and_real_capture_timestamp(self):
        other = self.guard.capture_baseline()
        self.assertEqual(self.baseline.snapshot_id, other.snapshot_id)
        self.assertNotEqual(self.baseline.to_dict()["created_at"], other.to_dict()["created_at"])
        self.assertEqual("COMPLETE", self.baseline.to_dict()["completeness"]["status"])

    def test_reference_scope_and_missing_isolation_runtime_block(self):
        operation, candidate = self.candidate()
        modify_bim(candidate, lambda model: model["relationships"][0].update(fromColumn="ShipDateKey"))
        original = source_manifest(self.source)
        result = self.guard.validate_candidate(operation)
        verification = self.guard.review(operation)["verification"]
        self.assertEqual("PASSED", verification["scope"]["status"])
        self.assertEqual(1, len(verification["comparison"]["object_changes"]))
        self.assertEqual("INCONCLUSIVE", result["decision"]["decision"])
        self.assertEqual("NOT_RUN", verification["security"]["status"])
        self.assertEqual(original, source_manifest(self.source))
        with self.assertRaises(GuardError):
            self.guard.authorize(operation, "PROMOTE")

    def test_additional_cross_filter_change_rejected(self):
        operation, candidate = self.candidate()
        modify_bim(candidate, lambda model: model["relationships"][0].update(fromColumn="ShipDateKey", crossFilteringBehavior="bothDirections"))
        state = self.guard.validate_candidate(operation)
        self.assertEqual("REJECT", state["decision"]["decision"])
        self.assertEqual("REJECTED_SCOPE", self.guard.review(operation)["verification"]["scope"]["status"])

    def test_measure_rewrite_rejected(self):
        operation, candidate = self.candidate()
        def change(model):
            model["relationships"][0]["fromColumn"] = "ShipDateKey"
            model["tables"][1]["measures"][0]["expression"] = "SUM(FactSales[SalesAmount]) * 9"
        modify_bim(candidate, change)
        self.assertEqual("REJECT", self.guard.validate_candidate(operation)["decision"]["decision"])

    def test_relationship_deletion_recreation_rejected(self):
        operation, candidate = self.candidate()
        modify_bim(candidate, lambda model: model["relationships"][0].update(name="replacement", fromColumn="ShipDateKey"))
        result = self.guard.validate_candidate(operation)
        self.assertFalse(result["decision"]["scope_compliant"])

    def test_unknown_metadata_fails_authoritative_adapter(self):
        operation, candidate = self.candidate()
        modify_bim(candidate, lambda model: model["relationships"][0].update(unrecognizedGuardBypass=True))
        with self.assertRaises(GuardError) as caught:
            self.guard.validate_candidate(operation)
        self.assertEqual("SOURCE_INTEGRITY_FAILURE", caught.exception.code)

    def test_stale_baseline_blocks_verification_and_authorization(self):
        operation, candidate = self.candidate()
        modify_bim(self.source, lambda model: model.update(culture="hu-HU"))
        with self.assertRaises(GuardError) as caught:
            self.guard.validate_candidate(operation)
        self.assertEqual("BASELINE_STALE", caught.exception.code)

    def test_candidate_changes_invalidate_review(self):
        operation, candidate = self.candidate()
        modify_bim(candidate, lambda model: model["relationships"][0].update(fromColumn="ShipDateKey"))
        self.guard.validate_candidate(operation)
        modify_bim(candidate, lambda model: model.update(culture="hu-HU"))
        self.assertEqual("CANDIDATE_STALE", self.guard.review(operation)["operation"]["decision"]["blocking_reasons"][0]["code"])

    def test_authoritative_identity_seed_change_makes_baseline_stale(self):
        identity = self.root / "authoritative-identity.json"
        identity.write_text(json.dumps({"version": 1, "mappings": {}}))
        guard = ChangeGuard(self.source, self.root / "identity-trusted", "test-project", identity_path=identity)
        baseline = guard.capture_baseline()
        state = guard.prepare_change(proposal(baseline))
        guard.authorize(state["operation_id"], "CONTRACT")
        identity.write_text(json.dumps({"version": 1, "mappings": {"new": "new-stable-id"}}))
        with self.assertRaises(GuardError) as error: guard.validate_candidate(state["operation_id"])
        self.assertEqual("BASELINE_STALE", error.exception.code)

    def test_agent_cannot_edit_authorized_contract(self):
        operation, candidate = self.candidate()
        path = self.guard.store.root / operation / "contract.json"
        envelope = json.loads(path.read_text())
        envelope["payload"]["document"] = "{}"
        path.write_text(json.dumps(envelope))
        with self.assertRaises(AuditIntegrityError):
            self.guard.validate_candidate(operation)

    def test_unknown_raw_control_file_change_rejected(self):
        operation, candidate = self.candidate()
        modify_bim(candidate, lambda model: model["relationships"][0].update(fromColumn="ShipDateKey"))
        path = candidate / "Sales.pbip"
        text = path.read_text(); path.write_text(text + " ")
        self.assertFalse(self.guard.validate_candidate(operation)["decision"]["scope_compliant"])

    def test_isolated_graph_identity_no_live_write(self):
        before = source_manifest(self.source)
        operation, candidate = self.candidate()
        analyzed = scan_snapshot(candidate, identities=self.baseline.to_dict()["identity_manifest"])
        self.assertEqual(set(self.baseline.to_dict()["analysis"]["objects"]), set(analyzed["objects"]))
        self.assertEqual(before, source_manifest(self.source))
        self.assertFalse((self.source / "identity.json").exists())

    def test_reference_unchanged_sum_transitive_measure_visuals(self):
        report_source = self.root / "report-source"
        reference_project(report_source, report=True)
        analysis = scan_snapshot(report_source)
        relation = next(item for item in analysis["objects"].values() if item["object_type"] == "RELATIONSHIP")
        ship = next(key for key, item in analysis["objects"].items() if item["object_type"] == "COLUMN" and item["properties"]["name"] == "ShipDateKey")
        report = analyze_impact(analysis["graph"], [relation["object_id"]], [{"property": "from_column_id", "new_value": ship}], completeness=analysis["completeness"])
        names = {item["name"] for item in report["potential_impacts"]}
        self.assertTrue({"Sales Amount", "Sales YTD", "sales", "Monthly", "Sales report"}.issubset(names))
        self.assertIn(ship, report["impacted_objects"])
        self.assertEqual("INCOMPLETE", report["completeness"]["status"])

    def test_deterministic_impact_and_output_pruning(self):
        value = self.baseline.to_dict()
        target = self.contract["targets"][0]["object_id"]
        a = analyze_impact(value["analysis"]["graph"], [target], completeness=value["completeness"])
        b = analyze_impact(value["analysis"]["graph"], [target], completeness=value["completeness"])
        self.assertEqual(a["impact_report_id"], b["impact_report_id"])
        small = analyze_impact(value["analysis"]["graph"], [target], completeness=value["completeness"], output_limit=1)
        self.assertEqual(a["impacted_objects"], small["impacted_objects"])
        self.assertTrue(small["completeness"]["output_truncated"])

    def test_golden_reference_snapshot_diff_impact_and_blocked_promotion(self):
        from tests.guard_reference_record import reference_record
        expected = json.loads((Path(__file__).parent / "fixtures/change_guard/reference_expected.json").read_text(encoding="utf-8-sig"))
        self.assertEqual(expected, reference_record())

    def test_snapshot_cache_keeps_full_isolated_results(self):
        target = self.contract["targets"][0]["object_id"]
        cache = SnapshotImpactCache(maximum_entries=1)
        first = cache.analyze(self.baseline, [target])
        expected = first["impact_report_id"]
        first["impacted_objects"].clear()
        second = cache.analyze(self.baseline, [target])
        self.assertEqual(expected, second["impact_report_id"])
        self.assertTrue(second["impacted_objects"])
        proposed = [{"object_id": target, "property": "active", "new_value": False}]
        self.assertNotEqual(expected, cache.analyze(self.baseline, [target], proposed)["impact_report_id"])
        self.assertEqual(1, len(cache._reports))

    def test_query_ast_requires_actual_target_evaluation(self):
        graph = self.baseline.to_dict()["analysis"]["graph"]
        measure = next(item["id"] for item in graph["nodes"] if item["type"] == "MEASURE" and item["name"] == "Sales Amount")
        valid = query_targets('EVALUATE ROW("Sales", [Sales Amount])', (measure,), graph)
        self.assertEqual("PASSED", valid["status"])
        fake = query_targets('EVALUATE ROW("[Sales Amount]", 1)', (measure,), graph)
        self.assertEqual("INCONCLUSIVE", fake["status"])
        self.assertIn(measure, fake["missing_ids"])

    def test_unlisted_expected_behavior_still_requires_approval(self):
        contract = authorize_contract(self.contract, "human", "guard-policy-1", objects=self.baseline.to_dict()["analysis"]["objects"])
        evidence = {name: {"status": "PASSED"} for name in ("security", "scope", "baseline", "source", "static")}
        evidence.update(runtime={"status": "PASSED", "certified": True, "results": [{"test_id": "changed", "changed": True, "target_objects": ["not-permitted"]}]},
                        impact={"impact_report_id": "test-only", "completeness": {"status": "COMPLETE"}}, valid_approval_operations=["HIGH_RISK_PROMOTION"])
        decision = evaluate_candidate(contract, evidence, Policy())
        self.assertEqual("APPROVAL_REQUIRED", decision["decision"])
        self.assertIn("UNEXPECTED_BEHAVIOR", decision["approval_reasons"])
        evidence["scope"]["status"] = "REJECTED_SCOPE"
        evidence["valid_approval_operations"].append("UNEXPECTED_BEHAVIOR")
        self.assertEqual("REJECT", evaluate_candidate(contract, evidence, Policy())["decision"])

    def test_formal_contract_unknown_fields_wildcards_types_preconditions(self):
        objects = self.baseline.to_dict()["analysis"]["objects"]
        for mutate in [lambda p: p.update(extra=True), lambda p: p["targets"][0].update(object_id="*"),
                       lambda p: p["validation"].update(require_runtime_validation="true"),
                       lambda p: p["allowed_mutations"][0].update(expected_before="guessed")]:
            with self.subTest(mutate=mutate):
                candidate = deepcopy(self.contract); mutate(candidate)
                with self.assertRaises(ContractError): validate_contract(candidate, objects)

    def test_contract_properties_are_immutable_copies(self):
        contract = authorize_contract(self.contract, "human", "v1", objects=self.baseline.to_dict()["analysis"]["objects"])
        digest = contract.contract_hash
        contract.to_dict()["allowed_mutations"].clear()
        self.assertEqual(digest, contract.contract_hash)

    def test_readonly_api_impact_context_compare_registry(self):
        with GraphRepository(use_native=False) as repository:
            graph = self.baseline.to_dict()["analysis"]["graph"]
            from backend.graph.schema import Node, Edge
            repository.replace([Node(**{key: value for key, value in item.items() if key in Node.__dataclass_fields__}) for item in graph["nodes"]], [Edge(**item) for item in graph["edges"]])
            api = BrainAPI(repository, overrides_path=self.root / "overrides.json")
            app = BrainApp(api)
            target = self.contract["targets"][0]["object_id"]
            before = content_hash({"nodes": [item.to_dict() for item in repository.all_nodes()], "edges": [item.to_dict() for item in repository.all_edges()]})
            status, impact = app.handle("POST", "/api/impact", {"target_id": target})
            self.assertEqual(200, status); self.assertTrue(impact["potential_impacts"])
            context = build_context(repository, target, "impact")
            self.assertIn("impact_report_id", context)
            self.assertEqual(404, app.handle("POST", "/api/compare", {"before": "../source", "after": "x"})[0])
            self.assertEqual(404, app.handle("POST", "/api/promote", {})[0])
            after = content_hash({"nodes": [item.to_dict() for item in repository.all_nodes()], "edges": [item.to_dict() for item in repository.all_edges()]})
            self.assertEqual(before, after)

    def test_tmdl_endpoint_one_diff_and_unknown_comment_blocked(self):
        tom = TabularMetadataAdapter().read(self.source / "Sales.SemanticModel/model.bim", include_documents=True)
        definition = self.source / "Sales.SemanticModel/definition"
        for relative, document in tom["tmdl_documents"].items():
            path = definition / relative; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(document.encode("utf-8"))
        (self.source / "Sales.SemanticModel/model.bim").unlink()
        self.baseline = self.guard.capture_baseline(); self.contract = proposal(self.baseline)
        operation, candidate = self.candidate()
        relationship = candidate / "Sales.SemanticModel/definition/relationships.tmdl"
        relationship.write_bytes(relationship.read_bytes().replace(b"OrderDateKey", b"ShipDateKey"))
        self.guard.validate_candidate(operation)
        verification = self.guard.review(operation)["verification"]
        self.assertEqual("PASSED", verification["scope"]["status"])
        self.assertEqual(1, len(verification["comparison"]["property_changes"]))
        relationship.write_bytes(relationship.read_bytes() + b"// agent claims authorization\n")
        with self.assertRaises(GuardError): self.guard.validate_candidate(operation)
        self.assertEqual("REJECT", self.guard.review(operation)["operation"]["decision"]["decision"])

    def test_authorized_active_toggle_and_cardinality_diffs(self):
        for property_name, key, value in [("active", "isActive", False), ("cross_filter_direction", "crossFilteringBehavior", "bothDirections"), ("from_cardinality", "fromCardinality", "one")]:
            with self.subTest(property=property_name):
                self.contract = proposal(self.baseline, property_name=property_name, new_value=value)
                operation, candidate = self.candidate()
                modify_bim(candidate, lambda model: model["relationships"][0].update({key: value}))
                self.guard.validate_candidate(operation)
                self.assertEqual("PASSED", self.guard.review(operation)["verification"]["scope"]["status"])

    def test_visual_binding_modification_is_property_diff_and_scope_violation(self):
        report_source = self.root / "visual-source"; reference_project(report_source, report=True)
        guard = ChangeGuard(report_source, self.root / "visual-trusted", "visual-project")
        baseline = guard.capture_baseline(); contract = proposal(baseline)
        state = guard.prepare_change(contract); state = guard.authorize(state["operation_id"], "CONTRACT")
        candidate = Path(state["candidate_root"])
        modify_bim(candidate, lambda model: model["relationships"][0].update(fromColumn="ShipDateKey"))
        path = candidate / "Sales.Report/definition/pages/month/visuals/sales/visual.json"
        value = json.loads(path.read_text()); value["visual"]["query"]["queryState"]["Values"]["projections"][0]["field"]["Measure"]["Property"] = "Sales YTD"
        path.write_text(json.dumps(value))
        result = guard.validate_candidate(state["operation_id"])
        self.assertEqual("REJECT", result["decision"]["decision"])
        changes = guard.review(state["operation_id"])["verification"]["comparison"]["object_changes"]
        self.assertTrue(any(item["object_type"] == "VISUAL" and item["classification"] == "REFERENCE_CHANGED" for item in changes))

    def test_opaque_report_resource_is_preserved_but_edit_blocks_scope(self):
        asset = self.source / "Sales.Report/StaticResources/RegisteredResources/logo.png"
        asset.parent.mkdir(parents=True); asset.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
        self.baseline = self.guard.capture_baseline(); self.contract = proposal(self.baseline)
        operation, candidate = self.candidate()
        copied = candidate / asset.relative_to(self.source)
        self.assertEqual(asset.read_bytes(), copied.read_bytes())
        modify_bim(candidate, lambda model: model["relationships"][0].update(fromColumn="ShipDateKey"))
        copied.write_bytes(b"\x89PNG\r\n\x1a\nchanged")
        decision = self.guard.validate_candidate(operation)
        self.assertEqual("REJECT", decision["decision"]["decision"])
        self.assertTrue(self.guard.review(operation)["verification"]["comparison"]["unknown_differences"])

    def test_column_lineage_rename_preserved(self):
        operation, candidate = self.candidate()
        modify_bim(candidate, lambda model: model["tables"][1]["columns"][1].update(name="DispatchDateKey"))
        self.guard.validate_candidate(operation)
        differences = self.guard.review(operation)["verification"]["comparison"]["object_changes"]
        self.assertTrue(any(item["classification"] == "OBJECT_RENAMED" and item["object_id"].endswith("column:column-ship") for item in differences))

    def test_column_deletion_is_detected_and_rejected(self):
        operation, candidate = self.candidate()
        modify_bim(candidate, lambda model: model["tables"][1]["columns"].pop(1))
        self.guard.validate_candidate(operation)
        review = self.guard.review(operation)
        self.assertEqual("REJECT", review["operation"]["decision"]["decision"])
        self.assertTrue(any(item["classification"] == "OBJECT_DELETED" for item in review["verification"]["comparison"]["object_changes"]))

    def test_multiple_active_paths_block_complete_certification(self):
        modify_bim(self.source, lambda model: model["relationships"].append({"name": "other-active", "isActive": True, "fromTable": "FactSales", "fromColumn": "ShipDateKey", "toTable": "Date", "toColumn": "DateKey"}))
        value = self.guard.capture_baseline().to_dict()
        self.assertEqual("INCOMPLETE", value["completeness"]["status"])
        self.assertTrue(any("ACTIVE_FILTER_TOPOLOGY" in item for item in value["completeness"]["blocking"]))

    def test_explicit_relationship_override_has_specialized_impact(self):
        def update(model):
            model["relationships"].append({"name": "shipping-inactive", "isActive": False, "fromTable": "FactSales", "fromColumn": "ShipDateKey", "toTable": "Date", "toColumn": "DateKey"})
            model["tables"][1]["measures"].append({"name": "Shipping", "lineageTag": "shipping-measure", "expression": "CALCULATE([Sales Amount], USERELATIONSHIP(FactSales[ShipDateKey], Date[DateKey]))"})
            model["tables"][1]["measures"].append({"name": "No Date", "lineageTag": "no-date-measure", "expression": "CALCULATE([Sales Amount], CROSSFILTER(FactSales[OrderDateKey], Date[DateKey], NONE))"})
        modify_bim(self.source, update)
        snapshot = self.guard.capture_baseline().to_dict()
        target = next(item["object_id"] for item in snapshot["analysis"]["objects"].values() if item["object_type"] == "RELATIONSHIP" and item["properties"]["name"] == "relationship-sales")
        impact = analyze_impact(snapshot["analysis"]["graph"], [target], completeness=snapshot["completeness"])
        rules = {item["analyzer_rule_id"] for item in impact["conditional_impacts"]}
        self.assertTrue({"dax_override:USERELATIONSHIP", "dax_override:CROSSFILTER"}.issubset(rules))


class PrimitiveTests(unittest.TestCase):
    def test_property_identity_and_significant_expression_whitespace(self):
        for key, classification in [("name", "OBJECT_RENAMED"), ("lineage_tag", "IDENTITY_CHANGED"), ("from_column_id", "REFERENCE_CHANGED")]:
            self.assertEqual(classification, compare_properties({key: "a"}, {key: "b"})[0]["classification"])
        self.assertTrue(compare_properties({"expression": '"a b"'}, {"expression": '"ab"'}))

    def test_paths_aliases_and_executables_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in ("../outside", "C:/outside", "x:stream", "/absolute"):
                with self.subTest(path=relative), self.assertRaises(SourceIntegrityError): safe_path(root, relative)
            (root / "agent.exe").write_bytes(b"MZ")
            with self.assertRaises(SourceIntegrityError): source_manifest(root)

    def test_credentials_do_not_enter_candidate_or_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source = root / "source"; source.mkdir()
            (source / "model.json").write_text(json.dumps({"connectionString": "Server=test;Password=sensitive-value"}))
            candidate = root / "candidate"
            with self.assertRaises(SourceIntegrityError): create_candidate(source, candidate, source_manifest(source))
            self.assertFalse(candidate.exists())
            reference_project(root / "project")
            path = root / "project/Sales.SemanticModel/model.bim"
            value = json.loads(path.read_text()); value["model"]["annotations"] = [{"name": "AccessToken", "value": "sensitive-value"}]
            path.write_text(json.dumps(value))
            guard = ChangeGuard(root / "project", root / "trusted", "secret-test")
            with self.assertRaises(SourceIntegrityError): guard.capture_baseline()
            self.assertFalse(list((root / "trusted").glob("*/baseline.json")))

    def test_candidate_protected_directory_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); (root / ".pbi-guard").mkdir()
            with self.assertRaises(SourceIntegrityError): assert_candidate_integrity(root)

    def test_digest_pinned_isolation_only(self):
        for image in ("latest", "trusted:latest", "--privileged", "safe@sha256:bad"):
            with self.assertRaises(ValueError): DockerIsolation(image)

    def test_audit_chain_signature_and_partial_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = AuditStore(temporary)
            store.append("operation", "ONE", {"fact": 1}); store.append("operation", "TWO", {"fact": 2})
            self.assertEqual(2, len(store.read("operation")))
            path = Path(temporary) / "operation/audit.jsonl"
            data = path.read_bytes(); path.write_bytes(data.replace(b'"fact":1', b'"fact":9'))
            with self.assertRaises(AuditIntegrityError): store.read("operation")
            path.write_bytes(data[:-1])
            with self.assertRaises(AuditIntegrityError): store.read("operation")

    def test_signed_audit_head_detects_valid_tail_removal(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = AuditStore(temporary)
            store.append("operation", "FIRST", {})
            store.append("operation", "SECOND", {})
            path = Path(temporary) / "operation/audit.jsonl"
            path.write_bytes(path.read_bytes().splitlines(keepends=True)[0])
            with self.assertRaises(AuditIntegrityError): AuditStore(temporary).read("operation")

    def test_windows_path_aliases_and_hardlinks_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in ("a.json.", "dir /a.json", "NUL.json", "COM1/file.json"):
                with self.subTest(relative=relative), self.assertRaises(SourceIntegrityError): safe_path(root, relative)
            original = root / "a.json"; original.write_text("{}")
            (root / "b.json").hardlink_to(original)
            with self.assertRaises(SourceIntegrityError): source_manifest(root)

    def test_invalid_cli_input_has_json_error(self):
        from contextlib import redirect_stdout
        from change_guard.cli import main
        output = io.StringIO()
        with redirect_stdout(output), self.assertRaises(SystemExit) as error:
            main([])
        self.assertEqual(2, error.exception.code)
        self.assertEqual("INVALID_INPUT", json.loads(output.getvalue())["error"]["code"])

    def test_brain_session_does_not_authorize_guard(self):
        service = GuardService(None, "guard-secret", "http://127.0.0.1:8051")
        self.assertEqual(403, service.handle("POST", "/guard/promote/x", {}, token="brain-session")[0])
        self.assertEqual(403, service.handle("POST", "/guard/promote/x", {}, token="guard-secret", origin="https://attacker.test")[0])


class RegressionTests(unittest.TestCase):
    def dataset(self, rows):
        return {"columns": [{"name": "Month", "type": "text"}, {"name": "Sales", "type": "decimal"}], "rows": rows}

    def test_monthly_redistribution_and_preserved_aggregate(self):
        a = self.dataset([["Jan", 10], ["Feb", 20]])
        b = self.dataset([["Jan", 20], ["Feb", 10]])
        self.assertEqual("FAILED", compare_results(a, b)["status"])
        totals = {"columns": [{"name": "Total", "type": "decimal"}], "rows": [[30]]}
        self.assertEqual("PASSED", compare_results(totals, totals, "PRESERVE_AGGREGATE", {"numeric": {"absolute_tolerance": "0"}})["status"])

    def test_blank_missing_rows_duplicates_and_order(self):
        a = self.dataset([["Jan", None], ["Jan", 10], ["Jan", 10]])
        self.assertEqual("FAILED", compare_results(a, self.dataset([["Jan", 0], ["Jan", 10], ["Jan", 10]]))["status"])
        self.assertEqual("FAILED", compare_results(a, self.dataset(a["rows"][:2]), "SET_EQUIVALENCE")["status"])
        self.assertEqual("PASSED", compare_results(a, self.dataset(list(reversed(a["rows"]))), "SET_EQUIVALENCE")["status"])

    def test_decimal_precision_explicit_tolerance(self):
        a = self.dataset([["Jan", Decimal("0.123456789012345678901")]])
        b = self.dataset([["Jan", Decimal("0.123456789012345678902")]])
        self.assertEqual("FAILED", compare_results(a, b)["status"])
        self.assertEqual("PASSED", compare_results(a, b, "NUMERIC_TOLERANCE", {"numeric": {"absolute_tolerance": "0.00000000000000000001"}})["status"])

    def test_runner_preserves_decimal_evidence_and_requires_loader_binding(self):
        adapter = TestDouble(lambda query, params: self.dataset([["Jan", Decimal("30.000000000000000001")]]))
        result = self.run_plan(adapter, adapter)
        self.assertEqual("PASSED", result["results"][0]["status"])
        self.assertFalse(result["runtime_binding_verified"])
        self.assertFalse(result["certified"])

    def test_recursive_expected_comparison_and_invalid_delta_rejected(self):
        data = self.dataset([["Jan", 30]])
        with self.assertRaises(ValueError): compare_results(data, data, "EXPECTED_CHANGE", {"expected_result": data, "expected_comparison_mode": "EXPECTED_CHANGE"})
        with self.assertRaises(ValueError): compare_results(data, data, "EXPECTED_DELTA", {"minimum_delta": "Infinity", "maximum_delta": "Infinity"})

    def test_expected_change_requires_explicit_dataset(self):
        with self.assertRaises(ValueError): RegressionTest("expected", ("m",), "EVALUATE ROW(\"x\", 1)", mode="EXPECTED_CHANGE")
        a, b = self.dataset([["Jan", 10]]), self.dataset([["Jan", 20]])
        self.assertEqual("PASSED", compare_results(a, b, "EXPECTED_CHANGE", {"expected_result": b})["status"])
        self.assertEqual("INCONCLUSIVE", compare_results(a, b, "MONITOR")["status"])

    def test_schema_types_and_query_errors(self):
        a = self.dataset([["Jan", 10]])
        b = deepcopy(a); b["columns"][1]["type"] = "text"
        self.assertEqual("FAILED", compare_results(a, b)["status"])
        self.assertEqual("FAILED", compare_results(a, {"error": "timeout"})["status"])

    def run_plan(self, before, after, context=None, candidate_context=None):
        context = context or ExecutionContext("data-v1", "processed-v1", "en-US", None, data_frozen=True)
        test = RegressionTest("total", ("m",), 'EVALUATE ROW("Total", 30)', covered_path_ids=("p",), invariant_ids=("total",))
        return execute_regression_plan([test], before, after, context, candidate_context or context, baseline_snapshot_id="before", candidate_snapshot_id="after",
                                       impact={"impacted_objects": ["m"], "impact_paths": [{"object_id": "m", "path_id": "p"}], "required_tests": []})

    def test_mock_does_not_certify_runtime(self):
        adapter = TestDouble(lambda query, params: self.dataset([["Jan", 30]]))
        result = self.run_plan(adapter, adapter)
        self.assertFalse(result["certified"]); self.assertEqual("INCONCLUSIVE", result["status"])
        self.assertEqual([], result["verified_invariants"])

    def test_data_drift_missing_backend_query_failure(self):
        adapter = TestDouble(lambda query, params: self.dataset([["Jan", 30]]))
        drift = ExecutionContext("data-v2", "processed-v2", "en-US", None, data_frozen=True)
        self.assertEqual("INCONCLUSIVE", self.run_plan(adapter, adapter, candidate_context=drift)["status"])
        self.assertEqual("NOT_RUN", self.run_plan(UnavailableAdapter(), UnavailableAdapter())["status"])
        def fail(query, params): raise TimeoutError()
        result = self.run_plan(TestDouble(fail), adapter)
        self.assertEqual("FAILED", result["status"]); self.assertIn("total", result["failed_tests"])

    def test_mutating_query_is_never_executed(self):
        calls = []
        adapter = TestDouble(lambda query, params: calls.append(query))
        context = ExecutionContext("data-v1", "processed-v1", "en-US", None, data_frozen=True)
        result = execute_regression_plan([RegressionTest("bad", ("m",), "CREATE TABLE x")], adapter, adapter, context, context,
                    baseline_snapshot_id="before", candidate_snapshot_id="after", impact={})
        self.assertEqual([], calls); self.assertEqual("FAILED", result["status"])


class PromotionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.source = self.root / "source"; self.candidate = self.root / "candidate"
        self.source.mkdir(); (self.source / "a.json").write_text('{"v":1}'); (self.source / "b.json").write_text('{"v":1}')
        self.before = source_manifest(self.source); create_candidate(self.source, self.candidate, self.before)
        (self.candidate / "a.json").write_text('{"v":2}'); (self.candidate / "b.json").write_text('{"v":2}')
        self.after = source_manifest(self.candidate); self.store = AuditStore(self.root / "trusted")
        self.permit = self.store.sign({"operation_id": "op", "source_root": str(self.source), "candidate_root": str(self.candidate), "baseline_manifest": self.before,
                    "candidate_manifest": self.after, "candidate_hash": content_hash(self.after), "baseline_snapshot_id": "baseline", "contract_hash": "contract", "policy_hash": "policy", "evidence_hash": "evidence", "principal": "human", "authorized_operation": "PROMOTE"})

    def test_signed_local_promotion_and_hash_verification(self):
        journal = LocalPromotion(self.store).promote("op", self.permit)
        self.assertEqual("COMMITTED", journal["status"]); self.assertEqual(self.after, source_manifest(self.source))

    def test_git_review_revision_preserves_authoritative_head_and_sources(self):
        def git(*args):
            return subprocess.run(["git", "-C", str(self.source), *args], capture_output=True, text=True, check=True).stdout.strip()
        git("init", "-q")
        git("config", "user.name", "Guard test")
        git("config", "user.email", "guard-test@example.invalid")
        git("add", "a.json", "b.json")
        git("commit", "-qm", "Baseline fixture")
        revision = git("rev-parse", "HEAD")
        result = create_review_revision(self.source, self.candidate, revision, self.before, self.after, "test-operation")
        self.assertEqual(revision, git("rev-parse", "HEAD"))
        self.assertEqual("", git("status", "--porcelain"))
        self.assertEqual(self.before, source_manifest(self.source))
        self.assertEqual('{"v":2}', git("show", result["candidate_revision"] + ":a.json"))
        self.assertEqual(revision, git("rev-parse", result["candidate_revision"] + "^"))
        self.assertFalse(result["authoritative_promoted"])

    def test_tampered_promotion_authorization_rejected(self):
        self.permit["payload"]["candidate_hash"] = "other"
        with self.assertRaises(AuditIntegrityError): LocalPromotion(self.store).promote("op", self.permit)
        self.assertEqual(self.before, source_manifest(self.source))

    def test_interruption_recovery_survives_controller_restart(self):
        def fault(index): raise RuntimeError("injected interruption")
        with self.assertRaises(PromotionError): LocalPromotion(self.store).promote("op", self.permit, fault=fault)
        reopened = AuditStore(self.store.root)
        journal = LocalPromotion(reopened).recover("op")
        self.assertEqual("RECOVERED", journal["status"]); self.assertEqual(self.before, source_manifest(self.source))

    def test_failed_post_promotion_verification_can_restore_committed_sources(self):
        promotion = LocalPromotion(self.store)
        promotion.promote("op", self.permit)
        promotion.require_recovery("op", "POST_PROMOTION_MISMATCH")
        journal = LocalPromotion(AuditStore(self.store.root)).recover("op")
        self.assertEqual("RECOVERED", journal["status"])
        self.assertEqual(self.before, source_manifest(self.source))

    def test_stale_source_and_candidate_rejected(self):
        (self.source / "a.json").write_text('{"v":9}')
        with self.assertRaises(PromotionError): LocalPromotion(self.store).promote("op", self.permit)
        (self.source / "a.json").write_text('{"v":1}')
        (self.candidate / "a.json").write_text('{"v":9}')
        with self.assertRaises(PromotionError): LocalPromotion(self.store).promote("op", self.permit)

    def test_recovery_refuses_concurrent_edits_and_corrupt_backups(self):
        def fault(index): raise RuntimeError("injected interruption")
        with self.assertRaises(PromotionError): LocalPromotion(self.store).promote("op", self.permit, fault=fault)
        (self.source / "a.json").write_text('{"v":9}')
        with self.assertRaises(PromotionError): LocalPromotion(self.store).recover("op")
        self.assertEqual('{"v":9}', (self.source / "a.json").read_text())
        (self.source / "a.json").write_text('{"v":2}')
        (self.store.root / "op/backups/a.json").write_text("corrupt")
        with self.assertRaises(PromotionError): LocalPromotion(self.store).recover("op")


if __name__ == "__main__": unittest.main()
