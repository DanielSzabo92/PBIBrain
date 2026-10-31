"""Build step S2: session store and local sources (technical design section 16, S2)."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from backend.adapters.pbir.validation import validate_report_documents
from backend.adapters.tabular_metadata import TabularMetadataAdapter
from backend.api.app import create_app
from backend.desktop import DesktopController
from backend.devcenter import contracts, jsapi
from backend.devcenter.errors import DevCenterError
from backend.devcenter.session import store
from backend.devcenter.session.manager import DevCenterSessions
from backend.devcenter.session.secrets import check_secrets, find_secrets
from backend.devcenter.session.jsapi_methods import S2_METHODS
from backend.devcenter.sources.fingerprint import source_files
from backend.devcenter.sources.kinds import (
    MESSAGE_PBIR_LEGACY_TARGET,
    MESSAGE_PBIX,
    MESSAGE_TMSL_TARGET,
    detect_local_source,
)
from backend.graph.repository import GraphRepository

REPOSITORY = Path(__file__).resolve().parents[1]
LAB = REPOSITORY / "tests" / "fixtures" / "merge_lab"
BRIDGE = REPOSITORY / "backend/adapters/tabular_metadata/dotnet/bin/Release/net8.0/TabularMetadata.dll"


class SessionTestCase(unittest.TestCase):
    """A temp project with the merge lab projects and one session manager."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.root = base / "project"
        self.app_data = base / "appdata"
        for name in ("SalesA", "SalesB", "Finance", "Legacy"):
            shutil.copytree(LAB / name, self.root / name)
        self.devcenter = self.manager()

    def tearDown(self) -> None:
        self.devcenter.close()
        self.temporary.cleanup()

    def manager(self) -> DevCenterSessions:
        manager = DevCenterSessions(app_data_dir=self.app_data)
        manager.attach_project(self.root)
        return manager

    def call(self, method: str, request: dict | None = None, *, manager: DevCenterSessions | None = None) -> dict:
        reply = jsapi.call(manager or self.devcenter, method, request)
        if "error" in reply:
            self.assertEqual([], contracts.errors(contracts.ERROR, reply), reply)
        else:
            self.assertEqual([], contracts.errors(contracts.jsapi_reply(method), reply), reply)
        return reply

    def ok(self, method: str, request: dict | None = None, *, manager: DevCenterSessions | None = None) -> dict:
        reply = self.call(method, request, manager=manager)
        self.assertNotIn("error", reply, reply)
        return reply

    def failed(self, method: str, request: dict | None = None, *, code: str, manager: DevCenterSessions | None = None) -> dict:
        reply = self.call(method, request, manager=manager)
        self.assertIn("error", reply, reply)
        self.assertEqual(code, reply["error"]["code"], reply)
        return reply["error"]

    def create(self, name: str = "Sales merge") -> dict:
        return self.ok("session_create", {"display_name": name})

    def add(self, relative: str) -> dict:
        reply = self.ok("source_add", {"base_revision": self.devcenter.revision, "path": str(self.root / relative)})
        return reply["source"]

    def session_folder(self, session_id: str) -> Path:
        return self.root / ".pbibrain" / "sessions" / session_id


