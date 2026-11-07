"""Cloud models and cloud reports as Brain project sources (issue #9).

No test makes a network call: a fake cloud service writes the PBIP fixture files
the way ``CloudService.read_model`` and ``report_to_folder`` write a TMDL export
and a report definition.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from backend.api.app import BrainAPI, get_overview
from backend.api.graph import get_lineage
from backend.graph.repository import GraphRepository
from backend.project_cloud import (
    REASON_MODEL_NOT_IN_PROJECT,
    REASON_NO_CLOUD_SERVICE,
    REASON_REPORT_NOT_READABLE,
    REASON_SIGN_IN_REQUIRED,
    connection_keys,
)
from backend.projects import ProjectConfigError, ProjectService
from tests.fixtures.pbip_sources import MEASURE_NET, MODEL_NAME, REPORT_NAME, VISUAL_SALES, write_pbip_project

WORKSPACE = "aaaaaaaa-0000-0000-0000-000000000001"
CLOUD_MODEL_ID = "bbbbbbbb-0000-0000-0000-000000000002"
CLOUD_REPORT_ID = "cccccccc-0000-0000-0000-000000000003"


class SignInRequired(Exception):
    pass


class ReportNotReadable(Exception):
    pass


class FakeCloudService:
    """The two read calls of ``CloudService`` that a project scan uses."""

    def __init__(self, fixture: Path, *, connection: str | None = None) -> None:
        self.model_dir = fixture / MODEL_NAME
        self.report_dir = fixture / REPORT_NAME
        self.connection = connection or f"semanticmodelid={CLOUD_MODEL_ID}"
        self.fail: Exception | None = None
        self.calls: list[tuple[str, str]] = []

    def read_model(self, workspace_name: str, database: str, folder: Path) -> None:
        self.calls.append(("model", database))
        if self.fail is not None:
            raise self.fail
        shutil.copytree(self.model_dir / "definition", folder)

    def report_to_folder(self, workspace_id: str, report_id: str, folder: Path) -> None:
        self.calls.append(("report", report_id))
        if self.fail is not None:
            raise self.fail
        shutil.copytree(self.report_dir, folder)
        (folder / "definition.pbir").write_text(json.dumps(
            {"version": "4.0", "datasetReference": {"byConnection": {"connectionString": self.connection}}}), encoding="utf-8")


def cloud_model(**extra) -> dict:
    return {"kind": "cloud_model", "workspace_id": WORKSPACE, "workspace_name": "Sales Analytics",
            "item_id": CLOUD_MODEL_ID, "name": "Cloud Finance", **extra}


def cloud_report(**extra) -> dict:
    return {"kind": "cloud_report", "workspace_id": WORKSPACE, "workspace_name": "Sales Analytics",
            "item_id": CLOUD_REPORT_ID, "name": "Cloud Finance Report", **extra}


class ProjectCloudSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.fixture = self.root / "fixture"
        write_pbip_project(self.fixture)
        self.local = write_pbip_project(self.root / "local" / "Local", include_extra=True)
        self.config = self.root / "project" / ".pbibrain" / "brain.json"
        self.cloud = FakeCloudService(self.fixture)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def save(self, sources: list[str], cloud_sources: list[dict]) -> ProjectService:
        service = ProjectService(self.config, cloud=lambda: self.cloud)
        service.save_config({"version": 1, "name": "Mixed", "sources": sources, "cloud_sources": cloud_sources,
                             "database": "brain.lbug", "identity_map": "identity.json"})
        return service

    def test_mixed_project_shows_cloud_model_and_report_with_impact_across_the_boundary(self):
        service = self.save([str(self.local)], [cloud_model(), cloud_report()])
        repository = GraphRepository(use_native=False)

        result = service.scan(repository)

        self.assertEqual((result.model_count, result.report_count), (2, 2))
        self.assertEqual(result.not_checked, ())
        self.assertEqual({item["status"] for item in result.cloud}, {"live"})
        nodes = repository.all_nodes()
        model = next(node for node in nodes if node.type == "MODEL" and node.name == "Cloud Finance")
        report = next(node for node in nodes if node.type == "REPORT" and node.name == "Cloud Finance Report")
        self.assertEqual(report.model_id, model.id)
        self.assertEqual((model.properties["origin"], model.properties["workspace_name"]), ("cloud", "Sales Analytics"))
        workspace = next(node for node in nodes if node.type == "WORKSPACE")
        contains = {(edge.from_id, edge.to_id) for edge in repository.get_edges(edge_types=["CONTAINS"])}
        self.assertIn((workspace.id, model.id), contains)
        self.assertIn((workspace.id, report.id), contains)
        self.assertIn((report.id, model.id), {(edge.from_id, edge.to_id) for edge in repository.get_edges(edge_types=["USES_MODEL"])})

        # Impact of a cloud-model measure lists the cloud report's visual.
        measure = next(node for node in nodes if node.type == "MEASURE" and node.name == MEASURE_NET and node.model_id == model.id)
        impact = BrainAPI(repository).get_impact(measure.id)
        visual = next(node for node in nodes if node.type == "VISUAL" and node.report_id == report.id)
        self.assertIn(VISUAL_SALES, visual.source_id or visual.id)
        self.assertIn(visual.id, json.dumps(impact))

        # Lineage carries the workspace group; the overview names the cloud roots.
        lineage = get_lineage(repository)
        self.assertIn(workspace.id, {node["id"] for node in lineage["nodes"]})
        overview = get_overview(repository)
        self.assertEqual([item["name"] for item in overview["workspaces"]], ["Sales Analytics"])
        cloud_roots = [item for item in overview["model_objects"] + overview["report_objects"] if item.get("origin") == "cloud"]
        self.assertEqual(len(cloud_roots), 2)
        self.assertTrue((self.config.parent / "tmp" / "cloud" / CLOUD_MODEL_ID / "definition" / "model.tmdl").is_file())

    def test_local_thin_report_binds_to_cloud_model_by_connection(self):
        thin = write_pbip_project(self.root / "thin" / "Thin", dataset_reference="byConnection")
        # The thin report fixture names the model with semanticmodelid=remote-finance-model.
        service = self.save([str(thin)], [cloud_model(item_id="remote-finance-model")])
        repository = GraphRepository(use_native=False)

        service.scan(repository)

        cloud = next(node for node in repository.all_nodes() if node.type == "MODEL" and node.name == "Cloud Finance")
        report = next(node for node in repository.all_nodes() if node.type == "REPORT")
        self.assertEqual(report.model_id, cloud.id)

    def test_thin_report_only_project_scans_with_not_checked_model(self):
        thin = write_pbip_project(self.root / "thin" / "Thin", dataset_reference="byConnection")
        # Keep only the report: delete the local model folder and its project reference.
        shutil.rmtree(thin.parent / MODEL_NAME)
        thin.write_text(json.dumps({"version": "1.0", "artifacts": [{"report": {"path": REPORT_NAME}}]}), encoding="utf-8")
        service = self.save([str(thin)], [])
        repository = GraphRepository(use_native=False)

        result = service.scan(repository)

        self.assertEqual((result.model_count, result.report_count), (0, 1))
        self.assertEqual([item["reason"] for item in result.not_checked], [REASON_MODEL_NOT_IN_PROJECT])
        self.assertEqual(result.not_checked[0]["reports"], ["Finance Report"])
        placeholder = next(node for node in repository.all_nodes() if node.type == "MODEL")
        self.assertEqual(placeholder.properties["check_status"], "not_checked")
        report = next(node for node in repository.all_nodes() if node.type == "REPORT")
        self.assertEqual(report.model_id, placeholder.id)
        self.assertEqual([item["type"] for item in get_overview(repository)["not_checked"]], ["MODEL"])

    def test_cloud_read_falls_back_to_cache_then_to_not_checked(self):
        service = self.save([], [cloud_model(), cloud_report()])
        service.scan(GraphRepository(use_native=False))
        self.cloud.fail = SignInRequired()

        repository = GraphRepository(use_native=False)
        cached = service.scan(repository)

        self.assertEqual({(item["status"], item["reason"]) for item in cached.cloud}, {("cached", REASON_SIGN_IN_REQUIRED)})
        self.assertEqual(cached.not_checked, ())
        self.assertEqual((cached.model_count, cached.report_count), (1, 1))

        shutil.rmtree(self.config.parent / "tmp" / "cloud")
        self.cloud.fail = ReportNotReadable()
        repository = GraphRepository(use_native=False)
        missing = service.scan(repository)

        self.assertEqual({item["reason"] for item in missing.not_checked}, {REASON_REPORT_NOT_READABLE})
        self.assertEqual((missing.model_count, missing.report_count), (0, 0))
        report = next(node for node in repository.all_nodes() if node.type == "REPORT")
        model = next(node for node in repository.all_nodes() if node.type == "MODEL")
        self.assertEqual(report.model_id, model.id)  # The report keeps its binding by dataset ID.

    def test_without_cloud_service_the_scan_uses_the_cache_only(self):
        self.save([], [cloud_model()])
        repository = GraphRepository(use_native=False)

        result = ProjectService(self.config).scan(repository)

        self.assertEqual(self.cloud.calls, [])
        self.assertEqual([item["reason"] for item in result.not_checked], [REASON_NO_CLOUD_SERVICE])

    def test_config_rejects_bad_cloud_entries(self):
        for entry, message in (
            ({**cloud_model(), "token": "x"}, "unsupported"),
            ({**cloud_model(), "kind": "cloud_lakehouse"}, "kind"),
            ({**cloud_model(), "item_id": "../x"}, "item_id"),
            ({**cloud_model(), "access_type": "Write"}, "access_type"),
            ({**cloud_model(), "dataset_id": CLOUD_MODEL_ID}, "dataset_id"),
        ):
            with self.subTest(message=message), self.assertRaisesRegex(ProjectConfigError, message):
                self.save([], [entry])
        with self.assertRaisesRegex(ProjectConfigError, "Duplicate cloud source"):
            self.save([], [cloud_model(), cloud_model()])
        saved = self.save([], [cloud_report(dataset_id=CLOUD_MODEL_ID)]).get_config()
        self.assertEqual(saved["cloud_sources"][0]["access_type"], "Read")

    def test_connection_keys(self):
        self.assertEqual(connection_keys("byConnection:semanticmodelid=abc"), {"model": "abc"})
        self.assertEqual(connection_keys("byConnection:" + CLOUD_MODEL_ID), {"model": CLOUD_MODEL_ID})
        self.assertEqual(
            connection_keys("byConnection:Data Source=powerbi://api.powerbi.com/v1.0/myorg/Sales Analytics;Initial Catalog=Finance"),
            {"workspace": "Sales Analytics", "catalog": "Finance"})

    def test_report_bound_by_catalog_name_in_workspace(self):
        self.cloud.connection = "Data Source=powerbi://api.powerbi.com/v1.0/myorg/Sales Analytics;Initial Catalog=Cloud Finance"
        service = self.save([], [cloud_model(), cloud_report()])
        repository = GraphRepository(use_native=False)

        result = service.scan(repository)

        self.assertEqual(result.not_checked, ())
        report = next(node for node in repository.all_nodes() if node.type == "REPORT")
        self.assertEqual(report.model_id, next(node.id for node in repository.all_nodes() if node.type == "MODEL"))


if __name__ == "__main__":
    unittest.main()
