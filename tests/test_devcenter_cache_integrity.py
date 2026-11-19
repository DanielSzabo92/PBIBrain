"""Cache integrity, compare row filter, removal policy alignment, and GET /api/devcenter/log tests."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from backend.api.app import create_app
from backend.devcenter import contracts
from backend.devcenter.compare import extract, rows as compare_rows
from backend.devcenter.impact import service as impact_service
from backend.devcenter.plan.compiler import PlanInput, compile_plan
from backend.devcenter.session.manager import DevCenterSessions
from backend.devcenter.sources.fingerprint import source_fingerprint
from backend.devcenter.sources.kinds import detect_local_source

REPOSITORY = Path(__file__).resolve().parents[1]
LAB = REPOSITORY / "tests" / "fixtures" / "merge_lab"


class CacheAndBackendFixTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "proj"
        shutil.copytree(LAB / "SalesA", self.root / "SalesA")
        shutil.copytree(LAB / "SalesB", self.root / "SalesB")
        self.devcenter = DevCenterSessions(app_data_dir=self.root / "appdata")
        self.devcenter.attach_project(self.root)
        self.app = create_app(use_native=False)
        self.app.devcenter = self.devcenter

    def tearDown(self) -> None:
        self.devcenter.close()
        self.app.close()
        self.tmp.cleanup()

    def test_compare_rows_not_same_and_type_conflict_filters(self) -> None:
        sample = [
            {"row_key": "r1", "object_type": "measure", "table": "S", "display_folder": "", "row_state": "same", "page": "", "changed": False, "marks": [], "name": "A", "cells": []},
            {"row_key": "r2", "object_type": "measure", "table": "S", "display_folder": "", "row_state": "different", "page": "", "changed": True, "marks": [], "name": "B", "cells": []},
            {"row_key": "r3", "object_type": "measure", "table": "S", "display_folder": "", "row_state": "type_conflict", "page": "", "changed": True, "marks": [], "name": "C", "cells": []},
            {"row_key": "r4", "object_type": "measure", "table": "S", "display_folder": "", "row_state": "missing", "page": "", "changed": True, "marks": [], "name": "D", "cells": []},
        ]
        not_same = compare_rows.filter_rows(sample, {"state": ["not_same"]})
        self.assertEqual([r["row_key"] for r in not_same], ["r2", "r3", "r4"])
        tc = compare_rows.filter_rows(sample, {"state": ["type_conflict"]})
        self.assertEqual([r["row_key"] for r in tc], ["r3"])
        multi = compare_rows.filter_rows(sample, {"state": ["different", "missing"]})
        self.assertEqual([r["row_key"] for r in multi], ["r2", "r4"])

    def test_impact_cache_keys_by_session_id_and_proposals_and_clears_on_commit_close(self) -> None:
        s1 = self.devcenter.create({"display_name": "Session 1"})["session_id"]
        self.devcenter.source_add({"base_revision": 1, "path": str(self.root / "SalesA" / "SalesA.pbip")})
        s1_summary = self.devcenter.session_summary()
        self.assertIn("removal_policies", s1_summary)
        self.assertEqual([], contracts.errors("http/session.reply.json", s1_summary))

        # Populate impact cache on session 1
        res1 = impact_service.get_impact(self.devcenter, {"target": ["plan"]})
        self.assertIsNotNone(self.devcenter._cached_impact)
        self.assertEqual(self.devcenter._cached_impact["key"][0], s1)
        self.assertEqual(self.devcenter._cached_impact["key"][3], "false")

        # Include_proposals query varies cache key cleanly
        impact_service.get_impact(self.devcenter, {"target": ["plan"], "include_proposals": ["ready"]})
        self.assertEqual(self.devcenter._cached_impact["key"][3], "ready")

        # Creating/switching session clears _cached_impact cleanly via _close()
        s2 = self.devcenter.create({"display_name": "Session 2"})["session_id"]
        self.assertNotEqual(s1, s2)
        self.assertIsNone(self.devcenter._cached_impact)

        # Adding a source via _commit clears any prior _cached_impact
        impact_service.get_impact(self.devcenter, {"target": ["plan"]})
        self.assertIsNotNone(self.devcenter._cached_impact)
        self.devcenter.source_add({"base_revision": 1, "path": str(self.root / "SalesB" / "SalesB.pbip")})
        self.assertIsNone(self.devcenter._cached_impact)

    def test_get_log_route_returns_filtered_paged_entries(self) -> None:
        self.devcenter.create({"display_name": "Log session"})
        added = self.devcenter.source_add({"base_revision": 1, "path": str(self.root / "SalesA" / "SalesA.pbip")})
        self.devcenter.source_add({"base_revision": 2, "path": str(self.root / "SalesB" / "SalesB.pbip")})

        status, body = self.app.handle("GET", "/api/devcenter/log")
        self.assertEqual(status, 200)
        self.assertEqual([], contracts.errors("http/log.reply.json", body))
        self.assertEqual(body["revision"], 3)
        self.assertGreaterEqual(body["total"], 3)
        # Newest entry first
        self.assertEqual(body["entries"][0]["action"], "source_add")

        status_f, body_f = self.app.handle("GET", "/api/devcenter/log?action=session_create&author=user&limit=1&offset=0")
        self.assertEqual(status_f, 200)
        self.assertEqual(len(body_f["entries"]), 1)
        self.assertEqual(body_f["entries"][0]["action"], "session_create")
        self.assertEqual(body_f["has_more"], False)
        _ = added

    def test_repoint_accepts_repoint_target_key_in_compiler(self) -> None:
        # Ensure compile_plan does not drop repoint_target stored by removal_policy_set
        from backend.devcenter.compare.rows import SessionSource, build_rows

        src = extract.load_objects(detect_local_source(self.root / "SalesA" / "SalesA.pbip"))
        rows = build_rows([SessionSource("t", src)], target_model="t", target_report=None)
        cols = [r["row_key"] for r in rows.rows if r["object_type"] == "column"]
        plan = compile_plan(
            PlanInput(
                session_id="s-repoint",
                result=rows,
                target_model="t",
                target_report=None,
                sources={"t": "SalesA"},
                merge_choices={cols[0]: {"kind": "remove"}},
                removal_policies={cols[0]: {"policy": "repoint", "repoint_target": cols[1]}},
            )
        )
        self.assertFalse(any(b["kind"] == "repoint_not_valid" for b in plan["blocking"]), plan["blocking"])

    def test_extract_cache_preserves_hits_and_misses_on_fingerprint_change(self) -> None:
        pbip = self.root / "SalesA" / "SalesA.pbip"
        src = detect_local_source(pbip)
        fp_before = source_fingerprint(src)
        objs1 = extract.load_objects(src)
        objs2 = extract.load_objects(src)
        self.assertIs(objs1, objs2)

        measure_file = self.root / "SalesA" / "SalesA.SemanticModel" / "definition" / "tables" / "Sales.tmdl"
        measure_file.write_text(measure_file.read_text(encoding="utf-8") + "\n\tmeasure CacheProbe = 42\n", encoding="utf-8")
        src2 = detect_local_source(pbip)
        self.assertNotEqual(fp_before, source_fingerprint(src2))
        objs3 = extract.load_objects(src2)
        self.assertIsNot(objs1, objs3)


if __name__ == "__main__":
    unittest.main()