class RoundTripTests(SessionTestCase):
    def test_create_change_save_open_gives_an_equal_canonical_file(self):
        created = self.create()
        target = self.add("SalesA/SalesA.pbip")
        self.add("SalesB/SalesB.pbip")
        self.ok("target_set", {"base_revision": self.devcenter.revision,
                               "model": {"mode": "existing", "source_id": target["source_id"]},
                               "report": {"mode": "existing", "source_id": target["source_id"]}})
        path = self.session_folder(created["session_id"]) / "session.json"
        saved = path.read_bytes()
        self.ok("session_close")

        other = self.manager()
        opened = self.ok("session_open", {"session_id": created["session_id"]}, manager=other)
        self.assertFalse(opened["read_only"])
        self.assertEqual(saved, path.read_bytes())
        document = json.loads(saved)
        self.assertEqual(document, other._open.document)
        self.assertEqual(store.canonical_bytes(document), saved)
        self.assertNotIn(b"\r", saved)
        self.assertTrue(saved.endswith(b"}\n"))
        self.assertEqual(4, document["revision"])
        self.assertEqual(["SalesA/SalesA.pbip", "SalesB/SalesB.pbip"], [item["path"] for item in document["sources"]])
        other.close()

    def test_each_change_appends_one_log_entry(self):
        created = self.create()
        self.add("SalesA/SalesA.pbip")
        lines = (self.session_folder(created["session_id"]) / "log.jsonl").read_text(encoding="utf-8").splitlines()
        entries = [json.loads(line) for line in lines]
        self.assertEqual(["session_create", "source_add"], [entry["action"] for entry in entries])
        self.assertEqual([1, 2], [entry["revision"] for entry in entries])
        self.assertEqual("user", entries[1]["author"])
        self.assertEqual({"time", "author", "mcp_client", "action", "target", "before", "after", "reason", "proposal_id", "revision"},
                         set(entries[1]))

    def test_session_has_no_absolute_path(self):
        created = self.create()
        self.add("SalesA/SalesA.pbip")
        text = (self.session_folder(created["session_id"]) / "session.json").read_text(encoding="utf-8")
        self.assertNotIn(str(self.root), text)
        self.assertNotIn(str(self.root).replace("\\", "/"), text)
        self.assertEqual([], find_secrets(json.loads(text)))

    def test_stale_base_revision_is_refused(self):
        self.create()
        error = self.failed("source_add", {"base_revision": 99, "path": str(self.root / "SalesA/SalesA.pbip")}, code="stale_revision")
        self.assertEqual(1, error["details"]["revision"])
        self.assertEqual(1, self.devcenter.revision)


class AtomicSaveTests(SessionTestCase):
    def test_save_interrupted_after_the_temp_write_leaves_the_old_file_valid(self):
        created = self.create()
        path = self.session_folder(created["session_id"]) / "session.json"
        before = path.read_bytes()
        written: list[Path] = []
        real_replace = os.replace

        def interrupted(source, destination):
            written.append(Path(source))
            self.assertTrue(Path(source).is_file())
            self.assertIn(b'"source_id": "src-1"', Path(source).read_bytes())
            raise OSError("power loss")

        with patch.object(store.os, "replace", interrupted):
            with self.assertRaises(OSError):
                self.devcenter.source_add({"base_revision": 1, "path": str(self.root / "SalesA/SalesA.pbip")})
        self.assertEqual(1, len(written))
        self.assertEqual(before, path.read_bytes())
        self.assertEqual(1, store.parse_session(path.read_bytes())["revision"])
        self.assertEqual(1, self.devcenter.revision)
        self.assertEqual([], self.devcenter._open.document["sources"])
        self.assertIs(os.replace, real_replace)

    def test_a_left_temp_file_does_not_block_open_or_list(self):
        created = self.create()
        folder = self.session_folder(created["session_id"])
        (folder / ".session.json.abc.tmp").write_bytes(b'{"half": ')
        self.ok("session_close")
        self.ok("session_open", {"session_id": created["session_id"]})
        rows = self.devcenter.sessions_list()["sessions"]
        self.assertEqual(["ok"], [row["schema_state"] for row in rows])


class SecretCheckTests(SessionTestCase):
    def test_token_like_strings_are_refused(self):
        for value in (
            "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.c2lnbmF0dXJlLXZhbHVlLXRleHQ",
            "Bearer abcdef1234567890",
            "ghp_0123456789abcdefABCDEF0123456789abcd",
            "password=hunter22",
            "QmFzZTY0VG9rZW5WYWx1ZTEyMzQ1Njc4OTBBQkNERUZHSElKSw",
        ):
            with self.subTest(value=value[:12]):
                with self.assertRaises(DevCenterError) as raised:
                    check_secrets({"display_name": value})
                self.assertEqual("invalid_payload", raised.exception.code)
                self.assertEqual("token", raised.exception.details["findings"][0]["kind"])
                self.assertNotIn(value, json.dumps(raised.exception.details))

    def test_absolute_user_paths_and_email_are_refused(self):
        cases = {
            "C:\\Users\\someone\\Documents\\Sales.pbip": "absolute_path",
            "D:/Work/Sales.pbip": "absolute_path",
            "/home/someone/sales": "absolute_path",
            "\\\\server\\share\\Sales.pbip": "absolute_path",
            "%USERPROFILE%\\Sales": "absolute_path",
            "owner@example.com": "email",
        }
        for value, kind in cases.items():
            with self.subTest(value=value):
                self.assertEqual([{"pointer": "/sources/0/path", "kind": kind}], find_secrets({"sources": [{"path": value}]}))

    def test_normal_session_values_pass(self):
        check_secrets({"session_id": "0" * 32, "hash": "sha256:" + "a" * 64, "path": "../Sales/Sales.pbip",
                       "row": "measure:Sales/Total Sales", "name": "Sales merge 2026"})

    def test_create_with_a_secret_name_writes_nothing(self):
        error = self.failed("session_create", {"display_name": "merge for owner@example.com"}, code="invalid_payload")
        self.assertEqual("secret_found", error["details"]["reason"])
        self.assertFalse((self.root / ".pbibrain" / "sessions").exists())


