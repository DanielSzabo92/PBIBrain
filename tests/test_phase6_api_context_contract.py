"""Phase 6 Brain API and context compiler contracts.

These tests use the canonical graph as the input boundary.  They do not
prescribe Ladybug queries or a particular context implementation.
"""

from __future__ import annotations

from collections.abc import Mapping
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, Iterable

from backend.api.app import BrainAPI
from backend.graph.loader import build_fact_graph
from backend.graph.repository import GraphRepository

from tests.fixtures.phase3_sources import (
    COL_NAMING_ONLY,
    MEASURE_BASE,
    MEASURE_NET,
    TABLE_NAMING_ONLY,
    semantic_model_source,
    semantic_report_source,
)


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    for name in ("to_dict", "as_dict", "model_dump", "dict"):
        method = getattr(value, name, None)
        if callable(method):
            converted = method()
            if isinstance(converted, Mapping):
                return dict(converted)
    try:
        return dict(vars(value))
    except TypeError:
        return {}


def _records(value: Any, *keys: str) -> list[Any]:
    """Read list-like API payloads without coupling tests to a container."""

    if value is None:
        return []
    if isinstance(value, (list, tuple, set, frozenset)):
        return list(value)
    if isinstance(value, Mapping):
        if "id" in value or "type" in value:
            return [dict(value)]
        for key in keys or ("items", "records", "objects", "nodes", "results", "data"):
            if key in value:
                return _records(value[key])
        return []
    for key in keys or ("items", "records", "objects", "nodes", "results", "data"):
        child = getattr(value, key, None)
        if child is not None:
            return _records(child)
    return [value]


def _ids(value: Any) -> set[str]:
    result: set[str] = set()
    for item in _records(value):
        if isinstance(item, str):
            result.add(item)
            continue
        converted = _mapping(item)
        if converted.get("id") is not None:
            result.add(str(converted["id"]))
    return result


def _path_ids(value: Any) -> list[str]:
    if isinstance(value, Mapping):
        for key in ("path", "nodes", "objects", "items", "results"):
            if key in value:
                return _path_ids(value[key])
        if value.get("id") is not None:
            return [str(value["id"])]
        return []
    if isinstance(value, (list, tuple)):
        result: list[str] = []
        for item in value:
            result.extend(_path_ids(item))
        return result
    if isinstance(value, str):
        return [value]
    converted = _mapping(value)
    return [str(converted["id"])] if converted.get("id") is not None else []


def _contains_key(value: Any, key: str) -> bool:
    if isinstance(value, Mapping):
        return key in value or any(_contains_key(child, key) for child in value.values())
    if isinstance(value, (list, tuple, set, frozenset)):
        return any(_contains_key(child, key) for child in value)
    return False


def _edge_records(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, Mapping):
        result: list[dict[str, Any]] = []
        if value.get("from_id") is not None and value.get("to_id") is not None:
            result.append(dict(value))
        for child in value.values():
            result.extend(_edge_records(child))
        return result
    if isinstance(value, (list, tuple, set, frozenset)):
        result = []
        for child in value:
            result.extend(_edge_records(child))
        return result
    return []


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


