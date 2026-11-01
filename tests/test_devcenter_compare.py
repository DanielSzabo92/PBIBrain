"""Build step S3: alignment and compare (technical design section 16, S3)."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import unittest
from urllib.parse import quote

from backend.api.app import create_app
from backend.devcenter import contracts, jsapi
from backend.devcenter.alignment import keys
from backend.devcenter.compare.extract import SourceObjects, model_objects
from backend.devcenter.compare.jsapi_methods import S3_METHODS
from backend.devcenter.compare.normalize import RenameMap, dax_equal, dax_key
from backend.devcenter.compare.properties import PROPERTY_PHRASE_IDS
from backend.devcenter.compare.rows import NOTE_IDS, STATES, WARNING_IDS, SessionSource, build_rows
from backend.devcenter.session.manager import DevCenterSessions
from backend.devcenter.session.secrets import ROW_KEY_KINDS
from backend.devcenter.sources.kinds import detect_local_source
from backend.devcenter.sources.objects import OBJECT_KINDS, object_index

REPOSITORY = Path(__file__).resolve().parents[1]
LAB = REPOSITORY / "tests" / "fixtures" / "merge_lab"
GOLDEN = REPOSITORY / "tests" / "fixtures" / "devcenter_compare" / "merge_lab_rows.json"
PHRASES = REPOSITORY / "backend" / "devcenter" / "contracts" / "phrases.json"
UPDATE_GOLDEN = os.environ.get("PBIBRAIN_UPDATE_GOLDEN") == "1"


# Synthetic models (TOM JSON shape) ---------------------------------------------


def measure(name: str, expression: str, tag: str | None = None, **extra) -> dict:
    item = {"name": name, "expression": expression, **extra}
    if tag:
        item["lineageTag"] = tag
    return item


def model(tables: list[dict], **parts) -> dict:
    return {"tables": tables, **parts}


def table(name: str, tag: str | None = None, **parts) -> dict:
    item = {"name": name, **parts}
    if tag:
        item["lineageTag"] = tag
    return item


def rows_of(*models: dict, target: str | None = "src-1", overrides=None, mode="default") -> list[dict]:
    sources = [SessionSource(f"src-{index}", SourceObjects(model_objects(item), [])) for index, item in enumerate(models, 1)]
    return build_rows(sources, target_model=target, target_report=None, overrides=overrides, mode=mode).rows


def by_key(rows: list[dict]) -> dict[str, dict]:
    return {row["row_key"]: row for row in rows}


def cell(row: dict, source_id: str) -> dict:
    return next(item for item in row["cells"] if item["source_id"] == source_id)


def notes(row: dict, source_id: str) -> list[str]:
    return [note["note_id"] for note in cell(row, source_id)["notes"]]


class AlignmentStepTests(unittest.TestCase):
    def test_lineage_tag_wins_over_name_renamed_plus_name_clash(self):
        target = model([table("Sales", "t", measures=[measure("Sales", "SUM(Sales[Amount])", "m-1")])])
        donor = model([table("Sales", "t", measures=[measure("Revenue", "SUM(Sales[Amount])", "m-1"),
                                                     measure("Sales", "COUNTROWS(Sales)", "m-2")])])
        rows = by_key(rows_of(target, donor))
        renamed = rows["measure:Sales/Sales"]
        self.assertEqual("renamed", cell(renamed, "src-2")["state"])
        self.assertEqual("measure:Sales/Revenue", cell(renamed, "src-2")["source_key"])
        clash = rows["measure:Sales/Sales@src-2"]
        self.assertEqual("missing", cell(clash, "src-1")["state"])
        self.assertEqual("measure:Sales/Sales", cell(clash, "src-2")["source_key"])
        self.assertIn("name_clash", notes(clash, "src-2"))
        self.assertEqual("measure:Sales/Sales", cell(clash, "src-2")["notes"][0]["other_row_key"])

    def test_duplicate_lineage_tag_is_ignored_with_a_warning(self):
        target = model([table("Sales", measures=[measure("A", "1", "dup-x")])])
        donor = model([table("Sales", measures=[measure("B", "1", "dup-x"), measure("C", "2", "dup-x")])])
        sources = [SessionSource("src-1", SourceObjects(model_objects(target), [])),
                   SessionSource("src-2", SourceObjects(model_objects(donor), []))]
        result = build_rows(sources, target_model="src-1", target_report=None)
        self.assertEqual([{"warning_id": "duplicate_lineage_tag", "source_id": "src-2", "lineage_tag": "dup-x",
                           "source_keys": ["measure:Sales/B", "measure:Sales/C"]}], result.warnings)
        rows = by_key(result.rows)
        self.assertEqual("missing", cell(rows["measure:Sales/A"], "src-2")["state"], "The duplicate tag must not align")
        self.assertIn("duplicate_lineage_tag", notes(rows["measure:Sales/B"], "src-2"))
        self.assertIn("duplicate_lineage_tag", notes(rows["measure:Sales/C"], "src-2"))

    def test_each_alignment_key_aligns_its_case(self):
        def rel(name, a, b):
            return {"name": name, "fromTable": a[0], "fromColumn": a[1], "toTable": b[0], "toColumn": b[1]}

        def role(name, column):
            return {"name": name, "modelPermission": "read",
                    "tablePermissions": [{"name": "Store", "filterExpression": "[Region] = \"West\"",
                                          "columnPermissions": [{"name": column, "metadataPermission": "none"}]}]}

        group = {"calculationItems": [{"name": "YTD", "expression": "SELECTEDMEASURE()", "ordinal": 0}]}
        target = model(
            [table("Sales", partitions=[{"name": "Sales-1", "mode": "import", "source": {"type": "m", "expression": "a"}}]),
             table("Time", calculationGroup=group),
             table("Store", partitions=[{"name": "P1", "mode": "import", "source": {"type": "m", "expression": "b"}},
                                        {"name": "P2", "mode": "import", "source": {"type": "m", "expression": "c"}}])],
            relationships=[rel("r-guid-1", ("Sales", "Store Key"), ("Store", "Store Key"))],
            roles=[role("West", "Manager Email")])
        donor = model(
            [table("Sales", partitions=[{"name": "Sales Part", "mode": "import", "source": {"type": "m", "expression": "a"}}]),
             table("time", calculationGroup=copy.deepcopy(group)),
             table("Store", partitions=[{"name": "p1", "mode": "import", "source": {"type": "m", "expression": "b"}},
                                        {"name": "P3", "mode": "import", "source": {"type": "m", "expression": "c"}}])],
            relationships=[rel("r-guid-2", ("store", "store key"), ("Sales", "Store Key"))],
            roles=[role("west", "MANAGER EMAIL")])
        rows = by_key(rows_of(target, donor))
        self.assertEqual("relationship:r-guid-2", cell(rows["relationship:r-guid-1"], "src-2")["source_key"], "Ends in any order")
        self.assertEqual("calculation_item:time/YTD", cell(rows["calculation_item:Time/YTD"], "src-2")["source_key"])
        self.assertEqual("role:west", cell(rows["role:West"], "src-2")["source_key"])
        self.assertEqual([], [p for p in cell(rows["role:West"], "src-2")["phrases"] if p["property"] == "ols"],
                         "OLS aligns by role + table + column, case-insensitive")
        self.assertEqual("partition:Sales/Sales Part", cell(rows["partition:Sales/Sales-1"], "src-2")["source_key"],
                         "One partition on each side: the table alone")
        self.assertEqual("partition:Store/p1", cell(rows["partition:Store/P1"], "src-2")["source_key"])
        self.assertFalse(cell(rows["partition:Store/P2"], "src-2")["present"], "Two partitions: table + name only")
        self.assertEqual(("relationship", (("sales", "store key"), ("store", "store key"))),
                         keys.relationship_key([("Store", "Store Key"), ("Sales", "store key")]))
        self.assertEqual(("west", "store", "manager email"), keys.ols_key("West", "Store", "Manager Email"))

    def test_report_alignment_keys(self):
        from backend.devcenter.compare.extract import CompareObject

        def page(key, page_id, display):
            return CompareObject("page", "page", "report", f"page:{key}", display, props={"display_name": display},
                                 extra={"page_id": page_id, "display_name": display})

        def visual(page_key, visual_id):
            return CompareObject("visual", "visual", "report", f"visual:{page_key}/{visual_id}", visual_id, table=page_key,
                                 extra={"visual_id": visual_id})

        def report_measure(entity, name):
            return CompareObject("report_measure", "report_measure", "report", f"report_measure:{entity}/{name}", name, table=entity,
                                 props={"expression": "1"})

        target = [page("p1", "p1", "Overview"), page("p2", "p2", "Detail"), visual("p1", "v1"), report_measure("Sales", "Target")]
        donor = [page("x9", "x9", "overview"), page("p2", "p2", "Other"), visual("p2", "V1"), report_measure("sales", "target")]
        sources = [SessionSource("src-1", SourceObjects([], target)), SessionSource("src-2", SourceObjects([], donor))]
        rows = by_key(build_rows(sources, target_model=None, target_report="src-1").rows)
        self.assertEqual("page:p2", cell(rows["page:p2"], "src-2")["source_key"], "Page ID first")
        self.assertEqual("page:x9", cell(rows["page:p1"], "src-2")["source_key"], "Then the page display name")
        self.assertEqual("visual:p2/V1", cell(rows["visual:p1/v1"], "src-2")["source_key"], "Visual ID only")
        self.assertEqual("report_measure:sales/target", cell(rows["report_measure:Sales/Target"], "src-2")["source_key"])

    def test_possible_rename_only_with_one_candidate_on_each_side(self):
        target = model([table("Sales", measures=[measure("Total", "SUM(Sales[Amount])")])])
        donor = model([table("Sales", measures=[measure("Revenue", "sum ( Sales[amount] )")])])
        rows = by_key(rows_of(target, donor))
        self.assertIn("possible_rename", notes(rows["measure:Sales/Total"], "src-2"))
        self.assertEqual("measure:Sales/Revenue", cell(rows["measure:Sales/Total"], "src-2")["notes"][0]["other_row_key"])
        self.assertIn("possible_rename", notes(rows["measure:Sales/Revenue"], "src-2"))
        self.assertFalse(cell(rows["measure:Sales/Total"], "src-2")["present"], "The user must confirm a possible rename")
        two = model([table("Sales", measures=[measure("Revenue", "SUM(Sales[Amount])"), measure("Income", "SUM(Sales[Amount])")])])
        rows = by_key(rows_of(target, two))
        self.assertEqual([], notes(rows["measure:Sales/Total"], "src-2"))
        self.assertEqual([], notes(rows["measure:Sales/Revenue"], "src-2"))

    def test_moved_and_type_conflict(self):
        target = model([table("Sales", measures=[measure("Cost", "1")], columns=[{"name": "Amount", "dataType": "decimal"}])])
        donor = model([table("Sales", measures=[measure("Amount", "2")]), table("Measures", measures=[measure("Cost", "1")])])
        rows = by_key(rows_of(target, donor))
        self.assertEqual("moved", cell(rows["measure:Sales/Cost"], "src-2")["state"])
        self.assertEqual("type_conflict", cell(rows["column:Sales/Amount"], "src-2")["state"])
        self.assertEqual("type_conflict", rows["column:Sales/Amount"]["row_state"])


class NormalizationTests(unittest.TestCase):
    CASES = {
        "whitespace": ("SUM(Sales[Amount])", " SUM ( Sales[Amount] )\n", "SUM(Sales[Cost])"),
        "comments": ("SUM(Sales[Amount])", "SUM(Sales[Amount]) // a\n-- b\n/* c */", "SUM(Sales[Amount]) + 1 // a"),
        "keyword and function case": ("VAR x = SUM(Sales[Amount]) RETURN x", "var x = sum(Sales[Amount]) return x",
                                      "VAR x = SUM(Sales[Amount]) RETURN x + 1"),
        "name case in references": ("SUM(Sales[Amount])", "SUM(sales[amount])", "SUM(Sales[Amounts])"),
        "quotes on table names": ("SUM('Sales'[Amount])", "SUM(Sales[Amount])", "SUM('Sales Data'[Amount])"),
        "table prefix on a measure reference": ("[Total]", "[total]", "Sales[Total]"),
    }

    def test_each_rule_has_a_pass_and_a_fail_case(self):
        for rule, (base, same, other) in self.CASES.items():
            with self.subTest(rule=rule):
                self.assertTrue(dax_equal(base, same, strict=False)[0])
                self.assertFalse(dax_equal(base, other, strict=False)[0])
        self.assertNotEqual(dax_key("[Total]"), dax_key("Sales[Total]"))
        self.assertNotEqual(dax_key('"Total"'), dax_key('"total"'), "String text stays exact")

    def test_strict_compares_the_exact_text(self):
        self.assertTrue(dax_equal("SUM(Sales[Amount])\r\n", "SUM(Sales[Amount])\n", strict=True)[0])
        self.assertFalse(dax_equal("SUM(Sales[Amount])", "sum(Sales[Amount])", strict=True)[0])

    def test_rename_map(self):
        renames = RenameMap(tables={"facts": "Sales"}, measures={"revenue": "Total"}, columns={("facts", "amt"): "Amount"})
        self.assertEqual((True, True), dax_equal("[Total] + SUM(Sales[Amount])", "[Revenue] + SUM('Facts'[Amt])", strict=False,
                                                 renames=renames))

    def test_same_after_rename_in_default_mode_and_different_in_strict_mode(self):
        target = model([table("Sales", measures=[measure("Total", "SUM(Sales[Amount])", "m-1"), measure("Double", "[Total] * 2", "m-2")])])
        donor = model([table("Sales", measures=[measure("Revenue", "SUM(Sales[Amount])", "m-1"), measure("Double", "[Revenue] * 2", "m-2")])])
        row = by_key(rows_of(target, donor))["measure:Sales/Double"]
        self.assertEqual("same", cell(row, "src-2")["state"])
        self.assertIn("same_after_rename", notes(row, "src-2"))
        row = by_key(rows_of(target, donor, mode="strict"))["measure:Sales/Double"]
        self.assertEqual("different", cell(row, "src-2")["state"])
        self.assertEqual(["expression_changed"], [p["phrase_id"] for p in cell(row, "src-2")["phrases"]])

    def test_default_ignores_lineage_tag_and_annotations_and_strict_does_not(self):
        target = model([table("Sales", measures=[measure("A", "1", "m-1", annotations=[{"name": "x", "value": "1"}])])])
        donor = model([table("Sales", measures=[measure("A", "1", "m-9")])])
        self.assertEqual("same", cell(by_key(rows_of(target, donor))["measure:Sales/A"], "src-2")["state"])
        phrases = cell(by_key(rows_of(target, donor, mode="strict"))["measure:Sales/A"], "src-2")["phrases"]
        self.assertEqual({"annotations_changed", "lineage_tag_changed"}, {p["phrase_id"] for p in phrases})

    def test_short_values_show_old_and_new(self):
        target = model([table("Sales", measures=[measure("A", "1", isHidden=False)])])
        donor = model([table("Sales", measures=[measure("A", "2", isHidden=True)])])
        phrases = {p["phrase_id"]: p for p in cell(by_key(rows_of(target, donor))["measure:Sales/A"], "src-2")["phrases"]}
        self.assertEqual((False, True, True), (phrases["hidden_changed"]["old"], phrases["hidden_changed"]["new"], phrases["hidden_changed"]["short"]))
        self.assertEqual((None, None, False), (phrases["expression_changed"]["old"], phrases["expression_changed"]["new"],
                                               phrases["expression_changed"]["short"]))


class OverrideTests(unittest.TestCase):
    TARGET = model([table("Sales", measures=[measure("Total", "SUM(Sales[Amount])"), measure("Margin", "1")])])
    DONOR = model([table("Sales", measures=[measure("Revenue", "SUM(Sales[Amount])"), measure("Margin", "2")])])

    def test_overrides_change_the_rows(self):
        confirm = {"src-2": [{"kind": "confirm", "target_key": "measure:Sales/Total", "donor_key": "measure:Sales/Revenue"}]}
        rows = by_key(rows_of(self.TARGET, self.DONOR, overrides=confirm))
        self.assertEqual("renamed", cell(rows["measure:Sales/Total"], "src-2")["state"])
        self.assertEqual("manual", cell(rows["measure:Sales/Total"], "src-2")["step"])
        self.assertNotIn("measure:Sales/Revenue", rows)
        broken = {"src-2": [{"kind": "break", "target_key": "measure:Sales/Margin", "donor_key": "measure:Sales/Margin"}]}
        rows = by_key(rows_of(self.TARGET, self.DONOR, overrides=broken))
        self.assertFalse(cell(rows["measure:Sales/Margin"], "src-2")["present"])
        self.assertIn("measure:Sales/Margin@src-2", rows)
        self.assertIn("name_clash", notes(rows["measure:Sales/Margin@src-2"], "src-2"))
        rejected = {"src-2": [{"kind": "reject_rename", "target_key": "measure:Sales/Total", "donor_key": "measure:Sales/Revenue"}]}
        rows = by_key(rows_of(self.TARGET, self.DONOR, overrides=rejected))
        self.assertEqual([], notes(rows["measure:Sales/Total"], "src-2"))

    def test_same_input_twice_gives_the_same_row_order_and_ids(self):
        first = rows_of(self.TARGET, self.DONOR)
        second = rows_of(copy.deepcopy(self.TARGET), copy.deepcopy(self.DONOR))
        self.assertEqual([(row["row_key"], row["row_id"]) for row in first], [(row["row_key"], row["row_id"]) for row in second])
        self.assertEqual(first, second)


class RowKeyKindTests(unittest.TestCase):
    def test_row_key_kinds_of_the_secret_check_equal_the_source_kinds(self):
        self.assertEqual(set(OBJECT_KINDS), set(ROW_KEY_KINDS))
        for name in ("SalesA", "SalesB", "Finance", "Legacy"):
            index = object_index(detect_local_source(LAB / name / f"{name}.pbip"))
            self.assertLessEqual({key.split(":", 1)[0] for key in index}, set(OBJECT_KINDS), name)


class LockReadTests(unittest.TestCase):
    def test_a_permission_error_on_the_lock_read_or_stat_gives_a_read_only_open(self):
        from unittest.mock import patch

        from backend.devcenter.session import store

        with tempfile.TemporaryDirectory() as folder:
            lock = Path(folder) / "session.lock"
            lock.write_bytes(store.canonical_bytes({"pid": 2 ** 31 - 2, "owner": "other"}))

            def denied(*args, **kwargs):
                raise PermissionError(13, "Access is denied")

            for name in ("read_bytes", "stat"):
                with self.subTest(call=name), patch.object(Path, name, denied):
                    self.assertFalse(store.SessionLock(Path(folder), "mine").acquire())


class PhraseContractTests(unittest.TestCase):
    EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️‍]")

    def phrases(self) -> dict:
        return json.loads(PHRASES.read_text(encoding="utf-8"))["phrases"]

    def problems(self, phrases: dict) -> list[str]:
        found = []
        for phrase_id, entry in phrases.items():
            text = entry["text"]
            if "—" in text or "–" in text:
                found.append(f"{phrase_id}: dash")
            if self.EMOJI.search(text):
                found.append(f"{phrase_id}: emoji")
            if len(text) > 60:
                found.append(f"{phrase_id}: too long")
        return found

    def test_each_engine_phrase_id_is_in_the_file(self):
        phrases = self.phrases()
        for phrase_id in (*PROPERTY_PHRASE_IDS, *NOTE_IDS, *WARNING_IDS):
            self.assertIn(phrase_id, phrases)
        self.assertEqual([], self.problems(phrases))
        self.assertIn("phrases.json", contracts.names())

    def test_the_check_refuses_a_dash_an_emoji_and_long_text(self):
        bad = {"a": {"text": "Expression — changed"}, "b": {"text": "Dash – here"}, "c": {"text": "Changed \U0001F600"},
               "d": {"text": "x" * 61}}
        self.assertEqual(["a: dash", "b: dash", "c: emoji", "d: too long"], self.problems(bad))


# Session tests on the merge lab ------------------------------------------------


class MergeLabTestCase(unittest.TestCase):
    """A temp project with the merge lab. Target SalesA (model and report), donors SalesB, Finance, Legacy."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name) / "project"
        for name in ("SalesA", "SalesB", "Finance", "Legacy"):
            shutil.copytree(LAB / name, cls.root / name)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def setUp(self) -> None:
        self.devcenter = DevCenterSessions(app_data_dir=None)
        self.devcenter.attach_project(self.root)
        self.app = create_app(use_native=False)
        self.app.devcenter = self.devcenter
        self.ok("session_create", {"display_name": "Compare"})
        for name in ("SalesA", "SalesB", "Finance", "Legacy"):
            self.ok("source_add", {"base_revision": self.devcenter.revision, "path": str(self.root / name / f"{name}.pbip")})
        self.ok("target_set", {"base_revision": self.devcenter.revision, "model": {"mode": "existing", "source_id": "src-1"},
                               "report": {"mode": "existing", "source_id": "src-1"}})

    def tearDown(self) -> None:
        self.devcenter.close()
        self.app.close()

    def ok(self, method: str, request: dict) -> dict:
        reply = jsapi.call(self.devcenter, method, request)
        self.assertNotIn("error", reply, reply)
        self.assertEqual([], contracts.errors(contracts.jsapi_reply(method), reply), reply)
        return reply

    def get(self, path: str, contract: str = "http/compare-rows.reply.json") -> dict:
        status, payload = self.app.handle("GET", "/api/devcenter/" + path)
        self.assertEqual(200, status, payload)
        self.assertEqual([], contracts.errors(contract, payload), payload)
        self.assertEqual(self.devcenter.revision, payload["revision"])
        return payload

    def all_rows(self, query: str = "") -> dict:
        return self.get("compare-rows?limit=1000" + (f"&{query}" if query else ""))


