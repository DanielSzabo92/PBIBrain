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
# The file names that S2 can use for the error shape schema.
S2_ERROR_SCHEMA_NAMES = ("error.schema.json", "error-shape.schema.json", "error_shape.schema.json", "errors.schema.json")


def _load_methods() -> list[dict[str, str]]:
    return json.loads(METHODS_FILE.read_text(encoding="utf-8"))


def _s2_error_schema() -> Path | None:
    for name in S2_ERROR_SCHEMA_NAMES:
        for path in (CONTRACTS / name, CONTRACTS / "jsapi" / name):
            if path.is_file():
                return path
    return None


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

    def test_the_list_equals_the_host_list_when_the_host_has_the_methods(self) -> None:
        from backend.desktop.host import DesktopController

        names = {entry["name"] for entry in _load_methods()}
        exposed = {name for name, _ in inspect.getmembers(DesktopController, callable) if not name.startswith("_")}
        present = names & exposed
        if present != names:
            self.skipTest(f"The host has {len(present)} of {len(names)} Development Center methods. S2 and later steps add the rest.")
        self.assertEqual(present, names)


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

    def test_the_fixture_validates_against_the_s2_schema(self) -> None:
        path = _s2_error_schema()
        if path is None:
            self.skipTest("S2 (ticket 04) did not create the error shape schema in backend/devcenter/contracts/ yet.")
        schema = json.loads(path.read_text(encoding="utf-8"))
        validator = jsonschema.validators.validator_for(schema)(schema)
        for reply in self.fixture_replies():
            validator.validate(reply)

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


if __name__ == "__main__":
    unittest.main()