class LockTests(SessionTestCase):
    def test_second_open_of_a_locked_session_is_read_only(self):
        created = self.create()
        second = self.manager()
        try:
            listed = second.sessions_list()["sessions"]
            self.assertEqual(["locked"], [row["lock_state"] for row in listed])
            opened = self.ok("session_open", {"session_id": created["session_id"]}, manager=second)
            self.assertTrue(opened["read_only"])
            self.assertTrue(second.session_summary()["read_only"])
            error = self.failed("source_add", {"base_revision": 1, "path": str(self.root / "SalesA/SalesA.pbip")},
                                code="action_not_allowed", manager=second)
            self.assertEqual("read_only", error["details"]["reason"])
            self.ok("session_close", manager=second)
            self.assertTrue((self.session_folder(created["session_id"]) / "session.lock").is_file())

            self.ok("session_close")
            self.assertEqual(["free"], [row["lock_state"] for row in second.sessions_list()["sessions"]])
            again = self.ok("session_open", {"session_id": created["session_id"]}, manager=second)
            self.assertFalse(again["read_only"])
        finally:
            second.close()

    def test_lock_of_a_dead_process_is_free(self):
        created = self.create()
        lock = self.session_folder(created["session_id"]) / "session.lock"
        self.ok("session_close")
        lock.write_bytes(store.canonical_bytes({"pid": 2 ** 31 - 2, "owner": "other"}))
        self.assertEqual("free", self.devcenter.sessions_list()["sessions"][0]["lock_state"])
        self.assertFalse(self.ok("session_open", {"session_id": created["session_id"]})["read_only"])


class SchemaVersionTests(SessionTestCase):
    def write_session(self, raw: bytes) -> str:
        created = self.create()
        self.ok("session_close")
        (self.session_folder(created["session_id"]) / "session.json").write_bytes(raw)
        return created["session_id"]

    def test_older_schema_version_migrates_with_a_backup(self):
        created = self.create()
        self.ok("session_close")
        path = self.session_folder(created["session_id"]) / "session.json"
        old = path.read_bytes()

        def to_two(document: dict) -> dict:
            document["migrated_field"] = True
            return document

        with patch.object(store, "SCHEMA_VERSION", 2), patch.dict(store.MIGRATIONS, {1: to_two}):
            opened = self.ok("session_open", {"session_id": created["session_id"]})
            self.assertTrue(opened["migrated"])
            backup = self.session_folder(created["session_id"]) / "session.json.v1.bak"
            self.assertEqual(old, backup.read_bytes())
            migrated = json.loads(path.read_bytes())
            self.assertEqual(2, migrated["schema_version"])
            self.assertTrue(migrated["migrated_field"])

    def test_newer_schema_version_is_refused(self):
        document = {"schema_version": store.SCHEMA_VERSION + 1, "display_name": "From a newer app"}
        session_id = self.write_session(store.canonical_bytes(document))
        error = self.failed("session_open", {"session_id": session_id}, code="action_not_allowed")
        self.assertEqual("newer", error["details"]["schema_state"])
        self.assertIsNone(self.devcenter.revision)

    def test_conflict_markers_and_invalid_json_are_refused(self):
        created = self.create()
        path = self.session_folder(created["session_id"]) / "session.json"
        good = path.read_text(encoding="utf-8")
        self.ok("session_close")
        conflict = good.replace('  "revision": 1,\n', '<<<<<<< HEAD\n  "revision": 1,\n=======\n  "revision": 2,\n>>>>>>> other\n')
        for raw, cause in ((conflict, "conflict_markers"), ("{not json", "invalid_json")):
            with self.subTest(cause=cause):
                path.write_text(raw, encoding="utf-8", newline="\n")
                error = self.failed("session_open", {"session_id": created["session_id"]}, code="action_not_allowed")
                self.assertEqual("damaged", error["details"]["schema_state"])
                self.assertEqual(cause, error["details"]["cause"])