class MergeLabCompareTests(MergeLabTestCase):
    def test_full_row_set_equals_the_golden_file(self):
        reply = self.all_rows()
        golden = {"rows": reply["rows"], "warnings": reply["warnings"], "state_counts": reply["state_counts"]}
        if UPDATE_GOLDEN:
            GOLDEN.parent.mkdir(parents=True, exist_ok=True)
            GOLDEN.write_text(json.dumps(golden, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
        self.assertEqual(json.loads(GOLDEN.read_text(encoding="utf-8")), golden)

    def test_known_merge_lab_cases(self):
        rows = by_key(self.all_rows()["rows"])
        self.assertEqual("renamed", cell(rows["measure:Sales/Total Sales"], "src-2")["state"])
        self.assertEqual("measure:Sales/Sales Amount", cell(rows["measure:Sales/Total Sales"], "src-2")["source_key"])
        self.assertEqual("same", cell(rows["measure:Sales/Total Sales"], "src-4")["state"], "TMSL reads the same as TMDL")
        self.assertEqual("moved", cell(rows["measure:Sales/Total Cost"], "src-2")["state"])
        self.assertIn("possible_rename", notes(rows["column:Store/Store Name"], "src-2"))
        self.assertIn("possible_rename", notes(rows["measure:Sales/Total Sales"], "src-3"))
        self.assertIn("duplicate_lineage_tag", notes(rows["measure:Sales/Average Sale"], "src-2"))

    def test_same_input_twice_gives_the_same_rows(self):
        self.assertEqual(self.all_rows()["rows"], self.all_rows()["rows"])

    def test_q_filters_by_name_case_insensitive(self):
        rows = self.all_rows("q=TOTAL")["rows"]
        self.assertEqual({"measure:Sales/Total Cost", "measure:Sales/Total Sales", "visual:overview/totalsales"},
                         {row["row_key"] for row in rows})
        self.assertIn("measure:Sales/Total Sales", {row["row_key"] for row in self.all_rows("q=sales%20amount")["rows"]},
                      "q also finds the donor name")

    def test_total_and_state_counts_are_for_the_full_filtered_set(self):
        full = self.all_rows("type=measure,column")
        page = self.get("compare-rows?type=measure,column&limit=3&offset=2")
        self.assertEqual(full["total"], page["total"])
        self.assertEqual(full["state_counts"], page["state_counts"])
        self.assertEqual(full["rows"][2:5], page["rows"])
        self.assertTrue(page["has_more"])
        counts = {state: sum(1 for row in full["rows"] if row["row_state"] == state) for state in STATES}
        self.assertEqual(counts, full["state_counts"])
        self.assertEqual(len(full["rows"]), full["total"])

    def test_sort_is_stable_asc_and_desc(self):
        default = [row["row_key"] for row in self.all_rows()["rows"]]
        for field, value in (("state", lambda row: STATES.index(row["row_state"])), ("name", lambda row: row["name"].casefold()),
                             ("type", lambda row: row["object_type"]), ("table", lambda row: (row["table"] or row["page"] or "").casefold())):
            for order in ("asc", "desc"):
                with self.subTest(field=field, order=order):
                    rows = self.all_rows(f"sort={field}:{order}")["rows"]
                    self.assertEqual(rows, self.all_rows(f"sort={field}&order={order}")["rows"])
                    values = [value(row) for row in rows]
                    if field != "type":
                        self.assertEqual(sorted(values, reverse=order == "desc"), values)
                    for left, right in zip(rows, rows[1:]):
                        if value(left) == value(right):
                            self.assertLess(default.index(left["row_key"]), default.index(right["row_key"]), "Equal values keep the order")

    def test_row_state_is_the_highest_precedence_cell_state_and_the_filter_uses_it(self):
        reply = self.all_rows()
        for row in reply["rows"]:
            states = [item["state"] for item in row["cells"]]
            self.assertEqual(min(states, key=STATES.index) if cell(row, "src-1")["present"] else "missing", row["row_state"])
        for state in STATES:
            filtered = self.all_rows(f"state={state}")["rows"]
            self.assertEqual([row["row_key"] for row in reply["rows"] if row["row_state"] == state], [row["row_key"] for row in filtered])

    def test_other_filters(self):
        self.assertTrue(all(row["table"] == "Sales" for row in self.all_rows("table=sales")["rows"]))
        self.assertTrue(all(row["page"] == "overview" for row in self.all_rows("page=overview")["rows"]))
        self.assertTrue(all(row["changed"] for row in self.all_rows("changed=true")["rows"]))
        finance = self.all_rows("source=src-3")["rows"]
        self.assertTrue(finance and all(cell(row, "src-3")["present"] for row in finance))

    def test_display_folders_of_a_source_and_the_type_filter(self):
        path = self.root / "SalesB/SalesB.SemanticModel/definition/tables/Measures.tmdl"
        original = path.read_text(encoding="utf-8")
        try:
            path.write_text(original.replace("\t\tformatString: 0%\n", "\t\tformatString: 0%\n\t\tdisplayFolder: Rates\\Discounts\n"),
                            encoding="utf-8")
            reply = self.get("display-folders?source=src-2", "http/display-folders.reply.json")
            self.assertEqual(["Rates\\Discounts"], reply["folders"])
            self.assertEqual([], self.get("display-folders?source=src-2&object_type=column", "http/display-folders.reply.json")["folders"])
            self.assertEqual(["Rates\\Discounts"], self.get("display-folders?source=src-2&type=measure",
                                                             "http/display-folders.reply.json")["folders"])
            self.assertEqual([], self.get("display-folders", "http/display-folders.reply.json")["folders"], "Default: the target model")
        finally:
            path.write_text(original, encoding="utf-8")

    def test_row_diff(self):
        rows = by_key(self.all_rows()["rows"])
        row = rows["measure:Sales/Margin"]
        for key in (row["row_id"], quote(row["row_key"], safe="")):
            reply = self.get(f"compare-rows/{key}/diff?source=src-2", "http/compare-row-diff.reply.json")
            self.assertEqual(("dax", "[Total Sales] - [Total Cost]"), (reply["language"], reply["reference_text"]))
            self.assertIn("DIVIDE", reply["source_text"])
        status, payload = self.app.handle("GET", "/api/devcenter/compare-rows/r-0000000000000000/diff")
        self.assertEqual((404, "not_found"), (status, payload["error"]["code"]))

    def test_marks_map_to_rows_by_source_key(self):
        path = self.root / "SalesB/SalesB.SemanticModel/definition/tables/Sales.tmdl"
        original = path.read_text(encoding="utf-8")
        try:
            path.write_text(original.replace("SUM(Sales[Amount])\n\t\tformatString: #,0", "SUM(Sales[Amount]) + 0\n\t\tformatString: #,0"),
                            encoding="utf-8")
            self.ok("sources_check", {"base_revision": self.devcenter.revision})
            row = by_key(self.all_rows("marks=any")["rows"])["measure:Sales/Total Sales"]
            self.assertEqual([{"source_id": "src-2", "row_key": "measure:Sales/Sales Amount", "mark": "source_changed"}], row["marks"])
            self.ok("row_confirm", {"base_revision": self.devcenter.revision, "row_keys": [row["marks"][0]["row_key"]]})
        finally:
            path.write_text(original, encoding="utf-8")
            self.ok("sources_check", {"base_revision": self.devcenter.revision})


class AlignmentOverrideTests(MergeLabTestCase):
    def test_break_removes_the_merge_choice_and_gives_the_new_row_keys(self):
        current = self.devcenter._open
        draft = copy.deepcopy(current.document)
        draft["merge_choices"]["measure:Sales/Margin"] = {"choice": "keep_target"}
        self.devcenter._commit(current, draft, "test_seed", None, None, None)
        reply = self.ok("alignment_override", {"base_revision": self.devcenter.revision, "action": "break", "source_id": "src-2",
                                               "row_key": "measure:Sales/Margin"})
        self.assertEqual(["measure:Sales/Margin", "measure:Sales/Margin@src-2"], reply["row_keys"])
        self.assertEqual(["measure:Sales/Margin"], reply["removed_choices"])
        self.assertNotIn("measure:Sales/Margin", self.devcenter._open.document["merge_choices"])
        rows = by_key(self.all_rows()["rows"])
        self.assertFalse(cell(rows["measure:Sales/Margin"], "src-2")["present"])
        self.assertIn("name_clash", notes(rows["measure:Sales/Margin@src-2"], "src-2"))
        reply = self.ok("alignment_override", {"base_revision": self.devcenter.revision, "action": "clear", "source_id": "src-2",
                                               "row_key": "measure:Sales/Margin"})
        self.assertEqual(["measure:Sales/Margin"], reply["row_keys"])
        self.assertTrue(cell(by_key(self.all_rows()["rows"])["measure:Sales/Margin"], "src-2")["present"])

    def test_confirm_and_reject_a_possible_rename(self):
        request = {"base_revision": self.devcenter.revision, "action": "confirm", "source_id": "src-2",
                   "row_key": "column:Store/Store Name", "other_row_key": "column:Store/Store Label"}
        reply = self.ok("alignment_override", request)
        self.assertEqual(["column:Store/Store Name"], reply["row_keys"])
        row = by_key(self.all_rows()["rows"])["column:Store/Store Name"]
        self.assertEqual(("renamed", "manual"), (cell(row, "src-2")["state"], cell(row, "src-2")["step"]))
        self.ok("alignment_override", {"base_revision": self.devcenter.revision, "action": "clear", "source_id": "src-2",
                                       "row_key": "column:Store/Store Name"})
        self.ok("alignment_override", {**request, "base_revision": self.devcenter.revision, "action": "reject_rename"})
        rows = by_key(self.all_rows()["rows"])
        self.assertEqual([], notes(rows["column:Store/Store Name"], "src-2"))
        self.assertEqual({"src-2": [{"kind": "reject_rename", "target_key": "column:Store/Store Name", "donor_key": "column:Store/Store Label"}]},
                         self.devcenter._open.document["alignment_overrides"])

    def test_compare_mode_set_changes_the_rows(self):
        path = self.root / "SalesB/SalesB.SemanticModel/definition/tables/Date.tmdl"
        original = path.read_text(encoding="utf-8")
        try:
            path.write_text(original.replace("\t\tsourceColumn: Date\n", "\t\tsourceColumn: Date\n\n\t\tannotation Note = x\n", 1),
                            encoding="utf-8")
            self.assertEqual("same", cell(by_key(self.all_rows()["rows"])["column:Date/Date"], "src-2")["state"])
            self.ok("compare_mode_set", {"base_revision": self.devcenter.revision, "compare_mode": "strict"})
            reply = self.all_rows()
            self.assertEqual("strict", reply["compare_mode"])
            found = cell(by_key(reply["rows"])["column:Date/Date"], "src-2")
            self.assertEqual(("different", ["annotations_changed"]), (found["state"], [p["phrase_id"] for p in found["phrases"]]))
        finally:
            path.write_text(original, encoding="utf-8")

    def test_errors_have_the_error_shape(self):
        for request in ({"base_revision": self.devcenter.revision, "action": "break", "source_id": "src-2", "row_key": "measure:Sales/Revenue"},
                        {"base_revision": self.devcenter.revision, "action": "confirm", "source_id": "src-2", "row_key": "measure:Sales/Margin"},
                        {"base_revision": 1, "action": "break", "source_id": "src-2", "row_key": "measure:Sales/Margin"},
                        {"base_revision": self.devcenter.revision, "action": "break", "source_id": "src-9", "row_key": "measure:Sales/Margin"}):
            with self.subTest(request=request):
                reply = jsapi.call(self.devcenter, "alignment_override", request)
                self.assertIn("error", reply)
                self.assertEqual([], contracts.errors(contracts.ERROR, reply))
        reply = jsapi.call(self.devcenter, "compare_mode_set", {"base_revision": self.devcenter.revision, "compare_mode": "loose"})
        self.assertEqual("invalid_payload", reply["error"]["code"])

    def test_each_s3_method_has_a_request_and_a_reply_schema(self):
        names = set(contracts.names())
        for method in S3_METHODS:
            self.assertIn(method, jsapi.METHODS)
            self.assertIn(contracts.jsapi_request(method), names)
            self.assertIn(contracts.jsapi_reply(method), names)


if __name__ == "__main__":
    unittest.main()
