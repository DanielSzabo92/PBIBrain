"""UI contract tests of the Development Center data layer (UI design step U2, section 10).

- frontend/src/devcenter/jsapi-methods.json equals the technical design section 14.2 list plus the
  change request calls of section 14.4, the fake server list, and (when it has them) the host list.
- The error shape fixture validates against the error shape. Until S2 (ticket 04) creates the schema in
  backend/devcenter/contracts/, the test uses a local copy of the shape of technical design section 12.
  When the S2 schema exists, the test also validates against it.
"""

from __future__ import annotations

import inspect
import json
import re
import unittest
from pathlib import Path

import jsonschema

from tests import devcenter_ui_server as fake

ROOT = Path(__file__).resolve().parents[1]
METHODS_FILE = ROOT / "frontend" / "src" / "devcenter" / "jsapi-methods.json"
ERRORS_JS = ROOT / "frontend" / "src" / "devcenter" / "errors.js"
ERROR_FIXTURE = ROOT / "tests" / "fixtures" / "devcenter_ui" / "errors.json"
CONTRACTS = ROOT / "backend" / "devcenter" / "contracts"

# Technical design section 14.2, in its order.
SECTION_14_2 = (
    "session_create", "session_open", "session_close", "source_add", "source_remove", "source_relink",
    "target_set", "compare_mode_set", "alignment_override", "merge_choice_set", "merge_choice_bulk_set",
    "removal_policy_set", "need_mapping_set", "impact_action_apply", "offer_select", "row_confirm",
    "sources_check", "naming_rule_confirm", "naming_rule_reject", "naming_rule_edit", "naming_rules_copy",
    "proposal_accept", "proposal_reject", "proposal_accept_all", "question_answer", "format_only_apply",
    "apply", "undo_apply", "change_report_write", "cloud_sign_in", "cloud_connect", "pull_to_local",
)
# Technical design section 14.4: the change requests that add a JS API call (UC13).
CHANGE_REQUEST_CALLS = ("cloud_items_list",)
# UI design section 10, "Busy".
LONG_METHODS = frozenset({
    "session_create", "session_open", "sources_check", "apply", "format_only_apply", "undo_apply",
    "pull_to_local", "cloud_connect", "cloud_sign_in", "merge_choice_bulk_set", "proposal_accept_all",
})
# Technical design section 12.
SECTION_12_CODES = (
    "not_found", "session_not_open", "stale_revision", "confidence_below_threshold", "reason_required",
    "user_choice_exists", "naming_rule_violation", "invalid_payload", "action_not_allowed", "source_changed",
)
CLIENT_CODES = ("network", "unknown")

# Local copy of the error shape of technical design section 12: {error: {code, message, details}}.
# Replace it with the S2 schema when backend/devcenter/contracts/ has it (ticket 04).
LOCAL_ERROR_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["error"],
    "additionalProperties": False,
    "properties": {
        "error": {
            "type": "object",
            "required": ["code", "message", "details"],
            "additionalProperties": False,
            "properties": {
                "code": {"type": "string", "enum": [*SECTION_12_CODES, *CLIENT_CODES]},
                "message": {"type": "string", "minLength": 1},
                "details": {"type": "object"},
            },
        }
    },
}
# The error shape schema of S2 (ticket 04). defs.json and the jsapi/ and http/ folders are next to it.
S2_ERROR_SCHEMA = CONTRACTS / "error.json"

# The public host methods that are not Development Center JS API methods (the desktop shell and its helpers).
HOST_OTHER_METHODS = frozenset({
    "attach_server", "get_session", "endpoint_session", "choose_folder", "choose_sources", "open_project",
    "add_sources", "close_project", "shutdown", "active_application",
})
# The methods of jsapi-methods.json that the host does not have yet, with the build step that adds each one
# (technical design section 16). Remove a method from this list when its step adds it to the host.
HOST_PENDING = {
    "format_only_apply": "S9", "apply": "S9", "undo_apply": "S9", "change_report_write": "S9",
    "proposal_accept": "S10", "proposal_reject": "S10", "proposal_accept_all": "S10", "question_answer": "S10",
}


