"""Targeted unit and integration tests for Milestone 1 open issues (#79-#86, #89)."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from backend.adapters.pbir.writer import PBIRWriteError, PBIRWriter
from backend.adapters.tabular_metadata import TabularMetadataAdapter
from backend.devcenter.apply import rescan
from backend.devcenter.apply.pipeline import ApplyJob, GuardPipeline
from backend.devcenter.apply.steps import ApplyFailure
from backend.devcenter.compare import extract, rows as compare_rows, service as compare_service
from backend.devcenter.errors import DevCenterError
from backend.devcenter.plan.compiler import PlanInput, compile_plan
from backend.devcenter.sources.kinds import MODEL_TMDL, REPORT_PBIR, LocalSource, detect_local_source
from backend.devcenter.sources.objects import object_index
from backend.devcenter.sources.targets import write_empty_target
from backend.graph.loader import FactGraphBuilder
from backend.validation.integrity import validate_integrity
from change_guard.audit import AuditStore
from change_guard.promotion.local import LocalPromotion

REPOSITORY = Path(__file__).resolve().parents[1]
LAB = REPOSITORY / "tests" / "fixtures" / "merge_lab"
BRIDGE = REPOSITORY / "backend/adapters/tabular_metadata/dotnet/bin/Release/net8.0/TabularMetadata.dll"


class Issue79Tests(unittest.TestCase):
    @unittest.skipUnless(BRIDGE.is_file(), "Build the TOM bridge first")
    def test_tmdl_scripts_folder_ignored_via_definition_resolution(self) -> None:
        adapter = TabularMetadataAdapter(BRIDGE)
        with tempfile.TemporaryDirectory() as tmp:
            model_dir = Path(tmp) / "SalesA.SemanticModel"
            shutil.copytree(LAB / "SalesA/SalesA.SemanticModel", model_dir)
            scripts_dir = model_dir / "TMDLScripts"
            scripts_dir.mkdir()
            # Invalid standalone TMDL script that would crash TOM if model_dir were read instead of definition/
            (scripts_dir / "Script 1.tmdl").write_text("createOrReplace\n\tref table Sales\n", encoding="utf-8")

            read_payload = adapter.read(model_dir)
            self.assertEqual(read_payload["status"], "PASSED")

            check_payload = adapter.canonical_check(model_dir)
            self.assertEqual(check_payload["status"], "PASSED")
            self.assertTrue(check_payload["is_canonical"])

            cmp_payload = adapter.tree_compare(model_dir, model_dir)
            self.assertEqual(cmp_payload["status"], "PASSED")
            self.assertTrue(cmp_payload["identical"])

            src = LocalSource(
                root=model_dir,
                display_name="SalesA",
                kind="semantic_model",
                model_dir=model_dir,
                model_format=MODEL_TMDL,
                report_dir=None,
                report_format=None,
            )
            objs = extract.load_objects(src, adapter=adapter)
            self.assertTrue(any(o.kind == "table" and o.name == "Sales" for o in objs.model))

    def test_compare_service_surfaces_unreadable_source_error(self) -> None:
        class _FakeDevCenter:
            def _load(self, record: dict) -> LocalSource:
                raise DevCenterError("action_not_allowed", "Model could not be parsed by TOM", {"reason": "model_unreadable"})

        doc = {
            "sources": [{"source_id": "src-fin", "display_name": "Finance"}],
            "source_status": {"src-fin": "ok"},
            "target": {},
            "alignment_overrides": {},
            "compare_mode": "default",
            "merge_choices": {},
            "source_marks": [],
        }
        result = compare_service.compute(_FakeDevCenter(), doc)
        self.assertEqual(len(result.source_errors), 1)
        self.assertEqual(result.source_errors[0]["warning_id"], "source_unreadable")
        self.assertEqual(result.source_errors[0]["source_id"], "src-fin")
        self.assertIn("Model could not be parsed", result.source_errors[0]["message"])
        self.assertTrue(any(w.get("warning_id") == "source_unreadable" and w.get("source_id") == "src-fin" for w in result.warnings))


class Issue80Tests(unittest.TestCase):
    def test_scan_detects_duplicate_tmdl_declarations_and_ignores_tmdlscripts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "BrokenProj"
            pbip = write_empty_target(root, "Broken")
            defn = root / "Broken.SemanticModel" / "definition"
            tables_dir = defn / "tables"
            tables_dir.mkdir(parents=True, exist_ok=True)
            (defn / "model.tmdl").write_text(
                "model Model\n\tculture: en-US\n\nexpression SourceFolder = \"C:\\\\Data\" meta [IsParameterQuery=true]\n",
                encoding="utf-8",
            )
            (defn / "expressions.tmdl").write_text(
                "expression SourceFolder = \"C:\\\\Other\" meta [IsParameterQuery=true]\n",
                encoding="utf-8",
            )
            (tables_dir / "Sales.tmdl").write_text("table Sales\n\tcolumn Id\n\t\tdataType: int64\n", encoding="utf-8")
            # Duplicate inside TMDLScripts/ should NOT be flagged
            scripts = defn / "TMDLScripts"
            scripts.mkdir()
            (scripts / "script.tmdl").write_text("table Sales\n", encoding="utf-8")

            graph = FactGraphBuilder().build(pbip)
            validation = validate_integrity(graph)
            self.assertFalse(validation.valid)
            dup_issues = [i for i in validation.issues if i.code == "duplicate_tmdl_declaration"]
            self.assertEqual(len(dup_issues), 1)
            self.assertEqual(dup_issues[0].severity, "ERROR")
            self.assertIn("SourceFolder", dup_issues[0].message)
            self.assertEqual(sorted(dup_issues[0].details["files"]), ["expressions.tmdl", "model.tmdl"])


class Issue81Tests(unittest.TestCase):
    @unittest.skipUnless(BRIDGE.is_file(), "Build the TOM bridge first")
    def test_empty_target_skeleton_passes_canonical_check_and_receives_model_header(self) -> None:
        adapter = TabularMetadataAdapter(BRIDGE)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target_dir = root / "EmptyOut"
            write_empty_target(target_dir, "EmptyOut")
            empty_model_dir = target_dir / "EmptyOut.SemanticModel"

            # Canonical check must NOT deadlock on empty skeleton's model.tmdl
            check = adapter.canonical_check(empty_model_dir)
            self.assertTrue(check["is_canonical"], check)
            self.assertEqual(check["non_canonical_files"], [])

            # Compile a plan merging a donor table into empty target with model_headers
            donor_table = extract.CompareObject(
                kind="table", subtype="table", domain=extract.MODEL, source_key="table:Orders", name="Orders",
                props={"description": None, "hidden": False, "data_category": None},
            )
            donor_col = extract.CompareObject(
                kind="column", subtype="data_column", domain=extract.MODEL, source_key="column:Orders/OrderId",
                name="OrderId", table="Orders",
                props={"data_type": "int64", "source_column": "OrderId", "hidden": False, "summarize_by": "none"},
            )
            donor_part = extract.CompareObject(
                kind="partition", subtype="m_partition", domain=extract.MODEL, source_key="partition:Orders/Orders",
                name="Orders", table="Orders",
                props={"m_text": 'let\n    Source = #table({"OrderId"}, {})\nin\n    Source', "mode": "import"},
            )
            res = compare_rows.build_rows(
                [
                    compare_rows.SessionSource("tgt", extract.SourceObjects([], [], model_header={})),
                    compare_rows.SessionSource("donor", extract.SourceObjects([donor_table, donor_col, donor_part], [], model_header={
                        "culture": "en-US",
                        "default_power_bi_data_source_version": "powerBI_V3",
                        "source_query_culture": "en-US",
                        "data_access_options": {"legacyRedirects": True, "returnErrorValuesAsNull": True},
                    })),
                ],
                target_model="tgt",
                target_report=None,
                merge_choices={"table:Orders": {"kind": "take", "source_id": "donor"}},
            )
            res.model_headers = {
                "tgt": {},
                "donor": {
                    "culture": "en-US",
                    "default_power_bi_data_source_version": "powerBI_V3",
                    "source_query_culture": "en-US",
                    "data_access_options": {"legacyRedirects": True, "returnErrorValuesAsNull": True},
                },
            }
            plan = compile_plan(PlanInput(
                session_id="s-81",
                result=res,
                target_model="tgt",
                target_report=None,
                sources={"tgt": "EmptyOut", "donor": "Donor"},
                merge_choices={"table:Orders": {"kind": "take", "source_id": "donor"}},
            ))
            model_ops = [op for op in plan["operations"] if op["domain"] == "model"]
            self.assertTrue(any(op["object_type"] == "model" and op["op"] == "SET_PROPERTIES" for op in model_ops))

            before_index = object_index(detect_local_source(target_dir / "EmptyOut.pbip"))
            cand_model_dir = root / "Candidate.SemanticModel"
            cand_def = cand_model_dir / "definition"
            adapter.write_model(empty_model_dir / "definition", cand_def, model_ops)
            reloaded = adapter.read(cand_def)["database"]["model"]
            self.assertEqual(reloaded.get("culture"), "en-US")
            self.assertEqual(reloaded.get("defaultPowerBIDataSourceVersion"), "powerBI_V3")
            self.assertEqual(reloaded.get("sourceQueryCulture"), "en-US")
            self.assertTrue((reloaded.get("dataAccessOptions") or {}).get("legacyRedirects"))

            after_index = object_index(LocalSource(
                kind="tmdl_folder",
                root=cand_model_dir,
                display_name="Candidate",
                model_dir=cand_model_dir,
                model_format=MODEL_TMDL,
                report_dir=None,
                report_format=None,
            ))
            self.assertIn("model:Model", before_index)
            self.assertIn("model:Model", after_index)
            self.assertNotEqual(before_index["model:Model"], after_index["model:Model"])
            self.assertEqual(rescan.differences(model_ops, before_index, after_index), [])

    def test_rescan_ignores_model_header_set_properties(self) -> None:
        donor_table = extract.CompareObject(
            kind="table", subtype="table", domain=extract.MODEL, source_key="table:Orders", name="Orders",
            props={"description": None, "hidden": False, "data_category": None},
        )
        res = compare_rows.build_rows(
            [
                compare_rows.SessionSource("tgt", extract.SourceObjects([], [], model_header={})),
                compare_rows.SessionSource("donor", extract.SourceObjects([donor_table], [], model_header={
                    "culture": "en-US",
                    "default_power_bi_data_source_version": "powerBI_V3",
                })),
            ],
            target_model="tgt",
            target_report=None,
            merge_choices={"table:Orders": {"kind": "take", "source_id": "donor"}},
        )
        res.model_headers = {
            "tgt": {},
            "donor": {
                "culture": "en-US",
                "default_power_bi_data_source_version": "powerBI_V3",
            },
        }
        plan = compile_plan(PlanInput(
            session_id="s-81-rescan",
            result=res,
            target_model="tgt",
            target_report=None,
            sources={"tgt": "EmptyOut", "donor": "Donor"},
            merge_choices={"table:Orders": {"kind": "take", "source_id": "donor"}},
        ))
        model_ops = [op for op in plan["operations"] if op["domain"] == "model"]
        self.assertTrue(any(op["object_type"] == "model" and op["row_key"] == "model:Model" for op in model_ops))

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before_dir = root / "Before.SemanticModel"
            (before_dir / "definition").mkdir(parents=True)
            (before_dir / "definition" / "model.tmdl").write_text("model Model\n", encoding="utf-8")

            after_dir = root / "After.SemanticModel"
            (after_dir / "definition" / "tables").mkdir(parents=True)
            (after_dir / "definition" / "model.tmdl").write_text(
                "model Model\n\tculture: en-US\n\tdefaultPowerBIDataSourceVersion: powerBI_V3\n",
                encoding="utf-8",
            )
            (after_dir / "definition" / "tables" / "Orders.tmdl").write_text("table Orders\n", encoding="utf-8")

            before_index = object_index(LocalSource(
                kind="tmdl_folder", root=before_dir, display_name="Before",
                model_dir=before_dir, model_format=MODEL_TMDL, report_dir=None, report_format=None,
            ))
            after_index = object_index(LocalSource(
                kind="tmdl_folder", root=after_dir, display_name="After",
                model_dir=after_dir, model_format=MODEL_TMDL, report_dir=None, report_format=None,
            ))
            self.assertIn("model:Model", before_index)
            self.assertIn("model:Model", after_index)
            self.assertNotEqual(before_index["model:Model"], after_index["model:Model"])

            # 1. Expected model header mutation via SET_PROPERTIES passes rescan
            self.assertEqual(rescan.differences(model_ops, before_index, after_index), [])
            # 2. Unexpected model header mutation without SET_PROPERTIES is caught
            ops_without_model = [op for op in model_ops if op["object_type"] != "model"]
            self.assertEqual(
                rescan.differences(ops_without_model, before_index, after_index),
                [{"object": "model:Model", "expected": "unchanged", "found": "changed"}],
            )
            # 3. Missing model:Model in after is caught as present/absent
            after_missing_model = {k: v for k, v in after_index.items() if k != "model:Model"}
            self.assertEqual(
                rescan.differences(model_ops, before_index, after_missing_model),
                [{"object": "model:Model", "expected": "present", "found": "absent"}],
            )


class Issue82And83And85ModelWriterTests(unittest.TestCase):
    @unittest.skipUnless(BRIDGE.is_file(), "Build the TOM bridge first")
    def test_82_83_85_properties_partition_fold_sort_by_column_relationship_direction_and_annotations(self) -> None:
        adapter = TabularMetadataAdapter(BRIDGE)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target_dir = root / "EmptyOut"
            write_empty_target(target_dir, "EmptyOut")
            base_def = target_dir / "EmptyOut.SemanticModel/definition"
            cand_dir = root / "candidate"

            ops = [
                # Table + same-name partition (should fold cleanly without duplicate partition error)
                {
                    "op": "CREATE", "object_type": "table", "name": "Dim_Customers",
                    "properties": {"hidden": True, "description": "Customers dim", "annotations": {"PBI_ResultType": "Table"}},
                },
                {
                    "op": "CREATE", "object_type": "partition", "table": "Dim_Customers", "name": "Dim_Customers",
                    "properties": {"m_text": 'let\n    Source = #table({"Customer_Key", "MonthName", "MonthNumber"}, {})\nin\n    Source', "mode": "import"},
                },
                # Non-alphabetical columns with deferred sort_by_column (MonthName created BEFORE MonthNumber!)
                {
                    "op": "CREATE", "object_type": "column", "table": "Dim_Customers", "name": "Customer_Key",
                    "properties": {"data_type": "int64", "source_column": "Customer_Key", "key": True, "annotations": {"SummarizationSetBy": "Automatic"}},
                },
                {
                    "op": "CREATE", "object_type": "column", "table": "Dim_Customers", "name": "MonthName",
                    "properties": {"data_type": "string", "source_column": "MonthName", "sort_by_column": "MonthNumber"},
                },
                {
                    "op": "CREATE", "object_type": "column", "table": "Dim_Customers", "name": "MonthNumber",
                    "properties": {"data_type": "int64", "source_column": "MonthNumber"},
                },
                # Hierarchy + SET_PROPERTIES on hierarchy & partition
                {
                    "op": "CREATE", "object_type": "hierarchy", "table": "Dim_Customers", "name": "Calendar",
                    "properties": {"levels": ["MonthName"], "hidden": True},
                },
                {
                    "op": "SET_PROPERTIES", "object_type": "hierarchy", "table": "Dim_Customers", "name": "Calendar",
                    "properties": {"description": "Updated hierarchy", "hidden": False, "levels": ["MonthNumber", "MonthName"]},
                },
                {
                    "op": "SET_PROPERTIES", "object_type": "partition", "table": "Dim_Customers", "name": "Dim_Customers",
                    "properties": {"m_text": 'let\n    Source = #table({"Customer_Key", "MonthName", "MonthNumber"}, {{1, "Jan", 1}})\nin\n    Source'},
                },
                # Fact table (sorts AFTER Dim_Customers alphabetically!)
                {"op": "CREATE", "object_type": "table", "name": "Fact_Orders", "properties": {}},
                {
                    "op": "CREATE", "object_type": "column", "table": "Fact_Orders", "name": "Customer_Key",
                    "properties": {"data_type": "int64", "source_column": "Customer_Key"},
                },
                # Relationship Fact_Orders[Customer_Key] -> Dim_Customers[Customer_Key]
                {
                    "op": "CREATE", "object_type": "relationship", "name": "rel_orders_cust",
                    "properties": {
                        "ends": [["Fact_Orders", "Customer_Key"], ["Dim_Customers", "Customer_Key"]],
                        "cardinality": "many:one",
                        "active": False,
                        "cross_filter_direction": "bothDirections",
                        "security_filter_direction": "bothDirections",
                        "referential_integrity": True,
                    },
                },
                # Calculated table with IsPrivate + ShowAsVariationsOnly + CalculatedTableColumn (#85)
                {
                    "op": "CREATE", "object_type": "table", "name": "LocalDateTable_Test", "subtype": "calculated_table",
                    "properties": {
                        "expression": "Calendar(Date(2024,1,1), Date(2024,12,31))",
                        "is_hidden": True,
                        "is_private": True,
                        "show_as_variations_only": True,
                        "annotations": {"__PBI_LocalDateTable": "true"},
                    },
                },
                {
                    "op": "CREATE", "object_type": "column", "table": "LocalDateTable_Test", "name": "Date",
                    "subtype": "calculated_table_column",
                    "properties": {"data_type": "dateTime", "source_column": "[Date]", "is_name_inferred": True},
                },
            ]

            adapter.write_model(base_def, cand_dir, ops)
            model = adapter.read(cand_dir)["database"]["model"]
            tables = {t["name"]: t for t in model["tables"]}

            dim = tables["Dim_Customers"]
            self.assertTrue(dim.get("isHidden"))
            self.assertEqual({a["name"]: a["value"] for a in dim.get("annotations", [])}.get("PBI_ResultType"), "Table")
            # Partition folded and updated via SET_PROPERTIES
            self.assertEqual(len(dim["partitions"]), 1)
            self.assertIn("Jan", "\n".join(dim["partitions"][0]["source"]["expression"]) if isinstance(dim["partitions"][0]["source"]["expression"], list) else dim["partitions"][0]["source"]["expression"])
            # Deferred sort_by_column resolved even though MonthName was created before MonthNumber
            cols = {c["name"]: c for c in dim["columns"]}
            self.assertEqual(cols["MonthName"].get("sortByColumn"), "MonthNumber")
            self.assertTrue(cols["Customer_Key"].get("isKey"))
            self.assertEqual({a["name"]: a["value"] for a in cols["Customer_Key"].get("annotations", [])}.get("SummarizationSetBy"), "Automatic")
            # Hierarchy updated via SET_PROPERTIES
            hier = dim["hierarchies"][0]
            self.assertEqual(hier.get("description"), "Updated hierarchy")
            self.assertFalse(hier.get("isHidden", False))
            self.assertEqual([l["column"] for l in hier["levels"]], ["MonthNumber", "MonthName"])

            # Relationship direction & properties preserved (#83)
            rel = model["relationships"][0]
            self.assertEqual(rel["fromTable"], "Fact_Orders")
            self.assertEqual(rel["fromColumn"], "Customer_Key")
            self.assertEqual(rel["toTable"], "Dim_Customers")
            self.assertEqual(rel["toColumn"], "Customer_Key")
            self.assertFalse(rel.get("isActive", True))
            self.assertEqual(rel.get("crossFilteringBehavior"), "bothDirections")
            self.assertEqual(rel.get("securityFilteringBehavior"), "bothDirections")
            self.assertTrue(rel.get("relyOnReferentialIntegrity"))

            # Auto-date calculated table flags & CalculatedTableColumn preserved (#85)
            local_dt = tables["LocalDateTable_Test"]
            self.assertTrue(local_dt.get("isPrivate"))
            self.assertTrue(local_dt.get("showAsVariationsOnly"))
            self.assertEqual({a["name"]: a["value"] for a in local_dt.get("annotations", [])}.get("__PBI_LocalDateTable"), "true")
            dt_col = next(c for c in local_dt["columns"] if c["name"] == "Date")
            self.assertEqual(dt_col.get("type"), "calculatedTableColumn")

    def test_83_extract_relationship_preserves_true_direction(self) -> None:
        rel_obj = extract._relationship({
            "name": "r1",
            "fromTable": "Fact_Orders",
            "fromColumn": "Customer_Key",
            "toTable": "Dim_Customers",
            "toColumn": "Customer_Key",
            "fromCardinality": "many",
            "toCardinality": "one",
        })
        self.assertEqual(rel_obj.extra["ends"], [("Fact_Orders", "Customer_Key"), ("Dim_Customers", "Customer_Key")])
        self.assertEqual(rel_obj.props["cardinality"], "many:one")

    def test_82_guard_pipeline_write_logs_and_preserves_exception(self) -> None:
        pipeline = GuardPipeline(adapter=object())
        job = ApplyJob(
            apply_id="a1", kind="apply", project_id="p1",
            target_root=Path("/tmp/none"), state_root=Path("/tmp/none"),
            model_path="M.SemanticModel/definition", report_path=None, plan={"operations": []},
        )
        boom = RuntimeError("Partition 'Orders' already exists")
        boom.code = "duplicate_partition"  # type: ignore[attr-defined]
        with patch("change_guard.orchestrator.ChangeGuard", side_effect=boom):
            with self.assertLogs("backend.devcenter.apply.pipeline", level="ERROR") as logs:
                with self.assertRaises(ApplyFailure) as ctx:
                    pipeline.write(job)
        self.assertIn("Partition 'Orders' already exists", ctx.exception.message)
        self.assertEqual(ctx.exception.details.get("error_code"), "duplicate_partition")
        self.assertEqual(ctx.exception.details.get("error_detail"), "Partition 'Orders' already exists")
        self.assertTrue(any("Merge candidate write failed" in line for line in logs.output))


class Issue84And85PlanTests(unittest.TestCase):
    @staticmethod
    def _make_report_pbir(root: Path, name: str, page_id: str, display_name: str, visuals: dict[str, str]) -> LocalSource:
        pbip_root = root / name
        write_empty_target(pbip_root, name)
        report_dir = pbip_root / f"{name}.Report"
        pages_dir = report_dir / "definition" / "pages"
        default_page = pages_dir / "page1"
        target_page = pages_dir / page_id
        if page_id != "page1":
            default_page.rename(target_page)
        page_doc = json.loads((target_page / "page.json").read_text(encoding="utf-8"))
        page_doc["name"] = page_id
        page_doc["displayName"] = display_name
        (target_page / "page.json").write_text(json.dumps(page_doc, indent=2) + "\n", encoding="utf-8")
        pages_doc = json.loads((pages_dir / "pages.json").read_text(encoding="utf-8"))
        pages_doc["pageOrder"] = [page_id]
        pages_doc["activePageName"] = page_id
        (pages_dir / "pages.json").write_text(json.dumps(pages_doc, indent=2) + "\n", encoding="utf-8")
        for vid, vtype in visuals.items():
            vdir = target_page / "visuals" / vid
            vdir.mkdir(parents=True, exist_ok=True)
            (vdir / "visual.json").write_text(json.dumps({
                "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.7.0/schema.json",
                "name": vid,
                "position": {"x": 0, "y": 0, "z": 0, "width": 100, "height": 100},
                "visual": {"visualType": vtype},
            }, indent=2) + "\n", encoding="utf-8")
        return LocalSource(
            kind="pbir_report",
            root=report_dir,
            display_name=name,
            model_dir=None,
            model_format=None,
            report_dir=report_dir,
            report_format=REPORT_PBIR,
        )

    def test_84_skip_visual_on_copied_page_excluded_and_not_double_copied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tgt_src = self._make_report_pbir(root, "Target", "page1", "Page 1", {})
            donor_src = self._make_report_pbir(root, "Donor", "p2", "Overview", {"v1": "card", "v2": "tableEx"})

            tgt_objs = extract.load_objects(tgt_src)
            donor_objs = extract.load_objects(donor_src)
            choices = {
                "page:p2": {"kind": "take", "source_id": "donor"},
                "visual:p2/v1": {"kind": "skip"},
            }
            res = compare_rows.build_rows(
                [
                    compare_rows.SessionSource("tgt", tgt_objs),
                    compare_rows.SessionSource("donor", donor_objs),
                ],
                target_model=None,
                target_report="tgt",
                merge_choices=choices,
            )
            plan = compile_plan(PlanInput(
                session_id="s-84",
                result=res,
                target_model=None,
                target_report="tgt",
                sources={"tgt": "Target", "donor": "Donor"},
                merge_choices=choices,
            ))
            ops = plan["operations"]
            copy_pages = [op for op in ops if op["op"] == "COPY_PAGE"]
            copy_visuals = [op for op in ops if op["op"] == "COPY_VISUAL"]
            self.assertEqual(len(copy_pages), 1)
            self.assertEqual(copy_pages[0].get("exclude_visuals"), ["v1"])
            # No redundant COPY_VISUAL for v2 (already copied by COPY_PAGE)
            self.assertEqual(copy_visuals, [])

            cand = root / "cand.Report"
            writer = PBIRWriter(tgt_src.report_dir, cand, donor_paths={"donor": donor_src.report_dir})
            writer.write(ops)
            cand_src = LocalSource(
                kind="pbir_report", root=cand, display_name="Cand",
                model_dir=None, model_format=None, report_dir=cand, report_format=REPORT_PBIR,
            )
            before = object_index(tgt_src)
            after = object_index(cand_src)
            self.assertIn("visual:p2/v2", after)
            self.assertNotIn("visual:p2/v1", after)
            self.assertEqual(rescan.differences(ops, before, after), [])

    def test_84_replace_page_with_explicit_child_visual_takes_avoids_redundant_ops_and_matches_rescan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tgt_src = self._make_report_pbir(root, "Target", "sales01", "Sales", {"v1": "card", "v2": "tableEx"})
            donor_src = self._make_report_pbir(
                root, "Donor", "sales01", "Sales Updated", {"v1": "kpi", "v2": "tableEx", "v3": "barChart"}
            )

            tgt_objs = extract.load_objects(tgt_src)
            donor_objs = extract.load_objects(donor_src)
            choices = {
                "page:sales01": {"kind": "take", "source_id": "donor_r"},
                "visual:sales01/v1": {"kind": "take", "source_id": "donor_r"},
                "visual:sales01/v2": {"kind": "skip"},
                "visual:sales01/v3": {"kind": "take", "source_id": "donor_r"},
            }
            res = compare_rows.build_rows(
                [
                    compare_rows.SessionSource("tgt", tgt_objs),
                    compare_rows.SessionSource("donor_r", donor_objs),
                ],
                target_model=None,
                target_report="tgt",
                merge_choices=choices,
            )
            plan = compile_plan(PlanInput(
                session_id="s-84-replace",
                result=res,
                target_model=None,
                target_report="tgt",
                sources={"tgt": "Target", "donor_r": "Donor"},
                merge_choices=choices,
            ))
            ops = plan["operations"]
            copy_pages = [op for op in ops if op["op"] == "COPY_PAGE"]
            delete_visuals = [op for op in ops if op["op"] == "DELETE_VISUAL"]
            copy_visuals = [op for op in ops if op["op"] == "COPY_VISUAL"]
            self.assertEqual(len(copy_pages), 1)
            self.assertTrue(copy_pages[0].get("replace"))
            self.assertEqual(copy_pages[0].get("exclude_visuals"), ["v2"])
            self.assertEqual(delete_visuals, [])
            self.assertEqual(copy_visuals, [])

            cand = root / "cand.Report"
            writer = PBIRWriter(tgt_src.report_dir, cand, donor_paths={"donor_r": donor_src.report_dir})
            writer.write(ops)
            cand_src = LocalSource(
                kind="pbir_report", root=cand, display_name="Cand",
                model_dir=None, model_format=None, report_dir=cand, report_format=REPORT_PBIR,
            )
            before = object_index(tgt_src)
            after = object_index(cand_src)
            self.assertIn("visual:sales01/v1", after)
            self.assertIn("visual:sales01/v3", after)
            self.assertNotIn("visual:sales01/v2", after)
            self.assertEqual(rescan.differences(ops, before, after), [])

    def test_84_mixed_donor_replace_page_and_visual_from_different_donor(self) -> None:
        # Case 2A (existing v1 replaced from donor_b while page:sales01 is replaced from donor_a, with and without extra v3)
        # and Case 2B (new v1 taken from donor_b while page:sales01 is replaced from donor_a).
        scenarios = [
            (
                "existing_v1_with_v3",
                {"v1": "card", "v2": "tableEx"},
                {"v1": "kpi", "v2": "tableEx", "v3": "barChart"},
                {"v1": "donutChart"},
                {"v1", "v3"},
            ),
            (
                "existing_v1_without_v3",
                {"v1": "card", "v2": "tableEx"},
                {"v1": "kpi", "v2": "tableEx"},
                {"v1": "donutChart"},
                {"v1"},
            ),
            (
                "new_v1_from_donor_b",
                {"v2": "tableEx"},
                {"v2": "tableEx", "v3": "barChart"},
                {"v1": "donutChart"},
                {"v1", "v3"},
            ),
        ]
        for label, tgt_vis, donor_a_vis, donor_b_vis, expected_visuals in scenarios:
            with self.subTest(case=label), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                tgt_src = self._make_report_pbir(root, "Target", "sales01", "Sales", tgt_vis)
                donor_a_src = self._make_report_pbir(root, "DonorA", "sales01", "Sales A", donor_a_vis)
                donor_b_src = self._make_report_pbir(root, "DonorB", "sales01", "Sales B", donor_b_vis)

                choices = {
                    "page:sales01": {"kind": "take", "source_id": "donor_a"},
                    "visual:sales01/v1": {"kind": "take", "source_id": "donor_b"},
                    "visual:sales01/v2": {"kind": "skip"},
                }
                res = compare_rows.build_rows(
                    [
                        compare_rows.SessionSource("tgt", extract.load_objects(tgt_src)),
                        compare_rows.SessionSource("donor_a", extract.load_objects(donor_a_src)),
                        compare_rows.SessionSource("donor_b", extract.load_objects(donor_b_src)),
                    ],
                    target_model=None,
                    target_report="tgt",
                    merge_choices=choices,
                )
                plan = compile_plan(PlanInput(
                    session_id=f"s-84-mixed-{label}",
                    result=res,
                    target_model=None,
                    target_report="tgt",
                    sources={"tgt": "Target", "donor_a": "DonorA", "donor_b": "DonorB"},
                    merge_choices=choices,
                ))
                ops = plan["operations"]
                op_names = [op["op"] for op in ops]
                self.assertIn("COPY_PAGE", op_names)
                self.assertIn("COPY_VISUAL", op_names)
                self.assertLess(op_names.index("COPY_PAGE"), op_names.index("COPY_VISUAL"))
                self.assertNotIn("DELETE_VISUAL", op_names)

                cand = root / "cand.Report"
                writer = PBIRWriter(
                    tgt_src.report_dir,
                    cand,
                    donor_paths={"donor_a": donor_a_src.report_dir, "donor_b": donor_b_src.report_dir},
                )
                writer.write(ops)
                v1_doc = json.loads((cand / "definition/pages/sales01/visuals/v1/visual.json").read_text(encoding="utf-8"))
                self.assertEqual(v1_doc["visual"]["visualType"], "donutChart")

                cand_src = LocalSource(
                    kind="pbir_report", root=cand, display_name="Cand",
                    model_dir=None, model_format=None, report_dir=cand, report_format=REPORT_PBIR,
                )
                before = object_index(tgt_src)
                after = object_index(cand_src)
                actual_visuals = {k.split("/", 1)[1] for k in after if k.startswith("visual:sales01/")}
                self.assertEqual(actual_visuals, expected_visuals)
                self.assertEqual(rescan.differences(ops, before, after), [])

    def test_85_shared_expression_conflict_warning(self) -> None:
        expr_a = extract.CompareObject(
            kind="expression", subtype="expression", domain=extract.MODEL, source_key="expression:SourceFolder",
            name="SourceFolder", props={"m_text": '"C:\\\\Sales"'},
        )
        expr_b = extract.CompareObject(
            kind="expression", subtype="expression", domain=extract.MODEL, source_key="expression:SourceFolder",
            name="SourceFolder", props={"m_text": '"C:\\\\Finance"'},
        )
        t_a = extract.CompareObject(kind="table", subtype="table", domain=extract.MODEL, source_key="table:Orders", name="Orders")
        p_a = extract.CompareObject(
            kind="partition", subtype="partition", domain=extract.MODEL, source_key="partition:Orders/Orders",
            name="Orders", table="Orders", props={"mode": "import", "m_text": 'let S = Csv.Document(File.Contents(SourceFolder & "\\orders.csv")) in S'},
        )
        t_b = extract.CompareObject(kind="table", subtype="table", domain=extract.MODEL, source_key="table:Invoices", name="Invoices")
        p_b = extract.CompareObject(
            kind="partition", subtype="partition", domain=extract.MODEL, source_key="partition:Invoices/Invoices",
            name="Invoices", table="Invoices", props={"mode": "import", "m_text": 'let S = Csv.Document(File.Contents(SourceFolder & "\\invoices.csv")) in S'},
        )
        choices = {
            "table:Orders": {"kind": "take", "source_id": "sales"},
            "table:Invoices": {"kind": "take", "source_id": "finance"},
        }
        res = compare_rows.build_rows(
            [
                compare_rows.SessionSource("tgt", extract.SourceObjects([], [])),
                compare_rows.SessionSource("sales", extract.SourceObjects([expr_a, t_a, p_a], [])),
                compare_rows.SessionSource("finance", extract.SourceObjects([expr_b, t_b, p_b], [])),
            ],
            target_model="tgt",
            target_report=None,
            merge_choices=choices,
        )
        plan = compile_plan(PlanInput(
            session_id="s-85",
            result=res,
            target_model="tgt",
            target_report=None,
            sources={"tgt": "Target", "sales": "Sales", "finance": "Finance"},
            merge_choices=choices,
        ))
        shared_warnings = [w for w in plan["warnings"] if w["kind"] == "shared_expression_conflict"]
        self.assertEqual(len(shared_warnings), 1)
        self.assertEqual(shared_warnings[0]["params"]["expression"], "SourceFolder")
        self.assertEqual(shared_warnings[0]["params"]["donors"], ["Finance", "Sales"])
        self.assertEqual(shared_warnings[0]["params"]["tables"], ["Invoices", "Orders"])


class Issue86BackendTests(unittest.TestCase):
    def test_86_local_promotion_undo_prunes_empty_parent_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            candidate = root / "candidate"
            state = root / "state"
            source.mkdir()
            candidate.mkdir()
            (source / "definition.pbism").write_text('{"version":"4.2"}', encoding="utf-8")
            (candidate / "definition.pbism").write_text('{"version":"4.2"}', encoding="utf-8")
            nested = candidate / "Report/definition/pages/p2/visuals/v1"
            nested.mkdir(parents=True)
            (nested / "visual.json").write_text("{}", encoding="utf-8")

            from backend.snapshots.manifest import content_hash, source_manifest

            base_manifest = source_manifest(source)
            cand_manifest = source_manifest(candidate)
            permit = {
                "operation_id": "op-1",
                "authorized_operation": "PROMOTE",
                "source_root": str(source),
                "candidate_root": str(candidate),
                "baseline_manifest": base_manifest,
                "candidate_manifest": cand_manifest,
                "candidate_hash": content_hash(cand_manifest),
                "baseline_snapshot_id": "snap-1",
                "contract_hash": "sha256:0",
                "policy_hash": "sha256:0",
                "evidence_hash": "sha256:0",
                "principal": "test-user",
            }
            store = AuditStore(state)
            promo = LocalPromotion(store)
            promo.promote("op-1", store.sign(permit))
            self.assertTrue((source / "Report/definition/pages/p2/visuals/v1/visual.json").is_file())

            promo.undo("op-1")
            self.assertFalse((source / "Report/definition/pages/p2/visuals/v1/visual.json").exists())
            self.assertFalse((source / "Report").exists())
            self.assertTrue((source / "definition.pbism").is_file())

    @unittest.skipUnless(BRIDGE.is_file(), "Build the TOM bridge first")
    def test_86_rescan_replace_page_and_calculated_table_partition(self) -> None:
        adapter = TabularMetadataAdapter(BRIDGE)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tgt_root = root / "Target"
            tgt_pbip = write_empty_target(tgt_root, "Target")
            donor_root = root / "Donor"
            write_empty_target(donor_root, "Donor")
            donor_page_json = donor_root / "Donor.Report/definition/pages/page1/page.json"
            page_doc = json.loads(donor_page_json.read_text(encoding="utf-8"))
            page_doc["displayName"] = "Updated Page 1"
            donor_page_json.write_text(json.dumps(page_doc, indent=2) + "\n", encoding="utf-8")

            report_ops = [
                {
                    "op": "COPY_PAGE",
                    "object_type": "page",
                    "domain": "report",
                    "row_key": "page:page1",
                    "source_id": "donor",
                    "source_key": "page:page1",
                    "page_id": "page1",
                    "replace": True,
                },
            ]
            model_ops = [
                {
                    "op": "CREATE",
                    "object_type": "table",
                    "subtype": "calculated_table",
                    "domain": "model",
                    "name": "LocalDateTable_1",
                    "row_key": "table:LocalDateTable_1",
                    "properties": {"expression": "Calendar(Date(2024,1,1), Date(2024,12,31))"},
                },
            ]
            ops = model_ops + report_ops

            cand_report = root / "Candidate.Report"
            PBIRWriter(
                tgt_root / "Target.Report",
                cand_report,
                donor_paths={"donor": donor_root / "Donor.Report"},
            ).write(report_ops)

            cand_model = root / "Candidate.SemanticModel"
            adapter.write_model(
                tgt_root / "Target.SemanticModel/definition",
                cand_model / "definition",
                model_ops,
            )

            before = object_index(detect_local_source(tgt_pbip))
            cand_src = LocalSource(
                kind="pbip",
                root=root,
                display_name="Candidate",
                model_dir=cand_model,
                model_format=MODEL_TMDL,
                report_dir=cand_report,
                report_format=REPORT_PBIR,
            )
            after = object_index(cand_src)
            self.assertIn("model:Model", after)
            self.assertIn("report:report", after)
            self.assertIn("partition:LocalDateTable_1/LocalDateTable_1", after)
            self.assertEqual(rescan.differences(ops, before, after), [])


class Issue89Tests(unittest.TestCase):
    def test_89_untouched_root_definition_pbir_without_schema_allowed_while_modified_or_extra_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target_pbip = root / "Target"
            write_empty_target(target_pbip, "Target")
            report_dir = target_pbip / "Target.Report"

            # Remove $schema from root definition.pbir (valid v4.0 structure)
            pbir_path = report_dir / "definition.pbir"
            pbir_doc = json.loads(pbir_path.read_text(encoding="utf-8"))
            pbir_doc.pop("$schema", None)
            pbir_path.write_text(json.dumps(pbir_doc, indent=2) + "\n", encoding="utf-8")

            # Untouched root definition.pbir without $schema should PASS
            cand_ok = root / "cand_ok.Report"
            writer_ok = PBIRWriter(report_dir, cand_ok)
            result = writer_ok.write([])
            self.assertEqual(result["changed_files"], [])

            # Extra malformed file definition/definition.pbir without $schema must STILL FAIL
            (report_dir / "definition" / "definition.pbir").write_text(json.dumps(pbir_doc), encoding="utf-8")
            cand_bad = root / "cand_bad.Report"
            writer_bad = PBIRWriter(report_dir, cand_bad)
            with self.assertRaises(PBIRWriteError) as ctx:
                writer_bad.write([])
            self.assertEqual(ctx.exception.code, "schema_validation_failed")


if __name__ == "__main__":
    unittest.main()
