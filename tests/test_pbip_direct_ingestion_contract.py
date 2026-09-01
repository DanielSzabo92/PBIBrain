"""Direct PBIP/PBIR ingestion contracts.

These tests deliberately provide only a file-backed PBIP project.  They do
not use Power BI Desktop, the Desktop Bridge CLI, a network connection, or a
pre-normalized JSON model.  The public seam under test is
``Scanner.scan(project_path)``; the CLI test exercises the same path through
``brain scan <project.pbip>`` with the repository replaced by the explicit
in-memory test double.
"""

from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.cli.main import main as cli_main
from backend.graph.repository import GraphRepository
from backend.scanner.pbip import read_pbip_project
from backend.scanner.pipeline import Scanner

from tests.fixtures.pbip_sources import (
    DATE_KEY_LINEAGE,
    GROSS_LINEAGE,
    MEASURE_GROSS,
    MEASURE_NET,
    MODEL_LINEAGE,
    NET_LINEAGE,
    PAGE_OVERVIEW,
    RELATIONSHIP_LINEAGE,
    SALES_LINEAGE,
    TABLE_DATE,
    TABLE_SALES,
    VISUAL_GROSS,
    VISUAL_SALES,
    write_pbip_project,
)


def _node_by_name(nodes, object_type: str, name: str):
    matches = [node for node in nodes if node.type == object_type and node.name == name]
    if len(matches) != 1:
        raise AssertionError(f"expected one {object_type} named {name!r}, got {matches!r}")
    return matches[0]


def _node_by_source(nodes, object_type: str, source_id: str):
    matches = [node for node in nodes if node.type == object_type and node.source_id == source_id]
    if len(matches) != 1:
        raise AssertionError(
            f"expected one {object_type} with source id {source_id!r}, got {matches!r}"
        )
    return matches[0]


def _status_map(sync_result) -> dict[str, str]:
    changes = getattr(sync_result, "changes", None)
    if changes is not None:
        records = getattr(changes, "records", None)
        if records is not None:
            return {str(record.id): str(record.status).upper() for record in records}
        by_status = getattr(changes, "by_status", None)
        if isinstance(by_status, dict):
            return {
                str(identifier): str(status).upper()
                for status, identifiers in by_status.items()
                for identifier in identifiers
            }
    payload = sync_result.to_dict() if hasattr(sync_result, "to_dict") else sync_result
    if isinstance(payload, dict):
        records = payload.get("change_records", [])
        return {
            str(record.get("id")): str(record.get("status", "")).upper()
            for record in records
            if isinstance(record, dict) and record.get("id")
        }
    return {}


def _native_ladybug_available() -> bool:
    try:
        with tempfile.TemporaryDirectory() as directory:
            repository = GraphRepository(Path(directory) / "probe.lbug")
            repository.close()
        return True
    except Exception:
        return False


class DirectPBIPIngestionContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.project = write_pbip_project(self.root / "fixture")
        self.repository = GraphRepository(use_native=False)
        self.scanner = Scanner(
            self.repository,
            identity_path=self.root / "identity.json",
        )

    def tearDown(self) -> None:
        self.repository.close()
        self.tempdir.cleanup()

    def test_scanner_scan_project_follows_pbip_artifacts_and_pbir_files(self):
        graph = self.scanner.scan(self.project)
        nodes = graph.nodes

        # The project contains no flat canonical JSON model.  A direct scan
        # must follow the semantic-model artifact and report artifact.
        self.assertGreaterEqual(len(nodes), 8, graph.to_dict())
        model = _node_by_source(nodes, "MODEL", MODEL_LINEAGE)
        sales = _node_by_source(nodes, "TABLE", SALES_LINEAGE)
        date = _node_by_name(nodes, "TABLE", TABLE_DATE)
        measure = _node_by_source(nodes, "MEASURE", NET_LINEAGE)
        report = _node_by_name(nodes, "REPORT", "Finance Report")
        page = _node_by_name(nodes, "PAGE", PAGE_OVERVIEW)
        visual = _node_by_name(nodes, "VISUAL", VISUAL_SALES)
        date_key = _node_by_source(nodes, "COLUMN", DATE_KEY_LINEAGE)

        self.assertEqual(model.type, "MODEL")
        self.assertEqual(sales.type, "TABLE")
        self.assertEqual(measure.name, MEASURE_NET)
        self.assertEqual(report.model_id, model.id)
        self.assertEqual(page.report_id, report.id)
        self.assertEqual(visual.report_id, report.id)

        edges = graph.edges
        self.assertTrue(
            any(
                edge.type == "USES_MODEL"
                and edge.from_id == report.id
                and edge.to_id == model.id
                for edge in edges
            ),
            edges,
        )
        used_ids = {
            edge.to_id
            for edge in edges
            if edge.type == "USES" and edge.from_id == visual.id
        }
        self.assertIn(measure.id, used_ids)
        self.assertIn(date_key.id, used_ids)

    def test_scanner_reads_dataset_model_bim_and_legacy_report_json(self):
        project = write_pbip_project(
            self.root / "dataset-fixture",
            model_format="tmsl",
            model_kind="dataset",
            report_format="legacy",
        )
        graph = self.scanner.scan(project)

        model = _node_by_source(graph.nodes, "MODEL", MODEL_LINEAGE)
        sales = _node_by_source(graph.nodes, "TABLE", SALES_LINEAGE)
        measure = _node_by_source(graph.nodes, "MEASURE", NET_LINEAGE)
        report = _node_by_name(graph.nodes, "REPORT", "Finance Legacy Report")
        page = _node_by_name(graph.nodes, "PAGE", PAGE_OVERVIEW)
        visual = _node_by_name(graph.nodes, "VISUAL", VISUAL_SALES)

        self.assertEqual(model.name, "FinanceModel")
        self.assertEqual(sales.name, TABLE_SALES)
        self.assertEqual(measure.name, MEASURE_NET)
        self.assertEqual(report.model_id, model.id)
        self.assertEqual(page.report_id, report.id)
        self.assertEqual(visual.report_id, report.id)
        self.assertEqual(visual.properties.get("visual_type"), "columnChart")
        self.assertEqual(visual.properties.get("title"), "Sales by date")
        self.assertTrue(
            any(
                edge.type == "USES"
                and edge.from_id == visual.id
                and edge.to_id == measure.id
                for edge in graph.edges
            ),
            graph.to_dict(),
        )

    def test_by_connection_report_does_not_bind_to_local_dataset(self):
        project = write_pbip_project(
            self.root / "remote-fixture",
            model_format="tmsl",
            model_kind="dataset",
            report_format="legacy",
            dataset_reference="byConnection",
        )
        bundle = read_pbip_project(project)

        self.assertEqual(len(bundle["models"]), 1)
        self.assertNotEqual(bundle["reports"][0].get("model_id"), bundle["models"][0].get("id"))

    def test_scanner_ignores_pbip_sidecars_outside_definitions(self):
        project = write_pbip_project(self.root / "ignored-fixture", include_ignored=True)
        graph = self.scanner.scan(project)
        names = {node.name for node in graph.nodes}

        self.assertNotIn("IgnoredSemanticScript", names)
        self.assertNotIn("Ignored semantic settings", names)
        self.assertNotIn("Ignored mobile state", names)
        self.assertNotIn("Ignored report resource", names)

    def test_cli_scan_project_path_uses_direct_project_ingestion(self):
        output = io.StringIO()
        with patch("backend.cli.main.GraphRepository", return_value=self.repository):
            with redirect_stdout(output):
                result = cli_main(
                    [
                        "--db",
                        str(self.root / "brain.lbug"),
                        "--identity",
                        str(self.root / "identity.json"),
                        "scan",
                        str(self.project),
                    ]
                )
        self.assertEqual(result, 0)
        payload = json.loads(output.getvalue())
        self.assertGreater(payload["nodes"], 0, payload)
        self.assertGreater(payload["edges"], 0, payload)
        self.assertTrue(any(node.type == "VISUAL" for node in self.repository.all_nodes()))

    def test_tmdl_relationship_has_no_missing_endpoint_validation_error_after_rescan(self):
        first = self.scanner.scan(self.project)
        relationship = _node_by_source(first.nodes, "RELATIONSHIP", RELATIONSHIP_LINEAGE)
        self.assertTrue(
            relationship.properties.get("from_column_id")
            or relationship.properties.get("from_ref"),
            relationship.to_dict(),
        )
        self.assertTrue(
            relationship.properties.get("to_column_id")
            or relationship.properties.get("to_ref"),
            relationship.to_dict(),
        )

        write_pbip_project(self.root / "fixture", include_extra=True)
        self.scanner.scan(self.project)

        validation = self.scanner.last_validation or self.repository.get_validation_result()
        payload = validation.to_dict() if hasattr(validation, "to_dict") else validation
        self.assertIsInstance(payload, dict, validation)
        issues = payload.get("issues", [])
        missing_endpoint = [
            issue
            for issue in issues
            if isinstance(issue, dict) and issue.get("code", issue.get("issue_type")) == "missing_relationship_endpoint"
        ]
        self.assertFalse(missing_endpoint, payload)

    def test_incremental_rescan_preserves_ids_and_adds_measure_and_visual(self):
        first = self.scanner.scan(self.project)
        tracked = {
            (node.type, node.name): node.id
            for node in first.nodes
            if (node.type, node.name)
            in {
                ("MODEL", "FinanceModel"),
                ("TABLE", TABLE_SALES),
                ("TABLE", TABLE_DATE),
                ("MEASURE", MEASURE_NET),
                ("REPORT", "Finance Report"),
                ("PAGE", PAGE_OVERVIEW),
                ("VISUAL", VISUAL_SALES),
            }
        }
        self.assertEqual(len(tracked), 7, tracked)
        self.assertNotIn(MEASURE_GROSS, {node.name for node in first.nodes})
        self.assertNotIn(VISUAL_GROSS, {node.name for node in first.nodes})

        write_pbip_project(self.root / "fixture", include_extra=True)
        second = self.scanner.scan(self.project)
        by_name = {(node.type, node.name): node for node in second.nodes}
        for key, identifier in tracked.items():
            self.assertIn(key, by_name)
            self.assertEqual(by_name[key].id, identifier, key)

        gross = _node_by_source(second.nodes, "MEASURE", GROSS_LINEAGE)
        gross_visual = _node_by_name(second.nodes, "VISUAL", VISUAL_GROSS)
        self.assertEqual(gross.name, MEASURE_GROSS)
        self.assertTrue(
            any(edge.type == "USES" and edge.from_id == gross_visual.id and edge.to_id == gross.id for edge in second.edges),
            second.to_dict(),
        )

        statuses = _status_map(self.scanner.last_sync)
        self.assertEqual(statuses.get(gross.id), "NEW", statuses)
        self.assertEqual(statuses.get(gross_visual.id), "NEW", statuses)