class SourceMarkTests(SessionTestCase):
    def edit(self, relative: str, old: str, new: str) -> None:
        path = self.root / relative
        data = path.read_bytes()
        self.assertIn(old.encode("utf-8"), data)
        path.write_bytes(data.replace(old.encode("utf-8"), new.encode("utf-8"), 1))

    def change_sales_a(self) -> None:
        table = "SalesA/SalesA.SemanticModel/definition/tables/Sales.tmdl"
        self.edit(table, "measure 'Total Cost' = SUM(Sales[Cost])", "measure 'Total Cost' = SUM(Sales[Cost]) * 2")
        self.edit(table, "\tmeasure Margin = [Total Sales] - [Total Cost]\r\n\t\tlineageTag: m-margin-a\r\n\r\n", "")
        self.edit(table, "\tcolumn 'Order Date'", "\tmeasure Fresh = 1\r\n\t\tlineageTag: m-fresh\r\n\r\n\tcolumn 'Order Date'")

    def test_changed_source_marks_rows_and_blocks_apply_until_each_row_is_confirmed(self):
        self.create()
        source = self.add("SalesA/SalesA.pbip")
        self.assertFalse(self.devcenter.apply_source_check()["blocking"])
        self.change_sales_a()

        checked = self.ok("sources_check", {"base_revision": self.devcenter.revision})
        self.assertEqual(3, checked["mark_count"])
        expected = [
            {"source_id": source["source_id"], "row_key": "measure:Sales/Fresh", "mark": "new_since_start"},
            {"source_id": source["source_id"], "row_key": "measure:Sales/Margin", "mark": "source_object_missing"},
            {"source_id": source["source_id"], "row_key": "measure:Sales/Total Cost", "mark": "source_changed"},
        ]
        self.assertEqual(expected, self.devcenter.marks())
        summary = self.devcenter.session_summary()
        self.assertEqual({"source_changed": 1, "source_object_missing": 1, "new_since_start": 1}, summary["counts"]["marks_by_kind"])
        self.assertEqual("changed", summary["sources"][0]["fingerprint_state"])

        blocked = self.devcenter.apply_source_check()
        self.assertTrue(blocked["blocking"])
        self.assertEqual([{"kind": "unconfirmed_marks", "row_keys": ["measure:Sales/Fresh", "measure:Sales/Margin", "measure:Sales/Total Cost"]}],
                         blocked["items"])

        revision = self.devcenter.revision
        self.failed("row_confirm", {"base_revision": revision, "row_keys": ["measure:Sales/Fresh", "measure:Sales/None"]}, code="not_found")
        self.assertEqual(3, len(self.devcenter.marks()))
        self.ok("row_confirm", {"base_revision": revision, "row_keys": ["measure:Sales/Fresh"]})
        self.assertTrue(self.devcenter.apply_source_check()["blocking"])
        self.assertEqual(2, len(self.devcenter.marks()))

    def test_row_confirm_with_a_key_list_confirms_each_row_in_one_revision_step(self):
        self.create()
        self.add("SalesA/SalesA.pbip")
        self.change_sales_a()
        self.ok("sources_check", {"base_revision": self.devcenter.revision})
        revision = self.devcenter.revision
        keys = [mark["row_key"] for mark in self.devcenter.marks()]
        reply = self.ok("row_confirm", {"base_revision": revision, "row_keys": keys})
        self.assertEqual(revision + 1, reply["revision"])
        self.assertEqual(keys, reply["confirmed"])
        self.assertEqual(0, reply["mark_count"])
        result = self.devcenter.apply_source_check()
        self.assertFalse(result["blocking"])
        self.assertEqual(revision + 1, result["revision"])
        self.assertEqual("same", self.devcenter.session_summary()["sources"][0]["fingerprint_state"])

    def test_open_checks_the_sources_and_keeps_the_marks(self):
        created = self.create()
        self.add("SalesA/SalesA.pbip")
        self.ok("session_close")
        self.change_sales_a()
        opened = self.ok("session_open", {"session_id": created["session_id"]})
        self.assertEqual(3, opened["mark_count"])
        self.ok("session_close")
        self.assertEqual(3, self.ok("session_open", {"session_id": created["session_id"]})["mark_count"])

    def test_a_missing_source_blocks_apply(self):
        self.create()
        source = self.add("Finance/Finance.pbip")
        shutil.rmtree(self.root / "Finance")
        self.ok("sources_check", {"base_revision": self.devcenter.revision})
        self.assertEqual("missing", self.devcenter.session_summary()["sources"][0]["status"])
        result = self.devcenter.apply_source_check()
        self.assertEqual([{"kind": "source_not_available", "source_ids": [source["source_id"]]}], result["items"])

    def test_relink_to_the_moved_folder_clears_the_missing_state(self):
        self.create()
        source = self.add("Finance/Finance.pbip")
        shutil.move(str(self.root / "Finance"), str(self.root / "Moved"))
        self.ok("sources_check", {"base_revision": self.devcenter.revision})
        relinked = self.ok("source_relink", {"base_revision": self.devcenter.revision, "source_id": source["source_id"],
                                             "path": str(self.root / "Moved/Finance.pbip")})
        self.assertEqual("Moved/Finance.pbip", relinked["source"]["path"])
        self.assertEqual("ok", relinked["source"]["status"])
        self.assertEqual(0, relinked["source"]["mark_count"])

    def test_an_unchanged_check_does_not_change_the_revision(self):
        self.create()
        self.add("SalesA/SalesA.pbip")
        first = self.ok("sources_check", {"base_revision": self.devcenter.revision})
        second = self.ok("sources_check", {"base_revision": first["revision"]})
        self.assertEqual(first["revision"], second["revision"])


