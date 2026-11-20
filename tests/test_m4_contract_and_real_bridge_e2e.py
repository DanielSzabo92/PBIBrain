from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from backend.adapters.tabular_metadata.bridge import TabularMetadataAdapter
from backend.devcenter.sources.targets import skeleton_files
from tests.devcenter_ui_server import FakeDevCenter, FakeError


class MockServerContractEnforcementTests(unittest.TestCase):
    """Issue #93: tests/devcenter_ui_server.py enforces backend/devcenter/contracts/jsapi schemas."""

    def setUp(self) -> None:
        self.state = FakeDevCenter()
        self.row_key = self.state._rows()[0]["row_key"]

    def test_rejects_legacy_invalid_merge_choice_payloads(self) -> None:
        rev = self.state.revision
        # Legacy {choice, source} rejected by additionalProperties: false
        with self.assertRaises(FakeError) as ctx1:
            self.state.call(
                "merge_choice_set",
                {"base_revision": rev, "row_key": self.row_key, "choice": {"choice": "take", "source": "src-2"}},
            )
        self.assertEqual(ctx1.exception.code, "invalid_payload")

        # Legacy take_from rejected
        with self.assertRaises(FakeError) as ctx2:
            self.state.call(
                "merge_choice_bulk_set",
                {"base_revision": rev, "row_keys": [self.row_key], "choice": {"kind": "take_from", "source_id": "src-2"}},
            )
        self.assertEqual(ctx2.exception.code, "invalid_payload")

        # Policy embedded in choice rejected
        with self.assertRaises(FakeError) as ctx3:
            self.state.call(
                "merge_choice_bulk_set",
                {"base_revision": rev, "row_keys": [self.row_key], "choice": {"kind": "remove", "policy": "block"}},
            )
        self.assertEqual(ctx3.exception.code, "invalid_payload")

    def test_accepts_canonical_choice_and_items_undo_with_previous_choices(self) -> None:
        rev = self.state.revision
        r1 = self.state.call(
            "merge_choice_set",
            {"base_revision": rev, "row_key": self.row_key, "choice": {"kind": "take", "source_id": "src-2"}},
        )
        self.assertEqual(r1["choice"], {"kind": "take", "source_id": "src-2"})

        r2 = self.state.call(
            "merge_choice_bulk_set",
            {"base_revision": r1["revision"], "row_keys": [self.row_key], "choice": {"kind": "keep"}},
        )
        self.assertIn("previous_choices", r2)
        self.assertEqual(r2["previous_choices"][self.row_key], {"kind": "take", "source_id": "src-2"})

        # Undo via items restores prior choice
        r3 = self.state.call(
            "merge_choice_bulk_set",
            {
                "base_revision": r2["revision"],
                "items": [{"row_key": self.row_key, "choice": r2["previous_choices"][self.row_key]}],
            },
        )
        self.assertEqual(r3["changed"], 1)
        self.assertEqual(self.state._row(self.row_key)["merge_choice"], {"kind": "take", "source_id": "src-2"})


