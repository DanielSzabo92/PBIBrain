"""Build step S4: naming rules (technical design sections 5 and 16, UC16, UC18, UC19, UC34)."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from backend.api.app import create_app
from backend.devcenter import contracts, jsapi
from backend.devcenter.naming.detector import NamingSettings, detect
from backend.devcenter.naming.jsapi_methods import S4_METHODS
from backend.devcenter.naming.objects import DATA_COLUMN, MEASURE, NamedObject, model_objects
from backend.devcenter.naming.proposer import breaks, propose
from backend.devcenter.naming.rules import identity_key, is_case, make_rule, obeys
from backend.devcenter.naming.tokens import tokenize
from backend.devcenter.session.manager import DevCenterSessions
from backend.devcenter.sources.kinds import detect_local_source
from tests.helpers.mock_pbip import copy_mock_project, dir_sha256_manifest, has_mock_data, mock_data_root

REPOSITORY = Path(__file__).resolve().parents[1]
LAB = REPOSITORY / "tests" / "fixtures" / "merge_lab"

# Ten measures in the table _Measures, title case with a space, five of them with
# a percent format and the unit word "%". Six measures start with "KPI " and live in the
# display folder "KPIs". One measure ("gross_profit") breaks the letter case rule.
MEASURES = (
    ("KPI Total Sales", "#,0", "KPIs"),
    ("KPI Total Cost", "#,0", "KPIs"),
    ("KPI Margin %", "0.0%", "KPIs"),
    ("KPI Growth %", "0.0%", "KPIs"),
    ("KPI Share %", "0.0%", "KPIs"),
    ("KPI Order Count", "#,0", "KPIs"),
    ("Average Price", "#,0.00", None),
    ("Return Rate %", "0%", None),
    ("Fill Rate %", "0%", None),
    ("gross_profit", "#,0", None),
)


def tmdl_name(name: str) -> str:
    return f"'{name}'" if any(char in name for char in " %-") else name


def write_model(folder: Path, measures=MEASURES, tables=("Sales", "Store", "Date", "Product", "Customer")) -> Path:
    definition = folder / "definition"
    (definition / "tables").mkdir(parents=True)
    (definition / "model.tmdl").write_text("model Model\n\tculture: en-US\n", encoding="utf-8")
    lines = ["table _Measures", "\tlineageTag: t-measures", ""]
    for index, (name, fmt, display_folder) in enumerate(measures):
        lines += [f"\tmeasure {tmdl_name(name)} = {index}", f"\t\tformatString: {fmt}"]
        if display_folder:
            lines.append(f"\t\tdisplayFolder: {display_folder}")
        lines += [f"\t\tlineageTag: m-{index}", ""]
    (definition / "tables" / "_Measures.tmdl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for table in tables:
        text = f"table {table}\n\tlineageTag: t-{table}\n\n\tcolumn Key\n\t\tdataType: int64\n\t\tsourceColumn: Key\n\n" \
               f"\tcolumn 'Key Text' = FORMAT([Key], \"0\")\n\t\tdataType: string\n"
        (definition / "tables" / f"{table}.tmdl").write_text(text, encoding="utf-8")
    return folder


class TokenizerTests(unittest.TestCase):
    def test_the_tokenizer_splits_separators_and_case_changes(self):
        expected = {
            "Total Sales": ["Total", "Sales"],
            "total_sales_amt": ["total", "sales", "amt"],
            "totalSalesAmt": ["total", "Sales", "Amt"],
            "TotalSales": ["Total", "Sales"],
            "HTTPServer": ["HTTP", "Server"],
            "dim-Customer": ["dim", "Customer"],
            "Q1Sales": ["Q", "1", "Sales"],
            "Margin %": ["Margin", "%"],
            "KPI_Margin%": ["KPI", "Margin", "%"],
            "Sales  Amount": ["Sales", "Amount"],
            "UPPER": ["UPPER"],
        }
        for name, tokens in expected.items():
            with self.subTest(name=name):
                self.assertEqual(tokens, tokenize(name))


def measures(names: list[str]) -> list[NamedObject]:
    return [NamedObject(MEASURE, name, "Sales") for name in names]


def prefix_rules(rules: list[dict]) -> list[dict]:
    return [rule for rule in rules if rule["check"]["kind"] == "prefix"]


class DetectionTests(unittest.TestCase):
    def test_detection_offers_a_rule_at_5_objects_and_80_percent(self):
        found = prefix_rules(detect(measures(["KPI A", "KPI B", "KPI C", "KPI D", "Other"])))
        self.assertEqual(["KPI "], [rule["check"]["value"] for rule in found])
        self.assertEqual(("proposed", "detected"), (found[0]["status"], found[0]["origin"]))

    def test_detection_does_not_offer_a_rule_at_4_objects(self):
        self.assertEqual([], prefix_rules(detect(measures(["KPI A", "KPI B", "KPI C", "KPI D"]))))

    def test_detection_offers_at_80_percent_but_not_at_79_percent(self):
        def names(count: int) -> list[str]:
            return [f"KPI M{index}" for index in range(count)] + [f"Other{index}" for index in range(100 - count)]

        self.assertEqual(1, len(prefix_rules(detect(measures(names(80))))))
        self.assertEqual([], prefix_rules(detect(measures(names(79)))))

    def test_the_limits_come_from_the_settings(self):
        four = measures(["KPI A", "KPI B", "KPI C", "KPI D"])
        self.assertEqual(1, len(prefix_rules(detect(four, NamingSettings(min_objects=4)))))
        five = measures(["KPI A", "KPI B", "KPI C", "Other", "More"])
        self.assertEqual([], prefix_rules(detect(five)))
        self.assertEqual(1, len(prefix_rules(detect(five, NamingSettings.from_mapping({"min_support": 0.6})))))

    def test_the_same_objects_give_the_same_rule_ids(self):
        objects = measures(["KPI A", "KPI B", "KPI C", "KPI D", "KPI E"])
        self.assertEqual([rule["rule_id"] for rule in detect(objects)], [rule["rule_id"] for rule in detect(list(reversed(objects)))])

    def test_the_reader_finds_the_object_types(self):
        with tempfile.TemporaryDirectory() as folder:
            objects = model_objects(detect_local_source(write_model(Path(folder) / "M.SemanticModel")))
        kinds = {(item.object_type, item.name) for item in objects}
        self.assertIn(("data_column", "Key"), kinds)
        self.assertIn(("calculated_column", "Key Text"), kinds)
        self.assertIn(("measure", "KPI Margin %"), kinds)
        margin = next(item for item in objects if item.name == "KPI Margin %")
        self.assertEqual(("_Measures", "KPIs", "percent"), (margin.table, margin.display_folder, margin.format_kind))
        lab = {(item.object_type, item.name) for item in model_objects(detect_local_source(LAB / "SalesA/SalesA.pbip"))}
        self.assertIn(("calculation_group", "Time Intelligence"), lab)
        self.assertIn(("calculated_table", "Metric Selector"), lab)
        self.assertIn(("hierarchy", "Calendar"), lab)


def confirmed(rule_id: str, kind: str, value: str, scope: dict | None = None, **extra) -> dict:
    return make_rule(rule_id, MEASURE, scope, {"kind": kind, "value": value, **extra}, "detected", "confirmed")


class ProposerTests(unittest.TestCase):
    RULES = [
        confirmed("nr-000000000005", "folder_by_type", "_Measures", folder="table"),
        confirmed("nr-000000000004", "unit_word", "%", {"format_kind": "percent"}),
        confirmed("nr-000000000003", "prefix", "KPI "),
        confirmed("nr-000000000002", "separator", "space"),
        confirmed("nr-000000000001", "letter_case", "title"),
        make_rule("nr-000000000009", MEASURE, None, {"kind": "suffix", "value": " X"}, "detected", "proposed"),
    ]

    def test_the_proposer_applies_the_fixed_order_and_gives_the_rule_ids(self):
        result = propose("gross_margin", MEASURE, {"table": "Sales", "format_kind": "percent"}, self.RULES, [])
        self.assertEqual("KPI Gross Margin %", result["name"])
        self.assertEqual(["nr-000000000001", "nr-000000000002", "nr-000000000003", "nr-000000000004", "nr-000000000005"],
                         result["rule_ids"])
        self.assertEqual("_Measures", result["table"])
        self.assertIsNone(result["clash"])

    def test_the_proposer_does_not_add_a_prefix_two_times(self):
        self.assertEqual("KPI Total Sales", propose("kpi total sales", MEASURE, {}, self.RULES, [])["name"])

    def test_a_clash_adds_the_donor_source_name(self):
        existing = [NamedObject(MEASURE, "kpi total sales", "_Measures")]
        result = propose("Total Sales", MEASURE, {}, self.RULES, existing, "Model B")
        self.assertEqual("KPI Total Sales (Model B)", result["name"])
        self.assertEqual("measure:_Measures/kpi total sales", result["clash"]["row_key"])
        existing.append(NamedObject(MEASURE, "KPI Total Sales (Model B)", "_Measures"))
        self.assertEqual("KPI Total Sales (Model B 2)", propose("Total Sales", MEASURE, {}, self.RULES, existing, "Model B")["name"])


class NamingSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "project"
        self.model = write_model(self.root / "Target.SemanticModel")
        shutil.copytree(LAB / "SalesB", self.root / "SalesB")
        shutil.copytree(LAB / "SalesA", self.root / "SalesA")
        self.devcenter = DevCenterSessions(app_data_dir=None)
        self.devcenter.attach_project(self.root)
        self.app = create_app(use_native=False)
        self.app.devcenter = self.devcenter
        self.ok("session_create", {"display_name": "Naming"})
        self.target = self.add("Target.SemanticModel")
        self.donor = self.add("SalesB/SalesB.pbip")
        self.ok("target_set", {"base_revision": self.devcenter.revision, "model": {"mode": "existing", "source_id": self.target}})

    def tearDown(self) -> None:
        self.devcenter.close()
        self.app.close()
        self.temporary.cleanup()

    def call(self, method: str, request: dict) -> dict:
        reply = jsapi.call(self.devcenter, method, request)
        name = contracts.ERROR if "error" in reply else contracts.jsapi_reply(method)
        self.assertEqual([], contracts.errors(name, reply), reply)
        return reply

    def ok(self, method: str, request: dict) -> dict:
        reply = self.call(method, request)
        self.assertNotIn("error", reply, reply)
        return reply

    def failed(self, method: str, request: dict, code: str) -> dict:
        reply = self.call(method, request)
        self.assertEqual(code, reply.get("error", {}).get("code"), reply)
        return reply["error"]

    def add(self, relative: str) -> str:
        return self.ok("source_add", {"base_revision": self.devcenter.revision, "path": str(self.root / relative)})["source"]["source_id"]

    def change(self, method: str, **request) -> dict:
        return self.ok(method, {"base_revision": self.devcenter.revision, **request})

    def rules(self) -> dict:
        status, payload = self.app.handle("GET", "/api/devcenter/naming-rules")
        self.assertEqual(200, status, payload)
        self.assertEqual([], contracts.errors("http/naming-rules.reply.json", payload), payload)
        self.assertEqual(self.devcenter.revision, payload["revision"])
        return payload

    def rule(self, kind: str, object_type: str = "measure", **scope) -> dict:
        found = [rule for rule in self.rules()["rules"] if rule["check"]["kind"] == kind and rule["object_type"] == object_type
                 and all(rule["scope"][key] == value for key, value in scope.items())]
        self.assertEqual(1, len(found), found)
        return found[0]

    def propose(self, body: dict) -> tuple[int, dict]:
        status, payload = self.app.handle("POST", "/api/devcenter/name-propose", json.dumps(body).encode("utf-8"))
        if status == 200:
            self.assertEqual([], contracts.errors("http/name-propose.reply.json", payload), payload)
        return status, payload

    def rule_file(self) -> Path:
        return self.root / ".pbibrain" / "naming-rules" / "Target.SemanticModel.json"

    def test_the_screen_shows_detected_rules_with_support_and_breaks(self):
        payload = self.rules()
        self.assertEqual({"source_id": self.target, "model_name": "Target",
                          "rule_file": ".pbibrain/naming-rules/Target.SemanticModel.json"}, payload["target"])
        letter_case = self.rule("letter_case")
        self.assertEqual(("title", "proposed", "detected"), (letter_case["check"]["value"], letter_case["status"], letter_case["origin"]))
        self.assertEqual({"count": 9, "total": 10}, letter_case["support"])
        self.assertEqual(1, letter_case["breaks"])
        self.assertEqual("Measure names use Title Case.", letter_case["text"])
        self.assertEqual("%", self.rule("unit_word", format_kind="percent")["check"]["value"])
        self.assertEqual("_Measures", self.rule("folder_by_type", name_prefix=None)["check"]["value"])
        self.assertEqual("KPIs", self.rule("folder_by_type", name_prefix="KPI ")["check"]["value"])
        self.assertFalse(self.rule_file().exists(), "A read must not write the rule file")

    def test_a_rejected_rule_is_not_offered_again(self):
        rule = self.rule("letter_case")
        reply = self.change("naming_rule_reject", rule_id=rule["rule_id"])
        self.assertEqual((False, "rejected"), (reply["removed"], reply["rule"]["status"]))
        again = [item for item in self.rules()["rules"] if item["check"]["kind"] == "letter_case" and item["object_type"] == "measure"]
        self.assertEqual([("rejected", rule["rule_id"])], [(item["status"], item["rule_id"]) for item in again])
        stored = json.loads(self.rule_file().read_text(encoding="utf-8"))
        self.assertEqual(["rejected"], [item["status"] for item in stored["rules"]])

    def test_uc16_reject_and_edit(self):
        created = self.change("naming_rule_edit", object_type="table", check={"kind": "prefix", "value": "dim"})["rule"]
        self.assertEqual(("user", "confirmed"), (created["origin"], created["status"]))
        removed = self.change("naming_rule_reject", rule_id=created["rule_id"])
        self.assertEqual((True, None), (removed["removed"], removed["rule"]))
        self.assertNotIn(created["rule_id"], [item["rule_id"] for item in self.rules()["rules"]])
        proposed = self.rule("separator")
        edited = self.change("naming_rule_edit", rule_id=proposed["rule_id"], object_type="measure",
                             check={"kind": "separator", "value": "underscore"})["rule"]
        self.assertEqual((proposed["rule_id"], "confirmed", "detected", "underscore"),
                         (edited["rule_id"], edited["status"], edited["origin"], edited["check"]["value"]))
        confirmed_rule = self.change("naming_rule_confirm", rule_id=self.rule("letter_case")["rule_id"])["rule"]
        self.assertEqual("confirmed", confirmed_rule["status"])
        session = self.devcenter._open.document["naming_rules"]
        self.assertEqual(".pbibrain/naming-rules/Target.SemanticModel.json", session["path"])
        self.assertTrue(session["hash"].startswith("sha256:"))

    def assert_unique_ids(self) -> list[dict]:
        rules = self.rules()["rules"]
        ids = [rule["rule_id"] for rule in rules]
        self.assertEqual(len(ids), len(set(ids)), ids)
        return rules

    def test_an_edited_detected_rule_is_not_offered_again(self):
        letter_case = self.rule("letter_case")
        self.change("naming_rule_edit", rule_id=letter_case["rule_id"], object_type="measure", check={"kind": "suffix", "value": " X"})
        rules = self.assert_unique_ids()
        self.assertEqual([], [rule for rule in rules if rule["object_type"] == "measure" and rule["check"]["kind"] == "letter_case"])
        edited = next(rule for rule in rules if rule["rule_id"] == letter_case["rule_id"])
        self.assertEqual(("suffix", "confirmed"), (edited["check"]["kind"], edited["status"]))

    def test_an_edited_then_rejected_rule_is_not_offered_again(self):
        separator = self.rule("separator")
        self.change("naming_rule_edit", rule_id=separator["rule_id"], object_type="measure",
                    check={"kind": "separator", "value": "underscore"})
        self.change("naming_rule_reject", rule_id=separator["rule_id"])
        rules = self.assert_unique_ids()
        found = [(rule["status"], rule["check"]["value"]) for rule in rules
                 if rule["object_type"] == "measure" and rule["check"]["kind"] == "separator"]
        self.assertEqual([("rejected", "underscore")], found)

    def test_a_damaged_rule_in_the_file_gives_rules_file_damaged(self):
        self.change("naming_rule_confirm", rule_id=self.rule("letter_case")["rule_id"])
        for damage in ({"check": None}, {"status": "unknown"}, {"scope": {"other": 1}}):
            with self.subTest(damage=damage):
                document = json.loads(self.rule_file().read_text(encoding="utf-8"))
                rule = {key: value for key, value in document["rules"][0].items() if key not in damage}
                rule.update({key: value for key, value in damage.items() if value is not None})
                self.rule_file().write_text(json.dumps({**document, "rules": [rule]}), encoding="utf-8")
                status, payload = self.app.handle("GET", "/api/devcenter/naming-rules")
                self.assertEqual((400, "rules_file_damaged"), (status, payload["error"]["details"]["reason"]))
                error = self.failed("naming_rule_edit", {"base_revision": self.devcenter.revision, "object_type": "table",
                                                         "check": {"kind": "prefix", "value": "d"}}, "action_not_allowed")
                self.assertEqual("rules_file_damaged", error["details"]["reason"])
                document["rules"][0].pop("text", None)
                self.rule_file().write_text(json.dumps(document), encoding="utf-8")

    def test_uc34_a_duplicate_rule_gives_action_not_allowed(self):
        existing = self.rule("letter_case")
        error = self.failed("naming_rule_edit", {"base_revision": self.devcenter.revision, "object_type": "measure",
                                                 "check": {"kind": "letter_case", "value": "camel"}}, "action_not_allowed")
        self.assertEqual(existing["rule_id"], error["details"]["existing_rule_id"])
        self.change("naming_rule_reject", rule_id=existing["rule_id"])
        self.change("naming_rule_edit", object_type="measure", check={"kind": "letter_case", "value": "camel"})

    def test_a_user_regex_rule_checks_a_name(self):
        rule = self.change("naming_rule_edit", object_type="measure", scope={"table": "_Measures"},
                           check={"kind": "regex", "value": "^[A-Z][A-Za-z %]+$"})["rule"]
        self.assertEqual({"count": 9, "total": 10}, rule["support"])
        status, payload = self.propose({"name": "x", "object_type": "measure", "table": "_Measures", "candidate": "bad_name"})
        self.assertEqual(200, status, payload)
        self.assertEqual([rule["rule_id"]], [item["rule_id"] for item in payload["breaks"]])
        status, payload = self.propose({"name": "x", "object_type": "measure", "table": "_Measures", "candidate": "Good Name"})
        self.assertEqual([], payload["breaks"])
        error = self.failed("naming_rule_edit", {"base_revision": self.devcenter.revision, "object_type": "table",
                                                 "check": {"kind": "regex", "value": "("}}, "invalid_payload")
        self.assertEqual("invalid_regex", error["details"]["reason"])

    def test_uc19_name_propose_gives_breaks_and_clash(self):
        letter_case = self.change("naming_rule_confirm", rule_id=self.rule("letter_case")["rule_id"])["rule"]
        before = (self.devcenter.revision, self.rule_file().read_bytes())
        status, payload = self.propose({"name": "kpi total sales", "object_type": "measure", "source_id": self.donor,
                                        "candidate": "kpi total SALES"})
        self.assertEqual(200, status, payload)
        self.assertEqual([letter_case["rule_id"]], [item["rule_id"] for item in payload["breaks"]])
        self.assertEqual("Measure names use Title Case.", payload["breaks"][0]["text"])
        self.assertEqual({"object_type": "measure", "name": "KPI Total Sales", "table": "_Measures",
                          "row_key": "measure:_Measures/KPI Total Sales"}, payload["clash"])
        self.assertEqual("Kpi Total Sales (SalesB)", payload["name"])
        self.assertEqual([letter_case["rule_id"]], payload["rule_ids"])
        self.assertEqual("KPI Total Sales", payload["resolved_clash"]["name"])
        status, payload = self.propose({"name": "net value", "object_type": "measure", "candidate": "Net Value"})
        self.assertEqual(([], None, "Net Value"), (payload["breaks"], payload["clash"], payload["name"]))
        self.assertEqual(before, (self.devcenter.revision, self.rule_file().read_bytes()), "name-propose must change nothing")
        status, payload = self.propose({"object_type": "measure"})
        self.assertEqual((400, "invalid_payload"), (status, payload["error"]["code"]))

    def test_uc18_naming_rules_gives_the_rule_count_of_each_source_model(self):
        self.add("SalesA/SalesA.pbip")
        # SalesB gives 4 detected rules, SalesA gives 2 (data column letter case and separator).
        self.assertEqual({"src-2": 4, "src-3": 2}, self.rules()["source_rule_counts"])
        user = make_rule("nr-00000000000a", "table", None, {"kind": "prefix", "value": "d"}, "user", "confirmed")
        path = self.root / ".pbibrain" / "naming-rules" / "SalesA.SemanticModel.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"schema_version": 1, "rules": [user]}), encoding="utf-8")
        self.assertEqual({"src-2": 4, "src-3": 3}, self.rules()["source_rule_counts"])
        rejected = make_rule("nr-00000000000b", "data_column", None, {"kind": "letter_case", "value": "title"}, "detected", "rejected")
        path.write_text(json.dumps({"schema_version": 1, "rules": [user, rejected]}), encoding="utf-8")
        self.assertEqual({"src-2": 4, "src-3": 2}, self.rules()["source_rule_counts"])

    def test_copy_of_a_rule_set_gives_proposed_rules(self):
        donor = write_model(self.root / "Donor.SemanticModel", measures=[(f"M_{index}", "#,0", None) for index in range(6)])
        source_id = self.add(donor.name)
        count = self.rules()["source_rule_counts"][source_id]
        self.assertGreater(count, 0)
        reply = self.change("naming_rules_copy", source_id=source_id)
        self.assertTrue(reply["copied"])
        self.assertEqual(count, len(reply["copied"]) + len(reply["skipped"]))
        self.assertTrue(all(rule["status"] == "proposed" and rule["copied_from"] == "Donor" for rule in reply["copied"]))
        self.assertIn("duplicate_rule", {item["reason"] for item in reply["skipped"]})
        self.failed("naming_rules_copy", {"base_revision": self.devcenter.revision, "source_id": self.target}, "action_not_allowed")

    def test_the_rule_file_is_outside_definition_and_a_tmdl_write_leaves_it(self):
        self.change("naming_rule_confirm", rule_id=self.rule("letter_case")["rule_id"])
        path = self.rule_file()
        self.assertTrue(path.is_file())
        self.assertNotIn(self.model.resolve(), path.resolve().parents)
        saved = path.read_bytes()
        self.assertTrue(saved.endswith(b"}\n") and b"\r" not in saved)
        # A TOM TMDL folder write rewrites each file and deletes each .tmdl file that it did not write.
        definition = self.model / "definition"
        texts = {item.relative_to(definition): item.read_bytes() for item in definition.rglob("*.tmdl")}
        shutil.rmtree(definition)
        for relative, data in texts.items():
            (definition / relative).parent.mkdir(parents=True, exist_ok=True)
            (definition / relative).write_bytes(data)
        self.assertEqual(saved, path.read_bytes())
        self.assertEqual("confirmed", self.rule("letter_case")["status"])

    def test_the_settings_of_the_rule_file_change_the_limits(self):
        self.change("naming_rule_confirm", rule_id=self.rule("letter_case")["rule_id"])
        document = json.loads(self.rule_file().read_text(encoding="utf-8"))
        document["settings"] = {"min_objects": 50}
        self.rule_file().write_text(json.dumps(document), encoding="utf-8")
        payload = self.rules()
        self.assertEqual(50, payload["settings"]["min_objects"])
        self.assertEqual(["confirmed"], [rule["status"] for rule in payload["rules"]])

    def test_a_stale_revision_and_an_unknown_rule_are_refused(self):
        rule_id = self.rule("letter_case")["rule_id"]
        self.failed("naming_rule_confirm", {"base_revision": self.devcenter.revision - 1, "rule_id": rule_id}, "stale_revision")
        self.failed("naming_rule_confirm", {"base_revision": self.devcenter.revision, "rule_id": "nr-000000000000"}, "not_found")
        self.assertFalse(self.rule_file().exists())

    def test_each_s4_method_has_a_request_and_a_reply_schema(self):
        names = set(contracts.names())
        for method in S4_METHODS:
            with self.subTest(method=method):
                self.assertIn(method, jsapi.METHODS)
                self.assertIn(contracts.jsapi_request(method), names)
                self.assertIn(contracts.jsapi_reply(method), names)


class NoTargetTests(unittest.TestCase):
    def test_no_target_gives_an_empty_read_and_refuses_a_change(self):
        with tempfile.TemporaryDirectory() as folder:
            devcenter = DevCenterSessions(app_data_dir=None)
            devcenter.attach_project(folder)
            app = create_app(use_native=False)
            app.devcenter = devcenter
            try:
                status, payload = app.handle("GET", "/api/devcenter/naming-rules")
                self.assertEqual((409, "session_not_open"), (status, payload["error"]["code"]))
                jsapi.call(devcenter, "session_create", {"display_name": "Empty"})
                status, payload = app.handle("GET", "/api/devcenter/naming-rules")
                self.assertEqual(200, status)
                self.assertEqual((None, []), (payload["target"], payload["rules"]))
                reply = jsapi.call(devcenter, "naming_rule_edit", {"base_revision": 1, "object_type": "table",
                                                                   "check": {"kind": "prefix", "value": "d"}})
                self.assertEqual("no_target", reply["error"]["details"]["reason"])
            finally:
                devcenter.close()
                app.close()


class AdversarialNamingFixesTests(unittest.TestCase):
    def test_title_case_rejects_all_caps_and_pascal_case(self) -> None:
        self.assertTrue(is_case("Total Sales", "title"))
        self.assertTrue(is_case("KPI Total Sales", "title"))
        self.assertTrue(is_case("Average Price", "title"))
        self.assertFalse(is_case("TOTAL SALES", "title"))
        self.assertFalse(is_case("UPPER", "title"))
        self.assertFalse(is_case("TotalSales", "title"))
        self.assertFalse(is_case("MyMeasure", "title"))
        self.assertFalse(is_case("KPI REVENUE", "title"))

    def test_decorated_names_from_propose_obey_their_rules(self) -> None:
        rules = [
            make_rule("nr-pref", MEASURE, None, {"kind": "prefix", "value": "m_"}, "user", "confirmed"),
            make_rule("nr-case", MEASURE, None, {"kind": "letter_case", "value": "title"}, "user", "confirmed"),
            make_rule("nr-sep", MEASURE, None, {"kind": "separator", "value": "space"}, "user", "confirmed"),
        ]
        proposed = propose("total_revenue", MEASURE, {"table": "Sales"}, rules, [])
        self.assertEqual("m_Total Revenue", proposed["name"])
        self.assertEqual([], breaks(proposed["name"], MEASURE, {"table": "Sales"}, rules))
        item = NamedObject(MEASURE, proposed["name"], "Sales")
        for r in rules:
            self.assertTrue(obeys(r, item, context_rules=rules), f"{proposed['name']} failed {r['rule_id']}")
        # Bad core inside decorated name must still fail case rule
        bad = NamedObject(MEASURE, "m_TotalRevenue", "Sales")
        self.assertFalse(obeys(rules[1], bad, context_rules=rules))

    def test_identity_key_distinguishes_folder_kind_and_multiple_regex_patterns(self) -> None:
        f_table = make_rule("nr-f1", MEASURE, None, {"kind": "folder_by_type", "value": "_Measures", "folder": "table"}, "user", "confirmed")
        f_df = make_rule("nr-f2", MEASURE, None, {"kind": "folder_by_type", "value": "KPIs", "folder": "display_folder"}, "user", "confirmed")
        self.assertNotEqual(identity_key(f_table), identity_key(f_df))

        rx1 = make_rule("nr-r1", MEASURE, None, {"kind": "regex", "value": "^[A-Z].+$"}, "user", "confirmed")
        rx2 = make_rule("nr-r2", MEASURE, None, {"kind": "regex", "value": "^(?!.*  ).*$"}, "user", "confirmed")
        self.assertNotEqual(identity_key(rx1), identity_key(rx2))

    def test_clash_obeys_underscore_and_regex_rules(self) -> None:
        rules = [
            make_rule("nr-sep", MEASURE, None, {"kind": "separator", "value": "underscore"}, "user", "confirmed"),
            make_rule("nr-case", MEASURE, None, {"kind": "letter_case", "value": "lower"}, "user", "confirmed"),
            make_rule("nr-rx", MEASURE, None, {"kind": "regex", "value": "^[a-z0-9_]+$"}, "user", "confirmed"),
        ]
        existing = [NamedObject(MEASURE, "total_sales", "Sales")]
        result = propose("Total Sales", MEASURE, {"table": "Sales"}, rules, existing, "Sales B")
        self.assertEqual("total_sales_sales_b", result["name"])
        self.assertEqual([], breaks(result["name"], MEASURE, {"table": "Sales"}, rules))

    def test_reject_copied_user_rule_marks_rejected_and_rule_view_exposes_breaking_objects(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write_model(root / "Target.SemanticModel")
            write_model(root / "Donor.SemanticModel", measures=[(f"M {i}", "#,0", None) for i in range(6)])
            user_rule = make_rule("nr-00000000000a", DATA_COLUMN, None, {"kind": "prefix", "value": "col_"}, "user", "confirmed")
            donor_rule_file = root / ".pbibrain" / "naming-rules" / "Donor.SemanticModel.json"
            donor_rule_file.parent.mkdir(parents=True, exist_ok=True)
            donor_rule_file.write_text(json.dumps({"schema_version": 1, "rules": [user_rule]}), encoding="utf-8")

            devcenter = DevCenterSessions(app_data_dir=None)
            devcenter.attach_project(root)
            app = create_app(use_native=False)
            app.devcenter = devcenter
            try:
                jsapi.call(devcenter, "session_create", {"display_name": "N"})
                t_id = jsapi.call(devcenter, "source_add", {"base_revision": devcenter.revision, "path": str(root / "Target.SemanticModel")})["source"]["source_id"]
                d_id = jsapi.call(devcenter, "source_add", {"base_revision": devcenter.revision, "path": str(root / "Donor.SemanticModel")})["source"]["source_id"]
                jsapi.call(devcenter, "target_set", {"base_revision": devcenter.revision, "model": {"mode": "existing", "source_id": t_id}})

                # Check breaking_objects returned in GET naming-rules
                _, payload = app.handle("GET", "/api/devcenter/naming-rules")
                lc = next(r for r in payload["rules"] if r["object_type"] == "measure" and r["check"]["kind"] == "letter_case")
                self.assertEqual(["gross_profit"], [b["name"] for b in lc["breaking_objects"]])

                # Check two regex rules allowed in same scope + column format_kind unit_word allowed
                r1 = jsapi.call(devcenter, "naming_rule_edit", {"base_revision": devcenter.revision, "object_type": "measure", "check": {"kind": "regex", "value": "^[A-Z].+"}})
                self.assertNotIn("error", r1)
                r2 = jsapi.call(devcenter, "naming_rule_edit", {"base_revision": devcenter.revision, "object_type": "measure", "check": {"kind": "regex", "value": "^.{1,40}$"}})
                self.assertNotIn("error", r2)
                c_unit = jsapi.call(devcenter, "naming_rule_edit", {"base_revision": devcenter.revision, "object_type": "data_column", "scope": {"format_kind": "percent"}, "check": {"kind": "unit_word", "value": "%"}})
                self.assertNotIn("error", c_unit)
                bad_scope = jsapi.call(devcenter, "naming_rule_edit", {"base_revision": devcenter.revision, "object_type": "table", "scope": {"table": "Sales"}, "check": {"kind": "prefix", "value": "dim"}})
                self.assertEqual("invalid_payload", bad_scope["error"]["code"])

                # Copy donor rules -> copied user rule arrives as proposed -> reject marks rejected instead of deleting
                copied = jsapi.call(devcenter, "naming_rules_copy", {"base_revision": devcenter.revision, "source_id": d_id})
                copied_user = next(r for r in copied["copied"] if r["check"]["kind"] == "prefix" and r["object_type"] == "data_column")
                self.assertEqual(("user", "proposed"), (copied_user["origin"], copied_user["status"]))
                rej = jsapi.call(devcenter, "naming_rule_reject", {"base_revision": devcenter.revision, "rule_id": copied_user["rule_id"]})
                self.assertEqual((False, "rejected"), (rej["removed"], rej["rule"]["status"]))
                # Re-copy skips rejected rule instead of duplicating it
                copied2 = jsapi.call(devcenter, "naming_rules_copy", {"base_revision": devcenter.revision, "source_id": d_id})
                self.assertIn("rejected_rule", {s["reason"] for s in copied2["skipped"]})
            finally:
                devcenter.close()
                app.close()

    @unittest.skipUnless(has_mock_data(), "Mock data PBIP folder not present")
    def test_real_mock_pbip_naming_detection_and_proposal(self) -> None:
        src_root = mock_data_root()
        before = dir_sha256_manifest(src_root / "1_finance_Aevum")
        with tempfile.TemporaryDirectory() as folder:
            proj_dir, pbip = copy_mock_project("finance", Path(folder))
            devcenter = DevCenterSessions(app_data_dir=None)
            devcenter.attach_project(proj_dir)
            app = create_app(use_native=False)
            app.devcenter = devcenter
            try:
                jsapi.call(devcenter, "session_create", {"display_name": "Finance Naming"})
                t_id = jsapi.call(devcenter, "source_add", {"base_revision": devcenter.revision, "path": str(pbip)})["source"]["source_id"]
                jsapi.call(devcenter, "target_set", {"base_revision": devcenter.revision, "model": {"mode": "existing", "source_id": t_id}})
                st, payload = app.handle("GET", "/api/devcenter/naming-rules")
                self.assertEqual(200, st)
                self.assertEqual([], contracts.errors("http/naming-rules.reply.json", payload))
                for rule in payload["rules"]:
                    self.assertEqual(rule["breaks"], len(rule["breaking_objects"]))
                st_p, prop = app.handle("POST", "/api/devcenter/name-propose", json.dumps({"name": "net_margin", "object_type": "measure"}).encode("utf-8"))
                self.assertEqual(200, st_p)
                self.assertEqual([], contracts.errors("http/name-propose.reply.json", prop))
            finally:
                devcenter.close()
                app.close()
        self.assertEqual(dir_sha256_manifest(src_root / "1_finance_Aevum"), before)


if __name__ == "__main__":
    unittest.main()
