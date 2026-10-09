from __future__ import annotations

import json
from time import perf_counter
from typing import Any
from backend.snapshots.manifest import content_hash, utc_now
from backend.validation.powerbi import PowerBIValidationHook, ValidationQuery, ReadOnlyValidationAdapter
from .comparison import compare_results, canonical_result
from .query_coverage import query_targets
from .schema import RegressionTest, ExecutionContext


def execute_regression_plan(tests: list[RegressionTest], baseline_adapter: Any, candidate_adapter: Any,
                            before_context: ExecutionContext, after_context: ExecutionContext, *,
                            baseline_snapshot_id: str, candidate_snapshot_id: str, impact: dict[str, Any], retain_results: bool = False,
                            baseline_graph: dict | None = None, candidate_graph: dict | None = None, static_verified: bool = False) -> dict[str, Any]:
    started = perf_counter()
    if len({test.test_id for test in tests}) != len(tests):
        raise ValueError("Duplicate regression test IDs")
    required = [test for test in tests if test.required]
    paths = {item["path_id"] for item in impact.get("impact_paths", [])}
    executed, covered, tested, verified_invariants, failed_invariants, unexplained = [], set(), set(), set(), set(), []
    structural_paths = {item["path_id"] for item in impact.get("impact_paths", []) if item.get("impact_category") in {"DIRECT", "STRUCTURAL"} and item.get("object_type") in {"RELATIONSHIP", "COLUMN"}} if static_verified else set()
    covered.update(structural_paths)
    data_equivalent = before_context == after_context and before_context.data_frozen and bool(before_context.data_snapshot_id) and bool(before_context.processed_state_id)
    capabilities = [getattr(adapter, "capabilities", None) for adapter in (baseline_adapter, candidate_adapter)]
    bindings = [getattr(adapter, "binding", None) for adapter in (baseline_adapter, candidate_adapter)]
    binding_matches = all(binding and binding.matches(snapshot, context) for binding, snapshot, context in
                          zip(bindings, (baseline_snapshot_id, candidate_snapshot_id), (before_context, after_context)))
    can_execute = all(cap and cap.query_readonly_enforced for cap in capabilities)
    certifiable = data_equivalent and binding_matches and all(cap and cap.real_execution and cap.frozen_data and cap.typed_results and (before_context.role is None or cap.role_context) for cap in capabilities)
    # Canonical typed values cross the legacy JSON-safe evidence transport.
    # Decimal/date objects otherwise become untyped strings in that API.
    hooks = [PowerBIValidationHook(ReadOnlyValidationAdapter(lambda query, params, adapter=adapter: canonical_result(adapter.execute_readonly(query, params))), max_queries=max(1, len(tests))) for adapter in (baseline_adapter, candidate_adapter)]
    for test in tests:
        query_coverage = [query_targets(test.query, test.target_objects, graph) for graph in (baseline_graph, candidate_graph)]
        record = {"test_id": test.test_id, "query": test.query, "query_hash": content_hash(test.query), "baseline_snapshot_id": baseline_snapshot_id,
                  "candidate_snapshot_id": candidate_snapshot_id, "context": before_context.__dict__, "context_hash": before_context.context_hash,
                  "data_snapshot_id": before_context.data_snapshot_id, "backend": [cap.backend if cap else "UNAVAILABLE" for cap in capabilities],
                  "executed_at": utc_now(), "required": test.required, "target_objects": list(test.target_objects), "category": test.category,
                  "query_target_coverage": query_coverage, "evidence_class": "OBSERVED"}
        timer = perf_counter()
        if not can_execute:
            record.update(status="NOT_RUN", error="READ_ONLY_RUNTIME_UNAVAILABLE")
        elif not data_equivalent:
            record.update(status="INCONCLUSIVE", error="EXECUTION_CONTEXT_OR_DATA_NOT_EQUIVALENT")
        else:
            try:
                query = ValidationQuery(test.query, test.target_objects[0], name=test.test_id, params=json.loads(before_context.parameters_json))
                results = [hook.run(query)["result"] for hook in hooks]
                comparison = compare_results(results[0], results[1], test.mode, json.loads(test.comparison_json))
                normalized = [canonical_result(result) for result in results]
                record.update(comparison, before_result_hash=content_hash(normalized[0]), after_result_hash=content_hash(normalized[1]))
                if retain_results:
                    record.update(before_result=normalized[0], after_result=normalized[1])
                if comparison["status"] == "PASSED":
                    # Path coverage must be bound by trusted planning to targets;
                    # arbitrary path labels for unrelated objects are invalid.
                    valid_paths = {item["path_id"] for item in impact.get("impact_paths", []) if item["object_id"] in test.target_objects}
                    if set(test.covered_path_ids) - valid_paths:
                        record.update(status="FAILED", error="INVALID_COVERAGE_CLAIM")
                    elif test.mode not in {"SCHEMA_ONLY", "MONITOR"} and all(part["status"] == "PASSED" for part in query_coverage):
                        covered.update(set(test.covered_path_ids) & paths)
                        tested.update(test.target_objects)
                        if test.mode in {"EXACT", "NUMERIC_TOLERANCE", "PRESERVE_AGGREGATE", "SET_EQUIVALENCE"}:
                            verified_invariants.update(test.invariant_ids)
                if comparison["status"] == "FAILED":
                    failed_invariants.update(test.invariant_ids)
                if comparison["changed"] and test.mode in {"MONITOR", "SCHEMA_ONLY"}:
                    unexplained.append(test.test_id)
            except Exception as error:
                # Never persist credentials or raw transport errors.
                record.update(status="FAILED", error=type(error).__name__, comparison_error="QUERY_EXECUTION_OR_RESULT_FAILURE")
        record["duration_seconds"] = perf_counter() - timer
        if not retain_results:
            for assertion in record.get("assertions", []):
                for key in ("before", "after", "delta", "message"):
                    assertion.pop(key, None)
        record["result_values_retained"] = retain_results
        executed.append(record)
    completed = [item for item in executed if item["status"] == "PASSED"]
    failed = [item for item in executed if item["status"] == "FAILED"]
    inconclusive = [item for item in executed if item["status"] in {"NOT_RUN", "INCONCLUSIVE"}]
    required_ids = {test.test_id for test in required}
    completed_ids = {item["test_id"] for item in completed}
    required_categories = {item["category"] for item in impact.get("required_tests", []) if item.get("required")}
    completed_categories = {item["category"] for item in completed if item["required"]}
    missing = sorted((required_ids - completed_ids) | (required_categories - completed_categories))
    uncovered = sorted(paths - covered)
    queries_verified = all(all(part["status"] == "PASSED" for part in item["query_target_coverage"]) for item in executed if item["required"])
    frozen_rechecked = all(not hasattr(adapter, "verify_frozen_data") or adapter.verify_frozen_data() for adapter in (baseline_adapter, candidate_adapter))
    certifiable = certifiable and queries_verified and frozen_rechecked
    status = "FAILED" if any(item["test_id"] in required_ids for item in failed) else "NOT_RUN" if not executed or not can_execute else "INCONCLUSIVE" if missing or uncovered or not certifiable else "PASSED"
    result = {"regression_version": 1, "status": status, "certified": status == "PASSED" and certifiable,
              "data_equivalent": data_equivalent, "runtime_binding_verified": bool(binding_matches), "results": executed, "impacted_objects": impact.get("impacted_objects", []),
              "tested_objects": sorted(tested), "untested_objects": sorted(set(impact.get("impacted_objects", [])) - tested),
              "covered_impact_paths": sorted(covered), "uncovered_impact_paths": uncovered, "required_tests": sorted(required_ids),
              "structurally_verified_paths": sorted(structural_paths), "frozen_data_rechecked": frozen_rechecked,
              "completed_tests": sorted(completed_ids), "failed_tests": [item["test_id"] for item in failed], "inconclusive_tests": [item["test_id"] for item in inconclusive],
              "missing_required_tests": missing, "verified_invariants": sorted(verified_invariants), "violated_invariants": sorted(failed_invariants),
              "unexplained_differences": unexplained, "duration_seconds": perf_counter() - started}
    result["evidence_hash"] = content_hash(result)
    return result
