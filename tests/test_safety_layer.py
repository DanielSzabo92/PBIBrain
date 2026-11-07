"""Safety layer (issue #17): no-container guard tier, TMDL create/delete/rename coverage,
the shared Breaks/Needs report, and pending changes from files edited outside the app."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from backend.adapters.tabular_metadata import TabularMetadataAdapter
from backend.api.app import BrainAPI, BrainApp
from backend.diff.snapshots import MISSING
from backend.graph.repository import GraphRepository
from backend.mcp_budget import TOOL_BUDGETS, budget_for
from backend.mcp_snapshot import SnapshotClient
from backend.pending_changes import SourceWatcher, compute_pending_changes
from backend.projects import ProjectService
from backend.safety import assess_change, find_needs, object_changes
from change_guard.contracts import ChangeContract
from change_guard.coverage import prove_tmdl_changes
from change_guard.orchestrator import ChangeGuard, GuardError
from change_guard.policy import Policy, evaluate_candidate
from change_guard.workspace import LocalCopyIsolation
from tests.guarded_fixture import reference_project

HAS_MCP = importlib.util.find_spec("mcp") is not None
FACT_TABLE = "Sales.SemanticModel/definition/tables/FactSales.tmdl"
SALES_AMOUNT_BLOCK = b"\tmeasure 'Sales Amount' = SUM(FactSales[SalesAmount])\r\n\t\tlineageTag: measure-sales\r\n\r\n"


def node(object_id, kind, name, **properties):
    return {"id": object_id, "type": kind, "name": name, "model_id": "model:m", "properties": properties}


def edge(source, target, kind="DEPENDS_ON"):
    return {"id": f"{kind}:{source}:{target}", "type": kind, "from_id": source, "to_id": target}


def graph(nodes, edges=()):
    return {"nodes": list(nodes), "edges": list(edges)}


TABLE = node("t", "TABLE", "Fact")
COLUMN = node("c", "COLUMN", "Amount", table_id="t")
TOTAL = node("m1", "MEASURE", "Total", table_id="t", expression="SUM(Fact[Amount])")
DOUBLE = node("m2", "MEASURE", "Double", table_id="t", expression="[Total] * 2")
VISUAL = {"id": "v", "type": "VISUAL", "name": "card", "report_id": "report:r", "model_id": "model:m", "properties": {}}
BEFORE = graph([TABLE, COLUMN, TOTAL, DOUBLE, VISUAL], [edge("m1", "c", "REFERENCES"), edge("m2", "m1"), edge("v", "m1", "USES")])


class SafetyReportTests(unittest.TestCase):
    def test_deleting_a_used_measure_breaks_its_users(self) -> None:
        after = graph([TABLE, COLUMN, DOUBLE, VISUAL], [])
        report = assess_change(BEFORE, after)
        self.assertEqual("BREAKS", report["status"])
        self.assertEqual([("m1", "deleted")], [(item["object_id"], item["change"]) for item in report["changes"]])
        self.assertEqual({("m2", "uses_deleted"), ("v", "uses_deleted")}, {(item["object_id"], item["reason"]) for item in report["breaks"]})
        self.assertTrue(all(item["uses"]["name"] == "Total" for item in report["breaks"]))
        self.assertEqual({"changes": 1, "deleted": 1, "breaks": 2, "needs": 0}, report["summary"])

    def test_objects_deleted_together_do_not_break_each_other(self) -> None:
        report = assess_change(BEFORE, graph([TABLE, COLUMN, VISUAL]))
        self.assertEqual(["v"], [item["object_id"] for item in report["breaks"]])

    def test_a_rename_breaks_users_that_still_use_the_old_name(self) -> None:
        renamed = {**TOTAL, "name": "Revenue"}
        stale = assess_change(BEFORE, graph([TABLE, COLUMN, renamed, DOUBLE, VISUAL], [edge("v", "m1", "USES")]))
        self.assertEqual([{"change": "renamed", "old_name": "Total", "name": "Revenue"}],
                         [{key: item[key] for key in ("change", "old_name", "name")} for item in stale["changes"]])
        self.assertEqual([("m2", "uses_old_name", "Revenue")], [(item["object_id"], item["reason"], item["uses"]["new_name"]) for item in stale["breaks"]])
        # The dependent was rewritten, so its reference resolves again: no break.
        rewritten = {**DOUBLE, "properties": {**DOUBLE["properties"], "expression": "[Revenue] * 2"}}
        fixed = assess_change(BEFORE, graph([TABLE, COLUMN, renamed, rewritten, VISUAL], [edge("m2", "m1"), edge("v", "m1", "USES")]))
        self.assertEqual([], fixed["breaks"])
        self.assertEqual([], fixed["needs"])

    def test_new_dax_that_names_a_missing_object_needs_it(self) -> None:
        created = node("m3", "MEASURE", "Margin", table_id="t", expression="[Total] - [Cost] + SUM(Fact[Tax]) + SUM('Budget'[Value]) // [Comment]")
        after = graph([TABLE, COLUMN, TOTAL, DOUBLE, created, VISUAL])
        needs = find_needs(after, object_changes(BEFORE, after))
        self.assertEqual([{"kind": "measure_or_column", "name": "Cost"}, {"kind": "column", "table": "Fact", "name": "Tax"},
                          {"kind": "table", "name": "Budget"}], needs[0]["missing"])

    def test_a_new_measure_that_resolves_has_no_needs(self) -> None:
        created = node("m3", "MEASURE", "Count", table_id="t", expression='COUNTROWS(Fact) + [Total] + LEN("[not a reference]")')
        report = assess_change(BEFORE, graph([TABLE, COLUMN, TOTAL, DOUBLE, created, VISUAL], BEFORE["edges"]))
        self.assertEqual("CHANGED", report["status"])
        self.assertEqual([("m3", "created")], [(item["object_id"], item["change"]) for item in report["changes"]])

    def test_parser_output_alone_is_not_a_change(self) -> None:
        noisy = {**DOUBLE, "properties": {**DOUBLE["properties"], "dax_diagnostics": ["x"], "dax_evidence": [1]}}
        self.assertEqual("UNCHANGED", assess_change(BEFORE, graph([TABLE, COLUMN, TOTAL, noisy, VISUAL], BEFORE["edges"]))["status"])


class PolicyTests(unittest.TestCase):
    def test_breaks_need_their_own_approval_and_the_default_policy_hash_is_unchanged(self) -> None:
        self.assertEqual(Policy().policy_hash, Policy(allow_local_copy=True).policy_hash)
        self.assertNotEqual(Policy().policy_hash, Policy(allow_local_copy=False).policy_hash)
        document = {"targets": [{"object_id": "m", "object_type": "MEASURE"}],
                    "allowed_mutations": [{"object_id": "m", "operation": "SET_PROPERTY", "property": "description"}],
                    "validation": {"require_runtime_validation": False, "require_impact_analysis": False, "require_complete_dependency_coverage": False},
                    "behavior": {"permitted_effects": [], "invariants": []}}
        contract = ChangeContract(json.dumps(document), "{}")
        evidence = {name: {"status": "PASSED"} for name in ("security", "scope", "baseline", "source", "static")}
        self.assertEqual("ALLOW", evaluate_candidate(contract, evidence, Policy())["decision"])
        broken = {**evidence, "safety": {"breaks": [{"object_id": "x"}]}}
        decision = evaluate_candidate(contract, broken, Policy())
        self.assertEqual(("APPROVAL_REQUIRED", ["BREAKS_DEPENDENTS"]), (decision["decision"], decision["approval_reasons"]))
        approved = evaluate_candidate(contract, {**broken, "valid_approval_operations": ["BREAKS_DEPENDENTS"]}, Policy())
        self.assertEqual("ALLOW", approved["decision"])


class LocalCopyIsolationTests(unittest.TestCase):
    def test_the_local_tier_runs_in_the_copy_without_credentials_and_says_it_is_weaker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            candidate = Path(temporary) / "candidate"
            candidate.mkdir()
            (candidate / "model.json").write_text("{}", encoding="utf-8")
            os.environ["PBI_TEST_SECRET_TOKEN"] = "do-not-pass"
            self.addCleanup(os.environ.pop, "PBI_TEST_SECRET_TOKEN", None)
            script = "import os,pathlib; pathlib.Path('model.json').write_text('[' + str('PBI_TEST_SECRET_TOKEN' in os.environ).lower() + ',' + repr(os.environ['PBI_GUARD_CANDIDATE']).replace(chr(39), chr(34)) + ']')"
            receipt = LocalCopyIsolation().run(candidate, [sys.executable, "-c", script])
            self.assertEqual(("LOCAL_COPY", "WEAKER_NO_CONTAINER", "PASSED", 0),
                             (receipt["backend"], receipt["isolation_strength"], receipt["status"], receipt["process_exit_code"]))
            self.assertEqual([False, str(candidate.absolute())], json.loads((candidate / "model.json").read_text(encoding="utf-8")))
            failed = LocalCopyIsolation().run(candidate, [sys.executable, "-c", "raise SystemExit(3)"])
            self.assertEqual(("FAILED", 3), (failed["status"], failed["process_exit_code"]))


def tmdl_project(root: Path) -> None:
    """The guard reference project, saved as TMDL by the model library."""

    reference_project(root)
    bim = root / "Sales.SemanticModel/model.bim"
    documents = TabularMetadataAdapter().read(bim, include_documents=True)["tmdl_documents"]
    definition = root / "Sales.SemanticModel/definition"
    for relative, document in documents.items():
        path = definition / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(document.encode("utf-8"))
    bim.unlink()


def measure_contract(baseline: dict, *, operation: str, measure: str = "Sales Amount") -> dict:
    target = next(item for item in baseline["analysis"]["objects"].values() if item["object_type"] == "MEASURE" and item["properties"]["name"] == measure)
    mutation = {"object_id": target["object_id"], "operation": operation, "property": "$object" if operation == "DELETE_OBJECT" else "expression",
                "expected_before": target if operation == "DELETE_OBJECT" else target["properties"]["expression"],
                "expected_after": MISSING if operation == "DELETE_OBJECT" else target["properties"]["expression"] + " * 1"}
    return {"contract_version": 1, "task_id": "safety", "project_id": "project-sales",
            "baseline": {"snapshot_id": baseline["snapshot_id"], "source_revision": baseline["source_revision"]},
            "intent": {"description": "Agent edit", "category": "MEASURE_CHANGE"},
            "targets": [{"object_id": target["object_id"], "object_type": "MEASURE"}], "allowed_mutations": [mutation],
            "forbidden": {"allow_unlisted_mutations": False, "allow_object_creation": False, "allow_object_deletion": operation == "DELETE_OBJECT", "allow_identity_changes": False},
            "behavior": {"permitted_effects": [], "invariants": []},
            "validation": {"require_static_validation": True, "require_runtime_validation": False, "require_impact_analysis": True, "require_complete_dependency_coverage": False},
            "approval": {"scope_expansion": "EXPLICIT", "unexpected_behavior": "EXPLICIT", "high_risk_promotion": "EXPLICIT"}}


class NoDockerAgentEditTests(unittest.TestCase):
    """Acceptance of issue #17, on a machine without Docker."""

    @classmethod
    def setUpClass(cls) -> None:
        if not TabularMetadataAdapter().bridge.is_file():
            raise unittest.SkipTest("Build the trusted TOM bridge to run the guard acceptance tests")

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        tmdl_project(self.source)
        self.guard = ChangeGuard(self.source, self.root / "trusted", "project-sales")
        self.baseline = self.guard.capture_baseline().to_dict()

    def candidate(self, contract: dict) -> tuple[str, Path]:
        state = self.guard.prepare_change(contract)
        state = self.guard.authorize(state["operation_id"], "CONTRACT")
        return state["operation_id"], Path(state["candidate_root"])

    def edit(self, candidate: Path, old: bytes, new: bytes) -> None:
        path = candidate / FACT_TABLE
        content = path.read_bytes()
        self.assertEqual(1, content.count(old))
        path.write_bytes(content.replace(old, new))

    def test_deleting_a_used_measure_is_caught_with_its_impact_before_acceptance(self) -> None:
        operation, candidate = self.candidate(measure_contract(self.baseline, operation="DELETE_OBJECT"))
        self.edit(candidate, SALES_AMOUNT_BLOCK, b"")
        self.guard.record_local_edit(operation)
        state = self.guard.validate_candidate(operation)
        review = self.guard.review(operation)
        verification = review["verification"]
        self.assertEqual("REJECT", state["decision"]["decision"])
        # The no-container tier passed the security gate and says it is weaker.
        self.assertEqual(("PASSED", "LOCAL_COPY", "WEAKER_NO_CONTAINER"),
                         (verification["security"]["status"], verification["security"]["backend"], verification["security"]["isolation_strength"]))
        # The deleted block is covered (TOM regeneration), the deletion is in scope, and the break is shown.
        self.assertEqual("PASSED", verification["source"]["status"])
        self.assertEqual([FACT_TABLE], verification["source"]["tmdl_coverage"]["proven_sources"])
        self.assertEqual("PASSED", verification["scope"]["status"])
        self.assertEqual("BREAKS", verification["safety"]["status"])
        self.assertEqual([("Sales YTD", "uses_deleted", "Sales Amount")],
                         [(item["name"], item["reason"], item["uses"]["name"]) for item in verification["safety"]["breaks"]])
        self.assertIn("BREAKS_DEPENDENTS", state["decision"]["approval_reasons"])
        with self.assertRaises(GuardError):
            self.guard.accept_candidate(operation, review["review_binding"], ["BREAKS_DEPENDENTS", "PROMOTE"])
        self.assertIn(SALES_AMOUNT_BLOCK, (self.source / FACT_TABLE).read_bytes())

    def test_creating_a_measure_passes_coverage_even_with_lf_line_endings(self) -> None:
        operation, candidate = self.candidate(measure_contract(self.baseline, operation="SET_PROPERTY"))
        self.edit(candidate, b"\tcolumn OrderDateKey", b"\tmeasure 'Sales Count' = COUNTROWS(FactSales)\n\t\tlineageTag: measure-count\n\n\tcolumn OrderDateKey")
        self.guard.record_local_edit(operation)
        self.guard.validate_candidate(operation)
        verification = self.guard.review(operation)["verification"]
        self.assertEqual("PASSED", verification["source"]["status"])
        self.assertEqual([], verification["comparison"]["unknown_differences"])
        self.assertEqual([FACT_TABLE], verification["source"]["tmdl_coverage"]["proven_sources"])
        self.assertEqual([("Sales Count", "created")], [(item["name"], item["change"]) for item in verification["safety"]["changes"]])
        self.assertEqual([], verification["safety"]["needs"])
        # The creation was not in the contract, so scope still rejects it: coverage is not permission.
        self.assertEqual("REJECTED_SCOPE", verification["scope"]["status"])

    def test_a_new_table_file_and_a_comment(self) -> None:
        candidate = self.root / "candidate"
        shutil.copytree(self.source, candidate)
        table = (b"table Budget\r\n\tlineageTag: table-budget\r\n\r\n\tcolumn Amount\r\n\t\tdataType: decimal\r\n"
                 b"\t\tlineageTag: column-budget\r\n\t\tsourceColumn: Amount\r\n\r\n")
        (candidate / "Sales.SemanticModel/definition/tables/Budget.tmdl").write_bytes(table)
        model = candidate / "Sales.SemanticModel/definition/model.tmdl"
        model.write_bytes(model.read_bytes().replace(b"ref table FactSales", b"ref table FactSales\r\nref table Budget"))
        proof = prove_tmdl_changes(self.source, candidate, TabularMetadataAdapter())
        self.assertEqual("created", proof["changed"]["Sales.SemanticModel/definition/tables/Budget.tmdl"])
        self.assertIn("Sales.SemanticModel/definition/tables/Budget.tmdl", proof["proven_sources"], proof)
        # A comment is text the model library does not keep: not proven, so the line check decides (and rejects).
        path = candidate / FACT_TABLE
        path.write_bytes(path.read_bytes().replace(b"\tcolumn OrderDateKey", b"\t// note for the agent\r\n\tcolumn OrderDateKey", 1))
        proof = prove_tmdl_changes(self.source, candidate, TabularMetadataAdapter())
        self.assertNotIn(FACT_TABLE, proof["proven_sources"])
        self.assertIn(FACT_TABLE, [item["file"] for item in proof["violations"]])

    def test_a_deleted_table_file_is_proven(self) -> None:
        candidate = self.root / "candidate"
        shutil.copytree(self.source, candidate)
        (candidate / "Sales.SemanticModel/definition/relationships.tmdl").unlink()
        proof = prove_tmdl_changes(self.source, candidate, TabularMetadataAdapter())
        self.assertEqual(["Sales.SemanticModel/definition/relationships.tmdl"], proof["proven_sources"], proof)

    def test_the_policy_can_require_a_container(self) -> None:
        guard = ChangeGuard(self.source, self.root / "strict", "project-sales", policy=Policy(allow_local_copy=False))
        baseline = guard.capture_baseline().to_dict()
        state = guard.authorize(guard.prepare_change(measure_contract(baseline, operation="SET_PROPERTY"))["operation_id"], "CONTRACT")
        with self.assertRaises(GuardError) as raised:
            guard.record_local_edit(state["operation_id"])
        self.assertEqual("LOCAL_COPY_DISABLED", raised.exception.code)