@unittest.skipUnless(_native_ladybug_available(), "Ladybug C API shared library is unavailable")
class NativePBIPLadybugIngestionTests(unittest.TestCase):
    def test_pbip_model_and_report_persist_after_native_database_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = write_pbip_project(root / "fixture")
            database = root / "brain.lbug"
            repository = GraphRepository(database)

            graph = Scanner(repository, identity_path=root / "identity.json").scan(project)
            expected_node_ids = {node.id for node in graph.nodes}
            expected_edge_ids = {edge.id for edge in graph.edges}
            repository.close()

            reopened = GraphRepository(database)
            self.assertEqual(reopened.storage, "ladybug")
            self.assertEqual({node.id for node in reopened.all_nodes()}, expected_node_ids)
            self.assertEqual({edge.id for edge in reopened.all_edges()}, expected_edge_ids)

            model = _node_by_source(reopened.all_nodes(), "MODEL", MODEL_LINEAGE)
            report = _node_by_name(reopened.all_nodes(), "REPORT", "Finance Report")
            visual = _node_by_name(reopened.all_nodes(), "VISUAL", VISUAL_SALES)
            measure = _node_by_source(reopened.all_nodes(), "MEASURE", NET_LINEAGE)
            self.assertTrue(
                reopened.get_edges(
                    from_id=report.id,
                    to_id=model.id,
                    edge_types="USES_MODEL",
                )
            )
            self.assertTrue(
                reopened.get_edges(
                    from_id=visual.id,
                    to_id=measure.id,
                    edge_types="USES",
                )
            )
            reopened.close()


if __name__ == "__main__":
    unittest.main()