def _load_methods() -> list[dict[str, str]]:
    return json.loads(METHODS_FILE.read_text(encoding="utf-8"))


def _contract_validator(name: str = "error.json", root: Path = CONTRACTS) -> jsonschema.protocols.Validator:
    """A validator for one contract file of the S2 folder (ticket 04).

    Use backend.devcenter.contracts.validator when the module exists. Else build the registry from the
    $id of each file in the folder: the S2 files have an absolute $id and refer to defs.json by that URL.
    """
    if root == CONTRACTS:
        try:
            from backend.devcenter import contracts
        except ImportError:
            contracts = None
        if contracts is not None and hasattr(contracts, "validator"):
            return contracts.validator(name)

    from referencing import Registry, Resource

    resources = []
    for file in sorted(root.rglob("*.json")):
        schema = json.loads(file.read_text(encoding="utf-8"))
        if "$id" not in schema:
            raise ValueError(f"The contract {file.relative_to(root).as_posix()} has no $id.")
        resources.append((schema["$id"], Resource.from_contents(schema)))
    registry = Registry().with_resources(resources)
    schema = json.loads((root / name).read_text(encoding="utf-8"))
    return jsonschema.Draft202012Validator(schema, registry=registry)


class JsApiMethodListTest(unittest.TestCase):
    def test_the_list_is_section_14_2_plus_the_change_request_calls(self) -> None:
        names = [entry["name"] for entry in _load_methods()]
        self.assertEqual(names, [*SECTION_14_2, *CHANGE_REQUEST_CALLS])

    def test_each_entry_has_a_name_and_the_kind_of_section_10(self) -> None:
        for entry in _load_methods():
            self.assertEqual(set(entry), {"name", "kind"}, entry)
            self.assertEqual(entry["kind"], "long" if entry["name"] in LONG_METHODS else "short", entry["name"])

    def test_the_list_equals_the_fake_server_list(self) -> None:
        self.assertEqual([entry["name"] for entry in _load_methods()], list(fake.JSAPI_METHODS))
        self.assertLessEqual(fake.JSAPI_READS | fake.NO_SESSION_METHODS | fake.LOCKED_METHODS, set(fake.JSAPI_METHODS))

    def test_each_host_method_is_in_the_list_and_each_missing_method_is_pending(self) -> None:
        from backend.desktop.host import DesktopController

        names = {entry["name"] for entry in _load_methods()}
        exposed = {name for name, _ in inspect.getmembers(DesktopController, callable) if not name.startswith("_")}
        devcenter = exposed - HOST_OTHER_METHODS
        self.assertEqual(devcenter - names, set(), "Add each new host JS API method to jsapi-methods.json, or to HOST_OTHER_METHODS.")
        self.assertLessEqual(set(HOST_PENDING), names, "HOST_PENDING names a method that is not in jsapi-methods.json.")
        self.assertEqual(
            names - devcenter, set(HOST_PENDING),
            "HOST_PENDING must list exactly the methods that the host does not have. Remove a method from it when its step adds it.",
        )
        self.assertLessEqual(set(HOST_PENDING.values()), {"S3", "S4", "S5", "S6", "S9", "S10", "S11"})


