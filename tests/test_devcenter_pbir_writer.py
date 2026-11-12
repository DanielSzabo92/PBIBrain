"""Build step S7b: PBIR report writer and refused item tests.

Acceptance criteria (technical design sections 8, 9.2, 16 S7, issue 17):
1. Page copy with a name clash keeps the old-to-new map and fixes pages.json,
   visual groups (parentGroupName), drillthrough (pageBinding and filterConfig),
   and visualInteractions.
2. REBIND_FIELD changes each field location (queryState projections, sortDefinition,
   filterConfig field and Where/From conditions, pageBinding.parameters[].fieldExpr,
   formatting object expressions, Hierarchy/HierarchyLevel, reportExtensions.json)
   and updates queryRef and nativeQueryRef.
3. A changed file keeps its $schema version; copied donor files keep their donor
   $schema version.
4. Output validates against the vendored Microsoft PBIR schemas.
5. No file is written with a UTF-8 BOM (0xEF 0xBB 0xBF).
6. Refused items (bookmark copy, sync slicer groups, custom visuals, static
   resources, baseline folder destination, PBIR-Legacy) raise PBIRWriteError
   with fixed reason codes and messages.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from backend.adapters.pbir import (
    PBIRWriteError,
    PBIRWriter,
    REFUSED_REASONS,
    write_report,
)
from backend.devcenter.compare.extract import load_objects
from backend.devcenter.compare.rows import SessionSource, build_rows
from backend.devcenter.plan.compiler import PlanInput, compile_plan
from backend.devcenter.sources.kinds import detect_local_source

REPOSITORY = Path(__file__).resolve().parents[1]
LAB = REPOSITORY / "tests" / "fixtures" / "merge_lab"
SALES_A_REPORT = LAB / "SalesA" / "SalesA.Report"
SALES_B_REPORT = LAB / "SalesB" / "SalesB.Report"
LEGACY_REPORT = LAB / "Legacy" / "Legacy.Report"


class PBIRWriterTests(unittest.TestCase):
    def test_01_page_copy_with_name_clash_fixes_pages_groups_drillthrough_and_interactions(self) -> None:
        """1. Page copy with a name clash keeps old-to-new map and fixes pages.json, groups, drillthrough, and interactions."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            donor_dir = temp_path / "Donor.Report"
            shutil.copytree(SALES_A_REPORT, donor_dir)

            # Enrich donor "detail" page with drillthrough pageBinding, bound filterConfig,
            # visual group (target -> targetgroup), and visualInteractions (including one dangling visual).
            donor_detail_page = donor_dir / "definition" / "pages" / "detail" / "page.json"
            page_doc = json.loads(donor_detail_page.read_text(encoding="utf-8"))
            page_doc["type"] = "Drillthrough"
            page_doc["filterConfig"] = {
                "filters": [
                    {
                        "name": "detail_store_filter",
                        "type": "Categorical",
                        "field": {
                            "Column": {
                                "Expression": {"SourceRef": {"Entity": "Store"}},
                                "Property": "Store Name",
                            }
                        },
                    }
                ]
            }
            page_doc["pageBinding"] = {
                "name": "detail",
                "type": "Drillthrough",
                "parameters": [
                    {
                        "name": "param_store",
                        "boundFilter": "detail_store_filter",
                        "fieldExpr": {
                            "Column": {
                                "Expression": {"SourceRef": {"Entity": "Store"}},
                                "Property": "Store Name",
                            }
                        },
                    }
                ],
            }
            page_doc["visualInteractions"] = [
                {"source": "calendarmatrix", "target": "target", "type": "DataFilter"},
                {"source": "target", "target": "missing_visual", "type": "NoFilter"},
            ]
            donor_detail_page.write_text(json.dumps(page_doc, indent=2) + "\n", encoding="utf-8")

            # Also give baseline "detail" page an existing pageBinding with the same names so they clash
            baseline_dir = temp_path / "Baseline.Report"
            shutil.copytree(SALES_A_REPORT, baseline_dir)
            base_detail_page = baseline_dir / "definition" / "pages" / "detail" / "page.json"
            base_page_doc = json.loads(base_detail_page.read_text(encoding="utf-8"))
            base_page_doc["filterConfig"] = copy.deepcopy(page_doc["filterConfig"])
            base_page_doc["pageBinding"] = copy.deepcopy(page_doc["pageBinding"])
            base_detail_page.write_text(json.dumps(base_page_doc, indent=2) + "\n", encoding="utf-8")

            candidate_dir = temp_path / "Candidate.Report"
            result = write_report(
                baseline_dir,
                candidate_dir,
                operations=[
                    {
                        "op": "COPY_PAGE",
                        "domain": "report",
                        "object_type": "page",
                        "row_key": "page:detail@donor",
                        "source_id": "donor",
                        "source_key": "page:detail",
                        "page_id": "detail",
                        "name": "Detail (Donor)",
                        "replace": False,
                    }
                ],
                donor_paths={"donor": donor_dir},
            )

            # 1. Old-to-new maps are recorded for page, visuals, and binding
            self.assertEqual(result["page_name_map"], {"detail": "detail_2"})
            self.assertEqual(
                result["visual_name_map"],
                {
                    "calendarmatrix": "calendarmatrix_2",
                    "target": "target_2",
                    "targetgroup": "targetgroup_2",
                },
            )
            self.assertEqual(result["binding_name_map"], {"detail": "detail_2"})

            # 2. pages.json has the new page appended and activePageName preserved
            pages_meta = json.loads((candidate_dir / "definition" / "pages" / "pages.json").read_text(encoding="utf-8"))
            self.assertEqual(pages_meta["pageOrder"], ["overview", "detail", "detail_2"])
            self.assertEqual(pages_meta["activePageName"], "overview")

            # 3. Copied page.json has updated name, displayName, pageBinding, filterConfig, and visualInteractions
            copied_page_path = candidate_dir / "definition" / "pages" / "detail_2" / "page.json"
            self.assertTrue(copied_page_path.is_file())
            copied_page = json.loads(copied_page_path.read_text(encoding="utf-8"))
            self.assertEqual(copied_page["name"], "detail_2")
            self.assertEqual(copied_page["displayName"], "Detail (Donor)")
            self.assertEqual(copied_page["pageBinding"]["name"], "detail_2")

            param = copied_page["pageBinding"]["parameters"][0]
            self.assertEqual(param["name"], "param_store_2")
            self.assertEqual(param["boundFilter"], "detail_store_filter_2")
            filter_item = copied_page["filterConfig"]["filters"][0]
            self.assertEqual(filter_item["name"], "detail_store_filter_2")

            # Dangling visual "missing_visual" was dropped; valid interaction was remapped
            self.assertEqual(
                copied_page["visualInteractions"],
                [{"source": "calendarmatrix_2", "target": "target_2", "type": "DataFilter"}],
            )

            # 4. Visual group parentGroupName on target_2 points to targetgroup_2
            target_visual = json.loads(
                (candidate_dir / "definition" / "pages" / "detail_2" / "visuals" / "target_2" / "visual.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(target_visual["name"], "target_2")
            self.assertEqual(target_visual["parentGroupName"], "targetgroup_2")

            group_visual = json.loads(
                (
                    candidate_dir / "definition" / "pages" / "detail_2" / "visuals" / "targetgroup_2" / "visual.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(group_visual["name"], "targetgroup_2")
            self.assertIn("visualGroup", group_visual)

    def test_02_rebind_field_across_all_pbir_locations(self) -> None:
        """2. REBIND_FIELD updates projections, queryRef, nativeQueryRef, sortDefinition, filterConfig, pageBinding, objects, and reportExtensions."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            baseline_dir = temp_path / "Baseline.Report"
            shutil.copytree(SALES_A_REPORT, baseline_dir)

            # Add sortDefinition, filterConfig (with From/Where), custom nativeQueryRef, and formatting objects to a visual
            visual_path = baseline_dir / "definition" / "pages" / "overview" / "visuals" / "marginbymonth" / "visual.json"
            visual_doc = json.loads(visual_path.read_text(encoding="utf-8"))
            # Add a second projection with a custom user label in nativeQueryRef (must stay unchanged per section 6.5)
            visual_doc["visual"]["query"]["queryState"]["Y"]["projections"].append(
                {
                    "field": {
                        "Measure": {
                            "Expression": {"SourceRef": {"Entity": "Sales"}},
                            "Property": "Total Sales",
                        }
                    },
                    "queryRef": "Sales.Total Sales",
                    "nativeQueryRef": "Custom Revenue Label",
                }
            )
            visual_doc["visual"]["query"]["sortDefinition"] = {
                "sort": [
                    {
                        "field": {
                            "Measure": {
                                "Expression": {"SourceRef": {"Entity": "Sales"}},
                                "Property": "Margin",
                            }
                        },
                        "direction": "Descending",
                    }
                ]
            }
            visual_doc["filterConfig"] = {
                "filters": [
                    {
                        "name": "f_month",
                        "type": "Categorical",
                        "field": {
                            "Column": {
                                "Expression": {"SourceRef": {"Entity": "Date"}},
                                "Property": "Month",
                            }
                        },
                        "filter": {
                            "Version": 2,
                            "From": [{"Name": "d", "Entity": "Date", "Type": 0}],
                            "Where": [
                                {
                                    "Condition": {
                                        "In": {
                                            "Expressions": [
                                                {
                                                    "Column": {
                                                        "Expression": {"SourceRef": {"Source": "d"}},
                                                        "Property": "Month",
                                                    }
                                                }
                                            ],
                                            "Values": [[{"Literal": {"Value": "'Jan'"}}]],
                                        }
                                    }
                                }
                            ],
                        },
                    }
                ]
            }
            visual_path.write_text(json.dumps(visual_doc, indent=2) + "\n", encoding="utf-8")

            candidate_dir = temp_path / "Candidate.Report"
            operations = [
                # Pointer-based rebind of Category projection (Date.Month -> Calendar.MonthName)
                {
                    "op": "REBIND_FIELD",
                    "domain": "report",
                    "object_type": "visual",
                    "row_key": "visual:overview/marginbymonth",
                    "pointer": "/visual/query/queryState/Category/projections/0/field",
                    "old": {"kind": "column", "entity": "Date", "property": "Month"},
                    "new": {"kind": "column", "entity": "Calendar", "property": "MonthName"},
                    "query_ref": {"old": "Date.Month", "new": "Calendar.MonthName"},
                    "native_query_ref": {"old": "Month", "new": "MonthName"},
                },
                # Pointer-based rebind of visual filterConfig (also updates semantic filter From/Where)
                {
                    "op": "REBIND_FIELD",
                    "domain": "report",
                    "object_type": "visual",
                    "row_key": "visual:overview/marginbymonth",
                    "pointer": "/filterConfig/filters/0/field",
                    "old": {"kind": "column", "entity": "Date", "property": "Month"},
                    "new": {"kind": "column", "entity": "Calendar", "property": "MonthName"},
                },
                # Pointer-based rebind of Y projection 0 (Sales.Margin -> Metrics.Gross Margin)
                {
                    "op": "REBIND_FIELD",
                    "domain": "report",
                    "object_type": "visual",
                    "row_key": "visual:overview/marginbymonth",
                    "pointer": "/visual/query/queryState/Y/projections/0/field",
                    "old": {"kind": "measure", "entity": "Sales", "property": "Margin"},
                    "new": {"kind": "measure", "entity": "Metrics", "property": "Gross Margin"},
                },
                # Pointer-based rebind of sortDefinition
                {
                    "op": "REBIND_FIELD",
                    "domain": "report",
                    "object_type": "visual",
                    "row_key": "visual:overview/marginbymonth",
                    "pointer": "/visual/query/sortDefinition/sort/0/field",
                    "old": {"kind": "measure", "entity": "Sales", "property": "Margin"},
                    "new": {"kind": "measure", "entity": "Metrics", "property": "Gross Margin"},
                },
                # Pointer-based rebind of Y projection 1 with custom nativeQueryRef
                {
                    "op": "REBIND_FIELD",
                    "domain": "report",
                    "object_type": "visual",
                    "row_key": "visual:overview/marginbymonth",
                    "pointer": "/visual/query/queryState/Y/projections/1/field",
                    "old": {"kind": "measure", "entity": "Sales", "property": "Total Sales"},
                    "new": {"kind": "measure", "entity": "Sales", "property": "Net Sales"},
                },
                # Pointer-based rebind of HierarchyLevel on calendarmatrix
                {
                    "op": "REBIND_FIELD",
                    "domain": "report",
                    "object_type": "visual",
                    "row_key": "visual:detail/calendarmatrix",
                    "pointer": "/visual/query/queryState/Rows/projections/0/field",
                    "old": {"kind": "hierarchy_level", "entity": "Date", "property": "Calendar", "level": "Year"},
                    "new": {"kind": "hierarchy_level", "entity": "CalendarDim", "property": "Fiscal", "level": "FiscalYear"},
                },
                # Report-wide tree-walk rebind of Sales.Total Sales -> Sales.Net Sales (updates totalsales, calendarmatrix, reportExtensions)
                {
                    "op": "REBIND_FIELD",
                    "domain": "report",
                    "old": {"kind": "measure", "entity": "Sales", "property": "Total Sales"},
                    "new": {"kind": "measure", "entity": "Sales", "property": "Net Sales"},
                },
            ]

            write_report(baseline_dir, candidate_dir, operations)

            updated_visual = json.loads(
                (candidate_dir / "definition" / "pages" / "overview" / "visuals" / "marginbymonth" / "visual.json").read_text(
                    encoding="utf-8"
                )
            )
            cat_proj = updated_visual["visual"]["query"]["queryState"]["Category"]["projections"][0]
            self.assertEqual(cat_proj["field"]["Column"]["Expression"]["SourceRef"]["Entity"], "Calendar")
            self.assertEqual(cat_proj["field"]["Column"]["Property"], "MonthName")
            self.assertEqual(cat_proj["queryRef"], "Calendar.MonthName")
            self.assertEqual(cat_proj["nativeQueryRef"], "MonthName")

            y_proj_0 = updated_visual["visual"]["query"]["queryState"]["Y"]["projections"][0]
            self.assertEqual(y_proj_0["field"]["Measure"]["Expression"]["SourceRef"]["Entity"], "Metrics")
            self.assertEqual(y_proj_0["field"]["Measure"]["Property"], "Gross Margin")
            self.assertEqual(y_proj_0["queryRef"], "Metrics.Gross Margin")
            self.assertEqual(y_proj_0["nativeQueryRef"], "Gross Margin")

            # Custom nativeQueryRef "Custom Revenue Label" was NOT equal to "Total Sales", so it is preserved
            y_proj_1 = updated_visual["visual"]["query"]["queryState"]["Y"]["projections"][1]
            self.assertEqual(y_proj_1["field"]["Measure"]["Property"], "Net Sales")
            self.assertEqual(y_proj_1["queryRef"], "Sales.Net Sales")
            self.assertEqual(y_proj_1["nativeQueryRef"], "Custom Revenue Label")

            # sortDefinition updated
            sort_field = updated_visual["visual"]["query"]["sortDefinition"]["sort"][0]["field"]
            self.assertEqual(sort_field["Measure"]["Expression"]["SourceRef"]["Entity"], "Metrics")
            self.assertEqual(sort_field["Measure"]["Property"], "Gross Margin")

            # filterConfig field AND semantic query From/Where updated
            f_item = updated_visual["filterConfig"]["filters"][0]
            self.assertEqual(f_item["field"]["Column"]["Expression"]["SourceRef"]["Entity"], "Calendar")
            self.assertEqual(f_item["field"]["Column"]["Property"], "MonthName")
            self.assertEqual(f_item["filter"]["From"][0]["Entity"], "Calendar")
            where_col = f_item["filter"]["Where"][0]["Condition"]["In"]["Expressions"][0]["Column"]
            self.assertEqual(where_col["Property"], "MonthName")

            # HierarchyLevel on calendarmatrix updated
            cal_visual = json.loads(
                (candidate_dir / "definition" / "pages" / "detail" / "visuals" / "calendarmatrix" / "visual.json").read_text(
                    encoding="utf-8"
                )
            )
            hl_proj = cal_visual["visual"]["query"]["queryState"]["Rows"]["projections"][0]
            hl = hl_proj["field"]["HierarchyLevel"]
            self.assertEqual(hl["Expression"]["Hierarchy"]["Expression"]["SourceRef"]["Entity"], "CalendarDim")
            self.assertEqual(hl["Expression"]["Hierarchy"]["Hierarchy"], "Fiscal")
            self.assertEqual(hl["Level"], "FiscalYear")
            self.assertEqual(hl_proj["queryRef"], "CalendarDim.Fiscal.FiscalYear")

            # reportExtensions.json references updated
            ext_doc = json.loads((candidate_dir / "definition" / "reportExtensions.json").read_text(encoding="utf-8"))
            ref_measure = ext_doc["entities"][0]["measures"][0]["references"]["measures"][0]
            self.assertEqual(ref_measure, {"entity": "Sales", "name": "Net Sales"})

    def test_03_schema_version_preserved_and_untouched_files_preserved(self) -> None:
        """3. Changed files keep their $schema version; copied donor files keep donor $schema version; untouched files stay byte-equal."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            candidate_dir = temp_path / "Candidate.Report"

            # SalesA uses page/2.1.0, visualContainer/2.13.0, pagesMetadata/1.1.0, report/3.3.0
            # SalesB uses page/2.0.0, visualContainer/2.0.0, pagesMetadata/1.0.0, report/2.0.0
            result = write_report(
                SALES_A_REPORT,
                candidate_dir,
                operations=[
                    {
                        "op": "COPY_PAGE",
                        "domain": "report",
                        "object_type": "page",
                        "row_key": "page:summary",
                        "source_id": "src-b",
                        "source_key": "page:summary",
                        "page_id": "summary",
                        "replace": False,
                    },
                    {
                        "op": "REBIND_FIELD",
                        "domain": "report",
                        "object_type": "visual",
                        "row_key": "visual:summary/salesamount",
                        "pointer": "/visual/query/queryState/Values/projections/0/field",
                        "old": {"kind": "measure", "entity": "Sales", "property": "Sales Amount"},
                        "new": {"kind": "measure", "entity": "Sales", "property": "Total Sales"},
                    },
                    {
                        "op": "REBIND_FIELD",
                        "domain": "report",
                        "object_type": "visual",
                        "row_key": "visual:overview/totalsales",
                        "pointer": "/visual/query/queryState/Values/projections/0/field",
                        "old": {"kind": "measure", "entity": "Sales", "property": "Total Sales"},
                        "new": {"kind": "measure", "entity": "Sales", "property": "Gross Sales"},
                    },
                ],
                donor_paths={"src-b": SALES_B_REPORT},
            )

            # Target pages.json keeps 1.1.0
            pages_doc = json.loads((candidate_dir / "definition" / "pages" / "pages.json").read_text(encoding="utf-8"))
            self.assertEqual(
                pages_doc["$schema"],
                "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.1.0/schema.json",
            )

            # Modified target visual keeps 2.13.0
            totalsales_doc = json.loads(
                (candidate_dir / "definition" / "pages" / "overview" / "visuals" / "totalsales" / "visual.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                totalsales_doc["$schema"],
                "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.13.0/schema.json",
            )

            # Copied donor page keeps 2.0.0 and copied donor visual keeps 2.0.0 even after REBIND_FIELD
            summary_page_doc = json.loads(
                (candidate_dir / "definition" / "pages" / "summary" / "page.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                summary_page_doc["$schema"],
                "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.0.0/schema.json",
            )
            salesamount_doc = json.loads(
                (candidate_dir / "definition" / "pages" / "summary" / "visuals" / "salesamount" / "visual.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                salesamount_doc["$schema"],
                "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.0.0/schema.json",
            )

            # Untouched files (definition.pbir, definition/report.json, definition/version.json) are byte-equal
            for untouched in ("definition.pbir", "definition/report.json", "definition/version.json"):
                self.assertEqual(
                    (candidate_dir / untouched).read_bytes(),
                    (SALES_A_REPORT / untouched).read_bytes(),
                )
                self.assertNotIn(untouched, result["changed_files"])

    def test_04_output_validates_against_vendored_schemas_and_has_no_bom(self) -> None:
        """4 & 5. Output validates against vendored schemas and no file has a UTF-8 BOM."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            baseline_with_bom = temp_path / "BomBaseline.Report"
            shutil.copytree(SALES_B_REPORT, baseline_with_bom)

            # Inject UTF-8 BOM into baseline files to verify the writer strips and never writes BOM
            pages_file = baseline_with_bom / "definition" / "pages" / "pages.json"
            pages_file.write_bytes(b"\xef\xbb\xbf" + pages_file.read_bytes())

            candidate_dir = temp_path / "Candidate.Report"
            result = write_report(
                baseline_with_bom,
                candidate_dir,
                operations=[
                    {
                        "op": "COPY_PAGE",
                        "domain": "report",
                        "object_type": "page",
                        "row_key": "page:overview",
                        "source_id": "src-a",
                        "source_key": "page:overview",
                        "page_id": "overview",
                        "replace": False,
                    },
                    {
                        "op": "CREATE_REPORT_MEASURE",
                        "domain": "report",
                        "object_type": "report_measure",
                        "row_key": "report_measure:Sales/Sales Target",
                        "source_id": "src-a",
                        "source_key": "report_measure:Sales/Sales Target",
                        "table": "Sales",
                        "name": "Sales Target",
                        "properties": {
                            "expression": "[Sales Amount] * 1.1",
                            "format_string": "$#,0.00",
                            "display_folder": "Targets",
                        },
                    },
                ],
                donor_paths={"src-a": SALES_A_REPORT},
            )

            self.assertEqual(result["validation"]["status"], "COMPLETE")
            self.assertEqual(result["validation"]["issues"], [])

            # Check every file in candidate_dir has no UTF-8 BOM
            for file_path in candidate_dir.rglob("*"):
                if file_path.is_file():
                    raw = file_path.read_bytes()
                    self.assertFalse(raw.startswith(b"\xef\xbb\xbf"), f"BOM found in {file_path}")

    def test_05_compile_plan_integration_with_pbir_writer(self) -> None:
        """End-to-end integration: compile_plan operations applied by write_report."""
        src_a = detect_local_source(LAB / "SalesA" / "SalesA.pbip")
        src_b = detect_local_source(LAB / "SalesB" / "SalesB.pbip")
        obj_a = load_objects(src_a)
        obj_b = load_objects(src_b)

        compare = build_rows(
            [SessionSource("src-a", obj_a), SessionSource("src-b", obj_b)],
            target_model="src-a",
            target_report="src-a",
        )
        # Take page:summary from src-b and promote report_measure:Sales/Sales Target
        plan = compile_plan(
            PlanInput(
                session_id="ses-pbir-writer",
                result=compare,
                target_model="src-a",
                target_report="src-a",
                sources={"src-a": "SalesA", "src-b": "SalesB"},
                merge_choices={
                    "page:summary": {"kind": "take", "source_id": "src-b"},
                    "report_measure:Sales/Sales Target": {"kind": "promote", "source_id": "src-a", "new_name": "Promoted Target"},
                },
            )
        )
        self.assertIn(plan["status"], {"valid", "valid_with_warnings"})

        with tempfile.TemporaryDirectory() as temp_dir:
            candidate_dir = Path(temp_dir) / "Candidate.Report"
            result = write_report(
                SALES_A_REPORT,
                candidate_dir,
                plan["operations"],
                donor_paths={"src-a": SALES_A_REPORT, "src-b": SALES_B_REPORT},
            )

            # 1. Summary page and its visuals were copied, and salesamount was rebound from Sales Amount to Total Sales
            salesamount_path = candidate_dir / "definition" / "pages" / "summary" / "visuals" / "salesamount" / "visual.json"
            self.assertTrue(salesamount_path.is_file())
            salesamount_doc = json.loads(salesamount_path.read_text(encoding="utf-8"))
            proj = salesamount_doc["visual"]["query"]["queryState"]["Values"]["projections"][0]
            self.assertEqual(proj["field"]["Measure"]["Property"], "Total Sales")
            self.assertEqual(proj["queryRef"], "Sales.Total Sales")
            self.assertEqual(proj["nativeQueryRef"], "Total Sales")

            # 2. Promoted report measure was rebound on detail/target visual and removed from reportExtensions.json
            target_vis_path = candidate_dir / "definition" / "pages" / "detail" / "visuals" / "target" / "visual.json"
            target_vis_doc = json.loads(target_vis_path.read_text(encoding="utf-8"))
            target_proj = target_vis_doc["visual"]["query"]["queryState"]["Values"]["projections"][0]
            self.assertEqual(target_proj["field"]["Measure"]["Property"], "Promoted Target")
            self.assertEqual(target_proj["queryRef"], "Sales.Promoted Target")

            ext_doc = json.loads((candidate_dir / "definition" / "reportExtensions.json").read_text(encoding="utf-8"))
            self.assertEqual(ext_doc["entities"], [])
            self.assertEqual(result["validation"]["issues"], [])

    def test_06_remove_field_and_delete_page_and_visual_operations(self) -> None:
        """REMOVE_FIELD, DELETE_VISUAL, DELETE_PAGE, REPLACE_REPORT_MEASURE, and REWRITE_EXPRESSION."""
        with tempfile.TemporaryDirectory() as temp_dir:
            candidate_dir = Path(temp_dir) / "Candidate.Report"
            write_report(
                SALES_A_REPORT,
                candidate_dir,
                operations=[
                    # Remove first projection from metrictable (which has 2 projections; 1 stays)
                    {
                        "op": "REMOVE_FIELD",
                        "domain": "report",
                        "object_type": "visual",
                        "row_key": "visual:overview/metrictable",
                        "pointer": "/visual/query/queryState/Values/projections/0/field",
                        "field": {"kind": "column", "entity": "Store", "property": "Store Name"},
                    },
                    # Delete timeslicer visual on overview
                    {
                        "op": "DELETE_VISUAL",
                        "domain": "report",
                        "object_type": "visual",
                        "row_key": "visual:overview/timeslicer",
                    },
                    # Rewrite report measure expression
                    {
                        "op": "REWRITE_EXPRESSION",
                        "domain": "report",
                        "object_type": "report_measure",
                        "row_key": "report_measure:Sales/Sales Target",
                        "table": "Sales",
                        "name": "Sales Target",
                        "new_text": "[Total Sales] * 1.25",
                    },
                    # Delete detail page
                    {
                        "op": "DELETE_PAGE",
                        "domain": "report",
                        "object_type": "page",
                        "row_key": "page:detail",
                    },
                ],
            )

            metrictable_doc = json.loads(
                (candidate_dir / "definition" / "pages" / "overview" / "visuals" / "metrictable" / "visual.json").read_text(
                    encoding="utf-8"
                )
            )
            projections = metrictable_doc["visual"]["query"]["queryState"]["Values"]["projections"]
            self.assertEqual(len(projections), 1)
            self.assertEqual(projections[0]["field"]["Column"]["Property"], "Metric Selector")

            self.assertFalse(
                (candidate_dir / "definition" / "pages" / "overview" / "visuals" / "timeslicer").exists()
            )
            self.assertFalse((candidate_dir / "definition" / "pages" / "detail").exists())

            pages_meta = json.loads((candidate_dir / "definition" / "pages" / "pages.json").read_text(encoding="utf-8"))
            self.assertEqual(pages_meta["pageOrder"], ["overview"])

            ext_doc = json.loads((candidate_dir / "definition" / "reportExtensions.json").read_text(encoding="utf-8"))
            self.assertEqual(ext_doc["entities"][0]["measures"][0]["expression"], "[Total Sales] * 1.25")

    def test_07_refused_items_give_fixed_reasons(self) -> None:
        """6. Refused items (bookmark copy, sync slicer groups, custom visuals, static resources, source folder, legacy) give fixed reasons."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            candidate_dir = temp_path / "Candidate.Report"

            # 1. Bookmark copy operation refused with fixed reason
            with self.assertRaises(PBIRWriteError) as ctx:
                write_report(
                    SALES_A_REPORT,
                    candidate_dir,
                    operations=[
                        {
                            "op": "COPY_BOOKMARK",
                            "domain": "report",
                            "object_type": "bookmark",
                            "row_key": "bookmark:ytdview",
                        }
                    ],
                )
            self.assertEqual(ctx.exception.code, "bookmark_copy_not_supported")
            self.assertEqual(ctx.exception.message, REFUSED_REASONS["bookmark_copy_not_supported"])

            # 2. Sync slicer group on copied visual refused with fixed reason
            donor_sync = temp_path / "DonorSync.Report"
            shutil.copytree(SALES_B_REPORT, donor_sync)
            sync_vis_path = donor_sync / "definition" / "pages" / "summary" / "visuals" / "salesamount" / "visual.json"
            sync_vis_doc = json.loads(sync_vis_path.read_text(encoding="utf-8"))
            sync_vis_doc["visual"]["syncGroup"] = {"groupName": "RegionSync", "fieldChanges": True}
            sync_vis_path.write_text(json.dumps(sync_vis_doc, indent=2) + "\n", encoding="utf-8")

            with self.assertRaises(PBIRWriteError) as ctx:
                write_report(
                    SALES_A_REPORT,
                    candidate_dir,
                    operations=[
                        {
                            "op": "COPY_VISUAL",
                            "domain": "report",
                            "object_type": "visual",
                            "row_key": "visual:summary/salesamount",
                            "source_id": "donor-sync",
                            "source_key": "visual:summary/salesamount",
                            "page_id": "overview",
                            "visual_id": "salesamount",
                        }
                    ],
                    donor_paths={"donor-sync": donor_sync},
                )
            self.assertEqual(ctx.exception.code, "sync_slicer_group_not_supported")
            self.assertEqual(ctx.exception.message, REFUSED_REASONS["sync_slicer_group_not_supported"])

            # 3. Custom visual refused with fixed reason
            donor_cv = temp_path / "DonorCustomVisual.Report"
            shutil.copytree(SALES_B_REPORT, donor_cv)
            cv_report_path = donor_cv / "definition" / "report.json"
            cv_report_doc = json.loads(cv_report_path.read_text(encoding="utf-8"))
            cv_report_doc["publicCustomVisuals"] = ["bulletChart1443347686880"]
            cv_report_path.write_text(json.dumps(cv_report_doc, indent=2) + "\n", encoding="utf-8")
            cv_vis_path = donor_cv / "definition" / "pages" / "summary" / "visuals" / "salesamount" / "visual.json"
            cv_vis_doc = json.loads(cv_vis_path.read_text(encoding="utf-8"))
            cv_vis_doc["visual"]["visualType"] = "bulletChart1443347686880"
            cv_vis_path.write_text(json.dumps(cv_vis_doc, indent=2) + "\n", encoding="utf-8")

            with self.assertRaises(PBIRWriteError) as ctx:
                write_report(
                    SALES_A_REPORT,
                    candidate_dir,
                    operations=[
                        {
                            "op": "COPY_PAGE",
                            "domain": "report",
                            "object_type": "page",
                            "row_key": "page:summary",
                            "source_id": "donor-cv",
                            "source_key": "page:summary",
                            "page_id": "summary",
                        }
                    ],
                    donor_paths={"donor-cv": donor_cv},
                )
            self.assertEqual(ctx.exception.code, "custom_visual_not_supported")
            self.assertEqual(ctx.exception.message, REFUSED_REASONS["custom_visual_not_supported"])

            # 4. Static resource on copied visual/page refused with fixed reason
            donor_sr = temp_path / "DonorStaticResource.Report"
            shutil.copytree(SALES_B_REPORT, donor_sr)
            sr_vis_path = donor_sr / "definition" / "pages" / "summary" / "visuals" / "salesamount" / "visual.json"
            sr_vis_doc = json.loads(sr_vis_path.read_text(encoding="utf-8"))
            sr_vis_doc["visual"]["objects"] = {
                "general": [
                    {
                        "properties": {
                            "imageUrl": {
                                "expr": {
                                    "ResourcePackageItem": {
                                        "PackageName": "RegisteredResources",
                                        "PackageType": 1,
                                        "ItemName": "logo.png",
                                    }
                                }
                            }
                        }
                    }
                ]
            }
            sr_vis_path.write_text(json.dumps(sr_vis_doc, indent=2) + "\n", encoding="utf-8")

            with self.assertRaises(PBIRWriteError) as ctx:
                write_report(
                    SALES_A_REPORT,
                    candidate_dir,
                    operations=[
                        {
                            "op": "COPY_PAGE",
                            "domain": "report",
                            "object_type": "page",
                            "row_key": "page:summary",
                            "source_id": "donor-sr",
                            "source_key": "page:summary",
                            "page_id": "summary",
                        }
                    ],
                    donor_paths={"donor-sr": donor_sr},
                )
            self.assertEqual(ctx.exception.code, "static_resource_not_supported")
            self.assertEqual(ctx.exception.message, REFUSED_REASONS["static_resource_not_supported"])

            # 5. Writing directly into baseline report folder or its definition folder is refused
            with self.assertRaises(PBIRWriteError) as ctx:
                PBIRWriter(SALES_A_REPORT, SALES_A_REPORT)
            self.assertEqual(ctx.exception.code, "destination_is_source_folder")

            with self.assertRaises(PBIRWriteError) as ctx:
                PBIRWriter(SALES_A_REPORT, SALES_A_REPORT / "definition")
            self.assertEqual(ctx.exception.code, "destination_is_source_folder")

            # 6. PBIR-Legacy baseline or donor is refused
            with self.assertRaises(PBIRWriteError) as ctx:
                PBIRWriter(LEGACY_REPORT, candidate_dir)
            self.assertEqual(ctx.exception.code, "pbir_legacy_not_supported")

    def test_08_replace_page_copy_visual_clash_and_extended_rebinds(self) -> None:
        """Page replace=True, standalone COPY_VISUAL clash, Aggregation/objects/pageBinding rebind, and dataset rebind."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            donor_dir = temp_path / "Donor.Report"
            shutil.copytree(SALES_B_REPORT, donor_dir)

            # Enrich donor visual with an Aggregation field and conditional formatting expression in objects
            vis_path = donor_dir / "definition" / "pages" / "summary" / "visuals" / "salesamount" / "visual.json"
            vis_doc = json.loads(vis_path.read_text(encoding="utf-8"))
            vis_doc["visual"]["query"]["queryState"]["Values"]["projections"].append(
                {
                    "field": {
                        "Aggregation": {
                            "Expression": {
                                "Column": {
                                    "Expression": {"SourceRef": {"Entity": "Sales"}},
                                    "Property": "Quantity",
                                }
                            },
                            "Function": 0,
                        }
                    },
                    "queryRef": "Sum(Sales.Quantity)",
                    "nativeQueryRef": "Quantity",
                }
            )
            vis_doc["visual"]["objects"] = {
                "dataPoint": [
                    {
                        "properties": {
                            "fill": {
                                "solid": {
                                    "color": {
                                        "expr": {
                                            "Measure": {
                                                "Expression": {"SourceRef": {"Entity": "Sales"}},
                                                "Property": "Sales Amount",
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                ]
            }
            vis_path.write_text(json.dumps(vis_doc, indent=2) + "\n", encoding="utf-8")

            candidate_dir = temp_path / "Candidate.Report"
            result = write_report(
                SALES_A_REPORT,
                candidate_dir,
                operations=[
                    # Replace existing "detail" page with donor "summary" page (replace=True)
                    {
                        "op": "COPY_PAGE",
                        "domain": "report",
                        "object_type": "page",
                        "row_key": "page:detail",
                        "source_id": "src-b",
                        "source_key": "page:summary",
                        "page_id": "detail",
                        "replace": True,
                    },
                    # Copy salesamount visual again onto overview page (clashes with salesamount on detail -> salesamount_2)
                    {
                        "op": "COPY_VISUAL",
                        "domain": "report",
                        "object_type": "visual",
                        "row_key": "visual:summary/salesamount#new",
                        "source_id": "src-b",
                        "source_key": "visual:summary/salesamount",
                        "page_id": "overview",
                        "visual_id": "salesamount",
                    },
                    # Rebind Aggregation field via pointer
                    {
                        "op": "REBIND_FIELD",
                        "domain": "report",
                        "object_type": "visual",
                        "row_key": "visual:summary/salesamount#new",
                        "pointer": "/visual/query/queryState/Values/projections/1/field/Aggregation/Expression",
                        "old": {"kind": "column", "entity": "Sales", "property": "Quantity"},
                        "new": {"kind": "column", "entity": "Orders", "property": "OrderQty"},
                    },
                    # Rebind conditional formatting Measure expression in objects via tree walk
                    {
                        "op": "REBIND_FIELD",
                        "domain": "report",
                        "object_type": "visual",
                        "row_key": "visual:summary/salesamount#new",
                        "old": {"kind": "measure", "entity": "Sales", "property": "Sales Amount"},
                        "new": {"kind": "measure", "entity": "Sales", "property": "Total Sales"},
                    },
                    # Replace report measure
                    {
                        "op": "REPLACE_REPORT_MEASURE",
                        "domain": "report",
                        "object_type": "report_measure",
                        "row_key": "report_measure:Sales/Sales Target",
                        "table": "Sales",
                        "name": "Sales Target",
                        "properties": {
                            "expression": "[Total Sales] * 1.15",
                            "data_type": "decimal",
                            "format_string": "$#,0",
                        },
                    },
                ],
                donor_paths={"src-b": donor_dir},
            )

            self.assertEqual(result["page_name_map"]["summary"], "detail")
            self.assertEqual(result["visual_name_map"]["salesamount"], "salesamount_2")

            copied_vis = json.loads(
                (candidate_dir / "definition" / "pages" / "overview" / "visuals" / "salesamount_2" / "visual.json").read_text(
                    encoding="utf-8"
                )
            )
            agg_proj = copied_vis["visual"]["query"]["queryState"]["Values"]["projections"][1]
            agg_col = agg_proj["field"]["Aggregation"]["Expression"]["Column"]
            self.assertEqual(agg_col["Expression"]["SourceRef"]["Entity"], "Orders")
            self.assertEqual(agg_col["Property"], "OrderQty")
            self.assertEqual(agg_proj["queryRef"], "Sum(Orders.OrderQty)")
            self.assertEqual(agg_proj["nativeQueryRef"], "OrderQty")

            color_expr = copied_vis["visual"]["objects"]["dataPoint"][0]["properties"]["fill"]["solid"]["color"]["expr"]
            self.assertEqual(color_expr["Measure"]["Property"], "Total Sales")

            ext_doc = json.loads((candidate_dir / "definition" / "reportExtensions.json").read_text(encoding="utf-8"))
            measure = ext_doc["entities"][0]["measures"][0]
            self.assertEqual(measure["dataType"], "Decimal")
            self.assertEqual(measure["expression"], "[Total Sales] * 1.15")
            self.assertEqual(measure["formatString"], "$#,0")


if __name__ == "__main__":
    unittest.main()
