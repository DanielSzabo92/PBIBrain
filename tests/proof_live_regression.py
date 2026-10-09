"""Real-engine relationship fixture. All data originates from sealed literals."""
from __future__ import annotations
from datetime import date, timedelta
import json
from pathlib import Path
import tempfile
import sys
import shutil
import subprocess
from copy import deepcopy
from decimal import Decimal
from backend.snapshots import capture_snapshot, content_hash, Snapshot
from backend.snapshots.scan import scan_snapshot
from change_guard.regression import ExecutionContext
from change_guard.regression.local import LocalAnalysisServices, LocalTestInstance
from tests.test_pbir_coverage import schema_report
from tests.test_guarded_development import proposal
from change_guard.orchestrator import ChangeGuard
from change_guard.policy.engine import Policy
from change_guard.workspace.windows import WindowsAppContainer
from change_guard.regression.schema import RegressionTest
from change_guard.regression.comparison import canonical_result, compare_results

ENGINE = Path(r"C:\Program Files\Microsoft Power BI Desktop\bin\msmdsrv.exe")

def frozen_fixture(root):
    schema_report(root)
    path = root / "Sales.SemanticModel/model.bim"
    database = json.loads(path.read_text())
    dates = [{"DateKey": i + 1, "Date": date(2025, 1, 1) + timedelta(days=i), "CalendarMonth": "2025-01" if i < 31 else "2025-02"} for i in range(59)]
    source = 'DATATABLE("DateKey", INTEGER, "Date", DATETIME, "CalendarMonth", STRING, {' + ",".join("{" + str(row["DateKey"]) + ',dt"' + row["Date"].isoformat() + '","' + row["CalendarMonth"] + '"}' for row in dates) + "})"
    database["model"]["tables"][0]["partitions"] = [{"name": "Date", "mode": "import", "source": {"type": "calculated", "expression": source}}]
    database["model"]["tables"][0]["columns"][1]["isKey"] = True
    sales = [[1,32,10],[2,33,20],[32,32,30],[9999,9999,5]]
    source = 'DATATABLE("OrderDateKey", INTEGER, "ShipDateKey", INTEGER, "SalesAmount", CURRENCY, {{1,32,10},{2,33,20},{32,32,30},{9999,9999,5}})'
    database["model"]["tables"][1]["partitions"] = [{"name": "FactSales", "mode": "import", "source": {"type": "calculated", "expression": source}}]
    for table in database["model"]["tables"]:
        for column in table["columns"]:
            column.update(type="calculatedTableColumn", sourceColumn="[" + column["name"] + "]")
    alternate = deepcopy(database["model"]["tables"][0])
    alternate.update(name="AlternateDate", lineageTag="table-alternate-date")
    for column in alternate["columns"]: column["lineageTag"] = "alternate-" + column["lineageTag"]
    database["model"]["tables"].append(alternate)
    database["model"]["relationships"].append({"name": "relationship-alternate-ship", "fromTable": "FactSales", "fromColumn": "ShipDateKey", "toTable": "AlternateDate", "toColumn": "DateKey", "isActive": False})
    database["model"]["tables"][1]["measures"].append({"name": "Explicit Ship Sales", "expression": "CALCULATE([Sales Amount], USERELATIONSHIP(FactSales[ShipDateKey], AlternateDate[DateKey]))", "lineageTag": "measure-explicit-ship"})
    database["model"].pop("defaultPowerBIDataSourceVersion", None)
    path.write_text(json.dumps(database, indent=2), encoding="utf-8")
    return {"dates": [{**row, "Date": row["Date"].isoformat()} for row in dates], "sales": sales}