def write_project(root: Path) -> Path:
    source = root / "sources" / "sales.json"
    source.parent.mkdir(parents=True, exist_ok=True)
    model = {"id": "sales", "name": "Sales", "tables": [{
        "id": "sales-facts", "name": "Facts", "columns": [{"id": "sales-amount", "name": "Amount", "dataType": "Double"}],
        "measures": [{"id": "sales-total", "name": "Total Sales", "expression": "SUM('Facts'[Amount])"},
                     {"id": "sales-double", "name": "Double Sales", "expression": "[Total Sales] * 2"}]}]}
    report = {"id": "sales-report", "name": "Sales Report", "modelId": "sales", "sections": [{
        "id": "sales-page", "name": "Overview", "visualContainers": [
            {"id": "sales-visual", "visualType": "card", "measures": [{"objectId": "sales-total"}]}]}]}
    source.write_text(json.dumps({"models": [model], "reports": [report]}), encoding="utf-8")
    config = root / ".pbibrain" / "brain.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(json.dumps({"version": 1, "name": "Sales", "sources": [os.path.relpath(source, config.parent)],
                                  "database": "brain.lbug", "identity_map": "identity.json"}), encoding="utf-8")
    return config


def drop_total_sales(root: Path) -> None:
    source = root / "sources" / "sales.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["models"][0]["tables"][0]["measures"] = payload["models"][0]["tables"][0]["measures"][1:]
    source.write_text(json.dumps(payload), encoding="utf-8")


class PendingChangesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.config = write_project(self.root)

    def scan(self) -> None:
        with GraphRepository(use_native=False) as repository:
            ProjectService(self.config).scan(repository)

    def test_no_scan_then_unchanged_then_breaks_then_rescan(self) -> None:
        self.assertEqual("NO_SCAN", compute_pending_changes(self.config)["status"])
        self.scan()
        self.assertEqual("UNCHANGED", compute_pending_changes(self.config)["status"])
        identity = (self.config.parent / "identity.json").read_bytes()
        snapshot = (self.config.parent / "agent-snapshot.json").read_bytes()
        drop_total_sales(self.root)
        reply = compute_pending_changes(self.config)
        self.assertEqual("BREAKS", reply["status"])
        self.assertEqual([{"file": "../sources/sales.json", "change": "changed"}], reply["files"])
        self.assertIn(("Total Sales", "deleted"), [(item["name"], item["change"]) for item in reply["safety"]["changes"]])
        breaks = {item["object_type"]: item for item in reply["safety"]["breaks"]}
        self.assertEqual("Double Sales", breaks["MEASURE"]["name"])
        self.assertIn("VISUAL", breaks)
        self.assertTrue(all(item["uses"]["name"] == "Total Sales" for item in breaks.values()))
        # The check wrote nothing: not the identity map, not the snapshot.
        self.assertEqual(identity, (self.config.parent / "identity.json").read_bytes())
        self.assertEqual(snapshot, (self.config.parent / "agent-snapshot.json").read_bytes())
        self.scan()
        self.assertEqual("UNCHANGED", compute_pending_changes(self.config)["status"])

    def test_a_file_that_cannot_be_read_is_reported_not_raised(self) -> None:
        self.scan()
        (self.root / "sources" / "sales.json").write_text("{ half saved", encoding="utf-8")
        self.assertEqual("UNREADABLE", compute_pending_changes(self.config)["status"])

    def test_the_watcher_reports_a_change_and_the_app_route_reads_it(self) -> None:
        self.scan()
        seen = []
        watcher = SourceWatcher(self.config, interval=0.05, on_change=seen.append).start()
        self.addCleanup(watcher.stop)
        self.assertIsNotNone(watcher.wait_for(lambda value: value["status"] == "UNCHANGED"))
        drop_total_sales(self.root)
        self.assertIsNotNone(watcher.wait_for(lambda value: value["status"] == "BREAKS"))
        self.assertEqual(["UNCHANGED", "BREAKS"], [item["status"] for item in seen])
        watcher.reset()
        self.assertIsNotNone(watcher.wait_for(lambda value: value["status"] == "BREAKS"))
        watcher.stop()

        project = ProjectService(self.config)
        app = BrainApp(BrainAPI(GraphRepository(use_native=False)), project=project)
        status, first = app.handle("GET", "/api/pending-changes")
        self.assertEqual(200, status)
        self.assertIn(first["status"], {"CHECKING", "BREAKS"})
        app._source_watcher.interval = 0.05
        self.addCleanup(app._source_watcher.stop)
        self.assertIsNotNone(app._source_watcher.wait_for(lambda value: value["status"] == "BREAKS"))
        self.assertEqual("BREAKS", app.handle("GET", "/api/pending-changes")[1]["status"])
        status, reply = BrainApp(BrainAPI(GraphRepository(use_native=False))).handle("GET", "/api/pending-changes")
        self.assertGreaterEqual(status, 400)

    def test_the_snapshot_client_answers_without_the_app(self) -> None:
        self.scan()
        drop_total_sales(self.root)
        reply = SnapshotClient(self.config).get("pending-changes")
        self.assertEqual("BREAKS", reply["status"])

    @unittest.skipUnless(HAS_MCP, "optional MCP SDK is not installed")
    def test_the_mcp_tool_fits_its_budget(self) -> None:
        from backend.mcp_server import create_server

        self.assertIn("brain_pending_changes", TOOL_BUDGETS)
        self.scan()
        drop_total_sales(self.root)
        server = create_server(None, config_path=self.config)
        result = asyncio.run(server.call_tool("brain_pending_changes", {}))
        payload = result[1] if isinstance(result, tuple) else json.loads(result[0].text)
        self.assertEqual("BREAKS", payload["status"])
        self.assertEqual("snapshot", payload["freshness"]["source"])
        self.assertLessEqual(len(json.dumps(payload, separators=(",", ":"))), budget_for("brain_pending_changes"))


if __name__ == "__main__":
    unittest.main()
