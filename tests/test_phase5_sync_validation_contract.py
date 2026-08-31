"""Phase 5 incremental-sync and validation acceptance tests.

These tests use only canonical graph objects and small source variants.  They
do not prescribe a persistence implementation; the public sync/validation
seams may be exposed from either the scanner package or a dedicated package.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
import importlib
import inspect
import json
from pathlib import Path
import tempfile
import unittest
from typing import Any, Callable, Mapping

from backend.api.review import OverrideStore
from backend.graph.loader import build_fact_graph
from backend.graph.repository import GraphRepository
from backend.graph.schema import Edge, Node
from backend.validation import (
    ValidationResult,
    validate,
    validate_dax_dependencies,
    validate_graph_integrity,
    validate_override_integrity,
    validate_reference_integrity,
    validate_semantic_integrity,
)

from tests.fixtures.phase5_sources import (
    COL_AMOUNT,
    MEASURE_BASE,
    MEASURE_FORECAST,
    MEASURE_LEGACY,
    MEASURE_NET,
    MODEL_ID,
    phase5_changed_source,
    phase5_deleted_source,
    phase5_model_source,
    phase5_new_source,
    phase5_renamed_source,
)


_STATUSES = {"UNCHANGED", "CHANGED", "NEW", "DELETED"}


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if is_dataclass(value):
        return dict(asdict(value))
    for name in ("to_dict", "as_dict"):
        method = getattr(value, name, None)
        if callable(method):
            converted = method()
            if isinstance(converted, Mapping):
                return dict(converted)
    try:
        return dict(vars(value))
    except TypeError:
        return {}


def _walk(value: Any):
    if isinstance(value, Mapping):
        yield dict(value)
        for child in value.values():
            yield from _walk(child)
    elif is_dataclass(value):
        yield from _walk(asdict(value))
    elif isinstance(value, (list, tuple, set, frozenset)):
        for child in value:
            yield from _walk(child)


def _status_records(value: Any) -> list[dict[str, Any]]:
    """Find status records without coupling tests to a result dataclass."""

    records = []
    for item in _walk(value):
        status = str(item.get("status", item.get("state", ""))).upper()
        if status in _STATUSES:
            records.append(item)
    return records


def _status_for(value: Any, marker: str) -> str:
    marker = str(marker).casefold()
    records = [
        item
        for item in _status_records(value)
        if marker in json.dumps(item, sort_keys=True, default=str).casefold()
    ]
    if not records:
        raise AssertionError(f"sync result has no status record for {marker}: {_mapping(value)}")
    return str(records[0].get("status", records[0].get("state"))).upper()


def _status_map(value: Any) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in _status_records(value):
        marker = item.get("source_id") or item.get("object_id") or item.get("object") or item.get("id")
        if marker:
            result[str(marker)] = str(item.get("status", item.get("state"))).upper()
    return result


def _call_with_supported(callable_value: Callable[..., Any], **values: Any) -> Any:
    """Call a seam while allowing equivalent keyword names."""

    try:
        signature = inspect.signature(callable_value)
    except (TypeError, ValueError):
        return callable_value(*values.values())
    accepts_kwargs = any(param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values())
    kwargs = {
        name: value
        for name, value in values.items()
        if value is not None and (accepts_kwargs or name in signature.parameters)
    }
    return callable_value(**kwargs)


def _make_incremental_sync(repository: GraphRepository, root: Path, overrides: OverrideStore | None = None) -> Any:
    modules = (
        "backend.scanner.sync",
        "backend.scanner.incremental",
        "backend.scanner.synchronization",
        "backend.sync",
    )
    class_names = ("IncrementalScanner", "IncrementalSync", "SyncEngine", "IncrementalSynchronizer")
    function_names = ("sync", "synchronize", "incremental_scan", "scan_incremental")
    values = {
        "repository": repository,
        "graph_repository": repository,
        "identity_path": root / "identity.json",
        "state_path": root / "sync-state.json",
        "snapshot_path": root / "sync-state.json",
        "overrides_path": overrides.path if overrides else root / "overrides.json",
        "override_store": overrides,
        "store": overrides,
    }
    errors: list[str] = []
    for module_name in modules:
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            if exc.name == module_name:
                continue
            raise
        for class_name in class_names:
            cls = getattr(module, class_name, None)
            if not inspect.isclass(cls):
                continue
            try:
                return _call_with_supported(cls, **values)
            except TypeError as exc:
                errors.append(f"{module_name}.{class_name}: {exc}")
        for function_name in function_names:
            function = getattr(module, function_name, None)
            if not callable(function):
                continue

            def invoke(source: Mapping[str, Any], function: Callable[..., Any] = function) -> Any:
                return _invoke_sync_callable(function, source, repository, values)

            return invoke
    raise AssertionError("Phase 5 incremental sync seam missing; expected backend.scanner.sync or equivalent")


def _invoke_sync_callable(callable_value: Callable[..., Any], source: Mapping[str, Any], repository: GraphRepository, values: Mapping[str, Any]) -> Any:
    method = callable_value
    for name in ("sync", "synchronize", "scan", "run", "process"):
        candidate = getattr(callable_value, name, None)
        if callable(candidate):
            method = candidate
            break
    try:
        signature = inspect.signature(method)
    except (TypeError, ValueError):
        return method(source)
    parameters = list(signature.parameters.values())
    kwargs: dict[str, Any] = {}
    source_names = {"source", "model_source", "model", "metadata", "model_metadata"}
    for parameter in parameters:
        if parameter.name in source_names:
            kwargs[parameter.name] = source
        elif parameter.name in values and values[parameter.name] is not None:
            kwargs[parameter.name] = values[parameter.name]
    if kwargs:
        return method(**kwargs)
    if any(parameter.kind in {inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD} for parameter in parameters):
        return method(source)
    return method()


def _sync(engine: Any, source: Mapping[str, Any]) -> Any:
    return _invoke_sync_callable(engine, source, getattr(engine, "repository", None), {})


def _issues(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, ValidationResult):
        return [item.to_dict() for item in value.issues]
    data = _mapping(value)
    issues = data.get("issues", data.get("findings", data.get("warnings", [])))
    if isinstance(issues, Mapping):
        issues = list(issues.values())
    return [_mapping(item) for item in (issues or [])]


def _result_state(value: Any) -> str:
    data = _mapping(value)
    state = data.get("state", data.get("status"))
    if state is None:
        state = getattr(value, "state", getattr(value, "status", None))
    return str(state or "").casefold()


class Phase5IncrementalSyncContractTests(unittest.TestCase):
    def test_sync_exposes_new_unchanged_changed_and_deleted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = GraphRepository(use_native=False)
            try:
                engine = _make_incremental_sync(repository, root)
                self.assertEqual(_status_for(_sync(engine, phase5_model_source()), MEASURE_NET), "NEW")
                self.assertEqual(_status_for(_sync(engine, phase5_model_source()), MEASURE_NET), "UNCHANGED")
                self.assertEqual(_status_for(_sync(engine, phase5_changed_source()), MEASURE_NET), "CHANGED")
                self.assertEqual(_status_for(_sync(engine, phase5_new_source()), MEASURE_FORECAST), "NEW")
                self.assertEqual(_status_for(_sync(engine, phase5_deleted_source()), MEASURE_LEGACY), "DELETED")
            finally:
                repository.close()

    def test_rename_keeps_stable_id_and_updates_display_name(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = GraphRepository(use_native=False)
            try:
                engine = _make_incremental_sync(repository, root)
                _sync(engine, phase5_model_source())
                before = next(node for node in repository.all_nodes() if node.source_id == MEASURE_NET)
                _sync(engine, phase5_renamed_source())
                after = next(node for node in repository.all_nodes() if node.source_id == MEASURE_NET)
                self.assertEqual(before.id, after.id)
                self.assertEqual(after.name, "Revenue After Discounts")
            finally:
                repository.close()

    def test_changed_expression_reanalyzes_only_affected_dax_and_keeps_fact_edges(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = GraphRepository(use_native=False)
            try:
                engine = _make_incremental_sync(repository, root)
                _sync(engine, phase5_model_source())
                before = next(node for node in repository.all_nodes() if node.source_id == MEASURE_NET)
                before_ast = before.properties.get("dax_ast")
                base_before = next(node for node in repository.all_nodes() if node.source_id == MEASURE_BASE)
                base_before_ast = base_before.properties.get("dax_ast")
                result = _sync(engine, phase5_changed_source())
                after = next(node for node in repository.all_nodes() if node.source_id == MEASURE_NET)
                self.assertEqual(_status_for(result, MEASURE_NET), "CHANGED")
                self.assertNotEqual(before_ast, after.properties.get("dax_ast"))
                base = next(node for node in repository.all_nodes() if node.source_id == MEASURE_BASE)
                self.assertEqual(base_before_ast, base.properties.get("dax_ast"))
                affected_ids = _mapping(result).get("affected_ids", [])
                self.assertIn(after.id, affected_ids)
                self.assertTrue(
                    any(
                        edge.type == "DEPENDS_ON"
                        and edge.from_id == after.id
                        and edge.to_id == base.id
                        and edge.evidence_class == "FACT"
                        for edge in repository.all_edges()
                    )
                )
            finally:
                repository.close()

    def test_repeated_sync_is_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first_repo = GraphRepository(use_native=False)
            second_repo = GraphRepository(use_native=False)
            try:
                first = _make_incremental_sync(first_repo, root / "one")
                second = _make_incremental_sync(second_repo, root / "two")
                sources = (phase5_model_source(), phase5_changed_source(), phase5_new_source())
                first_results = [_status_map(_sync(first, source)) for source in sources]
                second_results = [_status_map(_sync(second, source)) for source in sources]
                self.assertEqual(first_results, second_results)
                self.assertEqual(
                    [node.to_dict() for node in first_repo.all_nodes()],
                    [node.to_dict() for node in second_repo.all_nodes()],
                )
                self.assertEqual(
                    [edge.to_dict() for edge in first_repo.all_edges()],
                    [edge.to_dict() for edge in second_repo.all_edges()],
                )
            finally:
                first_repo.close()
                second_repo.close()

    def test_override_reconciliation_preserves_known_override_and_flags_stale_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = GraphRepository(use_native=False)
            overrides = OverrideStore(root / "overrides.json")
            try:
                engine = _make_incremental_sync(repository, root, overrides)
                _sync(engine, phase5_model_source())
                legacy = next(node for node in repository.all_nodes() if node.source_id == MEASURE_LEGACY)
                overrides.put(legacy.id, "business_concept", "legacy revenue")
                _sync(engine, phase5_deleted_source())
                records = overrides.records()
                self.assertEqual(records[0]["value"], "legacy revenue")
                result = _sync(engine, phase5_deleted_source())
                serialized = json.dumps(result, sort_keys=True, default=str).casefold()
                self.assertIn("stale", serialized)
                self.assertIn(legacy.id.casefold(), serialized)
            finally:
                repository.close()


class Phase5ValidationContractTests(unittest.TestCase):
    def test_valid_graph_has_structural_validation_result(self):
        graph = build_fact_graph(phase5_model_source(), analyze_dax=True)
        result = validate(graph)
        self.assertIsInstance(result, ValidationResult)
        self.assertIn(_result_state(result), {"valid", "warning"})
        self.assertFalse(result.blocking)

    def test_validation_catches_dangling_reference_and_blocking_cycle(self):
        model_id = "model:validation"
        table_id = f"{model_id}/table:sales"
        missing = f"{table_id}/column:missing"
        nodes = [Node(model_id, "MODEL", "Validation"), Node(table_id, "TABLE", "Sales", model_id=model_id)]
        dangling = Edge(
            "edge:dangling",
            "REFERENCES",
            table_id,
            missing,
            source="model_metadata",
            evidence=["fixture"],
        )
        cycle_a = Edge("edge:cycle-a", "CONTAINS", model_id, table_id, source="model_metadata", evidence=["fixture"])
        cycle_b = Edge("edge:cycle-b", "CONTAINS", table_id, model_id, source="model_metadata", evidence=["fixture"])
        result = validate_graph_integrity(nodes, [dangling, cycle_a, cycle_b])
        issues = _issues(result)
        codes = {item.get("code", item.get("issue_type")) for item in issues}
        self.assertIn("dangling_edge_endpoint", codes)
        self.assertIn("containment_cycle", codes)
        self.assertTrue(any(item.get("severity") == "BLOCKING" for item in issues))
        self.assertFalse(result.valid)

    def test_validation_reports_orphans_and_broken_report_bindings(self):
        model_id = "model:report-validation"
        report_id = "report:report-validation"
        page_id = f"{report_id}/page:overview"
        visual_id = f"{page_id}/visual:sales"
        orphan_table = f"{model_id}/table:orphan"
        nodes = [
            Node(model_id, "MODEL", "Report validation"),
            Node(orphan_table, "TABLE", "Orphan", model_id=model_id),
            Node(report_id, "REPORT", "Report", model_id=model_id),
            Node(page_id, "PAGE", "Overview", model_id=model_id, report_id=report_id),
            Node(
                visual_id,
                "VISUAL",
                "Sales",
                model_id=model_id,
                report_id=report_id,
                properties={"parent_id": page_id, "field_ids": [f"{model_id}/column:missing"]},
            ),
        ]
        edges = [
            Edge("edge:report-page", "CONTAINS", report_id, page_id, source="report_metadata", evidence=["fixture"]),
            Edge("edge:page-visual", "CONTAINS", page_id, visual_id, source="report_metadata", evidence=["fixture"]),
        ]
        result = validate_graph_integrity(nodes, edges)
        issues = _issues(result)
        codes = {str(item.get("code", item.get("issue_type", ""))).casefold() for item in issues}
        self.assertTrue(any("orphan" in code for code in codes), issues)
        self.assertIn("missing_object_reference", codes)

    def test_validation_separates_reference_dax_semantic_and_override_classes(self):
        repository = GraphRepository(use_native=False)
        try:
            graph = build_fact_graph(phase5_model_source(), analyze_dax=True)
            broken = Edge(
                "edge:broken-dax",
                "DEPENDS_ON",
                next(node.id for node in graph.nodes if node.source_id == MEASURE_NET),
                "model:phase5-model-001/measure:missing",
                source="dax_analysis",
                evidence=[{"source": "dax_analysis", "ast_location": {"start_offset": 0}}],
            )
            repository.replace(graph.nodes, [*graph.edges, broken])
            dax_result = validate_dax_dependencies(repository)
            reference_result = validate_reference_integrity(repository)
            semantic_result = validate_semantic_integrity(repository)
            override_result = validate_override_integrity(repository, OverrideStore())
            self.assertTrue(any(item.get("code") == "broken_dax_dependency" for item in _issues(dax_result)))
            self.assertIsInstance(reference_result, ValidationResult)
            self.assertIsInstance(semantic_result, ValidationResult)
            self.assertIsInstance(override_result, ValidationResult)
            for result in (dax_result, reference_result, semantic_result, override_result):
                for issue in _issues(result):
                    self.assertIn(issue.get("severity"), {"INFO", "WARNING", "ERROR", "BLOCKING"})
        finally:
            repository.close()

    def test_validation_is_read_only(self):
        repository = GraphRepository(use_native=False)
        try:
            graph = build_fact_graph(phase5_model_source(), analyze_dax=True)
            repository.replace(graph.nodes, graph.edges)
            before_nodes = [node.to_dict() for node in repository.all_nodes()]
            before_edges = [edge.to_dict() for edge in repository.all_edges()]
            validate(repository)
            self.assertEqual(before_nodes, [node.to_dict() for node in repository.all_nodes()])
            self.assertEqual(before_edges, [edge.to_dict() for edge in repository.all_edges()])
        finally:
            repository.close()

    def test_override_conflict_and_generated_fact_mutation_are_reviewable(self):
        repository = GraphRepository(use_native=False)
        try:
            graph = build_fact_graph(phase5_model_source(), analyze_dax=True)
            repository.replace(graph.nodes, graph.edges)
            target = next(node.id for node in graph.nodes if node.source_id == MEASURE_NET)
            records = [
                {"target": target, "property": "business_concept", "value": "net sales"},
                {"target": target, "property": "business_concept", "value": "net revenue"},
                {"target": target, "property": "name", "value": "Mutated fact"},
            ]
            result = validate_override_integrity(repository, records)
            issues = _issues(result)
            codes = {item.get("code", item.get("issue_type")) for item in issues}
            self.assertIn("duplicate_override", codes)
            self.assertIn("override_mutates_generated_fact", codes)
            self.assertTrue(any(item.get("severity") == "BLOCKING" for item in issues))
        finally:
            repository.close()


class Phase5PowerBIValidationHookTests(unittest.TestCase):
    def test_targeted_validation_hook_is_read_only_and_persists_evidence(self):
        from backend.validation import run_validation_query

        calls: list[tuple[str, Any]] = []

        def executor(query: str, params: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
            calls.append((query, params))
            self.assertNotRegex(query.upper(), r"\b(INSERT|UPDATE|DELETE|ALTER|CREATE|DROP)\b")
            return [{"Option": "LOCAL"}, {"Option": "USD"}]

        class ReadOnlyAdapter:
            def execute_readonly(self, query: str, params: Mapping[str, Any] | None = None) -> Any:
                return executor(query, params)

        adapter = ReadOnlyAdapter()
        result = run_validation_query(
            adapter,
            "EVALUATE VALUES('Display Options'[Option])",
            target_id="model:phase5-model-001/column:phase5-column-option",
            purpose="selector_options",
        )
        data = _mapping(result)
        serialized = json.dumps(result, sort_keys=True, default=str)
        self.assertEqual(len(calls), 1)
        self.assertIn("LOCAL", serialized)
        self.assertIn("USD", serialized)
        self.assertTrue(data.get("evidence") or getattr(result, "evidence", None))
        self.assertIn("selector_options", serialized)


class Phase5NoPhase6ContractTests(unittest.TestCase):
    def test_phase5_does_not_add_query_engine(self):
        self.assertFalse(Path("backend/query").exists(), "query engine is outside Phase 5")


if __name__ == "__main__":
    unittest.main()