def probe():
    with tempfile.TemporaryDirectory(prefix="guard-real-regression-") as temporary:
        root = Path(temporary) / "source"
        data = frozen_fixture(root)
        def git(*arguments):
            return subprocess.run(["git", "-C", str(root), *arguments], capture_output=True, text=True, check=True).stdout.strip()
        git("init"); git("config", "user.name", "PBIBrain proof"); git("config", "user.email", "proof@localhost")
        git("add", "."); git("commit", "-m", "Sealed literal baseline")
        guard = ChangeGuard(root, Path(temporary) / "trusted", "live-proof", policy=Policy(retain_results=True))
        snapshot = guard.capture_baseline()
        assert snapshot.to_dict()["completeness"]["status"] == "COMPLETE", snapshot.to_dict()["completeness"]
        contract = proposal(snapshot)
        objects = snapshot.to_dict()["analysis"]["objects"]
        relationship = next(value for value in objects.values() if value["object_type"] == "RELATIONSHIP" and value["properties"]["name"] == "relationship-sales")
        contract["targets"] = [{"object_id": relationship["object_id"], "object_type": "RELATIONSHIP"}]
        contract["allowed_mutations"][0].update(object_id=relationship["object_id"], expected_before=relationship["properties"]["from_column_id"])
        effect_targets = [key for key, value in objects.items() if value["object_type"] in {"MEASURE", "VISUAL", "PAGE", "REPORT", "TABLE"}]
        contract["behavior"] = {"permitted_effects": [{"category": "DATE_FILTER_BEHAVIOR", "targets": effect_targets}], "invariants": [{"id": "grand-total", "assertion": "PRESERVE"}]}
        state = guard.prepare_change(contract)
        operation = state["operation_id"]
        state = guard.authorize(operation, "CONTRACT")
        candidate = Path(state["candidate_root"])
        executable = Path(sys._base_executable).resolve()
        script = 'import json,pathlib; p=pathlib.Path("Sales.SemanticModel/model.bim"); d=json.loads(p.read_text()); d["model"]["relationships"][0]["fromColumn"]="ShipDateKey"; p.write_text(json.dumps(d,indent=2),encoding="utf-8")'
        guard.run_agent(operation, WindowsAppContainer((executable.parent,)), [str(executable), "-I", "-c", script])
        guard.validate_candidate(operation)
        review = guard.review(operation)["verification"]
        assert all(review[gate]["status"] == "PASSED" for gate in ("security", "source", "scope", "static", "baseline")), review
        candidate_snapshot = Snapshot.from_dict(guard.store.load(operation + "/candidate.json"))
        context = ExecutionContext(None, None, "en-US", None)
        with LocalTestInstance(ENGINE) as instance:
            before = LocalAnalysisServices(instance, root, snapshot, context)
            after = LocalAnalysisServices(instance, candidate, candidate_snapshot, context)
            context = LocalAnalysisServices.freeze_literal_pair(before, after)
            names = {node["id"]: node["name"] for node in snapshot.to_dict()["analysis"]["graph"]["nodes"]}
            ids = {(value["object_type"], value["properties"].get("name", names.get(key))): key for key, value in objects.items()}
            sales = ids["MEASURE", "Sales Amount"]
            ytd = ids["MEASURE", "Sales YTD"]
            explicit = ids["MEASURE", "Explicit Ship Sales"]
            monthly = 'EVALUATE SUMMARIZECOLUMNS(\'Date\'[CalendarMonth], "Sales", [Sales Amount])'
            def expected(columns, rows):
                return {"columns": [{"name": name, "type": datatype} for name, datatype in columns], "rows": rows}
            def decimal(value): return {"$decimal": str(value)}
            baseline_monthly = expected([("Date[CalendarMonth]", "String"), ("[Sales]", "Decimal")], [[None, decimal(5)], ["2025-01", decimal(30)], ["2025-02", decimal(30)]])
            candidate_monthly = expected([("Date[CalendarMonth]", "String"), ("[Sales]", "Decimal")], [[None, decimal(5)], ["2025-02", decimal(60)]])
            assert compare_results(before.execute_readonly(monthly), baseline_monthly, "SET_EQUIVALENCE")["status"] == "PASSED", canonical_result(before.execute_readonly(monthly))
            assert compare_results(after.execute_readonly(monthly), candidate_monthly, "SET_EQUIVALENCE")["status"] == "PASSED", canonical_result(after.execute_readonly(monthly))
            tests = []
            def add(category, query, targets, mode="EXACT", comparison=None, invariants=()):
                paths = tuple(item["path_id"] for item in review["impact"]["impact_paths"] if item["object_id"] in targets)
                tests.append(RegressionTest(category, tuple(targets), query, mode, json.dumps(comparison or {}), category=category, covered_path_ids=paths, invariant_ids=invariants))
            add("unfiltered_total", 'EVALUATE ROW("Sales", [Sales Amount])', [sales], invariants=("grand-total",))
            # Absolute value is independently checked in addition to equivalence.
            grand = canonical_result(before.execute_readonly('EVALUATE ROW("Sales", [Sales Amount])'))
            assert grand["rows"] == [[decimal(65)]], grand
            add("grouped_dimension_total", monthly, [sales, ids["TABLE", "Date"], ids["TABLE", "FactSales"]], "EXPECTED_CHANGE", {"expected_result": candidate_monthly, "expected_comparison_mode": "SET_EQUIVALENCE", "result_shape": {"allow_missing_rows": True}})
            add("affected_measure", 'EVALUATE ROW("Sales", [Sales Amount])', [sales])
            add("dependent_measure", 'EVALUATE ROW("YTD", [Sales YTD])', [sales, ytd])
            add("alternate_relationship", 'EVALUATE SUMMARIZECOLUMNS(AlternateDate[CalendarMonth], "Ship", [Explicit Ship Sales])', [sales, explicit, ids["TABLE", "AlternateDate"]], "SET_EQUIVALENCE")
            add("blank_unmatched_keys", 'EVALUATE ROW("Sales", CALCULATE([Sales Amount], FILTER(\'Date\', ISBLANK(\'Date\'[DateKey]))))', [sales])
            january = 'EVALUATE ROW("Sales", CALCULATE([Sales Amount], TREATAS({"2025-01"}, \'Date\'[CalendarMonth])))'
            assert canonical_result(before.execute_readonly(january))["rows"] == [[decimal(30)]]
            add("slicer_filter_context", january, [sales], "EXPECTED_CHANGE", {"expected_result": expected([("[Sales]", "Decimal")], [[None]])})
            add("time_intelligence", 'EVALUATE ROW("YTD", CALCULATE([Sales YTD], \'Date\'[Date] = DATE(2025,2,28)))', [sales, ytd])
            report_targets = [sales] + [key for key, value in objects.items() if value["object_type"] in {"VISUAL", "PAGE", "REPORT"}]
            add("report_bound_calculation", monthly, report_targets, "EXPECTED_CHANGE", {"expected_result": candidate_monthly, "expected_comparison_mode": "SET_EQUIVALENCE", "result_shape": {"allow_missing_rows": True}})
            for node in snapshot.to_dict()["analysis"]["graph"]["nodes"]:
                if node["type"] != "TABLE": continue
                columns = [field for field in snapshot.to_dict()["analysis"]["graph"]["nodes"] if field["type"] == "COLUMN" and field["properties"].get("table_id") == node["id"]]
                name = node["name"].replace("'", "''")
                query = "EVALUATE SELECTCOLUMNS(ALLNOBLANKROW('" + name + "')," + ",".join(json.dumps(field["name"]) + ", '" + name + "'[" + field["name"].replace("]", "]]") + "]" for field in columns) + ")"
                add("preserve_fields_" + node["name"], query, [node["id"], *[field["id"] for field in columns]], "SET_EQUIVALENCE")
            state = guard.execute_regression_plan(operation, tests, before, after, context, context)
            runtime = guard.review(operation)["verification"]["runtime"]
            assert runtime["certified"], {"status": runtime["status"], "binding": runtime["runtime_binding_verified"], "uncovered": [{"object": names.get(path["object_id"]), "category": path["category"]} for path in review["impact"]["impact_paths"] if path["path_id"] in runtime["uncovered_impact_paths"]], "tests": [{"test": row["test_id"], "error": row.get("error"), "assertions": row.get("assertions"), "coverage": row.get("query_target_coverage")} for row in runtime["results"] if row["status"] != "PASSED"]}
            assert state["state"] == "APPROVAL_REQUIRED", state
            assert state["decision"]["approval_reasons"] == ["HIGH_RISK_PROMOTION"], state
            # Explicit user instruction authorizes promotion of this disposable
            # acceptance fixture after successful proof. No user model is used.
            guard.authorize(operation, "HIGH_RISK_PROMOTION")
            guard.authorize(operation, "PROMOTE")
            promoted = guard.promote_candidate(operation, mode="git")
            assert promoted["state"] == "POST_PROMOTION_VERIFIED", promoted
            final = guard.review(operation)
            return {"proof_version": 1, "status": "PASSED", "kind": "REAL_DESKTOP_ENGINE", "scope": "SEALED_LITERAL_ACCEPTANCE_FIXTURE",
                "engine_version": before.load_evidence["engine_version"], "context": context.__dict__, "data_freeze": before.freeze_evidence,
                "permissions": [adapter.permission_evidence for adapter in (before, after)], "baseline_snapshot_id": snapshot.snapshot_id,
                "candidate_snapshot_id": candidate_snapshot.snapshot_id, "runtime": runtime, "policy_decision": promoted["decision"],
                "promotion_state": promoted["state"], "git_promotion": guard.store.load(operation + "/git-promotion.json"), "audit": guard.store.verify_integrity(operation)}

if __name__ == "__main__":
    result = probe()
    text = json.dumps(result, indent=2) + "\n"
    if len(sys.argv) == 2: Path(sys.argv[1]).write_text(text, encoding="utf-8")
    print(json.dumps({"status": result["status"], "engine_version": result["engine_version"], "tests": len(result["runtime"]["completed_tests"]), "covered_paths": len(result["runtime"]["covered_impact_paths"]), "promotion": result["promotion_state"], "audit_verified": result["audit"]["integrity_verified"]}))
