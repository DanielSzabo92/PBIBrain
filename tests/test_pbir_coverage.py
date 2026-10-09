from __future__ import annotations
from copy import deepcopy
import json
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from backend.adapters.pbir.validation import validate_report_documents
from backend.snapshots.scan import scan_snapshot
from tests.guarded_fixture import reference_project

PREFIX = "https://developer.microsoft.com/json-schemas/fabric/item/report/"

def schema_report(root: Path):
    reference_project(root, report=True)
    report = root / "Sales.Report"
    def write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2), encoding="utf-8")
    write(report / "definition.pbir", {"$schema": PREFIX + "definitionProperties/2.0.0/schema.json", "version": "4.0", "datasetReference": {"byPath": {"path": "../Sales.SemanticModel"}}})
    write(report / "definition/report.json", {"$schema": PREFIX + "definition/report/2.0.0/schema.json", "themeCollection": {"baseTheme": {"name": "CY24SU11", "reportVersionAtImport": "5.59", "type": "SharedResources"}}})
    write(report / "definition/pages/pages.json", {"$schema": PREFIX + "definition/pagesMetadata/1.0.0/schema.json", "pageOrder": ["month"], "activePageName": "month"})
    write(report / "definition/pages/month/page.json", {"$schema": PREFIX + "definition/page/2.0.0/schema.json", "name": "month", "displayName": "Monthly", "displayOption": "FitToPage", "height": 720, "width": 1280})
    visual_path = report / "definition/pages/month/visuals/sales/visual.json"
    visual = json.loads(visual_path.read_text())
    visual.update({"$schema": PREFIX + "definition/visualContainer/2.0.0/schema.json", "position": {"x": 0, "y": 0, "width": 600, "height": 300}})
    for role, state in visual["visual"]["query"]["queryState"].items():
        for projection in state["projections"]:
            field = next(iter(projection["field"].values()))
            projection["queryRef"] = field["Expression"]["SourceRef"]["Entity"] + "." + field["Property"]
    write(visual_path, visual)

def documents(root: Path):
    return {path.relative_to(root).as_posix(): json.loads(path.read_text()) for path in root.rglob("*") if path.suffix in {".json", ".pbir"}}

class PBIRCoverageTests(unittest.TestCase):
    def test_pinned_schema_bytes_survive_windows_git_conversion(self):
        repository = Path(__file__).resolve().parents[1]
        relative = Path("backend/adapters/pbir/schemas")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copytree(repository / relative, root / relative)
            shutil.copyfile(repository / ".gitattributes", root / ".gitattributes")
            def git(*arguments):
                return subprocess.check_output(["git", "-C", str(root), *arguments], stderr=subprocess.DEVNULL)
            git("init", "-q")
            git("config", "core.autocrlf", "true")
            git("add", "--all")
            checkout = root / "checkout"
            git("checkout-index", "--all", "--prefix=" + checkout.as_posix() + "/")
            manifest = json.loads((root / relative / "manifest.json").read_text())
            for path, record in manifest["files"].items():
                with self.subTest(schema=path):
                    blob = git("show", ":" + relative.as_posix() + "/" + path)
                    self.assertEqual(record["sha256"], hashlib.sha256(blob).hexdigest())
                    self.assertEqual(blob, (checkout / relative / path).read_bytes())

    def test_schema_and_bindings_are_independent_and_complete(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            schema_report(root)
            result = validate_report_documents(documents(root))
            self.assertEqual("COMPLETE", result["status"], result)
            scan = scan_snapshot(root)
            self.assertEqual("COMPLETE", scan["completeness"]["status"], scan["completeness"])
            visual = next(node for node in scan["graph"]["nodes"] if node["type"] == "VISUAL")
            self.assertTrue(visual["properties"]["field_ids"])

    def test_unknown_schema_property_and_dynamic_context_block(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); schema_report(root)
            original = documents(root)
            changed = deepcopy(original)
            changed["Sales.Report/definition/pages/month/page.json"]["unknown"] = True
            self.assertIn("PBIR_SCHEMA_INVALID", {item["code"] for item in validate_report_documents(changed)["issues"]})
            changed = deepcopy(original)
            changed["Sales.Report/definition/pages/month/page.json"]["$schema"] = PREFIX + "definition/page/99.0.0/schema.json"
            self.assertIn("PBIR_SCHEMA_UNSUPPORTED", {item["code"] for item in validate_report_documents(changed)["issues"]})
            changed["Sales.Report/definition/bookmarks/bookmarks.json"] = {}
            self.assertIn("PBIR_UNSUPPORTED_ARTIFACT", {item["code"] for item in validate_report_documents(changed)["issues"]})

if __name__ == "__main__": unittest.main()
