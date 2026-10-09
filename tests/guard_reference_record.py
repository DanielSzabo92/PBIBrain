"""Reproduce the fixed static reference case; no execution or source promotion."""
import json
from pathlib import Path
import tempfile
from backend.diff import compare_snapshots
from backend.impact import analyze_impact
from backend.snapshots import capture_snapshot, source_manifest
from backend.snapshots.scan import scan_snapshot
from change_guard.contracts import authorize_contract, enforce_scope
from change_guard.workspace import create_candidate
from tests.guarded_fixture import reference_project
from tests.test_guarded_development import proposal


def reference_record():
    with tempfile.TemporaryDirectory(prefix="guard-reference-") as temporary:
        root = Path(temporary); source = root / "source"; candidate = root / "candidate"
        reference_project(source, report=True)
        analysis = scan_snapshot(source)
        baseline = capture_snapshot(source, "reference-sales", identity_manifest=analysis["identity_manifest"], analysis=analysis)
        contract = authorize_contract(proposal(baseline), "reference-human", "guard-policy-1", objects=analysis["objects"])
        create_candidate(source, candidate, source_manifest(source))
        path = candidate / "Sales.SemanticModel/model.bim"
        value = json.loads(path.read_text()); value["model"]["relationships"][0]["fromColumn"] = "ShipDateKey"
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        after_analysis = scan_snapshot(candidate, identities=analysis["identity_manifest"])
        after = capture_snapshot(candidate, "reference-sales", identity_manifest=after_analysis["identity_manifest"], kind="CANDIDATE", analysis=after_analysis)
        diff = compare_snapshots(baseline, after, before_root=source, after_root=candidate)
        targets = [item["object_id"] for item in contract.to_dict()["targets"]]
        changes = [{"object_id": item["object_id"], "property": item["property"], "new_value": item["expected_after"]} for item in contract.to_dict()["allowed_mutations"]]
        impact = analyze_impact(analysis["graph"], targets, changes, baseline_snapshot_id=baseline.snapshot_id, completeness=analysis["completeness"])
        names = {item["id"]: item["name"] for item in analysis["graph"]["nodes"]}
        return {"reference_version": 1, "baseline_snapshot_id": baseline.snapshot_id, "candidate_snapshot_id": after.snapshot_id,
                "differences": [{key: item[key] for key in ("object_id", "object_type", "property_path", "previous_value", "new_value", "classification")} for item in diff["object_changes"]],
                "scope_status": enforce_scope(contract, diff)["status"], "impact_names": sorted(names[item] for item in impact["impacted_objects"]),
                "impact_ids": impact["impacted_objects"], "required_test_categories": [item["category"] for item in impact["required_tests"]],
                "impact_completeness": impact["completeness"]["status"], "blocking_completeness": analysis["completeness"]["blocking"],
                "runtime_status": "NOT_RUN", "isolation_status": "NOT_RUN", "automatic_promotion_allowed": False}


if __name__ == "__main__":
    print(json.dumps(reference_record(), indent=2))
