"""Authoritative metadata and source accounting regression cases."""
import json
from pathlib import Path
import tempfile
import unittest
import shutil
from backend.adapters.tabular_metadata import TabularMetadataAdapter
from backend.diff import compare_snapshots
from backend.snapshots import capture_snapshot
from backend.snapshots.scan import scan_snapshot
from backend.snapshots.literal_tables import literal_table
from tests.guarded_fixture import reference_project
from tests.test_pbir_coverage import schema_report


class CoverageExpansionTests(unittest.TestCase):
    def test_constant_table_rule_rejects_dynamic_expressions_and_references(self):
        self.assertIsNotNone(literal_table('DATATABLE("Key", INTEGER, {{1},{-2}})'))
        for expression in ('FILTER(FactSales, TRUE())', 'DATATABLE("Key", INTEGER, {{[Sales Amount]}})', 'DATATABLE("Key", INTEGER, {{NOW()}})', 'DATATABLE("Key", INTEGER, {{ExternalFunction()}})', 'DATATABLE("Key", INTEGER, {{1,2}})', 'DATATABLE("Key", INTEGER, {{1}}) + 1'):
            self.assertIsNone(literal_table(expression), expression)

    def test_invalid_pbir_is_static_failure_even_when_dependency_coverage_not_required(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            schema_report(root)
            path = root / "Sales.Report/definition/report.json"
            value = json.loads(path.read_text()); value["unexpected"] = "must not pass"
            path.write_text(json.dumps(value), encoding="utf-8")
            scan = scan_snapshot(root)
            self.assertEqual("FAILED", scan["validation_status"])
            self.assertTrue(any(issue["code"] == "PBIR_SCHEMA_INVALID" for issue in scan["validation"]["issues"]))

    def test_tom_tmdl_measure_and_column_properties_are_accounted_exactly(self):
        for object_kind, property_key, previous, value in (("measure", "formatString", "0.00", "0.000"), ("measure", "displayFolder", "Sales", "Revenue"), ("measure", "expression", "SUM(FactSales[SalesAmount])", "SUM(FactSales[SalesAmount]) * 2"), ("column", "formatString", "0", "000")):
            with self.subTest(property=property_key, object_kind=object_kind), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / "source"; reference_project(root)
                bim = root / "Sales.SemanticModel/model.bim"
                data = json.loads(bim.read_text())
                target = data["model"]["tables"][1]["measures" if object_kind == "measure" else "columns"][0]
                target[property_key] = previous
                bim.write_text(json.dumps(data), encoding="utf-8")
                tom = TabularMetadataAdapter().read(bim, include_documents=True)
                definition = root / "Sales.SemanticModel/definition"
                for relative, document in tom["tmdl_documents"].items():
                    path = definition / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(document.encode("utf-8"))
                bim.unlink()
                before_scan = scan_snapshot(root)
                before = capture_snapshot(root, "property-proof", analysis=before_scan, identity_manifest=before_scan["identity_manifest"])
                baseline_root = Path(temporary) / "baseline"
                shutil.copytree(root, baseline_root)
                table = definition / "tables/FactSales.tmdl"
                content = table.read_bytes()
                needle = ((" = " if property_key == "expression" else property_key + ": ") + previous).encode()
                replacement = ((" = " if property_key == "expression" else property_key + ": ") + value).encode()
                self.assertEqual(1, content.count(needle), content.decode())
                table.write_bytes(content.replace(needle, replacement))
                after_scan = scan_snapshot(root, identities=before_scan["identity_manifest"])
                after = capture_snapshot(root, "property-proof", analysis=after_scan, identity_manifest=after_scan["identity_manifest"])
                comparison = compare_snapshots(before, after, before_root=baseline_root, after_root=root)
                self.assertEqual([], comparison["unknown_differences"], comparison["unknown_differences"])
                self.assertEqual(1, len(comparison["property_changes"]), comparison["property_changes"])


if __name__ == "__main__": unittest.main()
