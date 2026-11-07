"""Issue #16: a model.bim source becomes a TMDL target with consent, and merge templates replay saved decisions."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from backend.devcenter import contracts, jsapi
from backend.devcenter.session.manager import DevCenterSessions
from backend.devcenter.sources.kinds import MESSAGE_TMSL_TARGET

REPOSITORY = Path(__file__).resolve().parents[1]
LAB = REPOSITORY / "tests" / "fixtures" / "merge_lab"
BRIDGE = REPOSITORY / "backend/adapters/tabular_metadata/dotnet/bin/Release/net8.0/TabularMetadata.dll"
MARGIN = "measure:Sales/Margin"


class MigrationTestCase(unittest.TestCase):
    names: tuple[str, ...] = ("SalesA", "SalesB")

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="migration-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "project"
        for name in self.names:
            shutil.copytree(LAB / name, self.root / name)
        self.devcenter = DevCenterSessions(app_data_dir=None)
        self.devcenter.attach_project(self.root)
        self.addCleanup(self.devcenter.close)
        self.ok("session_create", {"display_name": "Migration"})
        for name in self.names:
            self.ok("source_add", {"base_revision": self.rev, "path": str(self.root / name / f"{name}.pbip")})

    @property
    def rev(self) -> int:
        return self.devcenter.revision

    def call(self, method: str, request: dict) -> dict:
        reply = jsapi.call(self.devcenter, method, request)
        name = contracts.ERROR if "error" in reply else contracts.jsapi_reply(method)
        self.assertEqual([], contracts.errors(name, reply), reply)
        return reply

    def ok(self, method: str, request: dict) -> dict:
        reply = self.call(method, request)
        self.assertNotIn("error", reply, reply)
        return reply

    def failed(self, method: str, request: dict) -> dict:
        reply = self.call(method, request)
        self.assertIn("error", reply, reply)
        return reply["error"]


@unittest.skipUnless(BRIDGE.is_file(), "TOM bridge not built")
class ConvertToTmdlTests(MigrationTestCase):
    names = ("SalesA", "Legacy")

    def test_a_model_bim_target_needs_consent_then_becomes_tmdl(self) -> None:
        legacy = "src-2"
        error = self.failed("target_set", {"base_revision": self.rev, "model": {"mode": "existing", "source_id": legacy}})
        self.assertEqual(MESSAGE_TMSL_TARGET, error["message"])
        reply = jsapi.call(self.devcenter, "target_convert_tmdl", {"base_revision": self.rev, "source_id": legacy})
        self.assertEqual("invalid_payload", reply["error"]["code"])  # The contract needs consent: true.
        bim = self.root / "Legacy" / "Legacy.SemanticModel" / "model.bim"
        original = bim.read_bytes()

        converted = self.ok("target_convert_tmdl", {"base_revision": self.rev, "source_id": legacy, "consent": True})
        self.assertEqual("tmdl", converted["source"]["model_format"])
        self.assertFalse(bim.exists())
        self.assertTrue((self.root / "Legacy" / "Legacy.SemanticModel" / "definition" / "model.tmdl").is_file())
        self.assertEqual(original, (self.root / converted["backup_path"]).read_bytes())
        self.ok("target_set", {"base_revision": self.rev, "model": {"mode": "existing", "source_id": legacy}})
        # The new baseline is the converted model: no row is marked "source changed".
        self.ok("sources_check", {"base_revision": self.rev})
        self.assertEqual([], self.devcenter._open.document["source_marks"])

    def test_only_a_tmsl_source_is_converted(self) -> None:
        error = self.failed("target_convert_tmdl", {"base_revision": self.rev, "source_id": "src-1", "consent": True})
        self.assertEqual("not_tmsl", error["details"]["reason"])

    def test_a_failed_conversion_leaves_the_source_unchanged(self) -> None:
        from backend.adapters.tabular_metadata import ConvertFailed
        from backend.devcenter.sources import convert

        class Broken:
            def convert_tmdl(self, bim, folder):
                Path(folder).mkdir()
                (Path(folder) / "partial.tmdl").write_text("x", encoding="utf-8")
                raise ConvertFailed("roundtrip_failed")

        model = self.root / "Legacy" / "Legacy.SemanticModel"
        before = sorted(path.name for path in model.iterdir())
        with self.assertRaises(Exception) as caught:
            convert.convert_to_tmdl(self.devcenter, {"base_revision": self.rev, "source_id": "src-2", "consent": True}, Broken())
        self.assertEqual("convert_failed", caught.exception.details["reason"])
        self.assertEqual(before, sorted(path.name for path in model.iterdir()))


class MergeTemplateTests(MigrationTestCase):
    def test_save_and_replay_in_a_session_with_new_donor_versions(self) -> None:
        self.ok("target_set", {"base_revision": self.rev, "model": {"mode": "existing", "source_id": "src-1"},
                               "report": {"mode": "existing", "source_id": "src-1"}})
        self.ok("merge_choice_set", {"base_revision": self.rev, "row_key": MARGIN, "choice": {"kind": "take", "source_id": "src-2"}})
        self.ok("merge_choice_set", {"base_revision": self.rev, "row_key": "page:summary", "choice": "skip"})
        saved = self.ok("merge_template_save", {"base_revision": self.rev, "name": "Sales rollup"})
        self.assertEqual((2, ".pbibrain/templates/Sales rollup.json"), (saved["choice_count"], saved["path"]))
        stored = json.loads((self.root / saved["path"]).read_text(encoding="utf-8"))
        self.assertEqual({"kind": "take", "source_name": "SalesB"}, stored["choices"][MARGIN])
        self.assertEqual("template_exists", self.failed("merge_template_save", {"base_revision": self.rev, "name": "Sales rollup"})["details"]["reason"])
        listed = self.ok("merge_template_list", {})["templates"]
        self.assertEqual([("Sales rollup", 2, ["SalesB"])], [(item["name"], item["choice_count"], item["source_names"]) for item in listed])

        # A new session: the donors are added in another order, so the source IDs differ.
        self.ok("session_create", {"display_name": "Next month"})
        for name in ("SalesB", "SalesA"):
            self.ok("source_add", {"base_revision": self.rev, "path": str(self.root / name / f"{name}.pbip")})
        replay = self.ok("merge_template_apply", {"base_revision": self.rev, "name": "Sales rollup"})
        self.assertEqual(([MARGIN, "page:summary"], []), (replay["applied"], replay["skipped"]))
        choices = self.devcenter._open.document["merge_choices"]
        self.assertEqual({"kind": "take", "source_id": "src-1"}, choices[MARGIN])  # SalesB is src-1 here.
        self.assertEqual({"kind": "skip"}, choices["page:summary"])

    def test_a_choice_from_a_missing_source_is_skipped(self) -> None:
        self.ok("merge_choice_set", {"base_revision": self.rev, "row_key": MARGIN, "choice": {"kind": "take", "source_id": "src-2"}})
        self.ok("merge_template_save", {"base_revision": self.rev, "name": "t1"})
        self.ok("source_remove", {"base_revision": self.rev, "source_id": "src-2"})
        self.ok("merge_choice_set", {"base_revision": self.rev, "row_key": MARGIN, "choice": None})
        replay = self.ok("merge_template_apply", {"base_revision": self.rev, "name": "t1"})
        self.assertEqual([{"row_key": MARGIN, "reason": "source_not_in_session"}], replay["skipped"])
        self.assertNotIn(MARGIN, self.devcenter._open.document["merge_choices"])

    def test_a_bad_name_and_a_missing_template_are_refused(self) -> None:
        self.assertEqual("invalid_payload", self.failed("merge_template_save", {"base_revision": self.rev, "name": "../x"})["code"])
        self.assertEqual("not_found", self.failed("merge_template_apply", {"base_revision": self.rev, "name": "nothing"})["code"])


if __name__ == "__main__":
    unittest.main()