class Phase6BrainAPIContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        self.repository = GraphRepository(use_native=False)
        graph = build_fact_graph(
            semantic_model_source(),
            semantic_report_source(),
            analyze_dax=True,
        )
        self.repository.replace(graph.nodes, graph.edges)
        self.api = BrainAPI(self.repository, overrides_path=root / "overrides.json")
        self.measure_id = next(node.id for node in graph.nodes if node.source_id == MEASURE_NET)
        self.base_id = next(node.id for node in graph.nodes if node.source_id == MEASURE_BASE)
        self.naming_table_id = next(node.id for node in graph.nodes if node.source_id == TABLE_NAMING_ONLY)
        self.naming_column_id = next(node.id for node in graph.nodes if node.source_id == COL_NAMING_ONLY)
        self.visual_id = next(node.id for node in graph.nodes if node.type == "VISUAL")
        self.page_id = next(node.id for node in graph.nodes if node.type == "PAGE")
        self.report_id = next(node.id for node in graph.nodes if node.type == "REPORT")
        self.model_id = next(node.id for node in graph.nodes if node.type == "MODEL")
        self.visual_column_id = next(
            edge.to_id
            for edge in graph.edges
            if edge.from_id == self.visual_id
            and edge.type == "USES"
            and next(node for node in graph.nodes if node.id == edge.to_id).type == "COLUMN"
        )

    def tearDown(self) -> None:
        self.repository.close()
        self.tempdir.cleanup()

    def test_facade_exposes_stable_brain_operations(self):
        required = {
            "search_objects",
            "get_object",
            "get_neighbors",
            "get_dependencies",
            "get_dependents",
            "get_usage",
            "get_semantics",
            "get_context",
            "find_path",
            "validate_selection",
        }
        missing = sorted(name for name in required if not callable(getattr(self.api, name, None)))
        self.assertFalse(missing, f"Brain API operations missing: {missing}")

    def test_search_and_get_object_use_canonical_ids(self):
        matches = self.api.search_objects("booked revenue")
        match_ids = _ids(matches)
        self.assertIn(self.measure_id, match_ids, matches)

        item = _mapping(self.api.get_object(self.measure_id))
        self.assertEqual(item.get("id"), self.measure_id)
        for key in ("type", "name", "model_id", "source_id", "status"):
            self.assertIn(key, item)

    def test_dependencies_and_dependents_are_directional(self):
        outgoing = _ids(self.api.get_neighbors(self.measure_id, ["DEPENDS_ON"], direction="out"))
        incoming = _ids(self.api.get_neighbors(self.base_id, ["DEPENDS_ON"], direction="in"))
        self.assertIn(self.base_id, outgoing)
        self.assertIn(self.measure_id, incoming)
        self.assertIn(self.base_id, _ids(self.api.get_dependencies(self.measure_id)))
        self.assertIn(self.measure_id, _ids(self.api.get_dependents(self.base_id)))

    def test_usage_and_semantics_are_targeted(self):
        usage = _records(self.api.get_usage(self.measure_id))
        self.assertTrue(usage, "measure report usage missing")
        self.assertTrue(
            any("visual" in str(_mapping(item).get("id", "")).casefold() for item in usage),
            usage,
        )

        semantics = _records(self.api.get_semantics(self.measure_id), "semantics", "items", "records")
        semantic_blob = _json(semantics).casefold()
        self.assertTrue(semantics, "measure semantic records missing")
        self.assertIn("description", semantic_blob)
        self.assertTrue("inferred" in semantic_blob or "candidate" in semantic_blob, semantic_blob)
        self.assertIn("source", semantic_blob)
        self.assertIn("confidence", semantic_blob)
        self.assertIn("evidence", semantic_blob)

    def test_find_path_returns_ordered_canonical_nodes(self):
        path = _path_ids(self.api.find_path(self.measure_id, self.base_id))
        self.assertGreaterEqual(len(path), 2, path)
        self.assertEqual(path[0], self.measure_id)
        self.assertEqual(path[-1], self.base_id)

    def test_validate_selection_reports_valid_and_invalid_inputs(self):
        valid = self.api.validate_selection([self.measure_id, self.base_id])
        valid_data = _mapping(valid)
        valid_flags = [valid_data[key] for key in ("valid", "is_valid", "ok") if key in valid_data]
        if valid_flags:
            self.assertTrue(any(bool(flag) for flag in valid_flags), valid)
        else:
            self.assertNotRegex(_json(valid).casefold(), r"\b(blocking|invalid|error)\b")

        missing_id = f"{self.measure_id}/missing"
        invalid = self.api.validate_selection([self.measure_id, missing_id])
        invalid_data = _mapping(invalid)
        invalid_flags = [invalid_data[key] for key in ("valid", "is_valid", "ok") if key in invalid_data]
        if invalid_flags:
            self.assertFalse(all(bool(flag) for flag in invalid_flags), invalid)
        invalid_blob = _json(invalid).casefold()
        self.assertIn("missing", invalid_blob)

    def test_context_has_canonical_sections_and_scope(self):
        context = _mapping(self.api.get_context(self.measure_id, task="lineage"))
        required = {
            "target",
            "scope",
            "semantics",
            "relationships",
            "dependencies",
            "controls",
            "usage",
            "constraints",
            "evidence",
            "confidence",
            "warnings",
        }
        self.assertTrue(required.issubset(context), sorted(required - set(context)))
        target = _mapping(context["target"])
        self.assertEqual(target.get("id"), self.measure_id)
        scope = _mapping(context["scope"])
        self.assertIn("model_ids", scope)
        self.assertIn("report_ids", scope)
        self.assertIn("model:semantic-model-001", {str(value) for value in scope["model_ids"]})

    def test_context_preserves_semantic_provenance_status_confidence_and_evidence(self):
        context = _mapping(self.api.get_context(self.measure_id, task="semantics"))
        semantics = _records(context.get("semantics"), "items", "records")
        self.assertTrue(semantics, context)
        candidate_items = [
            item
            for item in semantics
            if "candidate" in _json(item).casefold() or "inferred" in _json(item).casefold()
        ]
        self.assertTrue(candidate_items, semantics)
        for item in candidate_items:
            self.assertTrue(_contains_key(item, "source"), item)
            self.assertTrue(_contains_key(item, "confidence"), item)
            self.assertTrue(_contains_key(item, "status"), item)
            self.assertTrue(_contains_key(item, "evidence"), item)
        self.assertIn("description", _json(context).casefold())

    def test_context_is_relevant_and_excludes_unrelated_model_branches(self):
        context = _mapping(self.api.get_context(self.measure_id, task="lineage"))
        blob = _json(context)
        self.assertIn(self.measure_id, blob)
        self.assertIn(self.base_id, blob)
        self.assertNotIn(self.naming_table_id, blob)
        self.assertNotIn(self.naming_column_id, blob)
        self.assertLess(len(blob), len(_json(self.repository.all_nodes())))

    def test_context_task_argument_is_supported_for_usage_scope(self):
        context = _mapping(self.api.get_context(self.measure_id, task="usage"))
        blob = _json(context).casefold()
        self.assertIn(self.measure_id.casefold(), blob)
        self.assertTrue(_records(context.get("usage"), "items", "records"), context)

    def test_visual_lineage_context_contains_bindings_and_page_report_model_ancestry(self):
        context = _mapping(self.api.get_context(self.visual_id, task="lineage"))
        edges = _edge_records(context)
        uses = [
            edge
            for edge in edges
            if edge.get("type") == "USES" and edge.get("from_id") == self.visual_id
        ]
        self.assertTrue(uses, context)
        self.assertEqual(
            {edge.get("to_id") for edge in uses},
            {self.measure_id, self.visual_column_id},
        )

        blob = _json(context)
        for identifier in (self.visual_id, self.page_id, self.report_id, self.model_id):
            self.assertIn(identifier, blob)
        self.assertTrue(
            any(
                edge.get("type") == "CONTAINS"
                and edge.get("from_id") == self.page_id
                and edge.get("to_id") == self.visual_id
                for edge in edges
            ),
            edges,
        )
        self.assertTrue(
            any(
                edge.get("type") == "CONTAINS"
                and edge.get("from_id") == self.report_id
                and edge.get("to_id") == self.page_id
                for edge in edges
            ),
            edges,
        )
        self.assertTrue(
            any(
                edge.get("type") == "USES_MODEL"
                and edge.get("from_id") == self.report_id
                and edge.get("to_id") == self.model_id
                for edge in edges
            ),
            edges,
        )

    def test_api_outputs_are_deterministic(self):
        other_repository = GraphRepository(use_native=False)
        other_tempdir = tempfile.TemporaryDirectory()
        try:
            graph = build_fact_graph(
                semantic_model_source(),
                semantic_report_source(),
                analyze_dax=True,
            )
            other_repository.replace(graph.nodes, graph.edges)
            other_api = BrainAPI(
                other_repository,
                overrides_path=Path(other_tempdir.name) / "overrides.json",
            )
            calls = (
                lambda api: api.search_objects("booked revenue"),
                lambda api: api.get_object(self.measure_id),
                lambda api: api.get_neighbors(self.measure_id, ["DEPENDS_ON"], direction="out"),
                lambda api: api.get_dependencies(self.measure_id),
                lambda api: api.get_dependents(self.base_id),
                lambda api: api.get_usage(self.measure_id),
                lambda api: api.get_semantics(self.measure_id),
                lambda api: api.get_context(self.measure_id, task="lineage"),
                lambda api: api.find_path(self.measure_id, self.base_id),
                lambda api: api.validate_selection([self.measure_id, self.base_id]),
            )
            for call in calls:
                self.assertEqual(_json(call(self.api)), _json(call(other_api)))
        finally:
            other_repository.close()
            other_tempdir.cleanup()

    def test_public_facade_does_not_expose_unrestricted_graph_query(self):
        self.assertFalse(callable(getattr(self.api, "query_graph", None)))
        self.assertFalse(callable(getattr(self.api, "execute", None)))


if __name__ == "__main__":
    unittest.main()