class ErrorShapeTest(unittest.TestCase):
    def fixture_replies(self) -> list[dict]:
        return json.loads(ERROR_FIXTURE.read_text(encoding="utf-8"))["replies"]

    def test_the_fixture_has_one_reply_for_each_code(self) -> None:
        codes = [reply["error"]["code"] for reply in self.fixture_replies()]
        self.assertEqual(sorted(codes), sorted([*SECTION_12_CODES, *CLIENT_CODES]))

    def test_the_fixture_validates_against_the_local_shape(self) -> None:
        validator = jsonschema.Draft202012Validator(LOCAL_ERROR_SCHEMA)
        for reply in self.fixture_replies():
            validator.validate(reply)

    def test_the_local_shape_refuses_a_bad_reply(self) -> None:
        validator = jsonschema.Draft202012Validator(LOCAL_ERROR_SCHEMA)
        for bad in (
            {"ok": False, "error": "text"},
            {"error": {"code": "not_found", "message": "No row."}},
            {"error": {"code": "disk_full", "message": "No space.", "details": {}}},
            {"error": {"code": "not_found", "message": "", "details": {}}},
        ):
            with self.subTest(bad=bad):
                self.assertFalse(validator.is_valid(bad))

    def server_replies(self) -> list[dict]:
        """The fixture replies with a section 12 code. network and unknown are client codes, not in the S2 schema."""
        return [reply for reply in self.fixture_replies() if reply["error"]["code"] in SECTION_12_CODES]

    def test_the_server_codes_of_the_fixture_validate_against_the_s2_schema(self) -> None:
        if not S2_ERROR_SCHEMA.is_file():
            self.skipTest("S2 (ticket 04) did not create backend/devcenter/contracts/error.json yet.")
        validator = _contract_validator("error.json")
        replies = self.server_replies()
        self.assertEqual(len(replies), len(SECTION_12_CODES))
        for reply in replies:
            validator.validate(reply)
        self.assertFalse(validator.is_valid({"error": {"code": "disk_full", "message": "No space.", "details": {}}}))

    def test_the_contract_validator_resolves_a_ref_to_defs_json_by_its_id(self) -> None:
        import tempfile

        base = "https://pbibrain.local/devcenter/contracts/"
        with tempfile.TemporaryDirectory(prefix="pbibrain-contracts-") as folder:
            root = Path(folder)
            (root / "jsapi").mkdir()
            (root / "defs.json").write_text(json.dumps({
                "$schema": "https://json-schema.org/draft/2020-12/schema", "$id": base + "defs.json",
                "$defs": {"code": {"enum": list(SECTION_12_CODES)}},
            }), encoding="utf-8")
            (root / "error.json").write_text(json.dumps({
                "$schema": "https://json-schema.org/draft/2020-12/schema", "$id": base + "error.json",
                "type": "object", "required": ["error"],
                "properties": {"error": {"type": "object", "required": ["code", "message", "details"],
                                         "properties": {"code": {"$ref": base + "defs.json#/$defs/code"}}}},
            }), encoding="utf-8")
            (root / "jsapi" / "x.reply.json").write_text(json.dumps({
                "$schema": "https://json-schema.org/draft/2020-12/schema", "$id": base + "jsapi/x.reply.json",
                "$ref": "../error.json",
            }), encoding="utf-8")
            for name in ("error.json", "jsapi/x.reply.json"):
                validator = _contract_validator(name, root)
                for reply in self.server_replies():
                    validator.validate(reply)
                self.assertFalse(validator.is_valid({"error": {"code": "network", "message": "x", "details": {}}}), name)

    def test_the_fake_server_error_replies_have_the_shape(self) -> None:
        validator = jsonschema.Draft202012Validator(LOCAL_ERROR_SCHEMA)
        state = fake.FakeDevCenter()
        state.load("default")
        failures = []
        for method, payload in (
            ("merge_choice_set", {"base_revision": -1}),
            ("no_such_method", {}),
        ):
            try:
                state.call(method, payload)
            except fake.FakeError as error:
                failures.append(error.body())
        state.load("no-sessions")
        try:
            state.call("merge_choice_set", {"base_revision": 0})
        except fake.FakeError as error:
            failures.append(error.body())
        self.assertEqual([body["error"]["code"] for body in failures], ["stale_revision", "not_found", "session_not_open"])
        for body in failures:
            validator.validate(body)

    def test_errors_js_has_the_section_12_codes_and_the_fake_server_status_map_agrees(self) -> None:
        source = ERRORS_JS.read_text(encoding="utf-8")
        block = re.search(r"SERVER_ERROR_CODES = Object\.freeze\(\[(.*?)\]\)", source, re.S)
        self.assertIsNotNone(block)
        self.assertEqual(re.findall(r'"([a-z_]+)"', block.group(1)), list(SECTION_12_CODES))
        self.assertEqual(set(fake.ERROR_STATUS), {*SECTION_12_CODES, *CLIENT_CODES})


