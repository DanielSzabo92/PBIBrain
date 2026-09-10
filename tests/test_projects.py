"""Project configuration and multi-source scan contracts."""

from __future__ import annotations

from contextlib import redirect_stderr
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.graph.repository import GraphRepository
from backend.cli.main import main as cli_main
from backend.projects import (
    ProjectConfigError,
    ProjectConfigStore,
    ProjectService,
    ProjectSourceCollisionError,
    ProjectSourceError,
)
from tests.fixtures.phase1_sources import REPORT_A_ID, model_source, report_source
from tests.fixtures.pbip_sources import MODEL_LINEAGE, write_pbip_project


def _model(identifier: str, label: str) -> dict:
    return {
        "id": identifier,
        "name": label,
        "tables": [
            {
                "id": f"{identifier}-table",
                "name": f"{label} Facts",
                "columns": [
                    {
                        "id": f"{identifier}-amount",
                        "name": "Amount",
                        "dataType": "Double",
                    }
                ],
                "measures": [
                    {
                        "id": f"{identifier}-total",
                        "name": f"{label} Total",
                        "expression": f"SUM('{label} Facts'[Amount])",
                    }
                ],
            }
        ],
    }


def _report(identifier: str, model_id: str, label: str) -> dict:
    return {
        "id": identifier,
        "name": f"{label} Report",
        "modelId": model_id,
        "sections": [
            {
                "id": f"{identifier}-page",
                "name": "Overview",
                "visualContainers": [
                    {
                        "id": f"{identifier}-visual",
                        "visualType": "card",
                        "measures": [{"objectId": f"{model_id}-total"}],
                    }
                ],
            }
        ],
    }


class ProjectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.config_path = self.root / "config" / "brain.json"
        self.store = ProjectConfigStore(self.config_path)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_source(self, name: str, model_id: str, report_id: str) -> Path:
        path = self.root / "sources" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "models": [_model(model_id, model_id.title())],
                    "reports": [_report(report_id, model_id, model_id.title())],
                }
            ),
            encoding="utf-8",
        )
        return path

    def _save(self, sources: list[Path]) -> dict:
        return self.store.save(
            {
                "version": 1,
                "name": "Portfolio",
                "sources": [os.path.relpath(path, self.config_path.parent) for path in sources],
                "database": "../data/portfolio.lbug",
                "identity_map": "identity.json",
            }
        )

    def test_legacy_v1_defaults_and_paths_resolve_from_config_directory(self):
        self.config_path.parent.mkdir(parents=True)
        self.config_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "database": "../data/brain.lbug",
                    "identity_map": "identity.json",
                }
            ),
            encoding="utf-8",
        )

        config = self.store.get()
        paths = ProjectService(self.config_path).paths()

        self.assertEqual(config["name"], "PBIBrain")
        self.assertEqual(config["sources"], [])
        self.assertEqual(paths["database"], (self.root / "data" / "brain.lbug").resolve())
        self.assertEqual(paths["identity_map"], (self.root / "config" / "identity.json").resolve())
        self.assertEqual(paths["overrides"], (self.root / "config" / "overrides.json").resolve())

    def test_invalid_or_duplicate_config_does_not_replace_saved_file(self):
        source = self._write_source("sales.json", "sales", "sales-report")
        self._save([source])
        original = self.config_path.read_bytes()
        payload = self.store.get()
        payload["sources"] = ["../sources/sales.json", "../SOURCES/SALES.json"]

        with self.assertRaisesRegex(ProjectConfigError, "Duplicate project source"):
            self.store.save(payload)

        self.assertEqual(self.config_path.read_bytes(), original)
        self.assertEqual(list(self.config_path.parent.glob(".brain.json.*.tmp")), [])

    def test_config_rejects_writable_path_and_source_aliases(self):
        payload = {
            "version": 1,
            "name": "Portfolio",
            "sources": ["../sources/model.json"],
            "database": "identity.json",
            "identity_map": "identity.json",
        }
        with self.assertRaisesRegex(ProjectConfigError, "database path"):
            self.store.save(payload)

        payload["database"] = "../sources/model.json"
        with self.assertRaisesRegex(ProjectConfigError, "Source path"):
            self.store.save(payload)

    def test_scan_combines_two_models_and_reports_in_one_repository(self):
        sales = self._write_source("sales.json", "sales", "sales-report")
        inventory = self._write_source("inventory.json", "inventory", "inventory-report")
        self._save([sales, inventory])
        repository = GraphRepository(use_native=False)

        result = ProjectService(self.config_path).scan(repository)

        self.assertEqual(result.source_count, 2)
        self.assertEqual(result.model_count, 2)
        self.assertEqual(result.report_count, 2)
        self.assertEqual({node.source_id for node in repository.all_nodes() if node.type == "MODEL"}, {"sales", "inventory"})
        self.assertEqual({node.source_id for node in repository.all_nodes() if node.type == "REPORT"}, {"sales-report", "inventory-report"})
        uses_models = repository.get_edges(edge_types=["USES_MODEL"])
        self.assertEqual({(edge.from_id, edge.to_id) for edge in uses_models}, {
            ("report:sales-report", "model:sales"),
            ("report:inventory-report", "model:inventory"),
        })

    def test_idless_model_identity_survives_source_reordering(self):
        sources: list[Path] = []
        for name in ("alpha", "beta"):
            path = self.root / "sources" / f"{name}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            model = _model(name, name.title())
            model.pop("id")
            path.write_text(json.dumps(model), encoding="utf-8")
            sources.append(path)
        self._save(sources)
        repository = GraphRepository(use_native=False)
        service = ProjectService(self.config_path)
        service.scan(repository)
        before = {node.name: node.id for node in repository.all_nodes() if node.type == "MODEL"}

        self._save(list(reversed(sources)))
        service.scan(repository)
        after = {node.name: node.id for node in repository.all_nodes() if node.type == "MODEL"}

        self.assertEqual(after, before)

    def test_two_pbip_sources_can_share_one_identical_model(self):
        project_root = self.root / "shared-pbip"
        first = write_pbip_project(project_root)
        shutil.copytree(project_root / "Finance.Report", project_root / "Operations.Report")
        second = project_root / "Operations.pbip"
        second.write_text(
            json.dumps(
                {
                    "version": "1.0.0",
                    "artifacts": [
                        {"report": {"path": "Operations.Report"}},
                        {"semanticModel": {"path": "Finance.SemanticModel"}},
                    ],
                }
            ),
            encoding="utf-8",
        )
        self._save([first, second])
        repository = GraphRepository(use_native=False)

        result = ProjectService(self.config_path).scan(repository)

        self.assertEqual(result.model_count, 1)
        self.assertEqual(result.report_count, 2)
        self.assertEqual(
            [node.source_id for node in repository.all_nodes() if node.type == "MODEL"],
            [MODEL_LINEAGE],
        )
        self.assertEqual(len(repository.get_edges(edge_types=["USES_MODEL"])), 2)

    def test_rescan_removes_deleted_source_without_losing_remaining_source(self):
        sales = self._write_source("sales.json", "sales", "sales-report")
        inventory = self._write_source("inventory.json", "inventory", "inventory-report")
        self._save([sales, inventory])
        repository = GraphRepository(use_native=False)
        service = ProjectService(self.config_path)
        service.scan(repository)

        self._save([sales])
        service.scan(repository)

        self.assertIsNotNone(repository.get_object("model:sales"))
        self.assertIsNone(repository.get_object("model:inventory"))
        self.assertFalse(any(node.model_id == "model:inventory" for node in repository.all_nodes()))

    def test_collision_and_broken_source_leave_previous_graph_unchanged(self):
        first = self._write_source("first.json", "shared", "first-report")
        second = self._write_source("second.json", "shared", "second-report")
        second_payload = json.loads(second.read_text(encoding="utf-8"))
        second_payload["models"][0]["name"] = "Conflicting Shared Model"
        second.write_text(json.dumps(second_payload), encoding="utf-8")
        self._save([first])
        repository = GraphRepository(use_native=False)
        service = ProjectService(self.config_path)
        service.scan(repository)
        before = ([node.to_dict() for node in repository.all_nodes()], [edge.to_dict() for edge in repository.all_edges()])

        self._save([first, second])
        with self.assertRaisesRegex(ProjectSourceCollisionError, "model:shared"):
            service.scan(repository)
        self.assertEqual(before, ([node.to_dict() for node in repository.all_nodes()], [edge.to_dict() for edge in repository.all_edges()]))

        second.write_text("{broken", encoding="utf-8")
        with self.assertRaises(ProjectSourceError):
            service.scan(repository)
        self.assertEqual(before, ([node.to_dict() for node in repository.all_nodes()], [edge.to_dict() for edge in repository.all_edges()]))

    def test_failed_repository_publish_restores_previous_identity_file(self):
        source = self._write_source("sales.json", "sales", "sales-report")
        self._save([source])
        identity = self.config_path.parent / "identity.json"
        identity.write_text('{"version":1,"mappings":{}}\n', encoding="utf-8")
        original = identity.read_bytes()
        repository = GraphRepository(use_native=False)

        with patch.object(repository, "replace", side_effect=RuntimeError("write failed")):
            with self.assertRaisesRegex(RuntimeError, "write failed"):
                ProjectService(self.config_path).scan(repository)

        self.assertEqual(identity.read_bytes(), original)
        self.assertEqual(repository.all_nodes(), [])

    def test_rescan_preserves_review_status_and_override_file(self):
        source = self.root / "sources" / "review.json"
        source.parent.mkdir(parents=True)
        source.write_text(
            json.dumps({"models": [model_source()], "reports": [report_source(REPORT_A_ID)]}),
            encoding="utf-8",
        )
        self._save([source])
        overrides = self.config_path.parent / "overrides.json"
        overrides.write_text('{"version":1,"overrides":[]}\n', encoding="utf-8")
        override_bytes = overrides.read_bytes()
        repository = GraphRepository(use_native=False)
        service = ProjectService(self.config_path)
        service.scan(repository)
        candidate = next(node for node in repository.all_nodes() if node.status == "candidate")
        candidate.status = "approved"
        repository.replace(repository.all_nodes(), repository.all_edges())

        service.scan(repository)

        self.assertEqual(repository.get_object(candidate.id).status, "approved")
        self.assertEqual(overrides.read_bytes(), override_bytes)

    def test_projects_keep_database_and_identity_paths_isolated(self):
        first_path = self.root / "first" / "brain.json"
        second_path = self.root / "second" / "brain.json"
        payload = {
            "version": 1,
            "name": "Project",
            "sources": [],
            "database": "data/brain.lbug",
            "identity_map": "state/identity.json",
        }
        ProjectConfigStore(first_path).save(payload)
        ProjectConfigStore(second_path).save(payload)

        first = ProjectService(first_path).paths()
        second = ProjectService(second_path).paths()

        self.assertNotEqual(first["database"], second["database"])
        self.assertNotEqual(first["identity_map"], second["identity_map"])

    def test_project_scan_and_serve_reject_storage_overrides_before_open(self):
        self._save([])
        cases = (
            ("project-scan", "--db", str(self.root / "wrong.lbug")),
            ("serve", "--identity", str(self.root / "wrong-identity.json")),
        )
        for command, flag, value in cases:
            with self.subTest(command=command), patch("backend.cli.main.GraphRepository") as repository:
                with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                    cli_main(["--config", str(self.config_path), flag, value, command])
                self.assertEqual(raised.exception.code, 2)
                repository.assert_not_called()


if __name__ == "__main__":
    unittest.main()