class TargetTests(SessionTestCase):
    def test_empty_target_writes_a_skeleton_that_the_bridge_loads(self):
        self.create()
        self.add("SalesA/SalesA.pbip")
        folder = self.root / "Merged"
        reply = self.ok("target_set", {"base_revision": self.devcenter.revision,
                                       "model": {"mode": "empty", "path": str(folder), "name": "Merged"}})
        added = reply["sources_added"]
        self.assertEqual(1, len(added))
        self.assertEqual({"path": "Merged/Merged.pbip", "role": "target", "model_format": "tmdl", "report_format": "pbir"},
                         {key: added[0][key] for key in ("path", "role", "model_format", "report_format")})
        self.assertEqual({"mode": "existing", "source_id": added[0]["source_id"]}, reply["target"]["report"])
        for relative in ("Merged.pbip", "Merged.SemanticModel/definition.pbism", "Merged.SemanticModel/definition/database.tmdl",
                         "Merged.SemanticModel/definition/model.tmdl", "Merged.Report/definition.pbir"):
            self.assertTrue((folder / relative).is_file(), relative)
        pbir = json.loads((folder / "Merged.Report/definition.pbir").read_text(encoding="utf-8"))
        self.assertEqual({"byPath": {"path": "../Merged.SemanticModel"}}, pbir["datasetReference"])
        documents = {path.relative_to(folder).as_posix(): json.loads(path.read_text(encoding="utf-8"))
                     for path in folder.rglob("*") if path.is_file() and path.suffix in {".json", ".pbir"} and path.relative_to(folder).parts[0] == "Merged.Report"}
        self.assertEqual([], validate_report_documents(documents)["issues"])
        if BRIDGE.is_file():
            database = TabularMetadataAdapter().read(folder / "Merged.SemanticModel/definition")["database"]
            self.assertEqual(1702, database["compatibilityLevel"])
            self.assertEqual([], database["model"].get("tables", []))
        else:
            self.skipTest("Build the TOM bridge first")

    def test_copy_of_leaves_the_original_unchanged(self):
        self.create()
        original = self.add("SalesB/SalesB.pbip")
        before = source_files(detect_local_source(self.root / "SalesB/SalesB.pbip"))
        reply = self.ok("target_set", {"base_revision": self.devcenter.revision,
                                       "model": {"mode": "copy_of", "source_id": original["source_id"], "path": str(self.root / "Target")}})
        after = source_files(detect_local_source(self.root / "SalesB/SalesB.pbip"))
        self.assertEqual(before, after)
        copied = reply["sources_added"][0]
        self.assertEqual("Target/SalesB.pbip", copied["path"])
        self.assertEqual(before, source_files(detect_local_source(self.root / "Target/SalesB.pbip")))
        self.assertEqual({"mode": "copy_of", "source_id": copied["source_id"], "copy_of": original["source_id"]}, reply["target"]["model"])
        roles = {item["source_id"]: item["role"] for item in self.devcenter.session_summary()["sources"]}
        self.assertEqual({original["source_id"]: "donor", copied["source_id"]: "target"}, roles)

    def test_copy_into_a_folder_that_is_not_empty_is_refused(self):
        self.create()
        original = self.add("SalesB/SalesB.pbip")
        error = self.failed("target_set", {"base_revision": self.devcenter.revision,
                                           "model": {"mode": "copy_of", "source_id": original["source_id"], "path": str(self.root / "SalesA")}},
                            code="action_not_allowed")
        self.assertEqual("folder_not_empty", error["details"]["reason"])

    def test_tmsl_and_pbir_legacy_targets_are_refused_with_the_fixed_message(self):
        self.create()
        legacy = self.add("Legacy/Legacy.pbip")
        sales = self.add("SalesA/SalesA.pbip")
        revision = self.devcenter.revision
        error = self.failed("target_set", {"base_revision": revision, "model": {"mode": "existing", "source_id": legacy["source_id"]}},
                            code="action_not_allowed")
        self.assertEqual(MESSAGE_TMSL_TARGET, error["message"])
        copy_folder = self.root / "LegacyCopy"
        error = self.failed("target_set", {"base_revision": revision,
                                           "model": {"mode": "copy_of", "source_id": legacy["source_id"], "path": str(copy_folder)}},
                            code="action_not_allowed")
        self.assertEqual(MESSAGE_TMSL_TARGET, error["message"])
        self.assertFalse(copy_folder.exists())
        error = self.failed("target_set", {"base_revision": revision,
                                           "model": {"mode": "existing", "source_id": sales["source_id"]},
                                           "report": {"mode": "existing", "source_id": legacy["source_id"]}},
                            code="action_not_allowed")
        self.assertEqual(MESSAGE_PBIR_LEGACY_TARGET, error["message"])
        bim = self.add("Legacy/Legacy.SemanticModel/model.bim")
        error = self.failed("target_set", {"base_revision": self.devcenter.revision, "model": {"mode": "existing", "source_id": bim["source_id"]}},
                            code="action_not_allowed")
        self.assertEqual(MESSAGE_TMSL_TARGET, error["message"])
        self.assertIsNone(self.devcenter.session_summary()["target"]["model"])

    def test_pbix_source_is_refused_with_the_fixed_message(self):
        self.create()
        pbix = self.root / "Old.pbix"
        pbix.write_bytes(b"PK")
        error = self.failed("source_add", {"base_revision": 1, "path": str(pbix)}, code="action_not_allowed")
        self.assertEqual(MESSAGE_PBIX, error["message"])

    def test_source_kinds_of_the_merge_lab(self):
        cases = {
            "SalesA/SalesA.pbip": ("pbip", "tmdl", "pbir"),
            "Legacy/Legacy.pbip": ("pbip", "tmsl", "pbir_legacy"),
            "Finance/Finance.SemanticModel": ("tmdl_folder", "tmdl", None),
            "Finance/Finance.SemanticModel/definition": ("tmdl_folder", "tmdl", None),
            "Legacy/Legacy.SemanticModel/model.bim": ("model_bim", "tmsl", None),
            "SalesB/SalesB.Report": ("pbir_report", None, "pbir"),
            "Legacy/Legacy.Report": ("pbir_legacy_report", None, "pbir_legacy"),
        }
        for relative, expected in cases.items():
            with self.subTest(path=relative):
                source = detect_local_source(self.root / relative)
                self.assertEqual(expected, (source.kind, source.model_format, source.report_format))

    def test_source_remove_keeps_the_merge_choices_and_gives_the_count(self):
        self.create()
        donor = self.add("SalesB/SalesB.pbip")
        current = self.devcenter._open
        current.document["merge_choices"] = {"measure:Sales/Margin": {"choice": "take", "source_id": donor["source_id"]}}
        reply = self.ok("source_remove", {"base_revision": self.devcenter.revision, "source_id": donor["source_id"]})
        self.assertEqual(1, reply["choice_count"])
        self.assertIn("measure:Sales/Margin", current.document["merge_choices"])
        self.assertEqual([], current.document["sources"])


