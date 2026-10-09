"""Synthetic PBIP benchmark using real TOM ingestion, not runtime acceptance."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from time import perf_counter
import tracemalloc
from backend.diff import compare_snapshots
from backend.impact.cache import SnapshotImpactCache
from backend.snapshots import capture_snapshot, source_manifest
from backend.snapshots.scan import scan_snapshot
from change_guard.workspace import create_candidate
from tests.guarded_fixture import reference_project


def run_case(label: str, count: int) -> dict:
    with tempfile.TemporaryDirectory(prefix="guard-benchmark-") as temporary:
        root = Path(temporary); source = root / "source"; candidate = root / "candidate"
        reference_project(source)
        file = source / "Sales.SemanticModel/model.bim"
        value = json.loads(file.read_text(encoding="utf-8"))
        for index in range(count):
            value["model"]["tables"][1]["measures"].append({"name": f"Sales {index:05}", "lineageTag": f"benchmark-{index:05}", "expression": "[Sales Amount] * 2"})
        file.write_text(json.dumps(value), encoding="utf-8")
        tracemalloc.start(); timer = perf_counter()
        before_analysis = scan_snapshot(source)
        before = capture_snapshot(source, "benchmark", identity_manifest=before_analysis["identity_manifest"], analysis=before_analysis)
        preflight = perf_counter() - timer
        objects = before_analysis["objects"]
        target = next(key for key, item in objects.items() if item["object_type"] == "RELATIONSHIP")
        ship = next(key for key, item in objects.items() if item["object_type"] == "COLUMN" and item["properties"]["name"] == "ShipDateKey")
        proposal = [{"object_id": target, "property": "from_column_id", "new_value": ship}]
        cache = SnapshotImpactCache(); timer = perf_counter()
        impact = cache.analyze(before, [target], proposal); traversal = perf_counter() - timer
        timer = perf_counter(); cached = cache.analyze(before, [target], proposal); cached_seconds = perf_counter() - timer
        assert cached["impact_report_id"] == impact["impact_report_id"]
        timer = perf_counter(); create_candidate(source, candidate, source_manifest(source)); preparation = perf_counter() - timer
        file = candidate / "Sales.SemanticModel/model.bim"; value = json.loads(file.read_text(encoding="utf-8"))
        value["model"]["relationships"][0]["fromColumn"] = "ShipDateKey"; file.write_text(json.dumps(value), encoding="utf-8")
        after_analysis = scan_snapshot(candidate, identities=before_analysis["identity_manifest"])
        after = capture_snapshot(candidate, "benchmark", identity_manifest=after_analysis["identity_manifest"], kind="CANDIDATE", analysis=after_analysis)
        timer = perf_counter(); diff = compare_snapshots(before, after, before_root=source, after_root=candidate); diff_seconds = perf_counter() - timer
        assert len(diff["property_changes"]) == 1 and not diff["unknown_differences"]
        _, peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
        return {"case": label, "fixture": "SYNTHETIC_PBIP_REAL_TOM", "additional_measures": count, "preflight_seconds": preflight,
                "graph_traversal_seconds": traversal, "cached_impact_seconds": cached_seconds, "semantic_diff_seconds": diff_seconds,
                "candidate_preparation_seconds": preparation, "peak_python_memory_bytes": peak, **{key: impact["metrics"][key] for key in ("nodes_examined", "edges_examined", "impacted_objects", "selected_tests")},
                "runtime_test_status": "NOT_RUN", "promotion_status": "NOT_RUN", "agent_input_tokens": 0, "agent_output_tokens": 0, "llm_calls": 0, "llm_cost": 0}


if __name__ == "__main__":
    output = {"benchmark_version": 1, "scope": "Synthetic 2-table PBIP projects; no Power BI numerical or production-scale acceptance", "results": [run_case(label, count) for label, count in (("small", 10), ("medium", 100), ("large", 1000))]}
    print(json.dumps(output, indent=2))
