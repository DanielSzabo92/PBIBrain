"""S0 foundations: PBIR schema versions, connection marker key, TOM version, merge lab."""

from __future__ import annotations

from copy import deepcopy
import io
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from backend import agent
from backend.adapters.pbir.validation import _catalog, validate_report_documents
from backend.adapters.tabular_metadata import TabularMetadataAdapter
from backend.desktop import DesktopController
from backend.graph.repository import GraphRepository
from backend.snapshots.scan import scan_snapshot
from tools.vendor_pbir_schemas import ROOTS, VERSIONS

REPOSITORY = Path(__file__).resolve().parents[1]
LAB = REPOSITORY / "tests" / "fixtures" / "merge_lab"
EXPECTED = json.loads((LAB / "EXPECTED.json").read_text(encoding="utf-8"))
PREFIX = "https://developer.microsoft.com/json-schemas/fabric/item/report/"
CURRENT = {"report": "3.3.0", "page": "2.1.0", "visualContainer": "2.13.0", "pagesMetadata": "1.1.0", "bookmark": "2.1.0",
           "bookmarksMetadata": "1.0.0", "reportExtension": "1.0.0", "versionMetadata": "1.0.0"}
SCHEMA_CODES = {"PBIR_SCHEMA_INVALID", "PBIR_SCHEMA_UNSUPPORTED"}
BRIDGE = REPOSITORY / "backend/adapters/tabular_metadata/dotnet/bin/Release/net8.0/TabularMetadata.dll"


def report_documents(project: str) -> dict[str, object]:
    root = LAB / project
    return {path.relative_to(root).as_posix(): json.loads(path.read_text(encoding="utf-8"))
            for path in root.rglob("*") if path.is_file() and path.suffix in {".json", ".pbir"} and ".Report" in path.relative_to(root).parts[0]}


def tmdl_models() -> list[Path]:
    return [LAB / record["path"] for project in EXPECTED["projects"].values() for record in project["models"].values() if record["format"] == "TMDL"]


class PBIRSchemaVersionTests(unittest.TestCase):
    def test_each_pinned_version_is_in_the_catalog(self):
        schemas, _, _ = _catalog()
        for family, version in CURRENT.items():
            self.assertEqual(version, VERSIONS[family][-1], family)
        for root in ROOTS:
            self.assertIn("https://developer.microsoft.com/json-schemas/" + root, schemas)

    def test_report_with_each_current_schema_version_validates(self):
        result = validate_report_documents(report_documents("SalesA"))
        self.assertEqual([], [issue for issue in result["issues"] if issue["code"] in SCHEMA_CODES])
        covered = {item["schema"] for item in result["coverage"] if item["validated"]}
        for family, version in CURRENT.items():
            self.assertIn(PREFIX + f"definition/{family}/{version}/schema.json", covered)
        self.assertIn(PREFIX + "definitionProperties/2.0.0/schema.json", covered)

    def test_report_with_older_schema_versions_validates(self):
        result = validate_report_documents(report_documents("SalesB"))
        self.assertEqual("COMPLETE", result["status"], result["issues"])
        self.assertIn(PREFIX + "definition/report/2.0.0/schema.json", {item["schema"] for item in result["coverage"]})

    def test_unknown_or_foreign_schema_fails_closed(self):
        original = report_documents("SalesA")
        for relative, document in original.items():
            if not isinstance(document, dict) or "$schema" not in document:
                continue
            for value in (re.sub(r"/\d+\.\d+\.\d+/", "/99.0.0/", document["$schema"]), PREFIX + "definition/page/2.1.0/schema.json", None):
                if value == document["$schema"]:
                    continue
                with self.subTest(file=relative, schema=value):
                    changed = deepcopy(original)
                    changed[relative]["$schema"] = value
                    issues = validate_report_documents(changed)["issues"]
                    self.assertIn(("PBIR_SCHEMA_UNSUPPORTED", relative), {(issue["code"], issue["source_file"]) for issue in issues})


