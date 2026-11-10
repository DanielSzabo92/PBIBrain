"""Tests for Issue 58: PBIP combination recognition and safe Trail cache export.

Covers:
1. Handling separate PBIP for model (with .SemanticModel and .Report) and separate
   PBIP for report (with .Report only).
2. Recognition of 'ReferencedObject' live connections and binding to project models.
3. Unrelated combinations generating not-checked placeholders and completing scan.
4. Robust Trail card path resolution and export when object names contain slashes,
   leading/trailing spaces, or Windows-invalid characters (e.g. 'LO / SP Data').
5. Direct model and report folder ingestion.
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from backend.graph.repository import GraphRepository
from backend.graph.schema import Node
from backend.graph.sqlite_store import SQLiteStore, _sanitize_path_segment
from backend.projects import ProjectService
from tests.fixtures.pbip_sources import write_pbip_project


class Issue58TrailExportTests(unittest.TestCase):
    def test_sanitize_path_segment(self):
        self.assertEqual(_sanitize_path_segment("LO / SP Data"), "LO _ SP Data")
        self.assertEqual(_sanitize_path_segment(" SP Data.md"), "SP Data.md")
        self.assertEqual(_sanitize_path_segment("Sales: 2024?"), "Sales_ 2024_")
        self.assertEqual(_sanitize_path_segment("CON"), "CON_obj")
        self.assertEqual(_sanitize_path_segment("  trailing space  "), "trailing space")
        self.assertEqual(_sanitize_path_segment("trailing dot."), "trailing dot")
        self.assertEqual(_sanitize_path_segment(""), "item")

    def test_resolve_card_path_handles_slashes_and_spaces(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_dir = Path(temp_dir)
            store = SQLiteStore(db_dir)

            # Node with slashes and spaces in name (the issue 58 bookmark name: 'LO / SP Data')
            bookmark = Node(
                id="bm-1",
                type="BOOKMARK",
                name="LO / SP Data",
                model_id="model:not-checked-ReferencedObject",
                report_id="report:Sales.Report",
            )
            path = store._resolve_card_path(bookmark)
            self.assertEqual(path, "Sales.Report/definition/bookmarks/LO _ SP Data")
            self.assertFalse(path.endswith(".md"))

            # Table node with special characters
            table = Node(
                id="tbl-1",
                type="TABLE",
                name="LO / SP Data",
                model_id="model:Sales.SemanticModel",
            )
            path = store._resolve_card_path(table)
            self.assertEqual(path, "Sales.SemanticModel/definition/tables/LO _ SP Data.tmdl")

            # Fallback project node
            custom = Node(
                id="c-1",
                type="CUSTOM",
                name="Some / Node: 1",
            )
            path = store._resolve_card_path(custom)
            self.assertEqual(path, "Project/Some _ Node_ 1")
            self.assertFalse(path.endswith(".md"))

    def test_export_trail_creates_cards_without_path_errors(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_dir = Path(temp_dir)
            store = SQLiteStore(db_dir)

            # Multiple nodes with tricky names that would cause WinError 3 without sanitization
            nodes = [
                Node(
                    id="bm-1",
                    type="BOOKMARK",
                    name="LO / SP Data",
                    model_id="model:not-checked-ReferencedObject",
                    report_id="report:Sales.Report",
                ),
                Node(
                    id="page-1",
                    type="PAGE",
                    name="Overview / Summary",
                    report_id="report:Sales.Report",
                ),
                Node(
                    id="tbl-1",
                    type="TABLE",
                    name="Sales Data",
                    model_id="model:not-checked-ReferencedObject",
                ),
            ]
            store.replace_all(nodes, [])

            # Check that Trail files and cards are generated cleanly
            wiring_file = db_dir / ".graph" / "wiring.json"
            index_file = db_dir / "INDEX.md"
            self.assertTrue(wiring_file.is_file())
            self.assertTrue(index_file.is_file())

            # Verify card files exist on disk
            card1 = db_dir / "Sales.Report" / "definition" / "bookmarks" / "LO _ SP Data.md"
            self.assertTrue(card1.is_file(), f"Expected card file at {card1}")
            card2 = db_dir / "Sales.Report" / "definition" / "pages" / "Overview _ Summary" / "page.json.md"
            self.assertTrue(card2.is_file(), f"Expected card file at {card2}")

            index_content = index_file.read_text(encoding="utf-8")
            self.assertIn("LO _ SP Data", index_content)
            self.assertNotIn(".md.md", index_content)


class Issue58PbipCombinationTests(unittest.TestCase):
    def test_separate_model_pbip_and_report_pbip_combination(self):
        """Model pbip has model + report folder, report pbip has report folder only with ReferencedObject."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            model_dir = root / "ModelPBIP"
            report_dir = root / "ReportPBIP"
            model_dir.mkdir(parents=True)
            report_dir.mkdir(parents=True)

            # 1. Model PBIP: has both .SemanticModel and .Report
            write_pbip_project(model_dir)
            model_pbip = model_dir / "Finance.pbip"

            # 2. Separate Report PBIP: report folder only, referencing ReferencedObject live
            report_pbip = report_dir / "ThinReport.pbip"
            report_folder = report_dir / "ThinReport.Report"
            report_folder.mkdir(parents=True)
            report_pbip.write_text(json.dumps({
                "version": "1.0.0",
                "artifacts": [{"report": {"path": "ThinReport.Report"}}]
            }), encoding="utf-8")

            definition_pbir = report_folder / "definition.pbir"
            definition_pbir.write_text(json.dumps({
                "version": "1.0",
                "datasetReference": {
                    "byConnection": {
                        "connectionString": None,
                        "pbiModelVirtualServerName": "sobe_wowvirtualserver",
                        "pbiModelDatabaseName": "ReferencedObject",
                        "name": "EntityDataSource",
                        "connectionType": "pbiServiceXmlaStyleLive"
                    }
                }
            }), encoding="utf-8")

            # Report definition with page, visual, and a bookmark named "LO / SP Data"
            pages_dir = report_folder / "definition" / "pages" / "p1"
            pages_dir.mkdir(parents=True)
            (pages_dir / "page.json").write_text(json.dumps({"name": "p1", "displayName": "Page 1"}), encoding="utf-8")
            (report_folder / "definition" / "pages" / "pages.json").write_text(json.dumps({"pageOrder": ["p1"]}), encoding="utf-8")

            bookmarks_dir = report_folder / "definition" / "bookmarks"
            bookmarks_dir.mkdir(parents=True)
            (bookmarks_dir / "bookmarks.json").write_text(json.dumps({"items": [{"name": "bm1"}]}), encoding="utf-8")
            (bookmarks_dir / "bm1.bookmark.json").write_text(json.dumps({
                "name": "bm1",
                "displayName": "LO / SP Data"
            }), encoding="utf-8")

            # Configure PBIBrain project with both PBIP sources
            project_config = root / "project.json"
            project_config.write_text(json.dumps({
                "version": 1,
                "name": "CombinedProject",
                "sources": [str(model_pbip), str(report_pbip)],
                "database": str(root / "data"),
                "identity_map": str(root / "identity.json"),
            }), encoding="utf-8")

            project = ProjectService(project_config)
            repo = GraphRepository(root / "data")
            result = project.scan(repo)

            # Verification:
            # Model is scanned, both reports are scanned
            self.assertGreater(result.model_count, 0)
            self.assertGreater(result.report_count, 0)

            # ThinReport is bound to the model (or recognized successfully)
            thin_report_nodes = [n for n in repo.all_nodes() if n.type == "REPORT" and n.name == "ThinReport"]
            self.assertEqual(len(thin_report_nodes), 1)

            # Bookmark "LO / SP Data" exists and was indexed
            bm_nodes = [n for n in repo.all_nodes() if n.type == "BOOKMARK"]
            self.assertTrue(any(n.name == "LO / SP Data" for n in bm_nodes))

            # Trail cards written without WinError 3
            cards_manifest = root / "data" / ".graph" / "cards_manifest.json"
            self.assertTrue(cards_manifest.is_file())

    def test_unrelated_model_and_report_combinations(self):
        """Unrelated combinations (e.g. report referencing external model) do not fail the scan."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            model_dir = root / "ModelPBIP"
            report_dir = root / "ReportPBIP"
            model_dir.mkdir(parents=True)
            report_dir.mkdir(parents=True)

            write_pbip_project(model_dir)
            model_pbip = model_dir / "Finance.pbip"

            report_pbip = report_dir / "ExternalReport.pbip"
            report_folder = report_dir / "ExternalReport.Report"
            report_folder.mkdir(parents=True)
            report_pbip.write_text(json.dumps({
                "version": "1.0.0",
                "artifacts": [{"report": {"path": "ExternalReport.Report"}}]
            }), encoding="utf-8")

            # Reference an external workspace model that is not in the project
            definition_pbir = report_folder / "definition.pbir"
            definition_pbir.write_text(json.dumps({
                "version": "1.0",
                "datasetReference": {
                    "byConnection": {
                        "connectionString": "Data Source=powerbi://api.powerbi.com/v1.0/myorg/OtherWorkspace;Initial Catalog=UnrelatedModel"
                    }
                }
            }), encoding="utf-8")

            # Configure PBIBrain project
            project_config = root / "project.json"
            project_config.write_text(json.dumps({
                "version": 1,
                "name": "UnrelatedProject",
                "sources": [str(model_pbip), str(report_pbip)],
                "database": str(root / "data"),
                "identity_map": str(root / "identity.json"),
            }), encoding="utf-8")

            project = ProjectService(project_config)
            repo = GraphRepository(root / "data")
            result = project.scan(repo)

            # Not checked items should include the unrelated external model
            self.assertTrue(any(item["name"] == "UnrelatedModel" for item in result.not_checked))

            # The scan completed cleanly
            self.assertGreater(result.report_count, 0)

    def test_direct_folder_source_ingestion(self):
        """Scan can accept .SemanticModel and .Report directories directly in sources."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pbip_dir = root / "PbipProject"
            pbip_dir.mkdir(parents=True)
            write_pbip_project(pbip_dir)

            model_folder = pbip_dir / "Finance.SemanticModel"
            report_folder = pbip_dir / "Finance.Report"

            project_config = root / "project.json"
            project_config.write_text(json.dumps({
                "version": 1,
                "name": "FolderSourcesProject",
                "sources": [str(model_folder), str(report_folder)],
                "database": str(root / "data"),
                "identity_map": str(root / "identity.json"),
            }), encoding="utf-8")

            project = ProjectService(project_config)
            repo = GraphRepository(root / "data")
            result = project.scan(repo)

            self.assertGreater(result.model_count, 0)
            self.assertGreater(result.report_count, 0)


if __name__ == "__main__":
    unittest.main()
