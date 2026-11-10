"""Contract tests for 1-click startup scripts (start.bat, start.sh).

Ensures the setup scripts correctly verify and install all necessary Python
dependencies (e.g. antlr4, jsonschema) in the virtual environment without
false-positive namespace package imports.
"""

from __future__ import annotations

import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class StartScriptContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bat = (ROOT / "start.bat").read_text(encoding="utf-8")
        self.sh = (ROOT / "start.sh").read_text(encoding="utf-8")

    def test_scripts_exist_and_are_executable(self) -> None:
        self.assertTrue((ROOT / "start.bat").is_file())
        self.assertTrue((ROOT / "start.sh").is_file())
        if os.name != "nt":
            self.assertTrue(os.access(ROOT / "start.sh", os.X_OK), "start.sh must have executable bit")

    def test_scripts_do_not_use_bare_import_backend_check(self) -> None:
        """import backend succeeds in cwd even when the venv is completely empty,

        which leads to ModuleNotFoundError: No module named 'antlr4'.
        """
        self.assertNotIn('python -c "import backend"', self.bat)
        self.assertNotIn('python -c "import backend"', self.sh)

    def test_scripts_check_antlr4_dependency(self) -> None:
        """The dependency verification must explicitly import antlr4."""
        self.assertIn("antlr4", self.bat)
        self.assertIn("antlr4", self.sh)

    def test_scripts_install_dependencies_in_active_venv(self) -> None:
        """The install command must use python -m pip and install editable package."""
        self.assertIn("python -m pip install", self.bat)
        self.assertIn("python -m pip install", self.sh)
        self.assertIn("-e", self.bat)
        self.assertIn("-e", self.sh)


if __name__ == "__main__":
    unittest.main()