class ConnectionMarkerTests(unittest.TestCase):
    def test_old_marker_with_session_id_loads(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "brain.json"
            marker = {"url": "http://127.0.0.1:9999", "config_path": str(config), "session_id": "abc"}
            (config.parent / "connection.json").write_text(json.dumps(marker), encoding="utf-8")
            reply = io.BytesIO(json.dumps({"connection_id": "abc", "project": {"config_path": str(config)}}).encode())
            with patch.object(agent, "BrainClient") as client:
                client.return_value.url = marker["url"]
                client.return_value.opener.open.return_value = reply
                self.assertEqual("abc", agent.live_client(config).session_id)

    def test_new_marker_with_connection_id_loads(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "brain.json"
            marker = {"url": "http://127.0.0.1:9999", "config_path": str(config), "connection_id": "xyz"}
            (config.parent / "connection.json").write_text(json.dumps(marker), encoding="utf-8")
            reply = io.BytesIO(json.dumps({"connection_id": "xyz", "project": {"config_path": str(config)}}).encode())
            with patch.object(agent, "BrainClient") as client:
                client.return_value.url = marker["url"]
                client.return_value.opener.open.return_value = reply
                self.assertEqual("xyz", agent.live_client(config).session_id)

    def test_next_save_writes_connection_id_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            static = root / "dist"
            static.mkdir()
            (static / "index.html").write_text("<main>PBIBrain</main>", encoding="utf-8")
            (root / "Project.pbip").write_text("{}", encoding="utf-8")
            marker_path = root / ".pbibrain" / "connection.json"
            marker_path.parent.mkdir()
            marker_path.write_text(json.dumps({"url": "http://127.0.0.1:9999", "config_path": "old", "session_id": "old"}), encoding="utf-8")
            controller = DesktopController(static_dir=static, repository_factory=lambda path: GraphRepository(path, use_native=False),
                                           runtime_configurer=lambda: None)
            try:
                controller.attach_server("http://127.0.0.1:8123")
                self.assertTrue(controller.open_project("Project", str(root))["ok"])
                marker = json.loads(marker_path.read_text(encoding="utf-8"))
                self.assertEqual({"url", "config_path", "connection_id"}, set(marker))
                self.assertEqual(marker["connection_id"], controller.endpoint_session()["connection_id"])
            finally:
                controller.shutdown()


@unittest.skipUnless(BRIDGE.is_file(), "Build the TOM bridge first")
class TOMBridgeTests(unittest.TestCase):
    def test_bridge_uses_the_pinned_tom_version(self):
        project = (REPOSITORY / "backend/adapters/tabular_metadata/dotnet/TabularMetadata.csproj").read_text(encoding="utf-8")
        version = re.search(r'Include="Microsoft.AnalysisServices" Version="([^"]+)"', project).group(1)
        lock = json.loads((REPOSITORY / "backend/adapters/tabular_metadata/dotnet/packages.lock.json").read_text(encoding="utf-8"))
        self.assertEqual(version, lock["dependencies"]["net8.0"]["Microsoft.AnalysisServices"]["resolved"])
        payload = TabularMetadataAdapter().read(LAB / "SalesB/SalesB.SemanticModel/definition")
        self.assertEqual(f"Microsoft.AnalysisServices/{version}/TOM+TMDL", payload["provenance"])

    def test_serialization_of_the_same_model_twice_gives_equal_bytes(self):
        sources = [path / "definition" for path in tmdl_models()] + [LAB / "Legacy/Legacy.SemanticModel/model.bim"]
        for source in sources:
            with self.subTest(source=source.relative_to(LAB).as_posix()):
                first = TabularMetadataAdapter().read(source, include_documents=True)["tmdl_documents"]
                second = TabularMetadataAdapter().read(source, include_documents=True)["tmdl_documents"]
                self.assertTrue(first)
                self.assertEqual({key: value.encode("utf-8") for key, value in first.items()},
                                 {key: value.encode("utf-8") for key, value in second.items()})

    def test_fixture_tmdl_is_canonical_except_the_marked_file(self):
        marked = {item["path"] for item in EXPECTED["non_canonical_tmdl"]}
        for model in tmdl_models():
            documents = TabularMetadataAdapter().read(model / "definition", include_documents=True)["tmdl_documents"]
            files = {path.relative_to(model / "definition").as_posix(): path for path in (model / "definition").rglob("*.tmdl")}
            self.assertEqual(set(documents), set(files))
            for relative, path in files.items():
                with self.subTest(file=path.relative_to(LAB).as_posix()):
                    data = path.read_bytes()
                    self.assertFalse(data.startswith(b"\xef\xbb\xbf"))
                    if path.relative_to(LAB).as_posix() in marked:
                        self.assertNotEqual(documents[relative].encode("utf-8"), data)
                        self.assertNotIn(b"\r\n", data)
                    else:
                        self.assertEqual(documents[relative].encode("utf-8"), data)
                        self.assertIn(b"\r\n", data)


@unittest.skipUnless(BRIDGE.is_file(), "Build the TOM bridge first")
class MergeLabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.databases = {}
        for project in EXPECTED["projects"].values():
            for name, record in project["models"].items():
                folder = LAB / record["path"]
                source = folder / "definition" if record["format"] == "TMDL" else folder / "model.bim"
                cls.databases[name] = TabularMetadataAdapter().read(source)["database"]

    def table(self, model: str, name: str) -> dict:
        return next(table for table in self.databases[model]["model"]["tables"] if table["name"] == name)

    def item(self, model: str, table: str, name: str) -> dict:
        found = self.table(model, table)
        return next(value for value in found.get("measures", []) + found.get("columns", []) if value["name"] == name)

    def test_fixture_set_has_the_planned_formats(self):
        models = [record["format"] for project in EXPECTED["projects"].values() for record in project["models"].values()]
        reports = [record["format"] for project in EXPECTED["projects"].values() for record in project["reports"].values()]
        self.assertEqual(["TMDL"] * 3 + ["TMSL"], sorted(models))
        self.assertEqual(["PBIR", "PBIR", "PBIR-Legacy"], sorted(reports))
        for project in EXPECTED["projects"].values():
            self.assertTrue((LAB / project["pbip"]).is_file())
            for record in project["models"].values():
                self.assertTrue((LAB / record["path"] / "definition.pbism").is_file())
                self.assertEqual(record["format"] == "TMDL", (LAB / record["path"] / "definition" / "model.tmdl").is_file())
            for record in project["reports"].values():
                legacy = record["format"] == "PBIR-Legacy"
                self.assertEqual(legacy, (LAB / record["path"] / "report.json").is_file())
                self.assertEqual(not legacy, (LAB / record["path"] / "definition" / "report.json").is_file())

    def test_merge_lab_projects_scan_without_errors(self):
        for project in EXPECTED["projects"]:
            with self.subTest(project=project):
                result = scan_snapshot(LAB / project)
                self.assertEqual([], result["completeness"]["scanner_errors"])
                # Only the known coverage gaps block. A new item is a fixture fault or a regression.
                self.assertEqual(sorted(EXPECTED["guarded_scan_gaps"][project]), result["completeness"]["blocking"])
                if not EXPECTED["guarded_scan_gaps"][project]:
                    self.assertEqual("COMPLETE", result["completeness"]["status"])

    def test_known_cases_are_in_the_models(self):
        for case in EXPECTED["known_renames"] + EXPECTED["moved_measures"]:
            source, target = case["from"], case["to"]
            name = case.get("name")
            self.assertEqual(case["lineage_tag"], self.item(source["model"], source["table"], source.get("name", name))["lineageTag"])
            self.assertEqual(case["lineage_tag"], self.item(target["model"], target["table"], target.get("name", name))["lineageTag"])
        for case in EXPECTED["name_clashes"]:
            for model, tag in case["lineage_tags"].items():
                self.assertEqual(tag, self.item(model, case["table"], case["name"]).get("lineageTag"))
        for case in EXPECTED["possible_renames"]:
            for side in (case["from"], case["to"]):
                self.assertEqual(side["lineage_tag"], self.item(side["model"], side["table"], side["name"]).get("lineageTag"))
        for case in EXPECTED["duplicate_lineage_tags"]:
            for item in case["objects"]:
                self.assertEqual(case["lineage_tag"], self.item(case["model"], item["table"], item["name"])["lineageTag"])
        for case in EXPECTED["no_lineage_tag"]:
            if case["object_type"] in {"MEASURE", "COLUMN"}:
                self.assertNotIn("lineageTag", self.item(case["model"], case["table"], case["name"]))

    def test_special_objects_are_in_the_models(self):
        for case in EXPECTED["calculation_groups"]:
            items = self.table(case["model"], case["table"])["calculationGroup"]["calculationItems"]
            self.assertEqual(case["items"], [item["name"] for item in items])
            self.assertTrue(all("lineageTag" not in item for item in items))
        for case in EXPECTED["field_parameters"]:
            table = self.table(case["model"], case["table"])
            expression = table["partitions"][0]["source"]["expression"]
            for field in case["fields"]:
                self.assertIn("NAMEOF(" + field + ")", expression)
            fields = next(column for column in table["columns"] if column["name"].endswith("Fields"))
            self.assertEqual("ParameterMetadata", fields["extendedProperties"][0]["name"])
            text = (LAB / "SalesA/SalesA.SemanticModel/definition/tables/Metric Selector.tmdl").read_text(encoding="utf-8")
            self.assertIn("groupByColumn: 'Metric Selector Fields'", text)
        for case in EXPECTED["functions"]:
            function = next(item for item in self.databases[case["model"]]["model"]["functions"] if item["name"] == case["name"])
            self.assertEqual(case["lineage_tag"], function["lineageTag"])
            for user in case["used_by"]:
                self.assertIn(case["name"] + "(", self.item(case["model"], user["table"], user["name"])["expression"])
        self.assertGreaterEqual(self.databases["SalesA"]["compatibilityLevel"], 1702)
        for case in EXPECTED["roles"]:
            role = next(item for item in self.databases[case["model"]]["model"]["roles"] if item["name"] == case["name"])
            permission = role["tablePermissions"][0]
            self.assertEqual(case["rls"][0]["filter"], permission["filterExpression"])
            self.assertEqual(case["ols"][0]["permission"], permission["columnPermissions"][0]["metadataPermission"])
        for case in EXPECTED["hierarchies"]:
            hierarchy = next(item for item in self.table(case["model"], case["table"])["hierarchies"] if item["name"] == case["name"])
            self.assertEqual(case["levels"], [level["name"] for level in hierarchy["levels"]])

    def test_report_cases_are_in_the_reports(self):
        documents = report_documents("SalesA")
        for case in EXPECTED["bookmarks"]:
            bookmark = documents[f"SalesA.Report/definition/bookmarks/{case['name']}.bookmark.json"]
            self.assertEqual(case["display_name"], bookmark["displayName"])
            self.assertIn({"name": case["name"]}, documents["SalesA.Report/definition/bookmarks/bookmarks.json"]["items"])
        extensions = documents["SalesA.Report/definition/reportExtensions.json"]["entities"]
        for case in EXPECTED["report_measures"]:
            entity = next(item for item in extensions if item["name"] == case["entity"])
            self.assertIn(case["name"], [measure["name"] for measure in entity["measures"]])

    def test_merge_lab_bytes_survive_windows_git_checkout(self):
        attributes = (REPOSITORY / ".gitattributes").read_text(encoding="utf-8").splitlines()
        self.assertIn("tests/fixtures/merge_lab/** -text", attributes)


class SourceManifestTests(unittest.TestCase):
    def test_model_settings_file_is_a_source_file(self):
        from backend.snapshots.manifest import source_manifest
        paths = {record["path"] for record in source_manifest(LAB / "SalesB")}
        self.assertIn("SalesB.SemanticModel/definition.pbism", paths)


if __name__ == "__main__":
    unittest.main()