class GitignoreTests(SessionTestCase):
    def test_pbibrain_gitignore_has_the_runtime_entries(self):
        user_file = self.root / ".pbibrain" / ".gitignore"
        user_file.parent.mkdir(parents=True)
        user_file.write_text("my-notes.txt\n", encoding="utf-8")
        self.create()
        lines = user_file.read_text(encoding="utf-8").splitlines()
        self.assertEqual("my-notes.txt", lines[0])
        for entry in ("connection.json", "*.lbug", "*.lock", "*.bak", "*.tmp", "backups/"):
            self.assertIn(entry, lines)
        self.create("Second")
        self.assertEqual(lines, user_file.read_text(encoding="utf-8").splitlines())


class SessionListTests(SessionTestCase):
    """UC1 and UC2: ``GET sessions`` and ``GET session`` through the real HTTP app."""

    def setUp(self) -> None:
        super().setUp()
        self.app = create_app(use_native=False)
        self.app.devcenter = self.devcenter

    def tearDown(self) -> None:
        self.app.close()
        super().tearDown()

    def get(self, path: str, contract: str) -> dict:
        status, payload = self.app.handle("GET", "/api/devcenter/" + path)
        self.assertEqual(200, status, payload)
        self.assertEqual([], contracts.errors(contract, payload), payload)
        return payload

    def test_get_sessions_lists_each_session_with_its_state(self):
        first = self.create("Open one")
        target = self.add("SalesA/SalesA.pbip")
        self.ok("target_set", {"base_revision": self.devcenter.revision, "model": {"mode": "existing", "source_id": target["source_id"]}})
        self.ok("session_close")
        locked = self.create("Locked one")
        self.ok("session_close")
        lock = self.session_folder(locked["session_id"]) / "session.lock"
        lock.write_bytes(store.canonical_bytes({"pid": os.getpid(), "owner": "other window"}))
        newer = self.create("Newer one")
        self.ok("session_close")
        path = self.session_folder(newer["session_id"]) / "session.json"
        document = json.loads(path.read_bytes())
        document["schema_version"] = store.SCHEMA_VERSION + 1
        path.write_bytes(store.canonical_bytes(document))
        damaged = self.create("Damaged one")
        self.ok("session_close")
        (self.session_folder(damaged["session_id"]) / "session.json").write_bytes(b"{")
        cloud = self.app_data / "sessions" / ("f" * 32)
        cloud.mkdir(parents=True)
        (cloud / "session.json").write_bytes(store.canonical_bytes({**document, "schema_version": 1, "session_id": "f" * 32}))
        self.ok("session_open", {"session_id": first["session_id"]})

        rows = {row["session_id"]: row for row in self.get("sessions", "http/sessions.reply.json")["sessions"]}
        self.assertEqual(5, len(rows))
        open_row = rows[first["session_id"]]
        self.assertEqual({"display_name": "Open one", "target_model_name": "SalesA", "target_report_name": None, "source_count": 1,
                          "plan_status": None, "lock_state": "free", "schema_state": "ok", "is_open": True, "location": "project"},
                         {key: open_row[key] for key in ("display_name", "target_model_name", "target_report_name", "source_count",
                                                         "plan_status", "lock_state", "schema_state", "is_open", "location")})
        self.assertEqual("locked", rows[locked["session_id"]]["lock_state"])
        self.assertEqual("newer", rows[newer["session_id"]]["schema_state"])
        self.assertEqual("damaged", rows[damaged["session_id"]]["schema_state"])
        self.assertEqual("app_data", rows["f" * 32]["location"])

    def test_each_read_reply_carries_the_session_revision(self):
        self.assertIsNone(self.get("sessions", "http/sessions.reply.json")["revision"])
        status, payload = self.app.handle("GET", "/api/devcenter/session")
        self.assertEqual((409, "session_not_open"), (status, payload["error"]["code"]))
        self.create()
        for step in range(3):
            with self.subTest(step=step):
                session = self.get("session", "http/session.reply.json")
                sessions = self.get("sessions", "http/sessions.reply.json")
                self.assertEqual(self.devcenter.revision, session["revision"])
                self.assertEqual(self.devcenter.revision, sessions["revision"])
                self.assertEqual(self.devcenter._open.document["revision"], session["revision"])
            self.add(("SalesA/SalesA.pbip", "SalesB/SalesB.pbip", "Finance/Finance.pbip")[step])


