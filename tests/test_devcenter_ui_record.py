"""Tests of the U12 fixture recorder (tools/record_devcenter_ui_fixtures.py).

The real recording needs the .NET TOM bridge (Windows). These tests check the
part that runs on each machine: the recorder writes the files in the shape of
the fake server, a round trip through the fake server gives the same replies,
and with no model engine the tool writes no file.

All text follows ASD-STE100 rules.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from tests.devcenter_ui_server import FIXTURES, FakeDevCenter, FakeError
from tools import record_devcenter_ui_fixtures as recorder


def fake_get(state: FakeDevCenter):
    def get(path: str) -> dict:
        parsed = urlsplit("/api/devcenter/" + path)
        try:
            return state.read("GET", parsed.path, parse_qs(parsed.query), {})
        except FakeError as error:
            raise recorder.RecordError(error.message) from error
    return get


READS = ("sessions", "session", "compare-rows?limit=200&offset=0", "display-folders", "naming-rules", "plan",
         "impact?limit=200&offset=0", "log?limit=50&offset=0", "wireframe/src-1")


class RecorderShapeTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="t26-record-")
        self.addCleanup(temporary.cleanup)
        self.fixtures = Path(temporary.name)
        shutil.copytree(FIXTURES, self.fixtures, dirs_exist_ok=True)

    def test_a_record_of_the_default_set_gives_the_same_replies_after_a_round_trip(self) -> None:
        original = FakeDevCenter(self.fixtures, sleep=lambda _: None)
        files = recorder.record(fake_get(original))
        self.assertTrue(set(files) <= set(recorder.RECORDED), set(files) - set(recorder.RECORDED))
        written = recorder.write(files, self.fixtures / "default")
        self.assertEqual({path.stem for path in written}, set(files))

        replayed = FakeDevCenter(self.fixtures, sleep=lambda _: None)
        get_original, get_replayed = fake_get(original), fake_get(replayed)
        for path in READS:
            with self.subTest(path=path):
                self.assertEqual(get_original(path), get_replayed(path))
        self.assertTrue(files["row-diffs"])
        for key, sources in files["row-diffs"].items():
            for source_id in sources:
                path = f"compare-rows/{key}/diff?source={source_id}"
                self.assertEqual(get_original(path), get_replayed(path))
        for key in files["removals"]:
            self.assertEqual(get_original(f"impact/removal/{key}"), get_replayed(f"impact/removal/{key}"))
        self.assertTrue(files["impact-paths"])
        for key in files["impact-paths"]:
            self.assertEqual(get_original(f"impact/{key}/paths"), get_replayed(f"impact/{key}/paths"))

    def test_the_large_scenario_stays_generated_on_the_recorded_default_set(self) -> None:
        meta = json.loads((FIXTURES / "large-5000-rows" / "scenario.json").read_text(encoding="utf-8"))
        self.assertEqual("default", meta["base"])
        self.assertEqual(5000, meta["generate"]["compare_rows"])
        self.assertEqual(["scenario.json"], sorted(path.name for path in (FIXTURES / "large-5000-rows").glob("*.json")))

    def test_a_failed_engine_read_goes_to_missing_and_its_file_is_not_written(self) -> None:
        state = FakeDevCenter(self.fixtures, sleep=lambda _: None)
        base = fake_get(state)

        def get(path: str) -> dict:
            if path == "plan":
                raise recorder.RecordError("The model engine is not available.")
            return base(path)

        missing: list[str] = []
        files = recorder.record(get, missing)
        self.assertNotIn("plan", files)
        self.assertEqual(1, len(missing))
        self.assertTrue(missing[0].startswith("plan: "))


class RecorderMergeLabTest(unittest.TestCase):
    def test_with_no_model_engine_the_tool_writes_no_file_and_says_why(self) -> None:
        with tempfile.TemporaryDirectory(prefix="t26-out-") as folder:
            out = Path(folder) / "default"
            stderr = io.StringIO()
            with redirect_stderr(stderr), mock.patch.object(recorder, "lab_reader", wraps=recorder.lab_reader) as reader:
                code = recorder.main(["--no-native", "--out", str(out)])
            self.assertEqual(2, code)
            self.assertFalse(out.exists())
            self.assertIn("Run the tool on the Windows PC with the TOM bridge", stderr.getvalue())
            self.assertEqual(False, reader.call_args.kwargs["use_native"])

    def test_the_session_reads_of_the_merge_lab_pass_their_contracts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="t26-lab-") as folder:
            get, source_ids, close = recorder.lab_reader(Path(folder) / "project", use_native=False)
            try:
                self.assertEqual(["src-1", "src-2"], source_ids)
                session = get("session")
                self.assertEqual(recorder.SESSION_NAME, session["display_name"])
                self.assertEqual(2, len(session["sources"]))
                self.assertEqual(1, len(get("sessions")["sessions"]))
                get("compare-rows?limit=200&offset=0")
            finally:
                close()


if __name__ == "__main__":
    unittest.main()