class RealBridgeTwoSourceMergeE2ETests(unittest.TestCase):
    """Issue #93: Real TOM bridge E2E test merging two sources into an empty target skeleton."""

    def test_two_source_merge_to_empty_target_roundtrips_through_real_tom_bridge(self) -> None:
        if not shutil.which("dotnet"):
            self.skipTest("dotnet SDK not available on PATH")

        adapter = TabularMetadataAdapter()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target_dir = root / "Combined"
            for rel, content in skeleton_files("Combined").items():
                dest = target_dir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(content)

            model_dir = target_dir / "Combined.SemanticModel"
            cand_dir = root / "candidate"

            # Canonical check on empty target skeleton passes (#81)
            check = adapter.canonical_check(model_dir)
            self.assertTrue(check["is_canonical"], check)
            self.assertEqual(check["non_canonical_files"], [])

            # Write merged ops representing tables/columns/partitions/relationships from 2 donors
            ops = [
                {
                    "op": "SET_PROPERTIES",
                    "object_type": "model",
                    "name": "Model",
                    "properties": {
                        "culture": "en-US",
                        "default_power_bi_data_source_version": "powerBI_V3",
                        "source_query_culture": "en-US",
                    },
                },
                {
                    "op": "CREATE",
                    "object_type": "table",
                    "name": "Dim_Customers",
                    "properties": {
                        "annotations": [{"name": "PBI_ResultType", "value": "Table"}],
                    },
                },
                {
                    "op": "CREATE",
                    "object_type": "column",
                    "table": "Dim_Customers",
                    "name": "CustomerKey",
                    "properties": {
                        "data_type": "int64",
                        "source_column": "CustomerKey",
                        "hidden": True,
                        "annotations": [{"name": "SummarizationSetBy", "value": "Automatic"}],
                    },
                },
                {
                    "op": "CREATE",
                    "object_type": "partition",
                    "table": "Dim_Customers",
                    "name": "Dim_Customers",
                    "properties": {
                        "m_text": 'let Source = #table({"CustomerKey"}, {{1}}) in Source',
                    },
                },
                {
                    "op": "CREATE",
                    "object_type": "table",
                    "name": "Fact_Orders",
                    "properties": {},
                },
                {
                    "op": "CREATE",
                    "object_type": "column",
                    "table": "Fact_Orders",
                    "name": "CustomerKey",
                    "properties": {
                        "data_type": "int64",
                        "source_column": "CustomerKey",
                    },
                },
                {
                    "op": "CREATE",
                    "object_type": "partition",
                    "table": "Fact_Orders",
                    "name": "Fact_Orders",
                    "properties": {
                        "m_text": 'let Source = #table({"CustomerKey"}, {{1}}) in Source',
                    },
                },
                {
                    "op": "CREATE",
                    "object_type": "relationship",
                    "name": "Fact_Orders_CustomerKey_Dim_Customers_CustomerKey",
                    "properties": {
                        "from_table": "Fact_Orders",
                        "from_column": "CustomerKey",
                        "to_table": "Dim_Customers",
                        "to_column": "CustomerKey",
                        "active": True,
                        "cross_filter_direction": "single",
                    },
                },
            ]

            adapter.write_model(model_dir / "definition", cand_dir, ops)
            readback = adapter.read(cand_dir)

            # Verify model header (#81)
            model_meta = (readback.get("database") or {}).get("model") or {}
            self.assertEqual(model_meta.get("culture"), "en-US")

            # Verify tables, hidden flag, partition M text, annotations (#82, #85)
            tables = {t["name"]: t for t in model_meta.get("tables", [])}
            self.assertIn("Dim_Customers", tables)
            self.assertIn("Fact_Orders", tables)

            dim_cols = {c["name"]: c for c in tables["Dim_Customers"].get("columns", [])}
            self.assertTrue(dim_cols["CustomerKey"].get("isHidden") or dim_cols["CustomerKey"].get("is_hidden"))

            dim_parts = tables["Dim_Customers"].get("partitions", [])
            self.assertEqual(len(dim_parts), 1)
            part_expr = dim_parts[0].get("expression") or (dim_parts[0].get("source") or {}).get("expression") or ""
            self.assertIn("#table", str(part_expr))

            # Verify relationship direction is NOT reversed (#83)
            rels = model_meta.get("relationships", [])
            self.assertEqual(len(rels), 1)
            self.assertEqual(rels[0].get("fromTable"), "Fact_Orders")
            self.assertEqual(rels[0].get("fromColumn"), "CustomerKey")
            self.assertEqual(rels[0].get("toTable"), "Dim_Customers")
            self.assertEqual(rels[0].get("toColumn"), "CustomerKey")


if __name__ == "__main__":
    unittest.main()