class ContractTests(SessionTestCase):
    """UC4: each JS API call of S2 has a request and a reply schema; each error reply has the error shape."""

    def test_each_s2_method_has_a_request_and_a_reply_schema(self):
        names = set(contracts.names())
        for method in S2_METHODS:
            with self.subTest(method=method):
                self.assertIn(method, jsapi.METHODS)
                self.assertIn(contracts.jsapi_request(method), names)
                self.assertIn(contracts.jsapi_reply(method), names)

    def test_each_error_reply_validates_against_the_error_shape(self):
        requests = {
            "session_create": {"display_name": ""},
            "session_open": {"session_id": "0" * 32},
            "session_close": {"base_revision": "x"},
            "source_add": {"base_revision": 1, "path": str(self.root / "missing.pbip")},
            "source_remove": {"base_revision": 1, "source_id": "src-9"},
            "source_relink": {"base_revision": 1, "source_id": "src-9", "path": str(self.root / "SalesA/SalesA.pbip")},
            "target_set": {"base_revision": 1, "model": {"mode": "existing", "source_id": "src-9"}},
            "sources_check": {"base_revision": 1},
            "row_confirm": {"base_revision": 1, "row_keys": ["measure:Sales/None"]},
        }
        self.assertEqual(set(S2_METHODS), set(requests))
        for method, request in requests.items():
            for state in ("no_session", "open"):
                with self.subTest(method=method, state=state):
                    if state == "open" and self.devcenter.revision is None:
                        self.create()
                    reply = jsapi.call(self.devcenter, method, request)
                    if method == "sources_check" and state == "open":
                        self.assertNotIn("error", reply)
                        continue
                    if method == "session_close":
                        self.assertEqual("invalid_payload", reply["error"]["code"])
                    self.assertIn("error", reply, reply)
                    self.assertEqual([], contracts.errors(contracts.ERROR, reply))
            self.devcenter.close()

    def test_a_request_that_breaks_its_schema_gives_invalid_payload(self):
        reply = jsapi.call(self.devcenter, "row_confirm", {"base_revision": 1, "row_keys": []})
        self.assertEqual("invalid_payload", reply["error"]["code"])
        reply = jsapi.call(self.devcenter, "source_add", {"base_revision": 1, "path": "x", "token": "y"})
        self.assertEqual("invalid_payload", reply["error"]["code"])


