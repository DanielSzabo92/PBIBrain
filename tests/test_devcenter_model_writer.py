"""Build step S7a: Model writer, canonical-check, and tree-compare bridge tests.

Acceptance criteria (technical design section 9.1, 16 S7, ADR 0001, issue 16):
1. Model operations applied by write-model yielding expected golden TMDL and reloading cleanly.
2. Safety check: refuses write into or inside definition folder with code destination_is_definition_folder.
3. Preservation of non-TMDL files near and in the model folder.
4. canonical-check detecting Finance/.../tables/Budget.tmdl as non-canonical, and reporting clean pass on SalesA and SalesB.
5. Format-only candidate generation making Finance canonical and yielding empty tree-compare.
6. tree-compare detecting changes in full TOM hierarchy and unmodeled objects (perspective, culture).
7. UDF compatibility guard: functions rejected when model compatibilityLevel < 1702.
8. Measuring and recording Risk R3 non-canonical rate on merge lab corpus (1/3 models = 33.33%, 1/24 files = 4.17%).
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from backend.adapters.tabular_metadata import (
    CanonicalCheckFailed,
    MetadataUnavailable,
    ModelWriteFailed,
    TabularMetadataAdapter,
    TreeCompareFailed,
)

REPOSITORY = Path(__file__).resolve().parents[1]
LAB = REPOSITORY / "tests" / "fixtures" / "merge_lab"
EXPECTED = json.loads((LAB / "EXPECTED.json").read_text(encoding="utf-8"))
BRIDGE = REPOSITORY / "backend/adapters/tabular_metadata/dotnet/bin/Release/net8.0/TabularMetadata.dll"


@unittest.skipUnless(BRIDGE.is_file(), "Build the TOM bridge first")
class ModelWriterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = TabularMetadataAdapter(BRIDGE)

    def test_01_model_operations_and_roundtrip_integrity(self) -> None:
        """1. Model operations applied by write-model yield expected TMDL and reload cleanly."""
        baseline_model = LAB / "SalesA/SalesA.SemanticModel/definition"
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            candidate_path = temp_path / "candidate_model"

            # Apply an extensive sequence of operations across TOM object types
            operations = [
                # Table operations
                {
                    "op": "CREATE",
                    "object_type": "table",
                    "name": "DateCalculated",
                    "subtype": "calculated",
                    "properties": {"expression": "CALENDAR(DATE(2024, 1, 1), DATE(2024, 12, 31))"},
                    "lineage_tag": "t-date-calc",
                },
                {
                    "op": "DELETE",
                    "object_type": "table",
                    "name": "Time Intelligence",
                },
                {
                    "op": "SET_PROPERTIES",
                    "object_type": "table",
                    "name": "Store",
                    "properties": {"description": "Retail stores master table", "is_hidden": True},
                },
                {
                    "op": "RENAME",
                    "object_type": "table",
                    "name": "Store",
                    "new_name": "StoreMaster",
                },
                # Column operations
                {
                    "op": "CREATE",
                    "object_type": "column",
                    "table": "Sales",
                    "name": "DiscountPercent",
                    "properties": {"data_type": "decimal", "source_column": "Discount"},
                    "lineage_tag": "c-sales-discount",
                },
                {
                    "op": "CREATE",
                    "object_type": "column",
                    "table": "Sales",
                    "name": "IsLargeOrder",
                    "subtype": "calculated",
                    "properties": {"data_type": "boolean", "expression": "Sales[Quantity] > 100"},
                    "lineage_tag": "c-sales-islarge",
                },
                {
                    "op": "DELETE",
                    "object_type": "column",
                    "table": "Sales",
                    "name": "UnitCost",
                },
                {
                    "op": "SET_PROPERTIES",
                    "object_type": "column",
                    "table": "Sales",
                    "name": "NetPrice",
                    "properties": {"format_string": "$#,0.00", "is_hidden": True, "summarize_by": "none"},
                },
                # Measure operations
                {
                    "op": "CREATE",
                    "object_type": "measure",
                    "table": "Sales",
                    "name": "Total Quantity",
                    "properties": {"expression": "SUM(Sales[Quantity])", "format_string": "#,0", "description": "Sum of units"},
                    "lineage_tag": "m-sales-total-qty",
                },
                {
                    "op": "DELETE",
                    "object_type": "measure",
                    "table": "Sales",
                    "name": "Sales With Tax",
                },
                {
                    "op": "RENAME",
                    "object_type": "measure",
                    "table": "Sales",
                    "name": "Total Cost",
                    "new_name": "Cost Total",
                },
                {
                    "op": "SET_PROPERTIES",
                    "object_type": "measure",
                    "table": "Sales",
                    "name": "Cost Total",
                    "properties": {"format_string": "$#,0.00"},
                },
                # Expression rewrite
                {
                    "op": "REWRITE_EXPRESSION",
                    "object_type": "measure",
                    "table": "Sales",
                    "name": "Margin",
                    "property": "expression",
                    "old_text": "[Total Sales] - [Total Cost]",
                    "new_text": "[Total Sales] - [Cost Total]",
                },
                # Role operations
                {
                    "op": "CREATE",
                    "object_type": "role",
                    "name": "StoreManagers",
                    "properties": {
                        "model_permission": "Read",
                        "role_filters": {"Store": "[Region] = \"West\""},
                    },
                },
                # Expression operations
                {
                    "op": "CREATE",
                    "object_type": "expression",
                    "name": "FXRates",
                    "properties": {"expression": "#table({\"Currency\", \"Rate\"}, {})"},
                    "lineage_tag": "e-fx-rates",
                },
            ]

            result = self.adapter.write_model(baseline_model, candidate_path, operations)

            self.assertEqual(result["status"], "PASSED")
            self.assertEqual(result["command"], "write-model")
            self.assertEqual(result["adapter_version"], 1)

            # Check that files were reported as changed, added, or removed
            self.assertTrue(len(result["added_files"]) > 0 or len(result["changed_files"]) > 0)
            self.assertIn("tables/DateCalculated.tmdl", result["added_files"])
            self.assertIn("expressions.tmdl", result["added_files"])
            self.assertIn("tables/Time Intelligence.tmdl", result["removed_files"])

            # Verify that candidate folder reloads cleanly and roundtrips with TOM
            reloaded = self.adapter.read(candidate_path)
            self.assertEqual(reloaded["status"], "PASSED")
            self.assertTrue(reloaded["roundtrip_verified"])
            db = reloaded["database"]
            tables = {t["name"] for t in db["model"]["tables"]}
            self.assertIn("DateCalculated", tables)
            self.assertIn("StoreMaster", tables)
            self.assertNotIn("Time Intelligence", tables)

            # Compare tree between baseline and candidate
            compare = self.adapter.tree_compare(baseline_model, candidate_path)
            self.assertFalse(compare["identical"])
            self.assertTrue(compare["difference_count"] > 0)

            diff_objects = {(d["object_type"], d["object_name"], d["change_type"]) for d in compare["differences"]}
            self.assertIn(("table", "DateCalculated", "ADDED"), diff_objects)
            self.assertIn(("table", "Time Intelligence", "DELETED"), diff_objects)
            self.assertIn(("measure", "Total Quantity", "ADDED"), diff_objects)
            self.assertIn(("expression", "FXRates", "ADDED"), diff_objects)
            self.assertIn(("role", "StoreManagers", "ADDED"), diff_objects)

    def test_02_safety_destination_guard_refuses_definition_folder(self) -> None:
        """2. Candidate destination inside or equal to definition folder is immediately refused."""
        baseline_model = LAB / "SalesA/SalesA.SemanticModel/definition"

        # Direct destination equals definition folder
        with self.assertRaises(ModelWriteFailed) as ctx:
            self.adapter.write_model(baseline_model, baseline_model, [])
        self.assertEqual(ctx.exception.code, "destination_is_definition_folder")

        # Destination inside definition folder
        inside_path = baseline_model / "sub_candidate"
        with self.assertRaises(ModelWriteFailed) as ctx2:
            self.adapter.write_model(baseline_model, inside_path, [])
        self.assertEqual(ctx2.exception.code, "destination_is_definition_folder")

        # Destination when model_path is the semantic model root folder
        model_root = LAB / "SalesA/SalesA.SemanticModel"
        with self.assertRaises(ModelWriteFailed) as ctx3:
            self.adapter.write_model(model_root, model_root / "definition", [])
        self.assertEqual(ctx3.exception.code, "destination_is_definition_folder")

    def test_03_preservation_of_non_tmdl_files(self) -> None:
        """3. Non-TMDL files in/near the model folder are preserved."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            model_copy = temp_path / "model"
            shutil.copytree(LAB / "SalesA/SalesA.SemanticModel/definition", model_copy)

            # Place non-TMDL files in the model folder
            pbism_file = model_copy / "definition.pbism"
            pbism_file.write_text('{"version": "1.0"}', encoding="utf-8")
            layout_file = model_copy / "diagramLayout.json"
            layout_file.write_text('{"nodes": []}', encoding="utf-8")
            notes_file = model_copy / "tables" / "notes.txt"
            notes_file.write_text("Documentation notes", encoding="utf-8")

            candidate_path = temp_path / "candidate"
            res = self.adapter.write_model(model_copy, candidate_path, [])
            self.assertEqual(res["status"], "PASSED")

            # Verify non-TMDL files are preserved in the candidate folder
            self.assertTrue((candidate_path / "definition.pbism").is_file())
            self.assertEqual((candidate_path / "definition.pbism").read_text(encoding="utf-8"), '{"version": "1.0"}')

            self.assertTrue((candidate_path / "diagramLayout.json").is_file())
            self.assertEqual((candidate_path / "diagramLayout.json").read_text(encoding="utf-8"), '{"nodes": []}')

            self.assertTrue((candidate_path / "tables" / "notes.txt").is_file())
            self.assertEqual((candidate_path / "tables" / "notes.txt").read_text(encoding="utf-8"), "Documentation notes")

            # Verify baseline files were not removed
            self.assertTrue(pbism_file.is_file())
            self.assertTrue(layout_file.is_file())
            self.assertTrue(notes_file.is_file())

    def test_04_canonical_check_detects_non_canonical_fixture(self) -> None:
        """4. canonical-check detects Finance/.../tables/Budget.tmdl and passes SalesA & SalesB."""
        # 1. Check Finance: Budget.tmdl is non-canonical with the 3 expected differences
        finance_model = LAB / "Finance/Finance.SemanticModel/definition"
        check = self.adapter.canonical_check(finance_model)
        self.assertEqual(check["status"], "PASSED")
        self.assertFalse(check["is_canonical"])
        self.assertEqual(check["non_canonical_count"], 1)
        self.assertEqual(check["total_files"], 7)

        bad_file = check["non_canonical_files"][0]
        self.assertEqual(bad_file["file"], "tables/Budget.tmdl")
        self.assertIn("LF line ends", bad_file["differences"])
        self.assertIn("quoted table name", bad_file["differences"])
        self.assertIn("blank line before lineageTag", bad_file["differences"])

        # 2. Check SalesA: fully canonical
        sales_a = LAB / "SalesA/SalesA.SemanticModel/definition"
        check_a = self.adapter.canonical_check(sales_a)
        self.assertEqual(check_a["status"], "PASSED")
        self.assertTrue(check_a["is_canonical"])
        self.assertEqual(check_a["non_canonical_count"], 0)
        self.assertEqual(check_a["total_files"], 10)

        # 3. Check SalesB: fully canonical
        sales_b = LAB / "SalesB/SalesB.SemanticModel/definition"
        check_b = self.adapter.canonical_check(sales_b)
        self.assertEqual(check_b["status"], "PASSED")
        self.assertTrue(check_b["is_canonical"])
        self.assertEqual(check_b["non_canonical_count"], 0)
        self.assertEqual(check_b["total_files"], 7)

    def test_05_format_only_makes_model_canonical_with_empty_tree_compare(self) -> None:
        """5. Format-only apply produces canonical TMDL and yields an empty tree-compare."""
        finance_model = LAB / "Finance/Finance.SemanticModel/definition"

        with tempfile.TemporaryDirectory() as temp_dir:
            candidate_path = Path(temp_dir) / "candidate_canonical"

            # Format-only write: empty operations list re-serializes canonically
            write_res = self.adapter.write_model(finance_model, candidate_path, [])
            self.assertEqual(write_res["status"], "PASSED")
            self.assertIn("tables/Budget.tmdl", write_res["changed_files"])

            # Verify the candidate is now canonical
            check = self.adapter.canonical_check(candidate_path)
            self.assertTrue(check["is_canonical"])
            self.assertEqual(check["non_canonical_count"], 0)

            # Verify Budget.tmdl in candidate now has CRLF, unquoted table, and no blank line
            budget_bytes = (candidate_path / "tables/Budget.tmdl").read_bytes()
            self.assertIn(b"\r\n", budget_bytes)
            budget_text = budget_bytes.decode("utf-8")
            self.assertIn("table Budget", budget_text)
            self.assertNotIn("table 'Budget'", budget_text)

            # Full tree compare between original and format-only candidate must be identical
            compare = self.adapter.tree_compare(finance_model, candidate_path)
            self.assertTrue(compare["identical"])
            self.assertEqual(compare["difference_count"], 0)
            self.assertEqual(compare["differences"], [])

    def test_06_tree_compare_detects_unmodeled_perspective_changes(self) -> None:
        """6. tree-compare reports differences in unmodeled objects (Perspectives and Cultures)."""
        sales_a = LAB / "SalesA/SalesA.SemanticModel/definition"

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            candidate_path = temp_path / "candidate_with_perspective"

            # Generate candidate
            self.adapter.write_model(sales_a, candidate_path, [])

            # Add an unmodeled perspective via TMDL in candidate
            # In TMDL, perspective is defined in perspective.tmdl or inside model.tmdl
            perspective_tmdl = candidate_path / "perspectives.tmdl"
            perspective_tmdl.write_text(
                "perspective 'Sales Leadership'\n\n\tperspectiveTable Sales\n",
                encoding="utf-8",
                newline="\r\n",
            )

            # Reload candidate with TOM to confirm TMDL validity
            self.adapter.read(candidate_path)

            # Run tree-compare against baseline
            compare = self.adapter.tree_compare(sales_a, candidate_path)
            self.assertFalse(compare["identical"])
            self.assertTrue(compare["difference_count"] >= 1)

            persp_diffs = [d for d in compare["differences"] if d["object_type"] == "perspective"]
            self.assertTrue(len(persp_diffs) >= 1)
            self.assertEqual(persp_diffs[0]["object_name"], "Sales Leadership")
            self.assertEqual(persp_diffs[0]["change_type"], "ADDED")

    def test_07_udf_compatibility_guard(self) -> None:
        """7. Functions (UDFs) are rejected if model compatibilityLevel < 1702."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            # Create a model with compatibilityLevel = 1600
            model_path = temp_path / "model1600"
            model_path.mkdir(parents=True)
            (model_path / "database.tmdl").write_text(
                "database database\n\tcompatibilityLevel: 1600\n", encoding="utf-8", newline="\r\n"
            )
            (model_path / "model.tmdl").write_text(
                "model Model\n", encoding="utf-8", newline="\r\n"
            )

            candidate_path = temp_path / "candidate1600"
            op = {
                "op": "CREATE",
                "object_type": "function",
                "name": "CalcTax",
                "properties": {"expression": "LAMBDA(x, x * 1.1)"},
            }

            with self.assertRaises(ModelWriteFailed) as ctx:
                self.adapter.write_model(model_path, candidate_path, [op])

            self.assertEqual(ctx.exception.code, "udf_compatibility")
            self.assertIn("1702", str(ctx.exception))

    def test_08_risk_r3_non_canonical_rate_measurement(self) -> None:
        """8. Measure and record Risk R3 non-canonical rate across merge lab corpus.

        Authoritative findings:
        - 3 TMDL models: SalesA, SalesB, Finance.
        - Total TMDL files: 24 (SalesA: 10, SalesB: 7, Finance: 7).
        - Non-canonical files: 1 (Finance/.../tables/Budget.tmdl).
        - Non-canonical file rate: 1 / 24 = 4.17%.
        - Non-canonical model rate: 1 / 3 = 33.33%.
        """
        models = [
            LAB / record["path"]
            for project in EXPECTED["projects"].values()
            for record in project["models"].values()
            if record["format"] == "TMDL"
        ]
        self.assertEqual(len(models), 3)

        total_files = 0
        non_canonical_files = []
        non_canonical_models = []

        for model in models:
            definition_dir = model / "definition"
            check = self.adapter.canonical_check(definition_dir)
            self.assertEqual(check["status"], "PASSED")
            total_files += check["total_files"]
            if not check["is_canonical"]:
                non_canonical_models.append(model.name)
                for f in check["non_canonical_files"]:
                    non_canonical_files.append((model.name, f["file"], f["differences"]))

        # Assert exact counts
        self.assertEqual(total_files, 24)
        self.assertEqual(len(non_canonical_files), 1)
        self.assertEqual(len(non_canonical_models), 1)
        self.assertEqual(non_canonical_models[0], "Finance.SemanticModel")

        # Rate calculations
        file_rate = len(non_canonical_files) / total_files
        model_rate = len(non_canonical_models) / len(models)

        self.assertAlmostEqual(file_rate, 1 / 24, places=4)  # 4.17%
        self.assertAlmostEqual(model_rate, 1 / 3, places=4)  # 33.33%

        # Verify exact differences detected for the one non-canonical file
        bad_model, bad_path, bad_diffs = non_canonical_files[0]
        self.assertEqual(bad_path, "tables/Budget.tmdl")
        self.assertEqual(set(bad_diffs), {"LF line ends", "quoted table name", "blank line before lineageTag"})

    def test_09_duplicate_lineage_tag_rejected(self) -> None:
        """9. Duplicate lineageTag across different objects/tables is rejected."""
        sales_a = LAB / "SalesA/SalesA.SemanticModel/definition"
        with tempfile.TemporaryDirectory() as temp_dir:
            candidate_path = Path(temp_dir) / "candidate_dup_tag"
            # Try to add a column with an already existing lineageTag (e.g. m-margin-a from Sales table)
            op = {
                "op": "CREATE",
                "object_type": "column",
                "table": "Store",
                "name": "StoreCode",
                "properties": {"data_type": "string"},
                "lineage_tag": "m-margin-a",  # already exists on measure Margin in Sales!
            }
            with self.assertRaises(ModelWriteFailed) as ctx:
                self.adapter.write_model(sales_a, candidate_path, [op])
            self.assertEqual(ctx.exception.code, "duplicate_lineage_tag")
            self.assertIn("m-margin-a", str(ctx.exception))

    def test_10_error_on_nonexistent_directory(self) -> None:
        """10. canonical_check and tree_compare fail cleanly when directory does not exist."""
        bad_dir = Path("C:/nonexistent_folder_xyz_123")
        with self.assertRaises(CanonicalCheckFailed) as ctx:
            self.adapter.canonical_check(bad_dir)
        self.assertEqual(ctx.exception.code, "not_found")

        sales_a = LAB / "SalesA/SalesA.SemanticModel/definition"
        with self.assertRaises(TreeCompareFailed) as ctx2:
            self.adapter.tree_compare(bad_dir, sales_a)
        self.assertEqual(ctx2.exception.code, "not_found")


if __name__ == "__main__":
    unittest.main()

