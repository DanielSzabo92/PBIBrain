"""Phase 1 scanner and canonical normalization acceptance tests."""

import copy
import tempfile
import unittest
from pathlib import Path

from backend.scanner.model_reader import ModelReader
from backend.scanner.report_reader import ReportReader
from backend.scanner.normalization import normalize_model, normalize_report

from tests.fixtures.phase1_sources import (
    MODEL_ID,
    REPORT_A_ID,
    REPORT_B_ID,
    model_source,
    renamed_model_source,
    report_source,
)
from tests.support.canonical import as_mapping, by_type, records


class ScannerContractTests(unittest.TestCase):
    def test_source_readers_unwrap_power_bi_envelopes(self):
        model = model_source()
        report = report_source(REPORT_A_ID)
        self.assertEqual(ModelReader().read({"model": model}), model)
        self.assertEqual(ReportReader().read({"report": report}), report)

    def test_model_normalization_emits_all_mechanical_v1_model_types(self):
        normalized = records(normalize_model(model_source()))
        typed = by_type(normalized)
        expected = {
            "MODEL",
            "TABLE",
            "COLUMN",
            "MEASURE",
            "RELATIONSHIP",
            "FIELD_PARAMETER",
            "SHARED_EXPRESSION",
            "USER_DEFINED_FUNCTION",
            "CALCULATION_GROUP",
            "CALCULATION_ITEM",
        }
        self.assertTrue(expected <= typed.keys())
        self.assertGreaterEqual(len(normalized), len(expected))

        for value in normalized:
            item = as_mapping(value)
            self.assertTrue(
                {
                    "id",
                    "type",
                    "name",
                    "description",
                    "model_id",
                    "report_id",
                    "source_id",
                    "status",
                } <= item.keys(),
                item,
            )
            if item["type"] != "MODEL":
                self.assertEqual(item["model_id"], f"model:{MODEL_ID}")
            self.assertEqual(item["status"], "factual")
            self.assertNotIn("business_concept", item)

        model = typed["MODEL"][0]
        self.assertEqual(model["id"], f"model:{MODEL_ID}")
        self.assertEqual(model["description"], "Synthetic model for canonical graph acceptance tests.")
        table = next(item for item in typed["TABLE"] if item["source_id"] == "table-sales")
        self.assertEqual(table["name"], "Sales")
        self.assertFalse(table["properties"]["hidden"])
        measure = typed["MEASURE"][0]
        self.assertEqual(measure["source_id"], "measure-sales")
        self.assertEqual(measure["properties"]["format_string"], "#,##0")

    def test_report_normalization_emits_report_page_visual_and_filter_types(self):
        normalized = records(normalize_report(report_source(REPORT_A_ID)))
        typed = by_type(normalized)
        self.assertTrue({"REPORT", "PAGE", "VISUAL", "VISUAL_FILTER", "PAGE_FILTER", "REPORT_FILTER"} <= typed.keys())
        for value in normalized:
            item = as_mapping(value)
            self.assertTrue(
                {
                    "id",
                    "type",
                    "name",
                    "description",
                    "model_id",
                    "report_id",
                    "source_id",
                    "status",
                } <= item.keys(),
                item,
            )
            self.assertEqual(item["report_id"], f"report:{REPORT_A_ID}")
            self.assertEqual(item["status"], "factual")
        report = typed["REPORT"][0]
        self.assertEqual(report["model_id"], f"model:{MODEL_ID}")
        visual = typed["VISUAL"][0]
        self.assertEqual(visual["properties"]["visual_type"], "columnChart")
        self.assertEqual(visual["properties"]["title"], "Sales by date")

    def test_native_source_ids_keep_identity_across_display_rename(self):
        before = by_type(records(normalize_model(model_source())))
        after = by_type(records(normalize_model(renamed_model_source())))
        before_measure = before["MEASURE"][0]
        after_measure = after["MEASURE"][0]
        self.assertEqual(before_measure["source_id"], after_measure["source_id"])
        self.assertEqual(before_measure["id"], after_measure["id"])
        self.assertEqual(before_measure["name"], "Sales")
        self.assertEqual(after_measure["name"], "Net Sales")

    def test_generated_identity_is_persisted_and_reused(self):
        source = model_source()
        source["tables"][0]["measures"][0].pop("id")
        with tempfile.TemporaryDirectory() as directory:
            mapping_path = Path(directory) / "source-mapping.json"
            first = records(normalize_model(source, identity_path=mapping_path))
            first_measure = next(item for item in by_type(first)["MEASURE"] if item["name"] == "Sales")
            self.assertTrue(first_measure["id"])
            self.assertTrue(mapping_path.exists())

            renamed = copy.deepcopy(source)
            renamed["tables"][0]["measures"][0]["name"] = "Net Sales"
            second = records(normalize_model(renamed, identity_path=mapping_path))
            second_measure = next(item for item in by_type(second)["MEASURE"] if item["name"] == "Net Sales")
            self.assertEqual(first_measure["id"], second_measure["id"])

    def test_normalization_does_not_mutate_adapter_source(self):
        source = model_source()
        original = copy.deepcopy(source)
        normalize_model(source)
        self.assertEqual(source, original)


if __name__ == "__main__":
    unittest.main()
