"""The start scripts rebuild the web UI when frontend sources are newer than frontend/dist."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from backend.ui_build import stale_reason


class UiBuildFreshnessTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.frontend = Path(self.temporary.name) / "frontend"
        (self.frontend / "src").mkdir(parents=True)
        self.source = self.frontend / "src" / "App.jsx"
        self.source.write_text("export default 1;\n", encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def _build(self, mtime: float) -> None:
        built = self.frontend / "dist" / "index.html"
        built.parent.mkdir(exist_ok=True)
        built.write_text("<html></html>", encoding="utf-8")
        os.utime(built, (mtime, mtime))

    def test_missing_build_is_stale(self):
        self.assertEqual(stale_reason(self.frontend), "the UI build is missing")

    def test_build_newer_than_sources_is_current(self):
        os.utime(self.source, (1_000, 1_000))
        self._build(2_000)
        self.assertIsNone(stale_reason(self.frontend))

    def test_source_changed_after_build_is_stale(self):
        # git pull rewrites changed files, so they are newer than the last build.
        self._build(1_000)
        os.utime(self.source, (2_000, 2_000))
        self.assertEqual(stale_reason(self.frontend), "src/App.jsx is newer than the UI build")

    def test_checkout_without_sources_is_never_stale(self):
        installed = Path(self.temporary.name) / "installed"
        (installed / "dist").mkdir(parents=True)
        self.assertIsNone(stale_reason(installed))


if __name__ == "__main__":
    unittest.main()