class SessionFixtureContractTest(unittest.TestCase):
    """Step U3: the session fixtures and the fake session and source replies follow the S2 schemas."""

    FIXTURES = ROOT / "tests" / "fixtures" / "devcenter_ui"

    def validate(self, name: str, value: object) -> None:
        errors = sorted(_contract_validator(name).iter_errors(value), key=lambda error: list(error.path))
        self.assertEqual([f"{list(error.path)}: {error.message}"[:300] for error in errors], [], name)

    def test_each_session_fixture_validates_against_the_get_session_schema(self) -> None:
        checked = 0
        for path in sorted(self.FIXTURES.glob("*/session.json")):
            value = json.loads(path.read_text(encoding="utf-8"))
            if value is None:
                continue
            with self.subTest(fixture=path.parent.name):
                self.validate("http/session.reply.json", value)
                checked += 1
        self.assertGreaterEqual(checked, 6)

    def test_each_scenario_gives_get_session_and_get_sessions_replies_of_the_schema(self) -> None:
        state = fake.FakeDevCenter()
        for name in fake.SCENARIOS:
            with self.subTest(scenario=name):
                state.load(name)
                try:
                    self.validate("http/sessions.reply.json", state.read("GET", "/api/devcenter/sessions", {}, {}))
                except fake.FakeError as error:
                    self.assertEqual((name, error.body()["error"]["details"]), ("no-project", {"reason": "no_project"}))
                    self.validate("error.json", error.body())
                if state.session is not None:
                    self.validate("http/session.reply.json", state.read("GET", "/api/devcenter/session", {}, {}))

    def call(self, state: fake.FakeDevCenter, method: str, payload: dict) -> dict:
        request = {"base_revision": state.revision if state.session is not None else None, **payload}
        self.validate(f"jsapi/{method}.request.json", request)
        reply = state.call(method, request)
        self.validate(f"jsapi/{method}.reply.json", reply)
        return reply

    def test_the_create_flow_replies_follow_the_jsapi_schemas(self) -> None:
        state = fake.FakeDevCenter()
        state.load("no-sessions")
        created = self.call(state, "session_create", {"display_name": "Sales model merge"})
        self.assertNotIn("session", created)
        first = self.call(state, "source_add", {"path": "sources/Sales.SemanticModel"})
        self.call(state, "source_add", {"path": "sources/Finance.SemanticModel"})
        target = self.call(state, "target_set", {"model": {"mode": "copy_of", "source_id": first["source"]["source_id"], "path": "target/Sales copy"},
                                                 "report": {"mode": "new_empty"}})
        self.assertEqual(len(target["sources_added"]), 1)
        self.validate("http/session.reply.json", state.read("GET", "/api/devcenter/session", {}, {}))
        rows = state.read("GET", "/api/devcenter/sessions", {}, {})
        self.validate("http/sessions.reply.json", rows)
        self.assertEqual((rows["sessions"][0]["display_name"], rows["sessions"][0]["is_open"], rows["sessions"][0]["source_count"]),
                         ("Sales model merge", True, 3))
        self.call(state, "sources_check", {})
        self.call(state, "session_close", {})
        self.assertIsNone(state.read("GET", "/api/devcenter/sessions", {}, {})["revision"])

    def test_the_open_and_source_replies_follow_the_jsapi_schemas(self) -> None:
        state = fake.FakeDevCenter()
        state.load("no-sessions")
        state.load("default")
        session_id = state.session["session_id"]
        self.call(state, "session_close", {})
        opened = self.call(state, "session_open", {"session_id": session_id})
        self.assertEqual((opened["session_id"], opened["read_only"]), (session_id, False))
        removed = self.call(state, "source_remove", {"source_id": "src-2"})
        self.assertEqual(removed["source_id"], "src-2")
        self.assertIsInstance(removed["choice_count"], int)
        self.call(state, "target_set", {"model": {"mode": "existing", "source_id": "src-1"}, "report": None})
        state.load("source-missing")
        relinked = self.call(state, "source_relink", {"source_id": "src-1", "path": "sources/Sales again"})
        self.assertEqual(relinked["source"]["status"], "ok")
        state.load("locked")
        self.call(state, "session_close", {})
        opened = self.call(state, "session_open", {"session_id": session_id})
        self.assertEqual(opened["read_only"], True)

    def test_naming_rules_fixture_validates_against_the_s4_schema(self) -> None:
        """Step U5: the default naming rules fixture validates against the S4 schema."""
        path = self.FIXTURES / "default" / "naming-rules.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        self.validate("http/naming-rules.reply.json", value)

    def test_the_naming_rules_replies_follow_the_s4_schemas(self) -> None:
        """Step U5: GET naming-rules and the naming rule JS API calls follow S4 schemas."""
        state = fake.FakeDevCenter()
        state.load("default")
        read_reply = state.read("GET", "/api/devcenter/naming-rules", {}, {})
        self.validate("http/naming-rules.reply.json", read_reply)
        rule_id = read_reply["rules"][0]["rule_id"]

        confirmed = self.call(state, "naming_rule_confirm", {"rule_id": rule_id})
        self.assertEqual(confirmed["rule"]["status"], "confirmed")

        edited = self.call(state, "naming_rule_edit", {
            "rule_id": rule_id,
            "object_type": "measure",
            "scope": {"table": None, "display_folder": None, "format_kind": "currency", "name_prefix": None},
            "check": {"kind": "suffix", "value": "Amount"},
        })
        self.assertEqual(edited["rule"]["status"], "confirmed")

        created = self.call(state, "naming_rule_edit", {
            "object_type": "table",
            "scope": {"table": None, "display_folder": None, "format_kind": None, "name_prefix": None},
            "check": {"kind": "suffix", "value": "Table"},
        })
        self.assertEqual(created["rule"]["origin"], "user")

        rejected_user = self.call(state, "naming_rule_reject", {"rule_id": created["rule"]["rule_id"]})
        self.assertEqual(rejected_user["removed"], True)

        rejected_detected = self.call(state, "naming_rule_reject", {"rule_id": rule_id})
        self.assertEqual((rejected_detected["removed"], rejected_detected["rule"]["status"]), (False, "rejected"))

        copied = self.call(state, "naming_rules_copy", {"source_id": "src-1"})
        self.assertEqual(len(copied["copied"]), 2)

        with self.assertRaises(fake.FakeError) as duplicate_ctx:
            state.call("naming_rule_edit", {
                "base_revision": state.revision,
                "object_type": "table",
                "scope": {"table": None, "display_folder": None, "format_kind": None, "name_prefix": None},
                "check": {"kind": "prefix", "value": "DimDuplicate"},
            })
        self.assertEqual(duplicate_ctx.exception.code, "action_not_allowed")
        self.assertEqual(duplicate_ctx.exception.details["reason"], "duplicate_rule")

    def test_plan_fixtures_and_replies_follow_the_s5_schemas(self) -> None:
        """Step U7: GET plan and POST plan-validate across scenarios follow the S5 schemas."""
        state = fake.FakeDevCenter()
        for scenario_name in ("default", "plan-invalid", "apply-ready"):
            with self.subTest(scenario=scenario_name):
                state.load(scenario_name)
                plan_reply = state.read("GET", "/api/devcenter/plan", {}, {})
                self.validate("http/plan.reply.json", plan_reply)
                for mode in ("quick", "full"):
                    validate_reply = state.read("POST", "/api/devcenter/plan-validate", {}, {"mode": mode})
                    self.validate("http/plan-validate.reply.json", validate_reply)
                    self.assertEqual(validate_reply["plan_hash"], plan_reply["plan_hash"])
                    self.assertEqual(validate_reply["status"], plan_reply["status"])
        state.load("default")
        removed = self.call(state, "source_remove", {"source_id": "src-2"})
        self.assertEqual(removed["choice_count"], 1)
        after_remove = state.read("GET", "/api/devcenter/plan", {}, {})
        self.validate("http/plan.reply.json", after_remove)
        self.assertEqual(after_remove["status"], "invalid")
        self.assertTrue(any(item["kind"] == "choice_source_removed" for item in after_remove["blocking"]))


if __name__ == "__main__":
    unittest.main()