class DesktopJSAPITests(unittest.TestCase):
    """The pywebview JS API object has the S2 methods, and the open project gives the session root."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.static = base / "dist"
        self.static.mkdir()
        (self.static / "index.html").write_text("<main>PBIBrain</main>", encoding="utf-8")
        self.project = base / "project"
        shutil.copytree(LAB / "SalesA", self.project / "SalesA")
        self.controller = DesktopController(
            static_dir=self.static,
            repository_factory=lambda path: GraphRepository(path, use_native=False),
            runtime_configurer=lambda: None,
            devcenter=DevCenterSessions(app_data_dir=None),
        )
        self.controller.attach_server("http://127.0.0.1:8123")

    def tearDown(self) -> None:
        self.controller.shutdown()
        self.temporary.cleanup()

    def test_js_api_methods_change_the_session_of_the_open_project(self):
        self.assertEqual("action_not_allowed", self.controller.session_create({"display_name": "No project"})["error"]["code"])
        self.assertTrue(self.controller.open_project("Sales", str(self.project))["ok"])
        created = self.controller.session_create({"display_name": "Sales merge"})
        self.assertEqual(1, created["revision"])
        added = self.controller.source_add({"base_revision": 1, "path": str(self.project / "SalesA/SalesA.pbip")})
        self.assertEqual("SalesA/SalesA.pbip", added["source"]["path"])
        status, payload = self.controller.active_application().handle("GET", "/api/devcenter/session")
        self.assertEqual((200, 2), (status, payload["revision"]))
        self.assertTrue((self.project / ".pbibrain/sessions" / created["session_id"] / "session.lock").is_file())
        self.controller.close_project()
        self.assertFalse((self.project / ".pbibrain/sessions" / created["session_id"] / "session.lock").exists())


if __name__ == "__main__":
    unittest.main()
